"""Where a dataset build writes: the interface, and an in-memory stand-in for tests.

A dataset is one row of `REF.DATASETS` plus rows in the tables below, each carrying the
dataset's ID in its `DATASET` column. The Snowflake version is `snowflake_store.SnowflakeStore`.
Column names match the numbered SQL files in `infra/migrations`.
"""

import hashlib
import struct
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from jev_trader.dataset.snapshots import EMBEDDING_SIZE

# The tables a build fills through `save`, in the order they are written.
TABLES = (
    "REF.DATASET_PERIODS",
    "REF.ASSETS",
    "REF.INSTRUMENTS",
    "REF.MISSING_BARS",
    "REF.PARTIAL_VOLUME_DAYS",
    "KEYS.ASSET_KEY",
    "RAW.BARS",
    "REF.WARMUP_STATS",
    "FEATURES.PATTERNS",
)
# Snapshots take two steps of their own: staged without an embedding, then moved into
# FEATURES.SNAPSHOTS with one (`stage_snapshots`, then `embed_snapshots`).
SNAPSHOT_TABLES = ("FEATURES.SNAPSHOTS_LOADING", "FEATURES.SNAPSHOTS")
# Every table holding a dataset's rows: what a failed build throws away. The playbook is shared
# by every dataset of its TA-Lib version, so it stays.
DATASET_TABLES = TABLES + SNAPSHOT_TABLES


class DatasetStatus(StrEnum):
    BEING_BUILT = "being built"
    PUBLISHED = "published"
    FAILED = "failed"


class DatasetStore(Protocol):
    def begin(self, name: str, columns: dict) -> tuple[int, int]:
        """Add a dataset being built; returns its ID and version (1 + earlier builds of `name`)."""

    def update(self, dataset_id: int, **columns) -> None:
        """Set columns of the dataset's row, such as its stage and progress."""

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        """Write the dataset's rows, table by table."""

    def save_playbook(self, rows: list[dict]) -> None:
        """Add the playbook of one TA-Lib version, unless that version's is already stored."""

    def stage_snapshots(self, dataset_id: int, rows: list[dict]) -> None:
        """Hold snapshot rows (measurements, feature vector, situation text) until embedded."""

    def embed_snapshots(self, dataset_id: int, asset: str) -> int:
        """Embed the staged situation texts of one asset and store its snapshots, each with its
        embedding, in FEATURES.SNAPSHOTS. Returns how many were stored."""

    def publish(self, dataset_id: int, without_check: bool) -> None:
        """Mark the dataset published, with the time. It never changes afterwards."""

    def fail(self, dataset_id: int, reason: str) -> None:
        """Mark the dataset failed with `reason` and throw away every row it wrote."""


def now() -> datetime:
    """The time now, in UTC, as Snowflake stores it (no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


def made_up_embedding(text: str) -> list[float]:
    """As many numbers as the model gives, drawn from the text, the same for the same text."""
    seed = hashlib.sha256(text.encode()).digest()
    numbers: list[float] = []
    block = 0
    while len(numbers) < EMBEDDING_SIZE:
        digest = hashlib.sha256(seed + block.to_bytes(4, "big")).digest()
        numbers += [n / 2**32 - 0.5 for n in struct.unpack(">8I", digest)]
        block += 1
    return numbers[:EMBEDDING_SIZE]


class InMemoryStore:
    """The store as plain dictionaries: `datasets` by ID, and `tables` by name.

    `embed` stands in for Snowflake's embedding model."""

    def __init__(self, embed: Callable[[str], list[float]] = made_up_embedding):
        self.datasets: dict[int, dict] = {}
        self.tables: dict[str, list[dict]] = defaultdict(list)
        self.embed = embed

    def begin(self, name: str, columns: dict) -> tuple[int, int]:
        dataset_id = len(self.datasets) + 1
        version = 1 + sum(1 for d in self.datasets.values() if d["NAME"] == name)
        self.datasets[dataset_id] = {
            "ID": dataset_id,
            "NAME": name,
            "VERSION": version,
            "STATUS": str(DatasetStatus.BEING_BUILT),
            "PUBLISHED_WITHOUT_CHECK": False,
            "FAILURE_REASON": None,
            "STARTED_AT": now(),
            **columns,
        }
        return dataset_id, version

    def update(self, dataset_id: int, **columns) -> None:
        self.datasets[dataset_id].update(columns)

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        for name in TABLES:
            self.tables[name] += tables.get(name, [])

    def save_playbook(self, rows: list[dict]) -> None:
        stored = {r["TALIB_VERSION"] for r in self.tables["REF.PLAYBOOK"]}
        self.tables["REF.PLAYBOOK"] += [
            r for r in rows if r["TALIB_VERSION"] not in stored
        ]

    def stage_snapshots(self, dataset_id: int, rows: list[dict]) -> None:
        self.tables["FEATURES.SNAPSHOTS_LOADING"] += rows

    def embed_snapshots(self, dataset_id: int, asset: str) -> int:
        staged = self.tables["FEATURES.SNAPSHOTS_LOADING"]
        mine = [r for r in staged if (r["DATASET"], r["ASSET"]) == (dataset_id, asset)]
        self.tables["FEATURES.SNAPSHOTS_LOADING"] = [
            r for r in staged if (r["DATASET"], r["ASSET"]) != (dataset_id, asset)
        ]
        self.tables["FEATURES.SNAPSHOTS"] += [
            {**r, "EMBEDDING": self.embed(r["SITUATION_TEXT"])} for r in mine
        ]
        return len(mine)

    def publish(self, dataset_id: int, without_check: bool) -> None:
        self.update(
            dataset_id,
            STATUS=str(DatasetStatus.PUBLISHED),
            PUBLISHED_WITHOUT_CHECK=without_check,
            PUBLISHED_AT=now(),
        )

    def fail(self, dataset_id: int, reason: str) -> None:
        for name in DATASET_TABLES:
            self.tables[name] = [
                r for r in self.tables[name] if r["DATASET"] != dataset_id
            ]
        self.update(dataset_id, STATUS=str(DatasetStatus.FAILED), FAILURE_REASON=reason)
