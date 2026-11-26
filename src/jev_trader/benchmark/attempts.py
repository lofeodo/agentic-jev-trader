"""One model's attempt at one saved moment, and the two seams around it: what makes an attempt
(`ModelRunner`) and where it is kept (`AttemptLog`) (spec appendix 9, section 8).

How an attempt went is one of four things (`Outcome`); the last three are the ways of going
wrong that count against a model: a failed reply (an answer code cannot use, such as a sentence
where a tool call was required), the time limit reached, or a call still failing after its
retries. The limits themselves (60 seconds, 3 retries) are the LLM's own settings
(`jev_trader.llm.selection.SelectionLimits`, `config/llm.toml`).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jev_trader.benchmark.moments import SavedMoment
from jev_trader.llm.clients import LlmCall, LlmFailed
from jev_trader.llm.selection import Selection
from jev_trader.llm.settings import LlmSettings


class Outcome(StrEnum):
    FINE = "fine"
    FAILED_REPLY = "failed reply"  # a reply code could not use
    TIME_LIMIT = "time limit"
    RETRIES_USED_UP = "retries used up"


@dataclass(frozen=True)
class Attempt:
    """One model's attempt at one moment, in one pass.

    `episode_ids` are the stored decision IDs the model named, most useful first (none when it
    never answered). `calls` holds each call to the model, its tokens and cost. `selection` is
    the whole selection (lookups, failed replies, the exchange word for word) when the model
    answered, and None when it did not; `failure` is then why not (`LlmFailed`, with its
    failed replies and the exchange up to the failure).
    """

    moment: SavedMoment
    model: str  # "anthropic:claude-haiku-5-5"
    pass_number: int  # from 1
    outcome: Outcome
    episode_ids: tuple[str, ...]
    calls: tuple[LlmCall, ...]
    selection: Selection | None = None
    failure: LlmFailed | None = None

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


class AttemptLog(Protocol):
    def keep(self, attempt: Attempt) -> None:
        """Write the attempt's calls to `SIM.CALLS` and its detail to a file."""
        ...
