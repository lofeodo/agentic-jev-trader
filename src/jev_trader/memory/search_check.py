"""The free check of the memory's search values (spec appendix 9, section 7).

Episode search ranks past episodes partly by a feature vector whose weights rest on two values set
by hand: shapes against context (half the say each) and how much less each older bar counts (15%).
The check asks whether those values find records that matter: for each record in a memory, did
the records the search calls most similar end the same way more often than records picked at
random did? It calls no model and costs nothing.

Each record is looked up the way the agent would have looked it up at its own step: among the
memory's earlier records of the same job (a full evaluation finds full evaluations, a position
review finds reviews of positions in the same direction), with no filter. The search is the real
one (`search.py`): both rankings, merged, repeats removed, `results` kept. "Picked at random" is
every record that search could have returned, so its share is the exact average of a random pick,
with no luck in it. Each checked record counts once in both shares.

Choices the spec leaves to the build:

- **Ended the same way** is the price going the same way (up, down, or not at all) over the same
  time after the decision: after 4 bars unless another is chosen. Every episode has the three
  prices, whatever was decided, so every record can be compared with every other.
- A record can be compared only once that price is known too, not just its episode complete (a
  trade closing in 2 bars completes its episode before its 4-bar price is in). So no record is
  compared with one whose ending falls in its own future.
- A record with fewer earlier records than the search returns is not checked: it has nothing to
  pick from.
- The feature vector ranking is also reported alone, since only it depends on the two values.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from jev_trader.memory.outcomes import OutcomeKind
from jev_trader.memory.search import (
    POSITION_REVIEW,
    Candidate,
    SearchSettings,
    best_without_repeats,
    feature_weights,
    merge,
)
from jev_trader.memory.store import UnknownSim


@dataclass(frozen=True)
class Record:
    """One episode of the memory, with how it ended."""

    id: str
    asset: str
    step: int
    kind: str  # full_evaluation or position_review
    direction: str | None  # a review's position: long or short
    known_from: int  # the step from which it and its ending are known
    features: Sequence[float]  # the 58-number feature vector
    embedding: Sequence[float]  # the situation text's embedding
    ended: str  # up, down or flat


def ended_as(change: float) -> str:
    """Which way the price went: a change of 0.002 (0.2%) is up."""
    return "up" if change > 0 else "down" if change < 0 else "flat"


@dataclass(frozen=True)
class Tally:
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


def check(
    records: Sequence[Record], settings: SearchSettings, sample: int | None = None
) -> Tally:
    """Look each record up in the records before it; `sample` checks only that many, evenly
    spread over the memory."""
    weights = np.array(feature_weights(settings))
    features = np.array([r.features for r in records], dtype=float) * weights
    embeddings = np.array([r.embedding for r in records], dtype=float)
    norms = np.linalg.norm(embeddings, axis=1)
    embeddings = embeddings / np.where(norms == 0, 1.0, norms)[:, None]
    ids = np.array([r.id for r in records])
    index = {r.id: i for i, r in enumerate(records)}
    steps = np.array([r.step for r in records])
    known = np.array([r.known_from for r in records])
    kinds = np.array([r.kind for r in records])
    directions = np.array([r.direction or "" for r in records])
    ended = np.array([r.ended for r in records])

    looked_up = range(len(records))
    if sample is not None and sample < len(records):
        looked_up = sorted(
            {int(i) for i in np.linspace(0, len(records) - 1, sample).round()}
        )

    similar, vector, random = [], [], []
    for q in looked_up:
        r = records[q]
        pool = (steps < r.step) & (known <= r.step) & (kinds == r.kind)
        if r.kind == POSITION_REVIEW:
            pool &= directions == directions[q]
        pool_at = np.flatnonzero(pool)
        if len(pool_at) < settings.results:
            continue
        distance = np.linalg.norm(features - features[q], axis=1)[pool_at]
        closeness = (embeddings @ embeddings[q])[pool_at]
        pool_ids = ids[pool_at]
        top = settings.each_ranking_top
        by_vector = pool_at[_top(distance, pool_ids, top)]
        by_text = pool_at[_top(-closeness, pool_ids, top)]
        merged = merge(
            [records[i].id for i in by_vector], [records[i].id for i in by_text]
        )
        kept = best_without_repeats(
            [_candidate(records[index[m.id]]) for m in merged], settings.results
        )
        nearest = best_without_repeats(
            [_candidate(records[i]) for i in by_vector], settings.results
        )
        if len(nearest) < settings.results < len(pool_at):
            # Repeats removed left too few: the vector ranking alone reaches further down.
            whole = pool_at[_top(distance, pool_ids, len(pool_at))]
            nearest = best_without_repeats(
                (_candidate(records[i]) for i in whole), settings.results
            )
        similar.append(_alike([index[c.id] for c in kept], ended, r.ended))
        vector.append(_alike([index[c.id] for c in nearest], ended, r.ended))
        random.append(_alike(pool_at, ended, r.ended))
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

_MEMORY = (
    "SELECT D.ID, D.ASSET, D.STEP, D.KIND, D.STANDING:direction::VARCHAR AS DIRECTION, "
    "GREATEST(D.OUTCOMES_KNOWN_FROM, O.KNOWN_FROM) AS KNOWN_FROM, "
    "S.FEATURE_VECTOR::ARRAY AS FEATURES, S.EMBEDDING::ARRAY AS EMBEDDING, "
    "O.VALUE:change::FLOAT AS CHANGE "
    "FROM MEMORY.DECISIONS D "
    "JOIN FEATURES.SNAPSHOTS S ON S.DATASET = D.DATASET AND S.ASSET = D.ASSET "
    "AND S.STEP = D.STEP "
    "JOIN MEMORY.OUTCOMES O ON O.SIM = D.SIM AND O.DECISION = D.ID AND O.KIND = ? "
    "WHERE D.SIM = ? AND D.KIND IN ('full_evaluation', 'position_review') "
    "AND D.OUTCOMES_KNOWN_FROM IS NOT NULL ORDER BY D.STEP, D.ID"
)


def load_memory(connection, sim: int, after: str) -> tuple[dict, list[Record]]:
    """The sim's settings and its memory's complete episodes, each with how it ended `after`
    (a key of `AFTER`). Read in one query; the connection must use `?` placeholders."""
    with connection.cursor() as cur:
        cur.execute("SELECT SETTINGS FROM SIM.SIMS WHERE ID = ?", [sim])
        found = cur.fetchone()
        if found is None:
            raise UnknownSim(sim)
        settings = json.loads(found[0]) if isinstance(found[0], str) else found[0]
        cur.execute(_MEMORY, [str(AFTER[after][0]), sim])
        names = [d[0] for d in cur.description]
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
    lines = []
    for i, settings in enumerate(tried):
        tally = check(records, settings, sample)
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
                f"by {gap:.1f} percentage points."
            )
        else:
            lines.append(
                "  So similar records did not end the same way more often than random "
                "ones. Try other values: --shape-share and --bar-decay each take several."
            )
    return "\n".join(lines)


def _candidate(r: Record) -> Candidate:
    return Candidate(r.id, r.asset, r.step)


def _alike(positions, ended: np.ndarray, way: str) -> float:
    return float(np.mean(ended[list(positions)] == way))


def _mean(shares: list[float]) -> float:
    return sum(shares) / len(shares) if shares else math.nan
