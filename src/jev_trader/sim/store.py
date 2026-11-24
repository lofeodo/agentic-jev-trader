"""Where a sim's records go, and how a step is written (spec appendix 6, sections 3.4 and 6).

A sim is one row of `SIM.SIMS` plus rows in the record tables below, each carrying the sim's ID
in its `SIM` column and an `ID` built from what the row describes (sim, step, asset). Column
names match `infra/migrations/V4__sim_tables.sql`. The Snowflake version is
`snowflake_store.SnowflakeSimStore`; `InMemorySimStore` is the stand-in the unit tests use.

**How a step is written.** `write_steps` stores everything one or more steps produced in one
transaction (all of it lands or none of it does), together with the sim's last completed step
and its saved account. The last completed step is also a lock: the write goes through only
if it still reads what the writer last saw and the sim is running, so two copies of one sim cannot
both write a step, and nothing is written to a finished sim.

An order's row changes as it goes from waiting to carried out or cancelled, so a write replaces
an order's earlier row (same ID) rather than adding a second one. Every other row is written
once.
"""

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

# The tables a step writes, in the order they are written.
TABLES = (
    "SIM.ORDERS",
    "SIM.ACCOUNT_STEPS",
    "SIM.CHARGES",
    "SIM.SIM_EVENTS",
    "SIM.CALLS",
    "SIM.JEV_REQUESTS",
    "MEMORY.DECISIONS",
)
# Tables whose rows a later step may rewrite, by ID.
REPLACED_BY_ID = frozenset({"SIM.ORDERS"})


class SimStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    FINISHED = "finished"
    FAILED = "failed"


class StopReason(StrEnum):
    """Why a sim stopped. Only the first and last are used by the holding sim."""

    FINISHED = "finished"
    SPENDING_CAP = "spending cap"
    JEV_FAILED = "Jev failed"
    LLM_FAILED = "LLM failed"
    ACCOUNT_AT_ZERO = "account at zero"
    STOPPED_BY_HAND = "stopped by hand"


class StepAlreadyWritten(Exception):
    """The last completed step had moved, or the sim was not running: another copy of the sim is writing,
    or the sim was finished or stopped meanwhile. Nothing from this write was stored."""


def now() -> datetime:
    """The time now, in UTC, as Snowflake stores it (no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class SimStore(Protocol):
    def create(self, row: dict) -> int:
        """Add a sim's row (status created); returns its ID."""

    def sim(self, sim_id: int) -> dict:
        """The sim's row, by column name. KeyError if there is none."""

    def update(self, sim_id: int, **columns) -> None:
        """Set columns of the sim's row, such as its status; never on a finished sim.

        Not for the last completed step, which only `write_steps` moves."""

    def write_steps(
        self,
        sim_id: int,
        after_step: int | None,
        through_step: int,
        rows: dict[str, list[dict]],
        state: dict,
    ) -> None:
        """Store `rows` and move the last completed step from `after_step` to `through_step`, all at once.

        `after_step` is the last completed step the writer last saw (None before the first
        write); `state` is the account after `through_step`. Raises `StepAlreadyWritten`, having
        stored nothing, if the last completed step no longer reads `after_step` or the sim is not running.
        """

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        """For each table with any, how many of the sim's record IDs appear more than once."""

    def save_reading(self, version: str, opening: str) -> None:
        """Store the opening of Jev's background, once per reading version."""

    def spent(self, sim_id: int) -> float:
        """The dollars of the sim's recorded paid calls."""

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        """How many screens Jev answered, and how many of them said yes (at `cut_off` or above)."""


class SimulatedKill(BaseException):
    """The in-memory store stopping the program mid-write, as a kill would.

    A BaseException, like a real kill it is not caught by the sim's own error handling.
    """


class InMemorySimStore:
    """The store as plain dictionaries: `sims` by ID, and `tables` by name.

    `kill_on_write(n)` makes the n-th `write_steps` call from now stop the program halfway
    through, with nothing stored, as a sim killed while it writes.
    """

    def __init__(self):
        self.sims: dict[int, dict] = {}
        self.tables: dict[str, list[dict]] = defaultdict(list)
        self.readings: dict[str, str] = {}
        self._kill_in: int | None = None

    def kill_on_write(self, n: int) -> None:
        self._kill_in = n

    def create(self, row: dict) -> int:
        sim_id = len(self.sims) + 1
        self.sims[sim_id] = {
            "ID": sim_id,
            "STATUS": str(SimStatus.CREATED),
            "LAST_COMPLETED_STEP": None,
            "ACCOUNT_STATE": None,
            "CREATED_AT": now(),
            **row,
        }
        return sim_id

    def sim(self, sim_id: int) -> dict:
        return dict(self.sims[sim_id])

    def update(self, sim_id: int, **columns) -> None:
        if self.sims[sim_id]["STATUS"] != SimStatus.FINISHED:
            self.sims[sim_id].update(columns)

    def write_steps(self, sim_id, after_step, through_step, rows, state) -> None:
        sim = self.sims[sim_id]
        if (
            sim["LAST_COMPLETED_STEP"] != after_step
            or sim["STATUS"] != SimStatus.RUNNING
        ):
            raise StepAlreadyWritten(
                f"sim {sim_id}: expected last completed step {after_step}, found "
                f"{sim['LAST_COMPLETED_STEP']} with status {sim['STATUS']}"
            )
        # Work on copies, so that a kill halfway leaves the stored tables untouched.
        staged = {name: list(self.tables[name]) for name in TABLES}
        for name in TABLES:
            new = rows.get(name, [])
            if name in REPLACED_BY_ID:
                ids = {r["ID"] for r in new}
                staged[name] = [
                    r
                    for r in staged[name]
                    if not (r["SIM"] == sim_id and r["ID"] in ids)
                ]
            staged[name] += [dict(r) for r in new]
            if self._kill_in == 1 and name == TABLES[len(TABLES) // 2]:
                self._kill_in = None
                raise SimulatedKill(f"killed while writing up to step {through_step}")
        if self._kill_in is not None:
            self._kill_in -= 1
        self.tables.update(staged)
        sim.update(
            LAST_COMPLETED_STEP=through_step, ACCOUNT_STATE=state, LAST_WRITTEN_AT=now()
        )

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        found = {}
        for name in TABLES:
            counts: dict[str, int] = defaultdict(int)
            for row in self.rows(name, sim_id):
                counts[row["ID"]] += 1
            duplicated = sum(1 for n in counts.values() if n > 1)
            if duplicated:
                found[name] = duplicated
        return found

    def save_reading(self, version: str, opening: str) -> None:
        self.readings.setdefault(version, opening)

    def spent(self, sim_id: int) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self.rows("SIM.CALLS", sim_id))

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        answers = [
            r["SCREEN_ANSWER"]
            for r in self.rows("MEMORY.DECISIONS", sim_id)
            if r["KIND"] == "screen" and r["SCREEN_ANSWER"] is not None
        ]
        return len(answers), sum(1 for a in answers if a >= cut_off)

    # For tests

    def rows(self, table: str, sim_id: int) -> list[dict]:
        return [r for r in self.tables[table] if r["SIM"] == sim_id]

    def all_rows(self, sim_id: int = 1) -> dict[str, list[dict]]:
        """Every record of a sim, table by table, in ID order: two sims compared row for row."""
        return {
            name: sorted(self.rows(name, sim_id), key=lambda r: r["ID"])
            for name in TABLES
        }
