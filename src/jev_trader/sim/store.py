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
    "SIM.LLM_EXCHANGES",
    "MEMORY.DECISIONS",
    "MEMORY.OUTCOMES",
)
# A sim's memory: the tables a sim with memory starts from a copy of (spec appendix 6, section
# 3.5). Each row's SIM is the memory it belongs to; FIRST_WRITTEN_BY the sim that wrote it.
# Only the MEMORY tables a step writes are copied: a later MEMORY table (POSITIONS, ...) must go
# into TABLES to be part of the copy.
MEMORY_TABLES = tuple(name for name in TABLES if name.startswith("MEMORY."))
# A decision's KIND. An asset with no position: a screen alone (tier 0 or 1), or a full evaluation
# (tier 2); both began with the screen, unless code skipped it. An open position: a position
# screen alone (tier 0 or 1), or a position review (tier 2), which began with the position screen
# unless it was an end-of-session review.
KIND_SCREEN = "screen"
KIND_FULL_EVALUATION = "full_evaluation"
SCREENED_KINDS = (KIND_SCREEN, KIND_FULL_EVALUATION)
KIND_POSITION_SCREEN = "position_screen"
KIND_POSITION_REVIEW = "position_review"
POSITION_KINDS = (KIND_POSITION_SCREEN, KIND_POSITION_REVIEW)
# A decision's ACTION: what was done.
ACTION_NOTHING = "nothing"
ACTION_ENTRY = "entry"
ACTION_CLOSE = "close"
ACTION_REDUCE = "reduce"
ACTION_ADD = "add"
# The statuses of a sim in progress (spec appendix 8, section 8.8).
IN_PROGRESS = ("created", "running")
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
        outcomes_known: dict[str, int] | None = None,
    ) -> None:
        """Store `rows` and move the last completed step from `after_step` to `through_step`, all at once.

        `after_step` is the last completed step the writer last saw (None before the first
        write); `state` is the account after `through_step`. `outcomes_known` sets the
        `OUTCOMES_KNOWN_FROM` step of decisions (by ID) whose outcomes became complete, in the
        same write. Raises `StepAlreadyWritten`, having
        stored nothing, if the last completed step no longer reads `after_step` or the sim is not running.
        """

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        """For each table with any, how many of the sim's record IDs appear more than once."""

    def base_memory_sim(self, dataset: int) -> int | None:
        """The sim whose memory is the dataset's base memory: its latest finished build-up sim
        of the agent (never a holding sim); None if it has none."""

    def memory_last_step(self, sim_id: int) -> int | None:
        """The latest step anything in the sim's memory was recorded at: a decision's step, or
        the step from which an outcome is known. None for an empty memory."""

    def start_with_memory(self, sim_id: int, memory_from: int, **columns) -> None:
        """Set columns of the sim's row (marking it running) and give it a copy of sim
        `memory_from`'s memory, all at once.

        Each copied row keeps its ID and `FIRST_WRITTEN_BY`; only its `SIM` (the memory it
        belongs to) changes. Whatever the sim's memory already held is replaced, so a sim killed
        after the copy and before its first step is copied again, not twice. Raises
        `StepAlreadyWritten`, having changed nothing, if the sim has stored a step or is
        finished."""

    def save_reading(self, version: str, opening: str) -> None:
        """Store the opening of Jev's background, once per reading version."""

    def save_prompt(
        self,
        version: str,
        system_prompts: dict[str, str],
        tools: dict[str, list[dict]],
    ) -> None:
        """Store the LLM's standing instructions and the tools it is offered, each by job (a
        full evaluation, a position review), once per prompt version."""

    def spent(self, sim_id: int) -> float:
        """The dollars of the sim's recorded paid calls."""

    def total_spent(self) -> float:
        """The dollars of every recorded paid call, those made outside a sim included."""

    def sims_in_progress(self) -> list[dict]:
        """Each sim created or running, holding sims included, in ID order: its ID, KIND,
        VARIANT, STATUS and SPENDING_CAP, and SPENT, the dollars of its recorded calls."""

    def latest_tier_2_share(self) -> float | None:
        """The share of checks that led to Tier 2 in the latest practice sim of the
        agent that made any; None if there is none."""

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        """How many screens Jev answered, and how many of them said yes (at `cut_off` or above)."""

    def full_evaluation_counts(self, sim_id: int) -> tuple[int, int]:
        """How many full evaluations ran, and how many of them placed an order to open a trade."""

    def position_screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        """How many position screens Jev answered, and how many said yes (at `cut_off` or above)."""

    def position_review_counts(self, sim_id: int) -> dict[str, int]:
        """How many position reviews ran ("reviews"), how many were end-of-session reviews
        ("end_of_session"), and how many closed, reduced or added (by action: "close", ...)."""


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
        self.prompts: dict[str, tuple[dict[str, str], dict[str, list[dict]]]] = {}
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

    def write_steps(
        self, sim_id, after_step, through_step, rows, state, outcomes_known=None
    ) -> None:
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
        known = outcomes_known or {}
        staged["MEMORY.DECISIONS"] = [
            {**r, "OUTCOMES_KNOWN_FROM": known[r["ID"]]}
            if r["SIM"] == sim_id and r["ID"] in known
            else r
            for r in staged["MEMORY.DECISIONS"]
        ]
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

    def base_memory_sim(self, dataset: int) -> int | None:
        found = [
            sim_id
            for sim_id, sim in self.sims.items()
            if sim["DATASET"] == dataset
            and sim["KIND"] == "build-up"
            and sim["VARIANT"] != "buy_hold"
            and sim["STATUS"] == SimStatus.FINISHED
        ]
        return max(found, default=None)

    def memory_last_step(self, sim_id: int) -> int | None:
        steps = [
            step
            for r in self.rows("MEMORY.DECISIONS", sim_id)
            for step in (r["STEP"], r.get("OUTCOMES_KNOWN_FROM"))
            if step is not None
        ] + [r["KNOWN_FROM"] for r in self.rows("MEMORY.OUTCOMES", sim_id)]
        return max(steps, default=None)

    def start_with_memory(self, sim_id: int, memory_from: int, **columns) -> None:
        sim = self.sims[sim_id]
        if (
            sim["LAST_COMPLETED_STEP"] is not None
            or sim["STATUS"] == SimStatus.FINISHED
        ):
            raise StepAlreadyWritten(
                f"sim {sim_id} has stored up to step {sim['LAST_COMPLETED_STEP']} with "
                f"status {sim['STATUS']}: its memory is not copied again"
            )
        for name in MEMORY_TABLES:
            self.tables[name] = [r for r in self.tables[name] if r["SIM"] != sim_id] + [
                {**r, "SIM": sim_id} for r in self.rows(name, memory_from)
            ]
        sim.update(columns)

    def save_reading(self, version: str, opening: str) -> None:
        self.readings.setdefault(version, opening)

    def save_prompt(
        self,
        version: str,
        system_prompts: dict[str, str],
        tools: dict[str, list[dict]],
    ) -> None:
        self.prompts.setdefault(version, (system_prompts, tools))

    def spent(self, sim_id: int) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self.rows("SIM.CALLS", sim_id))

    def total_spent(self) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self.tables["SIM.CALLS"])

    def sims_in_progress(self) -> list[dict]:
        shown = ("ID", "KIND", "VARIANT", "STATUS", "SPENDING_CAP")
        return [
            {**{k: sim.get(k) for k in shown}, "SPENT": self.spent(sim_id)}
            for sim_id, sim in sorted(self.sims.items())
            if sim["STATUS"] in IN_PROGRESS
        ]

    def latest_tier_2_share(self) -> float | None:
        for sim_id, sim in sorted(self.sims.items(), reverse=True):
            if sim.get("KIND") != "practice" or sim.get("VARIANT") == "buy_hold":
                continue
            kinds = [
                r["KIND"]
                for r in self.own_rows("MEMORY.DECISIONS", sim_id)
                if r["KIND"] in SCREENED_KINDS
            ]
            if kinds:
                return kinds.count(KIND_FULL_EVALUATION) / len(kinds)
        return None

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        return self._answered(sim_id, cut_off, SCREENED_KINDS)

    def position_screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        return self._answered(sim_id, cut_off, POSITION_KINDS)

    def _answered(self, sim_id, cut_off, kinds) -> tuple[int, int]:
        answers = [
            r["SCREEN_ANSWER"]
            for r in self.own_rows("MEMORY.DECISIONS", sim_id)
            if r["KIND"] in kinds and r["SCREEN_ANSWER"] is not None
        ]
        return len(answers), sum(1 for a in answers if a >= cut_off)

    def position_review_counts(self, sim_id: int) -> dict[str, int]:
        reviews = [
            r
            for r in self.own_rows("MEMORY.DECISIONS", sim_id)
            if r["KIND"] == KIND_POSITION_REVIEW
        ]
        actions = [r["ACTION"] for r in reviews]
        return {
            "reviews": len(reviews),
            "end_of_session": sum(1 for r in reviews if r["END_OF_SESSION"]),
            **{a: actions.count(a) for a in (ACTION_CLOSE, ACTION_REDUCE, ACTION_ADD)},
        }

    def full_evaluation_counts(self, sim_id: int) -> tuple[int, int]:
        actions = [
            r["ACTION"]
            for r in self.own_rows("MEMORY.DECISIONS", sim_id)
            if r["KIND"] == KIND_FULL_EVALUATION
        ]
        return len(actions), actions.count(ACTION_ENTRY)

    def own_rows(self, table: str, sim_id: int) -> list[dict]:
        """The sim's rows of a table that it wrote itself, without those it copied from the
        memory it started from."""
        return [
            r
            for r in self.rows(table, sim_id)
            if r.get("FIRST_WRITTEN_BY", sim_id) == sim_id
        ]

    # For tests

    def rows(self, table: str, sim_id: int) -> list[dict]:
        """Every row of the sim's in a table: in a memory table, those it copied too."""
        return [r for r in self.tables[table] if r["SIM"] == sim_id]

    def all_rows(self, sim_id: int = 1) -> dict[str, list[dict]]:
        """Every record of a sim, table by table, in ID order: two sims compared row for row."""
        return {
            name: sorted(self.rows(name, sim_id), key=lambda r: r["ID"])
            for name in TABLES
        }
