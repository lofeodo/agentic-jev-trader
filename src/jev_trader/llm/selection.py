"""The selection step: the LLM picks which past episodes Jev reads in a full evaluation (spec
appendix 5, sections 4 to 8; appendix 10, section 2).

Code runs the first search and hands its one-line summaries to a `Selector`. The selector may
look further through memory's lookups (`MemoryLookups`, for one moment: the sim, the step, the
asset and the job are filled in by code) and returns a `Selection`: the chosen episodes' IDs,
most useful first, and a one-line note, with what the decision record stores about how they
were chosen.

Only stand-ins are built: they select none and look nothing up. The real selector
(`LlmSelector`) is a small LangGraph tool loop over the LLM client the model setting names
(`jev_trader.llm.clients`), timed by a `WallClock` so its tests can run on a fake one. A provider
call still failing after its retries, or a third failed reply, raises `LlmFailed`, which stops
the sim.

Choices the spec leaves to the build:

- The lookups are called as plain (blocking) calls, as the agent's steps are; the memory bridge
  itself is asynchronous, so the real lookups wrap it.
"""

import time
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from langchain_core.language_models import BaseChatModel

from jev_trader.llm.settings import LlmSettings
from jev_trader.llm.wording import LlmWording
from jev_trader.memory.lookups import MOST_READ, Episodes, SearchResult
from jev_trader.memory.search import RESULTS
from jev_trader.memory.track_record import TrackRecord


@dataclass(frozen=True)
class SelectionLimits:
    """The selection's limits, stored with each sim (appendix 5, section 6)."""

    results_per_search: int = RESULTS
    most_selected: int = MOST_READ
    most_lookups: int = 6  # not counting the first search; the answer never counts
    seconds: float = 60.0
    failed_replies_to_stop: int = 3  # the third in one evaluation stops the sim
    note_length: int = 200


class LimitHit(StrEnum):
    LOOKUPS = "lookups"  # 6 lookups used
    TIME = "time"  # 60 seconds up


class MemoryLookups(Protocol):
    """Memory's three read-only lookups for one moment, as the agent and the selector use them."""

    def search(self, **filters: str) -> SearchResult: ...

    def read(self, episode_ids: list[str]) -> Episodes: ...

    def track_record(self, pattern: str, direction: str) -> TrackRecord: ...


@dataclass(frozen=True)
class Lookup:
    """One lookup the LLM made, in order: its tool and inputs, the episode IDs it returned,
    how long it took, and the reason it was refused if it was."""

    tool: str
    inputs: dict
    episode_ids: tuple[str, ...]
    latency_seconds: float
    refused: str | None = None


@dataclass(frozen=True)
class Shown:
    """An episode the LLM was shown: its label ("E1"), its ranks, which search found it first,
    and whether it was opened in full."""

    episode_id: str
    label: str
    vector_rank: int | None
    text_rank: int | None
    merged_rank: int
    from_first_search: bool
    opened: bool = False


@dataclass(frozen=True)
class Selection:
    """What the selection chose, and how, for the decision record.

    `episode_ids` are stored decision IDs, most useful first: none is a valid answer.
    `limit_hit` says which limit was reached, if one was. `failed_replies` holds each
    reply code could not use, word for word, and `exchange` every message sent and received.
    """

    episode_ids: tuple[str, ...]
    note: str
    shown: tuple[Shown, ...] = ()
    lookups: tuple[Lookup, ...] = ()
    limit_hit: LimitHit | None = None
    failed_replies: tuple[str, ...] = ()
    exchange: tuple[dict, ...] = ()
    model: str | None = None
    prompt_version: str | None = None


class Selector(Protocol):
    def select(
        self, lookups: MemoryLookups, first_search: SearchResult
    ) -> Selection: ...


class StandInSelector:
    """Selects no episode and looks nothing up."""

    def select(self, lookups: MemoryLookups, first_search: SearchResult) -> Selection:
        return Selection(episode_ids=(), note="")


class LlmFailed(Exception):
    """The LLM could not be used: a call still failing after its retries, or the third failed
    reply in one evaluation. It stops the sim, which can be resumed (stop reason "LLM failed")."""


class WallClock(Protocol):
    """Where the selection reads the time taken from, for its 60 seconds (not the dataset's
    step clock)."""

    def monotonic(self) -> float: ...


class SystemWallClock:
    def monotonic(self) -> float:
        return time.monotonic()


class LlmSelector:
    """The LLM's selection: a tool loop over `model` (by default the client `settings` names),
    within `limits`, timed by `clock`, in the words of `wording`, whose prompt version every
    selection carries.

    Not built yet: it selects none and looks nothing up, as the stand-in does.
    """

    def __init__(
        self,
        settings: LlmSettings,
        model: BaseChatModel | None = None,
        limits: SelectionLimits | None = None,
        clock: WallClock | None = None,
    ):
        self.settings, self.model = settings, model
        self.limits = limits or SelectionLimits()
        self.clock = clock or SystemWallClock()
        self.wording = LlmWording(
            most_lookups=self.limits.most_lookups,
            most_selected=self.limits.most_selected,
            note_length=self.limits.note_length,
        )

    def select(self, lookups: MemoryLookups, first_search: SearchResult) -> Selection:
        selection = StandInSelector().select(lookups, first_search)
        return replace(selection, prompt_version=self.wording.version)
