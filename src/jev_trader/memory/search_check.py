"""The free check of the episode search's values (spec appendix 9, section 7).

Episode search ranks past episodes partly by a feature vector whose weights rest on two values set
by hand: shapes against context (half the say each) and how much less each older bar counts (15%).
The check asks whether those values find records that matter: for each record (episode) in a
memory, did the records the search calls most similar end the same way more often than records
picked at random did? It calls no model and costs nothing.

Each record is looked up the way the agent would have looked it up at its own step: among the
memory's earlier records of the same job (a full evaluation finds full evaluations, a position
review finds reviews of positions in the same direction), with no filter. It is the search's own
recipe (`search.py`): its weights, both rankings, the merge, repeats removed, `results` kept. Only
the two rankings are redone here, in numpy, over the whole memory at once, with the same order
rules (straight-line distance, cosine similarity, ties by ID): one database query per record would
take hours. A test checks that it picks what `Lookups.search` picks. "Picked at random" is every
record that search could have returned, so its share is the exact average of a random pick, with
no luck in it. Each checked record counts once in both shares.

Choices the spec leaves to the build:

- **Ended the same way** is the price going the same way (up, down, or not at all) over the same
  time after the decision: after 4 bars unless another is chosen. Every episode has the three
  prices, whatever was decided, so every record can be compared with every other. It is not how a
  trade ended, which only traded records have.
- A record can be compared only once that price is known too, not just its episode complete: one
  stricter rule than the live search. A trade closing in 2 bars completes its episode before its
  4-bar price is in; the live search may return it then, the check leaves it out until the price
  is in. So no record is compared with one whose ending falls in its own future.
- A record with fewer earlier records than the search returns is not checked: it has nothing to
  pick from.
- The feature vector ranking is also reported alone, since only it depends on the two values.

A caveat for reading the result: records close in time can move together whatever they look like
(two coins on the same morning), so part of a lead over random may come from timing, not from
the values. Comparing values against each other is fairer than comparing one with random.
"""

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from jev_trader.memory.outcomes import EPISODE_KINDS, OutcomeKind
from jev_trader.memory.search import (
    POSITION_REVIEW,
    Candidate,
    Job,
    SearchSettings,
    best_without_repeats,
    feature_weights,
    merge,
)
from jev_trader.memory.store import UnknownSim

Ending = Literal["up", "down", "flat"]


@dataclass(frozen=True)
class Record:
    """One episode of the memory, with how it ended."""

    id: str
    asset: str
    step: int
    kind: Job
    direction: str | None  # a review's position: long or short
    known_from: int  # the step from which it and its ending are known
    features: Sequence[float]  # the 58-number feature vector
    embedding: Sequence[float]  # the situation text's embedding
    ended: Ending


def ended_as(change: float) -> Ending:
    """Which way the price went: a change of 0.002 (0.2%) is up."""
    return "up" if change > 0 else "down" if change < 0 else "flat"


@dataclass(frozen=True)
class Tally:
    """What the check found for one set of values."""

    checked: int  # records with enough earlier records to look up
    similar_alike: float  # share of the search's results that ended as their record did
    vector_alike: float  # the same, ranked by the feature vector alone
    random_alike: float  # share of all the records the search could have returned


def _top(scores: np.ndarray, ids: np.ndarray, top: int) -> np.ndarray:
    """The positions of the `top` lowest scores, ties broken by ID as the search does. Only the
    scores at or below the `top`-th are sorted, ties at the cut included, so it is exact."""
    if top < len(scores):
        cut = np.partition(scores, top - 1)[top - 1]
        within = np.flatnonzero(scores <= cut)
    else:
        within = np.arange(len(scores))
    return within[np.lexsort((ids[within], scores[within]))][:top]


def _candidate(r: Record) -> Candidate:
    return Candidate(r.id, r.asset, r.step)


@dataclass(frozen=True)
class _Found:
    similar: list[int]  # positions of what the search returns
    nearest: list[int]  # the same by the feature vector alone
    pool: np.ndarray  # positions of everything it could have returned


class Memory:
    """A memory's records, held as arrays so that each can be looked up quickly, for as many
    sets of values as are tried. The text ranking does not depend on them: it is worked out once
    per record."""

    def __init__(self, records: Iterable[Record]):
        self.records = list(records)
        r = self.records
        self._features = np.array([x.features for x in r], dtype=float)
        embeddings = np.array([x.embedding for x in r], dtype=float)
        norms = np.linalg.norm(embeddings, axis=1)
        self._embeddings = embeddings / np.where(norms == 0, 1.0, norms)[:, None]
        self._ids = np.array([x.id for x in r])
        self._index = {x.id: i for i, x in enumerate(r)}
        self._steps = np.array([x.step for x in r])
        self._known = np.array([x.known_from for x in r])
        self._kinds = np.array([x.kind for x in r])
        self._directions = np.array([x.direction or "" for x in r])
        self.ended = np.array([x.ended for x in r])
        self._by_text: dict[tuple[int, int], np.ndarray] = {}
        self._weighted_by: dict[tuple[float, ...], np.ndarray] = {}

    def __len__(self) -> int:
        return len(self.records)

    def similar_to(self, id: str, settings: SearchSettings) -> list[str]:
        """The IDs the search returns for the record `id`, best first."""
        found = self._look_up(self._index[id], settings)
        return [self.records[i].id for i in found.similar] if found else []

    def _pool(self, q: int) -> np.ndarray:
        r = self.records[q]
        pool = (
            (self._steps < r.step) & (self._known <= r.step) & (self._kinds == r.kind)
        )
        if r.kind == POSITION_REVIEW:
            pool &= self._directions == self._directions[q]
        return np.flatnonzero(pool)

    def _weighted(self, settings: SearchSettings) -> np.ndarray:
        """Every feature vector multiplied by the weights these values give, kept per values."""
        key = feature_weights(settings)
        if key not in self._weighted_by:
            self._weighted_by[key] = self._features * np.array(key)
        return self._weighted_by[key]

    def _look_up(self, q: int, settings: SearchSettings) -> _Found | None:
        pool = self._pool(q)
        if len(pool) < settings.results:
            return None
        records, ids, top = self.records, self._ids[pool], settings.each_ranking_top
        # Worked out over the whole memory, then cut to the pool: cheaper than copying the pool.
        features = self._weighted(settings)
        distance = np.linalg.norm(features - features[q], axis=1)[pool]
        by_vector = pool[_top(distance, ids, top)]
        if (q, top) not in self._by_text:
            closeness = (self._embeddings @ self._embeddings[q])[pool]
            self._by_text[(q, top)] = pool[_top(-closeness, ids, top)]
        by_text = self._by_text[(q, top)]
        merged = merge(
            [records[i].id for i in by_vector], [records[i].id for i in by_text]
        )
        kept = best_without_repeats(
            [_candidate(records[self._index[m.id]]) for m in merged], settings.results
        )
        nearest = best_without_repeats(
            [_candidate(records[i]) for i in by_vector], settings.results
        )
        if len(nearest) < settings.results < len(pool):
            # Repeats removed left too few: the vector ranking alone reaches further down.
            whole = pool[_top(distance, ids, len(pool))]
            nearest = best_without_repeats(
                (_candidate(records[i]) for i in whole), settings.results
            )
        return _Found(
            [self._index[c.id] for c in kept],
            [self._index[c.id] for c in nearest],
            pool,
        )


def check(
    memory: Memory | Sequence[Record],
    settings: SearchSettings,
    sample: int | None = None,
) -> Tally:
    """Look each record up in the records before it; `sample` checks only that many, evenly
    spread over the memory."""
    if not isinstance(memory, Memory):
        memory = Memory(memory)
    looked_up: Iterable[int] = range(len(memory))
    if sample is not None and sample < len(memory):
        looked_up = sorted(
            {int(i) for i in np.linspace(0, len(memory) - 1, sample).round()}
        )
    similar, vector, random = [], [], []
    for q in looked_up:
        found = memory._look_up(q, settings)
        if found is None:
            continue
        way = memory.records[q].ended
        similar.append(_alike(found.similar, memory.ended, way))
        vector.append(_alike(found.nearest, memory.ended, way))
        random.append(_alike(found.pool, memory.ended, way))
    return Tally(
        checked=len(similar),
        similar_alike=_mean(similar),
        vector_alike=_mean(vector),
        random_alike=_mean(random),
    )


# How long after the decision its ending is read: the episode's three prices.
AFTER = {
    "1_bar": (OutcomeKind.PRICE_AFTER_1_BAR, "1 bar after the decision"),
    "4_bars": (OutcomeKind.PRICE_AFTER_4_BARS, "4 bars after the decision"),
    "end_of_day": (OutcomeKind.PRICE_AT_END_OF_DAY, "at the end of the decision's day"),
}

_EPISODES = ", ".join(f"'{k}'" for k in EPISODE_KINDS)
# The sim's complete episodes with their ending, on each engine. Placeholders: the ending's
# outcome kind, then the sim.
_MEMORY = {
    "snowflake": (
        "SELECT D.ID, D.ASSET, D.STEP, D.KIND, D.STANDING:direction::VARCHAR AS DIRECTION, "
        "GREATEST(D.OUTCOMES_KNOWN_FROM, O.KNOWN_FROM) AS KNOWN_FROM, "
        "S.FEATURE_VECTOR::ARRAY AS FEATURES, S.EMBEDDING::ARRAY AS EMBEDDING, "
        "O.VALUE:change::FLOAT AS CHANGE "
        "FROM MEMORY.DECISIONS D "
        "JOIN FEATURES.SNAPSHOTS S ON S.DATASET = D.DATASET AND S.ASSET = D.ASSET "
        "AND S.STEP = D.STEP "
        "JOIN MEMORY.OUTCOMES O ON O.SIM = D.SIM AND O.DECISION = D.ID AND O.KIND = ? "
        f"WHERE D.SIM = ? AND D.KIND IN ({_EPISODES}) "
        "AND D.OUTCOMES_KNOWN_FROM IS NOT NULL ORDER BY D.STEP, D.ID"
    ),
    "postgres": (
        "SELECT d.id, d.asset, d.step, d.kind, d.standing->>'direction' AS direction, "
        "GREATEST(d.outcomes_known_from, o.known_from) AS known_from, "
        "s.feature_vector::real[] AS features, s.embedding::real[] AS embedding, "
        "(o.value->>'change')::float8 AS change "
        "FROM memory.decisions d "
        "JOIN features.snapshots s ON s.dataset = d.dataset AND s.asset = d.asset "
        "AND s.step = d.step "
        "JOIN memory.outcomes o ON o.sim = d.sim AND o.decision = d.id AND o.kind = %s "
        f"WHERE d.sim = %s AND d.kind IN ({_EPISODES}) "
        "AND d.outcomes_known_from IS NOT NULL ORDER BY d.step, d.id"
    ),
}
_SETTINGS = {
    "snowflake": "SELECT SETTINGS FROM SIM.SIMS WHERE ID = ?",
    "postgres": "SELECT settings FROM sim.sims WHERE id = %s",
}


def load_memory(
    connection, sim: int, after: str, engine: str = "snowflake"
) -> tuple[dict, list[Record]]:
    """The sim's settings and its memory's complete episodes, each with how it ended `after`
    (a key of `AFTER`). Read in one query, on `engine` (`snowflake`, whose connection uses `?`
    placeholders, or `postgres`)."""
    with connection.cursor() as cur:
        cur.execute(_SETTINGS[engine], [sim])
        found = cur.fetchone()
        if found is None:
            raise UnknownSim(sim)
        settings = json.loads(found[0]) if isinstance(found[0], str) else found[0]
        cur.execute(_MEMORY[engine], [str(AFTER[after][0]), sim])
        names = [d[0].upper() for d in cur.description]
        rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def listed(value) -> list[float]:
        return json.loads(value) if isinstance(value, str) else list(value)

    return settings or {}, [
        Record(
            id=r["ID"],
            asset=r["ASSET"],
            step=int(r["STEP"]),
            kind=r["KIND"],
            direction=r["DIRECTION"],
            known_from=int(r["KNOWN_FROM"]),
            features=listed(r["FEATURES"]),
            embedding=listed(r["EMBEDDING"]),
            ended=ended_as(r["CHANGE"]),
        )
        for r in rows
    ]


def _share(x: float) -> str:
    return f"{round(x * 100, 4):g}%"


def _percent(x: float) -> str:
    return f"{x * 100:.1f}%"


def report(
    sim: int,
    records: Sequence[Record],
    tried: Sequence[SearchSettings],
    after: str,
    sample: int | None = None,
) -> str:
    """The check for each set of values tried, in plain words (ASCII only)."""
    memory = Memory(records)
    lines: list[str] = []
    tallies = []
    for i, settings in enumerate(tried):
        tally = check(memory, settings, sample)
        tallies.append((tally, settings))
        if i == 0:
            lines += [
                (
                    f"The free check of the search values, on sim {sim}'s memory: "
                    f"{tally.checked} of {len(records)} records checked (a record needs "
                    f"at least {settings.results} records before it to look up)."
                ),
                (
                    'Two records "ended the same way" when the price went the same way '
                    f"(up, down or flat) {AFTER[after][1]}."
                ),
            ]
        lines += [
            "",
            (
                f"With shapes {_share(settings.shape_share)} of the say, each older bar "
                f"{_share(settings.bar_decay)} less:"
            ),
        ]
        if not tally.checked:
            lines.append("  No record had enough records before it to check.")
            continue
        lines += [
            (
                f"  The {settings.results} records the search called most similar ended "
                f"the same way {_percent(tally.similar_alike)} of the time."
            ),
            (
                "  Ranked by the feature vector alone (the part these values change): "
                f"{_percent(tally.vector_alike)}."
            ),
            f"  Records picked at random: {_percent(tally.random_alike)}.",
        ]
        gap = (tally.similar_alike - tally.random_alike) * 100
        if gap > 0:
            lines.append(
                "  So similar records ended the same way more often than random ones, "
                f"by {gap:.1f} percentage points ({_percent(tally.similar_alike)} against "
                f"{_percent(tally.random_alike)})."
            )
        else:
            lines.append(
                "  So similar records did not end the same way more often than random "
                "ones. Try other values: --shape-share and --bar-decay each take several."
            )
    checked = [(t, s) for t, s in tallies if t.checked]
    if len(checked) > 1:
        best, settings = max(checked, key=lambda found: found[0].similar_alike)
        lines += [
            "",
            (
                f"Best of the values tried: shapes {_share(settings.shape_share)} of the "
                f"say, each older bar {_share(settings.bar_decay)} less "
                f"({_percent(best.similar_alike)} ended the same way)."
            ),
        ]
    return "\n".join(lines)


def _alike(positions: Iterable[int], ended: np.ndarray, way: str) -> float:
    return float(np.mean(ended[list(positions)] == way))


def _mean(shares: list[float]) -> float:
    return sum(shares) / len(shares) if shares else math.nan
