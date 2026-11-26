"""The real model runner, and the run over every pass, moment and model (spec appendix 9,
section 8).

An attempt is the LLM's selection step and nothing after it: the model is handed the moment's
situation and first search, makes its own lookups in the base memory with every record not older
than the moment's "now" hidden, and names its episodes. Jev is not asked and nothing is traded.

`run_benchmark` hands each model every moment, `PASSES` times, one attempt at a time, taking the
models in turn on each moment, so a run the cap stops early still holds attempts of both. Before
each attempt it asks the spend meter; after it, the attempt is kept (`AttemptLog`: its calls in
`SIM.CALLS`, its detail in a file).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jev_trader.benchmark.attempts import Attempt, AttemptLog, ModelRunner, Outcome
from jev_trader.benchmark.moments import SavedMoment, context_at
from jev_trader.benchmark.spending import CapReached, SpendMeter
from jev_trader.llm.clients import LlmFailed
from jev_trader.llm.selection import (
    LimitHit,
    LlmSelector,
    MemoryLookups,
    Selection,
    Selector,
)
from jev_trader.llm.settings import LlmSettings
from jev_trader.memory.bridge import LookupContext

# Each model does every moment this many times: models do not answer the same way twice, so the
# passes show each model's own wobble.
PASSES = 3


class SelectionRunner:
    """The real runner: the LLM's selection step on the moment, its lookups from `lookups_at`,
    made for the moment's "now" in the base memory
    (`jev_trader.memory.bridge.Connection.lookups_at`).

    `selector_for` makes the selector for one model: by default the real one
    (`jev_trader.llm.selection.LlmSelector`); tests hand in one over a fake chat model."""

    def __init__(
        self,
        lookups_at: Callable[[LookupContext], MemoryLookups],
        selector_for: Callable[[LlmSettings], Selector] = LlmSelector,
    ):
        self.lookups_at = lookups_at
        self.selector_for = selector_for

    def run(self, moment: SavedMoment, model: LlmSettings, pass_number: int) -> Attempt:
        lookups = self.lookups_at(context_at(moment.sim, moment.situation))
        selector = self.selector_for(model)
        try:
            selection = selector.select(moment.situation, lookups, moment.first_search)
        except LlmFailed as failed:
            # A call still failing after its retries carries that call; the third failed
            # reply carries none.
            outcome = (
                Outcome.FAILED_REPLY if failed.call is None else Outcome.RETRIES_USED_UP
            )
            return Attempt(
                moment=moment,
                model=model.model,
                pass_number=pass_number,
                outcome=outcome,
                episode_ids=(),
                calls=failed.calls,
                failure=failed,
            )
        return Attempt(
            moment=moment,
            model=model.model,
            pass_number=pass_number,
            outcome=outcome_of(selection),
            episode_ids=selection.episode_ids,
            calls=selection.calls,
            selection=selection,
        )


def outcome_of(selection: Selection) -> Outcome:
    """How an answered attempt went: any reply code could not use makes it a failed reply,
    even when a later reply answered; the 60-second limit reached makes it a time limit. The
    limit of 6 lookups reached is not going wrong."""
    if selection.failed_replies:
        return Outcome.FAILED_REPLY
    if selection.limit_hit is LimitHit.TIME:
        return Outcome.TIME_LIMIT
    return Outcome.FINE


@dataclass(frozen=True)
class BenchmarkRun:
    """Every attempt made, in order, and why the run stopped early if it did (the spend
    meter's plain-words message)."""

    attempts: tuple[Attempt, ...]
    stopped: str | None = None


def run_benchmark(
    moments: Sequence[SavedMoment],
    models: Sequence[LlmSettings],
    runner: ModelRunner,
    meter: SpendMeter,
    log: AttemptLog,
) -> BenchmarkRun:
    """Each model's attempts at every moment, `PASSES` times, one at a time: the meter is asked
    before each attempt and told its cost after, and each attempt is kept by `log`. The run
    stops itself, keeping what it has, once the meter says the cap could be passed."""
    attempts: list[Attempt] = []
    for pass_number in range(1, PASSES + 1):
        for moment in moments:
            for model in models:
                try:
                    meter.check()
                except CapReached as stop:
                    return BenchmarkRun(tuple(attempts), stopped=str(stop))
                attempt = runner.run(moment, model, pass_number)
                meter.add(attempt.cost_usd)
                log.keep(attempt)
                attempts.append(attempt)
    return BenchmarkRun(tuple(attempts))
