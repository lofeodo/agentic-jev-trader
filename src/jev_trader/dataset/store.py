"""Where a dataset build writes: the interface, and an in-memory stand-in for tests.

A dataset is one row of `REF.DATASETS` plus rows in the tables below, each carrying the
dataset's ID in its `DATASET` column. The Snowflake version is `snowflake_store.SnowflakeStore`.
Column names match the numbered SQL files in `infra/migrations`.
"""

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

# The tables a build fills, in the order they are written.
TABLES = (
    "REF.DATASET_PERIODS",
    "REF.ASSETS",
    "REF.INSTRUMENTS",
    "REF.MISSING_BARS",
    "REF.PARTIAL_VOLUME_DAYS",
    "KEYS.ASSET_KEY",
    "RAW.BARS",
)


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

    def publish(self, dataset_id: int, without_check: bool) -> None:
        """Mark the dataset published, with the time. It never changes afterwards."""

    def fail(self, dataset_id: int, reason: str) -> None:
        """Mark the dataset failed with `reason` and throw away every row it wrote."""


def now() -> datetime:
    """The time now, in UTC, as Snowflake stores it (no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class InMemoryStore:
    """The store as plain dictionaries: `datasets` by ID, and `tables` by name."""

    def __init__(self):
        self.datasets: dict[int, dict] = {}
        self.tables: dict[str, list[dict]] = defaultdict(list)

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

    def publish(self, dataset_id: int, without_check: bool) -> None:
        self.update(
            dataset_id,
            STATUS=str(DatasetStatus.PUBLISHED),
            PUBLISHED_WITHOUT_CHECK=without_check,
            PUBLISHED_AT=now(),
        )

    def fail(self, dataset_id: int, reason: str) -> None:
        for name in TABLES:
            self.tables[name] = [
                r for r in self.tables[name] if r["DATASET"] != dataset_id
            ]
        self.update(dataset_id, STATUS=str(DatasetStatus.FAILED), FAILURE_REASON=reason)
