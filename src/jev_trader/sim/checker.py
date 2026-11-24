"""The one checker: every refusal of a sim comes from here (spec appendix 8, section 8.6).

`check` returns every refusal at once, each with a code, what is wrong, and how to fix it;
`require_allowed` raises them together as `Refused`. `check_resume` is the part that still
applies when a stopped sim is carried on. The sim command uses both now; the form
(`GET /sims/check`) and the API's start and resume will use them too.

Of the spec's six refusals, these are built: test period days in a sim that is not a
measurement (1), a cap that could take spending past the ceiling (3), a fifth sim in progress
(4), and a dataset that is not published (5). The memory refusal (2) and the unknown model (6)
come with the agent with memory. The other refusals are the limits of what is built so far.

Choices the spec leaves to the build (appendix 8, "Not decided by any ticket"):

- "In progress" is a status of created or running. A sim shown as not responding is still
  running, so it counts; a stopped sim does not count until it is resumed.
- The sim of holding the five assets is never refused for test period days, the ceiling or the
  limit on sims in progress: it decides nothing, calls nothing paid, and is shared by every sim on its days,
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
    spending_cap_given: float | None = (
        None  # a practice sim's cap, if the developer raised it
    )


def check(
    sim: Planned, info: DatasetInfo, store: SimStore, settings: SpendingSettings
) -> list[Refusal]:
    """Every reason the spec refuses `sim`, in a fixed order; empty if it may start."""
    refusals = _dataset(info) + _request(sim, info)
    if sim.variant == "buy_hold":
        return refusals
    lowest_cap = settings.practice_cap_usd if sim.kind == "practice" else 0.0
    return (
        refusals
        + _practice_cap(sim, settings)
        + _test_period_days(sim, info)
        + _ceiling(sim.spending_cap or 0.0, store, settings, lowest_cap)
        + _too_many(store, settings)
    )


def require_allowed(
    sim: Planned, info: DatasetInfo, store: SimStore, settings: SpendingSettings
) -> None:
    refusals = check(sim, info, store, settings)
    if refusals:
        raise Refused(refusals)


def check_resume(
    sim: dict, store: SimStore, settings: SpendingSettings
) -> list[Refusal]:
    """The refusals that still apply when a stopped sim (its row, `sim`) is carried on: the
    ceiling, with what is left under its cap, and the limit on sims in progress, itself left
    out of both. The rest were checked when it started and have not changed."""
    if sim["VARIANT"] == "buy_hold":
        return []
    left = max(0.0, (sim.get("SPENDING_CAP") or 0.0) - store.spent(sim["ID"]))
    return _ceiling(left, store, settings, None, excluding=sim["ID"]) + _too_many(
        store, settings, excluding=sim["ID"]
    )


def require_resumable(sim: dict, store: SimStore, settings: SpendingSettings) -> None:
    refusals = check_resume(sim, store, settings)
    if refusals:
        raise Refused(refusals)


def _dataset(info: DatasetInfo) -> list[Refusal]:
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
    elif sim.variant == "memory_off" and sim.kind != "practice":
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


def _practice_cap(sim: Planned, settings: SpendingSettings) -> list[Refusal]:
    """A practice sim's cap may only be raised above the usual one, for that one sim."""
    given = sim.spending_cap_given
    if sim.kind != "practice" or given is None or given > settings.practice_cap_usd:
        return []
    return [
        Refusal(
            "cap_not_raised",
            f"a practice sim's cap can only be raised above ${settings.practice_cap_usd:.2f}, "
            f"not set to ${given:.2f}",
            f"give a cap above ${settings.practice_cap_usd:.2f}, or none",
        )
    ]


def _ceiling(
    may_add: float,
    store: SimStore,
    settings: SpendingSettings,
    lowest_cap: float | None,
    excluding: int | None = None,
) -> list[Refusal]:
    """Refusal 3: money paid, plus what the other sims in progress may still spend under their
    caps, plus what this sim may spend (`may_add`), must stay within the ceiling.

    `lowest_cap` is the smallest cap this sim could be given (0 when a shorter sim gives a
    smaller one); None when its cap cannot change, as on a resume."""
    may_still_spend = sum(
        max(0.0, (s["SPENDING_CAP"] or 0.0) - s["SPENT"])
        for s in store.sims_in_progress()
        if s["ID"] != excluding
    )
    paid = store.total_spent()
    spoken_for = paid + may_still_spend
    if spoken_for + may_add <= settings.ceiling_usd + 1e-9:
        return []
    room = max(
        0.0, math.floor(round((settings.ceiling_usd - spoken_for) * 100, 6)) / 100
    )
    wait = "wait for a sim in progress to end, or stop one"
    if lowest_cap is None or room <= lowest_cap:
        fix = wait
    elif lowest_cap > 0:  # a practice sim given a higher cap
        fix = f"give a --spending-cap of ${room:.2f} or less, or {wait}"
    else:
        fix = f"shorten the sim so its cap is ${room:.2f} or less, or {wait}"
    return [
        Refusal(
            "over_ceiling",
            f"this sim may spend ${may_add:.2f} more, which could take spending to "
            f"${spoken_for + may_add:.2f}, past the ${settings.ceiling_usd:.2f} ceiling "
            f"(${paid:.2f} paid, ${may_still_spend:.2f} more allowed to the sims in "
            f"progress; ${room:.2f} is left)",
            fix,
        )
    ]


def _too_many(
    store: SimStore, settings: SpendingSettings, excluding: int | None = None
) -> list[Refusal]:
    """Refusal 4: no more sims of the agent in progress at once than the setting allows, with
    no waiting line."""
    running = [
        s
        for s in store.sims_in_progress()
        if s["VARIANT"] != "buy_hold" and s["ID"] != excluding
    ]
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
