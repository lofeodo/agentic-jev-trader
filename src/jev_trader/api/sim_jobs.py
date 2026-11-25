"""Starting, stopping and resuming a sim from the API (spec appendix 8, sections 8.3, 8.7, 8.10).

- **Start** stores the sim's row through the same check as the command line, marks it running,
  then starts its job: `python -m jev_trader.sim resume <id>`, the command the developer types.
- **Stop** kills the job at once, then marks the sim "stopped by hand". The half-done step is
  thrown away and redone on resume. A job already gone (not responding) is simply marked.
- **Resume** restarts a stopped or not responding sim from its last stored step, after making
  sure its old job is gone. A sim its spending cap stopped needs a new cap, above what it has
  spent and not able to take total spending past the ceiling.

**Check** answers the New trading sim form before a start: the refusals, the cost estimate, the
spending cap and what is left under the ceiling, storing nothing. For now it answers a placeholder
of that shape; the New trading sim form's later tickets build it on the one checker.

Every refusal comes back together with a code and a message saying what to change. A start goes
through the one checker (`jev_trader.sim.checker`) inside `create_sim`; a resume goes through its
`check_resume` (the ceiling, with the new cap if one is given, and the limit of sims in
progress). The checks only the API makes (command-line-only kinds, days, the new cap) stay here.
"""

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from jev_trader.api.sim_page import SimNotFound
from jev_trader.api.sims_list import is_not_responding
from jev_trader.api.store import ApiStore
from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.jobs import JobNotKilled, Launcher
from jev_trader.sim import checker
from jev_trader.sim.runner import SimRequest, create_sim
from jev_trader.sim.spending import SpendingSettings, load_spending_settings
from jev_trader.sim.store import SimStatus, StopReason

IN_PROGRESS = (SimStatus.CREATED, SimStatus.RUNNING)
COMMAND_LINE_ONLY = ("practice", "tuning")


class Refusal(BaseModel):
    code: str
    message: str  # what is wrong, and how to fix it


class Refused(Exception):
    def __init__(self, *refusals: Refusal):
        super().__init__("; ".join(r.message for r in refusals))
        self.refusals = list(refusals)


def _refuse(code: str, message: str) -> Refused:
    return Refused(Refusal(code=code, message=message))


def _from_checker(refused: checker.Refused) -> Refused:
    """The one checker's refusals, each with its fix, as the API answers them."""
    return Refused(
        *(
            Refusal(code=r.code, message=f"{r.problem}. Fix: {r.fix}")
            for r in refused.refusals
        )
    )


class SimToStart(BaseModel):
    """A sim to start. Days are real dates (UTC); give a test period or days, or neither for
    every day after the warm-up."""

    dataset: int
    kind: str  # measurement, build-up or free; practice and tuning start from the command line
    variant: str  # buy_hold, memory_off or memory_on
    market: str | None = None  # a test period's name, such as "falling market"
    first_day: date | None = None
    last_day: date | None = None
    starting_value: float = 10_000.0
    # The LLM or LLMs, such as ["claude-haiku-5-5", "glm-5.3-flash"]: a measurement names one or
    # both, a free sim one. None: the default (`config/llm.toml`).
    models: list[str] | None = None
    # A free sim's partner: the same days played the other way (with memory or without), side
    # by side. A measurement always plays both.
    partner: bool = False


class SimCheck(BaseModel):
    """May this sim start, and what would it cost? Every refusal at once, and the money in US
    dollars: the estimate and cap of all the sims the request creates, and what is left under
    the ceiling for new sims (money paid and other sims' caps taken off)."""

    refusals: list[Refusal]
    estimate_usd: float
    spending_cap_usd: float
    left_under_ceiling_usd: float
    ceiling_usd: float


class Resumption(BaseModel):
    spending_cap_usd: float | None = (
        None  # needed, and only allowed, after a spending cap stop
    )


@dataclass(frozen=True)
class Jobs:
    store: ApiStore
    launcher: Launcher
    spending_ceiling: float
    quiet_limit: timedelta

    def check(self, wanted: SimToStart) -> SimCheck:
        """The form's question about `wanted`: stores nothing, starts nothing. A placeholder
        until the one checker answers it."""
        return SimCheck(
            refusals=[],
            estimate_usd=0.0,
            spending_cap_usd=0.0,
            left_under_ceiling_usd=0.0,
            ceiling_usd=self.spending_ceiling,
        )

    def start(self, wanted: SimToStart, at: datetime) -> list[int]:
        if wanted.kind in COMMAND_LINE_ONLY:
            raise _refuse(
                "command_line_only",
                f"a {wanted.kind} sim is started from the command line only: "
                "python -m jev_trader.sim",
            )
        try:
            info = self.store.dataset(wanted.dataset)
        except KeyError:
            raise _refuse(
                "no_such_dataset", f"there is no dataset {wanted.dataset}"
            ) from None
        first_step, last_step = self._steps(wanted, info)
        request = SimRequest(
            dataset=wanted.dataset,
            variant=wanted.variant,
            kind=wanted.kind,
            first_step=first_step,
            last_step=last_step,
            starting_value=wanted.starting_value,
            market=wanted.market,
            # One sim per start for now. The New trading sim form's later tickets create one sim
            # per model (and the partner); until then a sim with memory is refused as not built.
            model=wanted.models[0] if wanted.models else None,
        )
        try:
            sim_id = create_sim(self.store, self.store, request, self._spending())
        except checker.Refused as refused:
            raise _from_checker(refused) from None
        except ValueError as refused:
            raise _refuse("not_allowed", str(refused)) from None
        self._launch(sim_id, at, {})
        return [sim_id]

    def _steps(self, wanted: SimToStart, info) -> tuple[int, int]:
        if wanted.market is not None:
            if wanted.first_day or wanted.last_day:
                raise _refuse("days_and_period", "give a test period or days, not both")
            for period in info.test_periods():
                if period.name == wanted.market:
                    return period.first_step, period.last_step
            names = ", ".join(f'"{p.name}"' for p in info.test_periods()) or "none"
            raise _refuse(
                "no_such_period",
                f'dataset {info.dataset_id} has no test period "{wanted.market}"; '
                f"it has {names}",
            )
        first_step, last_step = info.warm_up_last_step + 1, info.last_step
        if wanted.first_day or wanted.last_day:
            first_day = self._first_day(info.dataset_id)
            if wanted.first_day:
                first_step = (wanted.first_day - first_day).days * STEPS_PER_DAY + 1
            if wanted.last_day:
                last_step = (wanted.last_day - first_day).days * STEPS_PER_DAY + (
                    STEPS_PER_DAY
                )
        return first_step, last_step

    def _first_day(self, dataset_id: int) -> date:
        """The real day step 1 falls on, from the asset key."""
        days = [
            k["FIRST_DAY"] for k in self.store.asset_key() if k["DATASET"] == dataset_id
        ]
        if not days:
            raise _refuse(
                "no_asset_key",
                f"dataset {dataset_id} has no asset key, so its days cannot be named: "
                "give a test period instead",
            )
        return min(days)

    def stop(self, sim_id: int, at: datetime) -> None:
        sim = self._sim(sim_id)
        if sim["STATUS"] not in IN_PROGRESS:
            raise _refuse(
                "nothing_to_stop", f"sim {sim_id} is {sim['STATUS']}: nothing to stop"
            )
        self._kill(sim)
        # The job may have ended by itself meanwhile (finished, or stopped at its cap).
        if self._sim(sim_id)["STATUS"] in IN_PROGRESS:
            self.store.update(
                sim_id,
                STATUS=str(SimStatus.STOPPED),
                STOP_REASON=str(StopReason.STOPPED_BY_HAND),
                ENDED_AT=at,
            )

    def resume(self, sim_id: int, wanted: Resumption, at: datetime) -> None:
        sim = self._sim(sim_id)
        status = sim["STATUS"]
        # Running but quiet, or running with its job gone (it died before storing anything).
        if (
            status == SimStatus.RUNNING
            and not is_not_responding(sim, at, self.quiet_limit)
            and self.launcher.is_running(sim.get("RUNNING_ON"))
        ):
            raise _refuse(
                "not_resumable", f"sim {sim_id} is still running: nothing to resume"
            )
        if status not in (SimStatus.STOPPED, SimStatus.RUNNING):
            raise _refuse(
                "not_resumable",
                f"sim {sim_id} is {status}: only a stopped or not responding sim resumes",
            )
        new_cap = self._new_cap(sim, wanted.spending_cap_usd)
        refusals = checker.check_resume(
            {**sim, **new_cap}, self.store, self._spending()
        )
        if refusals:
            raise _from_checker(checker.Refused(refusals))
        self._kill(sim)  # a not responding sim's job may hang on
        self._launch(sim_id, at, new_cap)

    def _new_cap(self, sim: dict, cap: float | None) -> dict:
        """The columns a resume sets for the cap: none, or the new cap once it is checked."""
        stopped_by_cap = sim.get("STOP_REASON") == StopReason.SPENDING_CAP or sim.get(
            "STOPPED_BY_CAP"
        )
        if not stopped_by_cap:
            if cap is not None:
                raise _refuse(
                    "cap_not_reached",
                    f"sim {sim['ID']} was not stopped by its cap: resume it without a new cap",
                )
            return {}
        spent = self.store.spent_on(sim["ID"])
        if cap is None:
            raise _refuse(
                "needs_new_cap",
                f"sim {sim['ID']} stopped at its ${sim['SPENDING_CAP']:.2f} cap: "
                "give a new cap to resume it",
            )
        if cap <= spent:
            raise _refuse(
                "cap_not_above_spent",
                f"sim {sim['ID']} has spent ${spent:.2f}: give a cap above that",
            )
        # Rounded down, so that following the advice is never refused.
        most = (
            math.floor((self._room_under_ceiling(sim["ID"]) + spent) * 100 + 1e-6) / 100
        )
        if cap > most + 1e-9:
            raise _refuse(
                "over_ceiling",
                f"a ${cap:.2f} cap could take spending past the "
                f"${self.spending_ceiling:.2f} ceiling: lower the cap to ${most:.2f} or less",
            )
        return {"SPENDING_CAP": cap, "STOPPED_BY_CAP": False}

    def _spending(self) -> SpendingSettings:
        """The spending settings, with the ceiling the API was started with."""
        return replace(load_spending_settings(), ceiling_usd=self.spending_ceiling)

    def _room_under_ceiling(self, sim_id: int) -> float:
        """The ceiling, less money already spent and the unspent caps of other sims in progress."""
        spent_by = self.store.spent_by_sim()
        promised = sum(
            max(0.0, s["SPENDING_CAP"] - spent_by.get(s["ID"], 0.0))
            for s in self.store.sims()
            if s["ID"] != sim_id
            and s["STATUS"] in IN_PROGRESS
            and s["SPENDING_CAP"] is not None
        )
        return self.spending_ceiling - self.store.total_spent() - promised

    def _launch(self, sim_id: int, at: datetime, columns: dict) -> None:
        """Mark the sim running, then start its job. The sim is marked first so that a job quick
        to stop by itself is not marked running again afterwards."""
        running = {
            "STATUS": str(SimStatus.RUNNING),
            "STOP_REASON": None,
            "FAILURE_REASON": None,
            "ENDED_AT": None,
            "STARTED_AT": at,
            **columns,
        }
        before = self._sim(sim_id)
        self.store.update(sim_id, **running)
        try:
            running_on = self.launcher.start(sim_id)
        except Exception:
            self.store.update(sim_id, **{k: before.get(k) for k in running})
            raise
        self.store.update(sim_id, RUNNING_ON=running_on)

    def _kill(self, sim: dict) -> None:
        try:
            self.launcher.stop(sim.get("RUNNING_ON"))
        except JobNotKilled as error:
            raise _refuse(
                "job_not_killed",
                f"{error}; the sim is left as it was: end that program by hand, then try again",
            ) from None

    def _sim(self, sim_id: int) -> dict:
        sim = self.store.sim(sim_id)
        if sim is None:
            raise SimNotFound(sim_id)
        return sim
