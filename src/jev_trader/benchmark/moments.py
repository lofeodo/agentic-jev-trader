"""The saved moments the benchmark hands each model (spec appendix 9, section 8).

A saved moment is one point in the build-up sim where the LLM was asked to pick past episodes:
25 full evaluations and 25 position reviews, 5 of each per asset, drawn at random from the
build-up year's last 30 days. Each model starts where the sim did: the same situation text and
the same first search, whose ten episodes it sees as one-line summaries in today's wording
(not the wording the build-up sim had).
"""

from dataclasses import dataclass

from jev_trader.benchmark import NotBuilt
from jev_trader.llm.selection import Situation
from jev_trader.memory.lookups import SearchResult
from jev_trader.memory.search import Job


@dataclass(frozen=True)
class SavedMoment:
    """One moment from the build-up sim `sim`.

    `situation` holds what the model is told: the asset (masked) and its class, the situation
    text, and in a position review the open position. Its step is the moment's "now": the
    model's own lookups see only the records older than it. `first_search` is code's first
    search at that moment, the ten episodes whose summaries open the exchange.
    """

    sim: int
    situation: Situation
    first_search: SearchResult

    @property
    def job(self) -> Job:
        """Full evaluation or position review."""
        return self.situation.job

    @property
    def asset(self) -> str:
        return self.situation.asset

    @property
    def now(self) -> int:
        """The step the moment was saved at."""
        return self.situation.step

    @property
    def id(self) -> str:
        """The same for every pass and model: "12-4410-ASSET_03-full_evaluation"."""
        return f"{self.sim}-{self.now}-{self.asset}-{self.job}"


def saved_moments(sim: int, database: str) -> list[SavedMoment]:
    """The 50 moments the build-up sim `sim` saved, read from `database`, in a fixed order."""
    raise NotBuilt("reading the build-up sim's saved moments")
