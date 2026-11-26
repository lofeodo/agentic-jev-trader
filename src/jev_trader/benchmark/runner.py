"""One model's attempt at one saved moment, and the run over every model, pass and moment (spec
appendix 9, section 8).

An attempt is the LLM's selection step and nothing after it: the model is handed the moment's
situation and first search, makes its own lookups in the base memory with every record not older
than the moment's "now" hidden, and names its episodes. Jev is not asked and nothing is traded.

How an attempt went is one of four things (`Outcome`); the last three are the ways of going
wrong that count against a model: a failed reply (an answer code cannot use, such as a sentence
where a tool call was required, three times in one attempt), the 60-second limit reached, or a
call still failing after 3 retries.

`run_benchmark` hands each model every moment, `PASSES` times, one attempt at a time. Before each
attempt it asks the spend meter; after it, the attempt is kept (`AttemptLog`: its calls in
`SIM.CALLS`, its detail in a file).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jev_trader.benchmark import NotBuilt
from jev_trader.benchmark.moments import SavedMoment
from jev_trader.benchmark.records import AttemptLog
from jev_trader.benchmark.spending import CapReached, SpendMeter
from jev_trader.llm.clients import LlmCall
from jev_trader.llm.selection import MemoryLookups, Selection
from jev_trader.llm.settings import LlmSettings
from jev_trader.memory.bridge import LookupContext

# Each model does every moment this many times: models do not answer the same way twice, so the
# passes show each model's own wobble.
PASSES = 3


class Outcome(StrEnum):
    FINE = "fine"
    FAILED_REPLY = "failed reply"  # three replies code could not use
    TIME_LIMIT = "60-second limit"
    RETRIES_USED_UP = "still failing after 3 retries"


@dataclass(frozen=True)
class Attempt:
    """One model's attempt at one moment, in one pass.

    `episode_ids` are the stored decision IDs the model named, most useful first (none when it
    went wrong before answering). `calls` holds each call to the model, its tokens and cost.
    `selection` is the whole selection (lookups, failed replies, the exchange word for word)
    when the model answered, and None when it did not.
    """

    moment: SavedMoment
    model: str  # "anthropic:claude-haiku-5-5"
    pass_number: int  # 1 to PASSES
    outcome: Outcome
    episode_ids: tuple[str, ...]
    calls: tuple[LlmCall, ...]
    selection: Selection | None = None

    @property
    def went_wrong(self) -> bool:
        return self.outcome is not Outcome.FINE

    @property
    def cost_usd(self) -> float:
        return sum(call.cost_usd for call in self.calls)

    @property
    def tokens_in(self) -> int:
        return sum(call.tokens_in or 0 for call in self.calls)

    @property
    def tokens_out(self) -> int:
        return sum(call.tokens_out or 0 for call in self.calls)


class ModelRunner(Protocol):
    def run(self, moment: SavedMoment, model: LlmSettings, pass_number: int) -> Attempt:
        """`model`'s attempt at `moment`. Never raises for a model going wrong: that is the
        attempt's outcome."""
        ...


class SelectionRunner:
    """The real runner: the LLM's selection step (`jev_trader.llm.selection.LlmSelector`) on
    the moment, its lookups from `lookups_at`, made for the moment's "now" in the base memory
    (`jev_trader.memory.bridge.Connection.lookups_at`)."""

    def __init__(self, lookups_at: Callable[[LookupContext], MemoryLookups]):
        self.lookups_at = lookups_at

    def run(self, moment: SavedMoment, model: LlmSettings, pass_number: int) -> Attempt:
        raise NotBuilt("a model's attempt at a saved moment")


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
    passes: int = PASSES,
) -> BenchmarkRun:
    """Each model's attempts at every moment, `passes` times, one at a time: the meter is asked
    before each attempt and told its cost after, and each attempt is kept by `log`. The run
    stops itself, keeping what it has, once the meter says the cap could be passed."""
    attempts: list[Attempt] = []
    for model in models:
        for pass_number in range(1, passes + 1):
            for moment in moments:
                try:
                    meter.check()
                except CapReached as stop:
                    return BenchmarkRun(tuple(attempts), stopped=str(stop))
                attempt = runner.run(moment, model, pass_number)
                meter.add(attempt.cost_usd)
                log.keep(attempt)
                attempts.append(attempt)
    return BenchmarkRun(tuple(attempts))
