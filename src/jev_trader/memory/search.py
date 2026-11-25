"""Episode search: finding the past episodes most like the present moment (spec appendix 5,
section 3).

An episode is a stored full evaluation or position review with how it turned out. A search
always starts from the current snapshot (the asset's measurements at this step) and ranks the
sim's own complete episodes two ways:

1. **By feature vector**: the snapshot's 58 standard scores, each multiplied by the square root
   of its share of the say, compared by straight-line distance (smaller is more alike). Shapes
   (the last 8 bars) and context (the surroundings) each hold half the say; each older bar holds
   15% less than the bar after it, so the newest bar holds 10.3% and the oldest 3.3%, and one
   context measurement 5%.
2. **By situation text**: the paragraph's 768-number embedding, compared by cosine similarity
   (higher is more alike).

Each ranking gives its top 50; an episode scores 1 / (60 + rank) in each and the two are added,
so close both ways beats close one way (1st and 3rd scores about 0.032). Among results from one
asset less than 8 bars apart only the closest match is kept, and 10 are returned.

Choices the spec leaves to the build (appendix 5, "Not decided by any ticket"):

- A bar's share of the say is split evenly over its six numbers.
- The filters narrow the candidates before each ranking's top 50 is cut, so a narrow filter still
  finds its 10 when memory holds them.
- Repeats are removed after the merge and before the 10 are taken, so a search returns 10 when
  memory holds 10 that are not repeats.
- "8 bars apart" is counted in steps (15 minutes each): a stock's bars on either side of a night
  are never repeats of each other.
- Equal scores are ordered by the vector's rank, then the text's, then the episode's ID, so the
  same memory always gives the same order.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from jev_trader.dataset.measurements import CONTEXT_NAMES, SHAPE_BARS, SHAPE_FIELDS

SHAPE_SHARE = 0.5
BAR_DECAY = 0.15
RESULTS = 10
EACH_RANKING_TOP = 50
RANK_OFFSET = 60
REPEAT_STEPS = 8

Job = Literal["full_evaluation", "position_review"]
FULL_EVALUATION: Job = "full_evaluation"
POSITION_REVIEW: Job = "position_review"

ASSET_FILTERS = ("any", "same_asset", "same_asset_class")
DECIDED_FILTERS: dict[str, tuple[str, ...]] = {
    FULL_EVALUATION: ("any", "long", "short", "no_trade"),
    POSITION_REVIEW: ("any", "hold", "close", "reduce", "add"),
}
STANDING_FILTERS = ("any", "in_profit", "at_a_loss")
DIRECTIONS = ("long", "short")


@dataclass(frozen=True)
class SearchSettings:
    """Sim settings with these starting values, stored with each sim (`memory_search`)."""

    shape_share: float = SHAPE_SHARE
    bar_decay: float = BAR_DECAY
    results: int = RESULTS
    each_ranking_top: int = EACH_RANKING_TOP

    @classmethod
    def of_sim(cls, settings: dict | None) -> "SearchSettings":
        found = (settings or {}).get("memory_search") or {}
        return cls(**{k: v for k, v in found.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Filters:
    """The narrowing the LLM may ask for; "any" everywhere is the automatic first search."""

    asset: str = "any"
    pattern: str = "any"
    decided: str = "any"
    standing: str = "any"  # a position review's search only


@dataclass(frozen=True)
class Query:
    """One search, as code fills it in: the sim and step, the asset looked at, the job, and for a
    position review the open position's direction (only reviews of the same direction match)."""

    sim: int
    step: int
    asset: str
    asset_class: str
    job: Job
    direction: str | None
    filters: Filters
    dataset: int


def feature_weights(settings: SearchSettings) -> tuple[float, ...]:
    """What each of the 58 standard scores is multiplied by: the square root of its share."""
    bar_shares = [(1 - settings.bar_decay) ** k for k in range(SHAPE_BARS)]
    total = sum(bar_shares)
    weights = []
    for share in bar_shares:
        number = settings.shape_share * share / total / len(SHAPE_FIELDS)
        weights += [math.sqrt(number)] * len(SHAPE_FIELDS)
    context = (1 - settings.shape_share) / len(CONTEXT_NAMES)
    weights += [math.sqrt(context)] * len(CONTEXT_NAMES)
    return tuple(weights)


@dataclass(frozen=True)
class Merged:
    id: str
    vector_rank: int | None  # 1 is the closest; None: outside that ranking's top
    text_rank: int | None
    score: float
    merged_rank: int = 0


def merge(by_vector: list[str], by_text: list[str]) -> list[Merged]:
    """The two rankings (episode IDs, closest first) merged by rank, best first."""
    vector = {id: rank for rank, id in enumerate(by_vector, start=1)}
    text = {id: rank for rank, id in enumerate(by_text, start=1)}
    found = []
    for id in dict.fromkeys([*by_vector, *by_text]):
        ranks = [r for r in (vector.get(id), text.get(id)) if r is not None]
        found.append(
            Merged(
                id,
                vector.get(id),
                text.get(id),
                sum(1 / (RANK_OFFSET + r) for r in ranks),
            )
        )
    found.sort(
        key=lambda m: (
            -m.score,
            m.vector_rank or math.inf,
            m.text_rank or math.inf,
            m.id,
        )
    )
    return [
        Merged(m.id, m.vector_rank, m.text_rank, m.score, rank)
        for rank, m in enumerate(found, start=1)
    ]


@dataclass(frozen=True)
class Candidate:
    id: str
    asset: str
    step: int


def best_without_repeats(ranked: Iterable[Candidate], how_many: int) -> list[Candidate]:
    """The first `how_many` of `ranked` (best first), skipping any from the same asset less than
    8 steps from one already kept."""
    kept: list[Candidate] = []
    for c in ranked:
        if len(kept) == how_many:
            break
        if not any(
            k.asset == c.asset and abs(k.step - c.step) < REPEAT_STEPS for k in kept
        ):
            kept.append(c)
    return kept
