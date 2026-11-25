"""Starting, stopping and resuming a sim from the API (spec appendix 8, sections 8.3, 8.7, 8.10).

- **Start** stores the rows of the sims asked for through the one checker, marks each running,
  then starts its job: `python -m jev_trader.sim resume <id>`, the command the developer types.
  A measurement makes a sim with memory for each model named and one without memory they share
  (three sims for both models, a pair for one); a free sim uses one model, the default
  (`config/llm.toml`) unless one is named, and makes its partner too if asked.
- **Stop** kills the job at once, then marks the sim "stopped by hand". The half-done step is
  thrown away and redone on resume. A job already gone (not responding) is simply marked.
- **Resume** restarts a stopped or not responding sim from its last stored step, after making
  sure its old job is gone. A sim its spending cap stopped needs a new cap, above what it has
  spent and not able to take total spending past the ceiling.

**Check** answers the New trading sim form before a start: the refusals, the cost estimate, the
spending cap and what is left under the ceiling, storing nothing. It works the start's sims out
exactly as the start does, so the two refuse the same things and the check's money is what the
start stores.

Every refusal comes back together with a code and a message saying what to change. A start goes
through the one checker (`jev_trader.sim.checker`), its sims checked together and let past the
two "not built yet" refusals (see `checker`); a resume goes through its `check_resume` (the
ceiling, with the new cap if one is given, and the limit of sims in progress). The checks only
the API makes (command-line-only kinds, days, a free sim's one model, the new cap) stay here.
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
from jev_trader.sim.runner import PlannedSim, SimRequest, plan_sim
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


def _variants_and_models(
    wanted: SimToStart, models: list[str]
) -> list[tuple[str, str | None]]:
    """The sims a start makes, each as its variant and model (None: the default; only the
    agent with memory uses one). A measurement plays both sides: memory with each model named,
    and one sim without memory the models share. A free or build-up sim is one sim, and its
    partner if asked for: the same days the other way."""
    model = models[0] if models else None
    if wanted.variant not in ("memory_on", "memory_off"):
        # The holding sim, or a variant the checker refuses.
        return [(wanted.variant, model)]
    if wanted.kind == "measurement":
        return [("memory_on", m) for m in models or [None]] + [("memory_off", None)]
    sims = [(wanted.variant, model)]
    if wanted.partner:
        other = "memory_off" if wanted.variant == "memory_on" else "memory_on"
        sims.append((other, model))
    return sims


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
        """The form's question about `wanted`: stores nothing, starts nothing. The money is that
        of every sim the start would create: its cap is the sum of their caps, each rounded up
        to the cent on its own, so it is what the start stores."""
        sims, refusals = self._plan(wanted)
        return SimCheck(
            refusals=refusals,
            estimate_usd=sum(sim.row["ESTIMATED_COST"] for sim in sims),
            spending_cap_usd=round(
                sum(sim.row["SPENDING_CAP"] or 0.0 for sim in sims), 2
            ),
            left_under_ceiling_usd=max(
                0.0, math.floor(round(self._room_under_ceiling(None) * 100, 6)) / 100
            ),
            ceiling_usd=self.spending_ceiling,
        )

    def start(self, wanted: SimToStart, at: datetime) -> list[int]:
        """Store every sim `wanted` makes, through the same check as `check`, then start each
        one's job. Refused, it stores and starts nothing."""
        sims, refusals = self._plan(wanted)
        if refusals:
            raise Refused(*refusals)
        sim_ids = [sim.store_in(self.store) for sim in sims]
        for sim_id in sim_ids:
            self._launch(sim_id, at, {})
        return sim_ids

    def _plan(self, wanted: SimToStart) -> tuple[list[PlannedSim], list[Refusal]]:
        """The sims `wanted` makes, worked out but not stored, and every reason to refuse
        them: the API's own first, then the one checker's for the sims as a group."""
        if wanted.kind in COMMAND_LINE_ONLY:
            return [], [
                Refusal(
                    code="command_line_only",
                    message=f"a {wanted.kind} sim is started from the command line only: "
                    "python -m jev_trader.sim",
                )
            ]
        try:
            info = self.store.dataset(wanted.dataset)
        except KeyError:
            return [], [
                Refusal(
                    code="no_such_dataset",
                    message=f"there is no dataset {wanted.dataset}",
                )
            ]
        try:
            first_step, last_step = self._steps(wanted, info)
        except Refused as refused:
            return [], refused.refusals
        models = list(dict.fromkeys(m.lower() for m in wanted.models or []))
        refusals = []
        if wanted.kind != "measurement" and len(models) > 1:
            refusals.append(
                Refusal(
                    code="one_model",
                    message=f"a {wanted.kind} sim uses one model, not {len(models)}. "
                    "Fix: pick one of them",
                )
            )
            models = models[:1]
        spending = self._spending()
        sims = [
            plan_sim(
                self.store,
                self.store,
                SimRequest(
                    dataset=wanted.dataset,
                    variant=variant,
                    kind=wanted.kind,
                    first_step=first_step,
                    last_step=last_step,
                    starting_value=wanted.starting_value,
                    market=wanted.market,
                    model=model,
                ),
                spending,
            )
            for variant, model in _variants_and_models(wanted, models)
        ]
        refused = checker.check_together(
            [sim.planned for sim in sims],
            info,
            self.store,
            spending,
            unbuilt_allowed=True,
        )
        if refused:
            refusals += _from_checker(checker.Refused(refused)).refusals
        return sims, refusals

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

    def _room_under_ceiling(self, sim_id: int | None) -> float:
        """The ceiling, less money already spent and the unspent caps of the sims in progress
        but `sim_id`."""
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
