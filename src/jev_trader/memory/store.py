"""What the memory server reads, and the one rule every read follows (spec appendix 5, section 3,
"Never seeing the future").

Memory is a sim's own copy of `MEMORY.DECISIONS` and `MEMORY.OUTCOMES` (rows whose `SIM` is the
sim), read beside the dataset's snapshots (`FEATURES`, `REF`) and the sim's settings
(`SIM.SIMS`). The Snowflake version is `snowflake_store.SnowflakeMemoryStore` and the Postgres one
`postgres_store.PostgresMemoryStore`, each logged in with the memory server's own role, which can
only read; `InMemoryMemoryStore` is the stand-in the tests
use, with made-up embeddings.

**The rule.** Every read takes the current step and returns only what was known by then. Each
store holds the episode rule once (`_visible`, `_VISIBLE` in the database versions) and every read of
episodes goes through it (the search, reading in full, the track record's closed trades): an
episode (a full evaluation or position review) of this sim's memory, decided before now, whose
outcomes were all known by now (`OUTCOMES_KNOWN_FROM`). A traded full evaluation is complete
only once its trade has closed, so the track record counts a trade from the step it closed.
What is read beside an allowed episode is cut at now too: its outcomes known by now
(`KNOWN_FROM`), its position's bars before now. The agent has no other path to these tables.
"""

import math
from collections.abc import Sequence
from typing import Protocol

from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.memory.outcomes import EPISODE_KINDS, OutcomeKind
from jev_trader.memory.search import (
    FULL_EVALUATION,
    Candidate,
    Query,
)
from jev_trader.sim.store import (
    ACTION_ENTRY,
    ACTION_NOTHING,
    KIND_FULL_EVALUATION,
    POSITION_KINDS,
)

# The snapshot columns a decision row is read with.
SNAPSHOT_COLUMNS = ("ASSET_CLASS", "SITUATION_TEXT", "MEASUREMENTS")


class UnknownSim(LookupError):
    pass


class NoSnapshot(LookupError):
    """The asset has no snapshot at the step asked about."""


class MemoryStore(Protocol):
    def sim(self, sim_id: int) -> dict:
        """The sim's DATASET and SETTINGS. UnknownSim if there is none."""

    def snapshot(self, dataset: int, asset: str, step: int) -> dict:
        """The asset's snapshot at `step`: ASSET_CLASS, MEASUREMENTS, SITUATION_TEXT, and the
        two vectors FEATURE_VECTOR and EMBEDDING. NoSnapshot if there is none."""

    def ranked(
        self, query: Query, current: dict, weights: Sequence[float], top: int
    ) -> tuple[list[Candidate], list[Candidate]]:
        """The visible episodes the query's job and filters allow, closest first, at most `top`
        each: by weighted feature vector distance, and by situation text similarity."""

    def decisions(self, sim: int, step: int, ids: Sequence[str]) -> list[dict]:
        """The visible episodes among `ids`, each with its snapshot's columns."""

    def outcomes(self, sim: int, step: int, decisions: Sequence[str]) -> list[dict]:
        """The outcomes of `decisions` known by `step`."""

    def position_rows(
        self, sim: int, step: int, positions: Sequence[int]
    ) -> list[dict]:
        """Every decision row about `positions` (their journals) decided before `step`."""

    def closed_trades(self, sim: int, step: int, asset_class: str) -> list[dict]:
        """The trades of `asset_class` closed by `step`: each traded full evaluation with its
        snapshot's columns, PROFIT and CLOSED_STEP."""


def _distance(a: Sequence[float], b: Sequence[float], weights: Sequence[float]):
    return math.sqrt(sum((w * (x - y)) ** 2 for x, y, w in zip(a, b, weights)))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norms if norms else 0.0


def review_decided(action: str) -> str:
    """What a review decided, as the search filter names it: an add the limits left nothing
    of did nothing, so it reads "hold"."""
    return "hold" if action == ACTION_NOTHING else action


class InMemoryMemoryStore:
    """The memory tables as lists of rows, for tests."""

    def __init__(self):
        self.sims: dict[int, dict] = {}
        self.decisions_table: list[dict] = []
        self.outcomes_table: list[dict] = []
        self.snapshots: dict[tuple[int, str, int], dict] = {}
        self.patterns: list[dict] = []  # FEATURES.PATTERNS rows

    # The one rule

    @staticmethod
    def _visible(row: dict, sim: int, step: int) -> bool:
        """An episode of this sim's memory, decided before `step`, complete by `step`."""
        known_from = row.get("OUTCOMES_KNOWN_FROM")
        return (
            row["SIM"] == sim
            and row["KIND"] in EPISODE_KINDS
            and row["STEP"] < step
            and known_from is not None
            and known_from <= step
        )

    # Reads

    def sim(self, sim_id):
        if sim_id not in self.sims:
            raise UnknownSim(sim_id)
        return self.sims[sim_id]

    def snapshot(self, dataset, asset, step):
        found = self.snapshots.get((dataset, asset, step))
        if found is None:
            raise NoSnapshot(f"{asset} has no snapshot at step {step}")
        return found

    def _with_snapshot(self, row: dict) -> dict:
        s = self.snapshots[(row["DATASET"], row["ASSET"], row["STEP"])]
        return {**row, **{c: s[c] for c in SNAPSHOT_COLUMNS}}

    def _patterned(self, row: dict, pattern: str) -> bool:
        return any(
            p["DATASET"] == row["DATASET"]
            and p["ASSET"] == row["ASSET"]
            and p["BAR_SIZE"] == "15m"
            and row["STEP"] - PATTERN_WINDOW_STEPS < p["STEP"] <= row["STEP"]
            and p["PATTERN"] == pattern
            for p in self.patterns
        )

    def _carried_out(self, row: dict) -> bool:
        """A full evaluation whose entry was carried out: it traded."""
        return row["ACTION"] == ACTION_ENTRY and any(
            o["SIM"] == row["SIM"]
            and o["DECISION"] == row["ID"]
            and o["KIND"] == OutcomeKind.ORDER_CARRIED_OUT
            and o["VALUE"].get("carried_out")
            for o in self.outcomes_table
        )

    def _allowed(self, row: dict, query: Query, current: dict) -> bool:
        f = query.filters
        s = self.snapshots[(row["DATASET"], row["ASSET"], row["STEP"])]
        if f.asset == "same_asset" and row["ASSET"] != query.asset:
            return False
        if f.asset == "same_asset_class" and s["ASSET_CLASS"] != current["ASSET_CLASS"]:
            return False
        if f.pattern != "any" and not self._patterned(row, f.pattern):
            return False
        if query.job == FULL_EVALUATION:
            traded = self._carried_out(row)
            decided = row["PICK"].split("_")[0] if traded else "no_trade"
            return f.decided in ("any", decided)
        standing = row["STANDING"]
        if standing["direction"] != query.direction:
            return False
        if f.decided not in ("any", review_decided(row["ACTION"])):
            return False
        if f.standing == "in_profit":
            return standing["profit"] > 0
        if f.standing == "at_a_loss":
            return standing["profit"] < 0
        return True

    def ranked(self, query, current, weights, top):
        rows = [
            r
            for r in self.decisions_table
            if self._visible(r, query.sim, query.step)
            and r["KIND"] == query.job
            and self._allowed(r, query, current)
        ]

        def snap(r):
            return self.snapshots[(r["DATASET"], r["ASSET"], r["STEP"])]

        def candidate(r):
            return Candidate(r["ID"], r["ASSET"], r["STEP"])

        by_vector = sorted(
            rows,
            key=lambda r: (
                _distance(
                    snap(r)["FEATURE_VECTOR"], current["FEATURE_VECTOR"], weights
                ),
                r["ID"],
            ),
        )
        by_text = sorted(
            rows,
            key=lambda r: (
                -_cosine(snap(r)["EMBEDDING"], current["EMBEDDING"]),
                r["ID"],
            ),
        )
        return (
            [candidate(r) for r in by_vector[:top]],
            [candidate(r) for r in by_text[:top]],
        )

    def decisions(self, sim, step, ids):
        wanted = set(ids)
        return [
            self._with_snapshot(r)
            for r in self.decisions_table
            if r["ID"] in wanted and self._visible(r, sim, step)
        ]

    def outcomes(self, sim, step, decisions):
        wanted = set(decisions)
        return [
            o
            for o in self.outcomes_table
            if o["SIM"] == sim and o["DECISION"] in wanted and o["KNOWN_FROM"] <= step
        ]

    def position_rows(self, sim, step, positions):
        wanted = set(positions)
        return [
            r
            for r in self.decisions_table
            if r["SIM"] == sim
            and r["KIND"] in POSITION_KINDS
            and r.get("POSITION") in wanted
            and r["STEP"] < step
        ]

    def closed_trades(self, sim, step, asset_class):
        closed = {
            o["DECISION"]: o
            for o in self.outcomes_table
            if o["SIM"] == sim
            and o["KIND"] == OutcomeKind.POSITION_CLOSED
            and o["KNOWN_FROM"] <= step
        }
        found = []
        for r in self.decisions_table:
            o = closed.get(r["ID"])
            if (
                o is None
                or r["KIND"] != KIND_FULL_EVALUATION
                or not self._visible(r, sim, step)
            ):
                continue
            row = self._with_snapshot(r)
            if row["ASSET_CLASS"] == asset_class:
                found.append(
                    {
                        **row,
                        "PROFIT": o["VALUE"]["profit"],
                        "CLOSED_STEP": o["KNOWN_FROM"],
                    }
                )
        return found
