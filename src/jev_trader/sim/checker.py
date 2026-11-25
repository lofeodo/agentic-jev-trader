"""The one checker: every refusal of a sim comes from here (spec appendix 8, section 8.6).

`check` returns every refusal at once, each with a code, what is wrong, and how to fix it;
`require_allowed` raises them together as `Refused`. `check_together` checks the sims one start
creates as a group (a measurement's three, say): the ceiling and the limit on sims in progress
count them all. `check_resume` is the part that still applies when a stopped sim is carried on.
The sim command uses `check`; the API's start and the form's question (`GET /sims/check`) use
`check_together`, and its resume `check_resume`.

All six of the spec's refusals are built: test period days in a sim that is not a measurement
(1), a memory the sim may not start from (2), a cap that could take spending past the ceiling
(3), a fifth sim in progress (4), a dataset that is not published (5), and an unknown model (6).
The other refusals are the limits of what is built so far. A start from the app is let past the
two "not built yet" ones (the developer's decision on the New trading sim form's tickets, #174
and #176): its sims are stored and their jobs started. Until the agent with memory is built, a
sim with memory's job fails in its first moment ("not built yet"), before any paid call; a
measurement, build-up or free sim without memory really runs, calling Jev up to its cap.

`check_models` is the request's own refusal about models, before any sim is planned: only a
measurement names more than one.

**Refusal 2, the memory** (appendix 5, section 2; ADR 0007). A sim with memory starts from a
copy of another sim's memory: the base memory (the latest finished build-up sim's on the
dataset) unless one is named. The sim it copies must be finished, on the same dataset, and ended
before this sim's first step, and its memory must hold nothing recorded at or after that step
(a decision's step, or the step from which an outcome is known): the agent never remembers its
own future. Only a practice sim may name a memory other than a build-up sim's: the rehearsal's
later sims start from the small memory its first sim left. `require_memory` repeats these checks
in the job's first moment, before the copy is made.

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
from jev_trader.llm.models import load_model_settings
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
    memory_from: int | None = None  # the sim whose memory it starts from a copy of
    model: str | None = (
        None  # the LLM a sim with memory uses, such as "claude-haiku-5-5"
    )


def check(
    sim: Planned, info: DatasetInfo, store: SimStore, settings: SpendingSettings
) -> list[Refusal]:
    """Every reason the spec refuses `sim`, in a fixed order; empty if it may start."""
    return check_together([sim], info, store, settings)


def check_together(
    sims: list[Planned],
    info: DatasetInfo,
    store: SimStore,
    settings: SpendingSettings,
    *,
    unbuilt_allowed: bool = False,
) -> list[Refusal]:
    """Every reason the spec refuses starting `sims` together (one start's sims, all on one
    dataset), in a fixed order, each said once; empty if they may start.

    The ceiling counts all their caps at once, and the limit on sims in progress all the agent's
    sims among them. `unbuilt_allowed` lets through what is not built yet (the agent with memory,
    and the agent without memory beyond practice sims): a start from the app, which the developer
    allowed so the New trading sim form works before the agent with memory does. A sim with
    memory's job then fails in its first moment, before any paid call; a sim without memory
    really runs, up to its cap."""
    refusals = _dataset(info)
    for sim in sims:
        refusals += (
            _request(sim, info, unbuilt_allowed)
            + _unknown_model(sim)
            + _memory(sim, store)
        )
    agents = [sim for sim in sims if sim.variant != "buy_hold"]
    if agents:
        for sim in agents:
            refusals += _practice_cap(sim, settings) + _test_period_days(sim, info)
        practice = any(sim.kind == "practice" for sim in agents)
        refusals += _ceiling(
            sum(sim.spending_cap or 0.0 for sim in agents),
            store,
            settings,
            settings.practice_cap_usd if practice else 0.0,
            sim_count=len(agents),
        ) + _too_many(store, settings, adding=len(agents))
    return list(dict.fromkeys(refusals))


def check_models(kind: str, models: list[str]) -> list[Refusal]:
    """What is wrong with the models a start names (`models`, in lower case, each once): only
    a measurement plays more than one."""
    if kind == "measurement" or len(models) <= 1:
        return []
    return [
        Refusal(
            "one_model",
            f"a {kind} sim uses one model, not {len(models)}",
            f"pick one of {', '.join(models)}",
        )
    ]


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


def require_memory(sim: dict, store: SimStore) -> None:
    """Refusal 2 again, in the job's first moment: may the sim (its row, `sim`) start from a
    copy of the memory its row names?"""
    refusals = memory_refusals(
        sim["DATASET"], sim["KIND"], sim["FIRST_STEP"], sim["MEMORY_FROM_SIM"], store
    )
    if refusals:
        raise Refused(refusals)


def _memory(sim: Planned, store: SimStore) -> list[Refusal]:
    """Refusal 2: only the agent with memory starts from one, and only from a memory it may."""
    if sim.variant != "memory_on":
        if sim.memory_from is None:
            return []
        return [
            Refusal(
                "reads_no_memory",
                f"the {sim.variant} variant reads no memory, so it starts from none",
                "leave out the memory to start from, or pick memory_on",
            )
        ]
    if sim.memory_from is None:
        return [
            Refusal(
                "no_base_memory",
                f"dataset {sim.dataset} has no base memory yet: no build-up sim on it has "
                "finished",
                "run the build-up sim first, or name a memory to start a practice sim from",
            )
        ]
    return memory_refusals(
        sim.dataset, sim.kind, sim.first_step, sim.memory_from, store
    )


def memory_refusals(
    dataset: int, kind: str, first_step: int, memory_from: int, store: SimStore
) -> list[Refusal]:
    """What stops a sim of `kind` on `dataset`, starting at `first_step`, from starting from a
    copy of sim `memory_from`'s memory."""
    try:
        source = store.sim(memory_from)
    except KeyError:
        source = None  # the sim store raises; the API's store answers None
    if source is None:
        return [
            Refusal(
                "memory_not_found",
                f"there is no sim {memory_from} to copy a memory from",
                "name a finished sim on this dataset",
            )
        ]
    found = []
    if source["STATUS"] != "finished":
        found.append(
            Refusal(
                "memory_not_finished",
                f"sim {memory_from} is {source['STATUS']}, not finished: its memory may "
                "still change",
                f"wait for sim {memory_from} to finish, or name a finished sim",
            )
        )
    if source["DATASET"] != dataset:
        found.append(
            Refusal(
                "memory_other_dataset",
                f"sim {memory_from} ran on dataset {source['DATASET']}, not {dataset}: its "
                "step numbers and assets mean something else there",
                f"name a sim that ran on dataset {dataset}",
            )
        )
    elif source["LAST_STEP"] >= first_step:
        found.append(
            Refusal(
                "memory_ends_too_late",
                f"sim {memory_from} ends at step {source['LAST_STEP']}, not before this "
                f"sim's first step ({first_step})",
                f"start this sim after step {source['LAST_STEP']}, or name a sim that "
                "ended earlier",
            )
        )
    latest = store.memory_last_step(memory_from)
    if latest is not None and latest >= first_step:
        found.append(
            Refusal(
                "memory_from_the_future",
                f"sim {memory_from}'s memory holds a record from step {latest}, at or after "
                f"this sim's first step ({first_step}): the agent would remember its own "
                "future",
                f"start this sim after step {latest}, or name a memory recorded earlier",
            )
        )
    if memory_from == store.base_memory_sim(dataset):
        return found
    if kind != "practice":
        found.append(
            Refusal(
                "not_base_memory",
                f"a {kind} sim starts from the base memory (the latest finished build-up "
                f"sim's), not from sim {memory_from}'s",
                "leave out the memory to start from the base memory; only a practice sim "
                "(the rehearsal) starts from another",
            )
        )
    elif (source["KIND"], source["VARIANT"]) != ("practice", "memory_off"):
        found.append(
            Refusal(
                "not_rehearsal_memory",
                f"a practice sim starts from the base memory or, in the rehearsal, from the "
                f"memory a practice sim without memory left; sim {memory_from} is a "
                f"{source['KIND']} {source['VARIANT']} sim",
                "leave out the memory to start from the base memory, or name the "
                "rehearsal's first sim",
            )
        )
    return found


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


def _request(sim: Planned, info: DatasetInfo, unbuilt_allowed: bool) -> list[Refusal]:
    """The limits of what is built (unless `unbuilt_allowed`), and steps the dataset does not
    have."""
    found = []
    if sim.variant not in VARIANTS:
        found.append(
            Refusal(
                "unknown_variant",
                f'there is no variant "{sim.variant}"',
                f"pick one of {', '.join(VARIANTS)}",
            )
        )
    elif sim.variant not in BUILT_VARIANTS and not unbuilt_allowed:
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
    elif sim.variant == "memory_off" and sim.kind != "practice" and not unbuilt_allowed:
        found.append(
            Refusal(
                "not_built",
                f"only practice sims of the agent are built so far, not {sim.kind} sims",
                "start a practice sim",
            )
        )
    elif sim.variant == "memory_on" and sim.kind == "build-up":
        found.append(
            Refusal(
                "build_up_reads_no_memory",
                "a build-up sim plays Jev alone and reads no memory: it builds the base memory",
                "pick memory_off",
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


def _unknown_model(sim: Planned) -> list[Refusal]:
    """Refusal 6: a model that is not one of the models in `config/llm.toml`. Only the agent
    with memory has a model; its name is already in lower case (`runner.plan_sim`)."""
    known = load_model_settings().models
    if sim.model is None or sim.model in known:
        return []
    return [
        Refusal(
            "unknown_model",
            f'there is no model "{sim.model}"',
            f"pick {' or '.join(known)}",
        )
    ]


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
    sim_count: int = 1,
) -> list[Refusal]:
    """Refusal 3: money paid, plus what the other sims in progress may still spend under their
    caps, plus what this sim (or these `sim_count` sims started together) may spend (`may_add`), must stay
    within the ceiling.

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
    elif sim_count == 1:
        fix = f"shorten the sim so its cap is ${room:.2f} or less, or {wait}"
    else:
        fix = f"shorten the sims so their caps add up to ${room:.2f} or less, or {wait}"
    these = "this sim" if sim_count == 1 else f"these {sim_count} sims"
    return [
        Refusal(
            "over_ceiling",
            f"{these} may spend ${may_add:.2f} more, which could take spending to "
            f"${spoken_for + may_add:.2f}, past the ${settings.ceiling_usd:.2f} ceiling "
            f"(${paid:.2f} paid, ${may_still_spend:.2f} more allowed to the sims in "
            f"progress; ${room:.2f} is left)",
            fix,
        )
    ]


def _too_many(
    store: SimStore,
    settings: SpendingSettings,
    excluding: int | None = None,
    adding: int = 1,
) -> list[Refusal]:
    """Refusal 4: no more sims of the agent in progress at once than the setting allows, with
    no waiting line. `adding` is how many sims of the agent the start adds."""
    running = [
        s
        for s in store.sims_in_progress()
        if s["VARIANT"] != "buy_hold" and s["ID"] != excluding
    ]
    most = settings.most_sims_in_progress
    if len(running) + adding <= most:
        return []
    names = ", ".join(
        f"sim {s['ID']} ({s['KIND']}, {s['VARIANT']}, {s['STATUS']})" for s in running
    )
    if adding == 1:
        problem = f"{len(running)} sims in progress, the most at once: {names}"
    else:
        problem = (
            f"this start adds {adding} sims to the {len(running)} in progress, past the "
            f"most at once ({most}): {names or 'none in progress'}"
        )
    too_many = len(running) + adding - most
    if too_many == 1:
        fix = "wait for one to finish, or stop one"
    else:
        fix = f"wait for {too_many} to finish, or stop {too_many}"
    return [Refusal("too_many_sims", problem, fix)]
