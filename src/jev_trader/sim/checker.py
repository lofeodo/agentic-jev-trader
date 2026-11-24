"""The one checker: every refusal of a sim comes from here (spec appendix 8, section 8.6).

`check` returns every refusal at once, each with a code, what is wrong, and how to fix it;
`require_allowed` raises them together as `Refused`. The sim command uses it now; the form
(`GET /sims/check`) and the API's start will use it too.

Of the spec's six refusals, these are built: test period days in a sim that is not a
measurement (1), a cap that could take spending past the ceiling (3), a fifth sim in progress
(4), and a dataset that is not published (5). The memory refusal (2) and the unknown model (6)
come with the agent with memory. The other refusals are the limits of what is built so far.

Choices the spec leaves to the build (appendix 8, "Not decided by any ticket"):

- "In progress" is a status of created or running. A sim shown as not responding is still
  running, so it counts; a stopped sim does not count until it is resumed.
- The sim of holding the five assets is never refused for test period days, the ceiling or the
  limit of 4: it decides nothing, calls nothing paid, and is shared by every sim on its days,
  measurement sims included.
"""

import math
from dataclasses import dataclass

from jev_trader.dataset.store import DatasetStatus
from jev_trader.sim.market import DatasetInfo
from jev_trader.sim.spending import SpendingSettings
from jev_trader.sim.store import SimStore

KINDS = ("practice", "tuning", "build-up", "measurement", "free")
VARIANTS = ("buy_hold", "memory_off", "memory_on")
BUILT_VARIANTS = ("buy_hold", "memory_off")
# A practice sim of the agent: at most one replayed day (spec appendix 9, section 2).
PRACTICE_MOST_STEPS = 96


@dataclass(frozen=True)
class Refusal:
    code: str
    problem: str
    fix: str


class Refused(ValueError):
    """Every reason a sim was refused. A ValueError, so callers that catch those still do."""

    def __init__(self, refusals: list[Refusal]):
        self.refusals = refusals
        super().__init__("; ".join(r.problem for r in refusals))


@dataclass(frozen=True)
class Planned:
    """The sim being checked, as the checker needs it."""

    dataset: int
    variant: str
    kind: str
    first_step: int
    last_step: int
    starting_value: float
    spending_cap: float | None


def check(
    sim: Planned, info: DatasetInfo, store: SimStore, settings: SpendingSettings
) -> list[Refusal]:
    """Every reason the spec refuses `sim`, in a fixed order; empty if it may start."""
    refusals = _dataset(sim, info) + _request(sim, info)
    if sim.variant == "buy_hold":
        return refusals
    return (
        refusals
        + _test_period_days(sim, info)
        + _ceiling(sim, store, settings)
        + _too_many(store, settings)
    )


def require_allowed(
    sim: Planned, info: DatasetInfo, store: SimStore, settings: SpendingSettings
) -> None:
    refusals = check(sim, info, store, settings)
    if refusals:
        raise Refused(refusals)


def _dataset(sim: Planned, info: DatasetInfo) -> list[Refusal]:
    if info.status == DatasetStatus.PUBLISHED:
        return []
    return [
        Refusal(
            "dataset_not_published",
            f"dataset {info.dataset_id} is {info.status}, not published: no sim can start on it",
            "pick a published dataset, or wait for this one's build to publish it",
        )
    ]


def _request(sim: Planned, info: DatasetInfo) -> list[Refusal]:
    """The limits of what is built, and steps the dataset does not have."""
    found = []
    if sim.variant not in VARIANTS:
        found.append(
            Refusal(
                "unknown_variant",
                f'there is no variant "{sim.variant}"',
                f"pick one of {', '.join(VARIANTS)}",
            )
        )
    elif sim.variant not in BUILT_VARIANTS:
        found.append(
            Refusal(
                "not_built",
                f"the {sim.variant} variant is not built yet",
                f"pick one of {', '.join(BUILT_VARIANTS)}",
            )
        )
    if sim.kind not in KINDS:
        found.append(
            Refusal(
                "unknown_kind",
                f'there is no kind of sim "{sim.kind}"',
                f"pick one of {', '.join(KINDS)}",
            )
        )
    elif sim.variant in BUILT_VARIANTS[1:] and sim.kind != "practice":
        found.append(
            Refusal(
                "not_built",
                f"only practice sims of the agent are built so far, not {sim.kind} sims",
                "start a practice sim",
            )
        )
    if not sim.first_step <= sim.last_step:
        found.append(
            Refusal(
                "steps_reversed",
                f"the first step ({sim.first_step}) comes after the last ({sim.last_step})",
                "give a first step before the last",
            )
        )
    if not (info.first_step <= sim.first_step and sim.last_step <= info.last_step):
        found.append(
            Refusal(
                "outside_dataset",
                f"steps {sim.first_step} to {sim.last_step} are not all in the dataset",
                f"pick steps from {info.first_step} to {info.last_step}",
            )
        )
    if sim.first_step <= info.warm_up_last_step:
        found.append(
            Refusal(
                "warm_up_days",
                f"step {sim.first_step} is in the warm-up period: no sim runs in it",
                f"start after step {info.warm_up_last_step}",
            )
        )
    if (
        sim.variant != "buy_hold"
        and sim.kind == "practice"
        and sim.last_step - sim.first_step + 1 > PRACTICE_MOST_STEPS
    ):
        found.append(
            Refusal(
                "practice_too_long",
                f"a practice sim is at most one replayed day ({PRACTICE_MOST_STEPS} steps)",
                f"end it by step {sim.first_step + PRACTICE_MOST_STEPS - 1}",
            )
        )
    if not sim.starting_value > 0:
        found.append(
            Refusal(
                "no_starting_value",
                "the starting account value must be above zero",
                "give a starting account value such as $10,000",
            )
        )
    return found


def _test_period_days(sim: Planned, info: DatasetInfo) -> list[Refusal]:
    """Refusal 1: nothing but a measurement may see the test period's days."""
    if sim.kind == "measurement":
        return []
    found = []
    for period in info.test_periods():
        if sim.first_step <= period.last_step and period.first_step <= sim.last_step:
            before = period.first_step - 1
            found.append(
                Refusal(
                    "test_period_days",
                    f'a {sim.kind} sim cannot use test period days ("{period.name}", steps '
                    f"{period.first_step} to {period.last_step})",
                    f"end the sim by step {before}, or start it after step {period.last_step}",
                )
            )
    return found


def _ceiling(
    sim: Planned, store: SimStore, settings: SpendingSettings
) -> list[Refusal]:
    """Refusal 3: money paid, plus what the sims in progress may still spend under their caps,
    plus this sim's cap, must stay within the ceiling."""
    cap = sim.spending_cap or 0.0
    may_still_spend = sum(
        max(0.0, (s["SPENDING_CAP"] or 0.0) - s["SPENT"])
        for s in store.sims_in_progress()
    )
    spoken_for = store.total_spent() + may_still_spend
    if spoken_for + cap <= settings.ceiling_usd + 1e-9:
        return []
    room = math.floor(round((settings.ceiling_usd - spoken_for) * 100, 6)) / 100
    fix = (
        f"lower the cap to ${room:.2f} or less (a shorter sim has a smaller estimate), "
        "or wait for a sim in progress to end"
        if room > 0
        else "wait for a sim in progress to end: nothing is left under the ceiling"
    )
    return [
        Refusal(
            "over_ceiling",
            f"this sim's ${cap:.2f} cap could take spending to ${spoken_for + cap:.2f}, past "
            f"the ${settings.ceiling_usd:.2f} ceiling (${store.total_spent():.2f} paid, "
            f"${may_still_spend:.2f} more allowed to the sims in progress)",
            fix,
        )
    ]


def _too_many(store: SimStore, settings: SpendingSettings) -> list[Refusal]:
    """Refusal 4: at most 4 sims of the agent in progress, with no waiting line."""
    running = [s for s in store.sims_in_progress() if s["VARIANT"] != "buy_hold"]
    if len(running) < settings.most_sims_in_progress:
        return []
    names = ", ".join(
        f"sim {s['ID']} ({s['KIND']}, {s['VARIANT']}, {s['STATUS']})" for s in running
    )
    return [
        Refusal(
            "too_many_sims",
            f"{len(running)} sims in progress, the most at once: {names}",
            "wait for one to finish, or stop one",
        )
    ]
