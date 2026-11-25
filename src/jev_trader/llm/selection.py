"""The selection step: the LLM picks which past episodes Jev reads in a full evaluation (spec
appendix 5, sections 4 to 8; appendix 10, section 2).

Code runs the first search and hands its one-line summaries to a `Selector`. The selector may
look further through memory's lookups (`MemoryLookups`, for one moment: the sim, the step, the
asset and the job are filled in by code) and returns a `Selection`: the chosen episodes' IDs,
most useful first, and a one-line note, with what the decision record stores about how they
were chosen.

Only the stand-in is built: it selects none and looks nothing up. The real selector is a small
LangGraph tool loop over the LLM client the model setting names (`jev_trader.llm.clients`).

Choices the spec leaves to the build:

- The lookups are called as plain (blocking) calls, as the agent's steps are; the memory bridge
  itself is asynchronous, so the real lookups wrap it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

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
