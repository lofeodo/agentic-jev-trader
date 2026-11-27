"""The memory server's reads from Postgres, as the memory login, whose role can only read
(`memory`, `features`, `ref`, and the sims table for a sim's settings). `connection` is the
process's one connection (`jev_trader.storage.postgres.connection`), with `%s` placeholders.
What each read returns, and the rule they all follow, is in `store.py`.

A search is one statement: both rankings are worked out in Postgres. The feature vector's
weighted straight-line distance is plain SQL, number by number; the situation texts are compared
with `pgvector`'s cosine distance (`<=>`, which is 1 minus the cosine similarity), in place of
Snowflake's `VECTOR_COSINE_SIMILARITY` (spec appendix 11, section 2; ADR 0018). Nothing is
turned into numbers here: the texts got their numbers when the dataset was built. Ties are
broken by the episode's ID in byte order (every text column is `COLLATE "C"`), as Snowflake
sorts, so the order is the same as before (`tests/postgres/test_search_against_snowflake.py`
replays searches Snowflake made). One case follows the in-memory stand-in rather than Snowflake:
a text whose numbers are all 0, which real texts never give.

**Read once per step** (spec appendix 11, section 4). Within one step the agent's lookups ask
for the same things again and again: the sim's row and the asset's snapshot on every lookup, the
same closed trades for each pattern's track record. What a lookup reads at a step cannot change
during that step (a step's own records are written after its decisions), so each answer is kept:

- the sim's row (its dataset and settings, fixed when the sim is made) for as long as the
  store lives;
- a snapshot (a published dataset's, never changed) among the last `_SNAPSHOTS_KEPT` read;
- every other read with its sim and step, until the sim's lookups move to another step.

Answers are handed out as kept; callers only read them.
"""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Sequence

from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.memory.search import FULL_EVALUATION, Candidate, Query
from jev_trader.memory.store import NoSnapshot, UnknownSim

# The one rule, for the episodes read through `d`: of this sim's memory, decided before now,
# with every outcome known by now. Its three `%s` are the sim, the step and the step.
_VISIBLE = (
    "d.sim = %s AND d.kind IN ('full_evaluation', 'position_review') "
    "AND d.step < %s AND d.outcomes_known_from <= %s"
)
_WITH_SNAPSHOT = (
    "JOIN features.snapshots s ON s.dataset = d.dataset AND s.asset = d.asset "
    "AND s.step = d.step "
    "JOIN ref.assets a ON a.dataset = d.dataset AND a.masked_id = d.asset"
)
# A full evaluation that traded: its entry was carried out (one cancelled shows as no trade).
_TRADED = (
    "(d.action = 'entry' AND EXISTS (SELECT 1 FROM memory.outcomes o "
    "WHERE o.sim = d.sim AND o.decision = d.id AND o.kind = 'order_carried_out' "
    "AND (o.value->>'carried_out')::boolean))"
)
_DECISION_COLUMNS = (
    "id",
    "sim",
    "dataset",
    "asset",
    "step",
    "kind",
    "action",
    "pick",
    "candidate_trades",
    "size_after_trimming",
    "reduce_share",
    "standing",
    "end_of_session",
    "position",
    "outcomes_known_from",
)
_POSITION_COLUMNS = (
    "step",
    "action",
    "reduce_share",
    "standing",
    "size_after_trimming",
    "position",
)
# A step's lookups read one snapshot per asset looked at; 256 holds several steps of every asset
# in a dataset, a few hundred kilobytes.
_SNAPSHOTS_KEPT = 256
_MISSING = object()


class PostgresMemoryStore:
    def __init__(self, connection):
        self.con = connection
        self._lock = threading.Lock()  # guards the kept answers below
        self._sims: dict[int, dict] = {}
        self._snapshots: OrderedDict[tuple, dict] = OrderedDict()
        # Per sim: the step its lookups are at, and what they have read at it.
        self._steps: dict[int, tuple[int, dict[Hashable, object]]] = {}

    def _rows(self, sql: str, params: Sequence = ()) -> list[dict]:
        """The rows `sql` reads, each a dict under Snowflake's (upper-case) column names. JSON
        columns come back parsed."""
        with self.con.cursor() as cur:
            cur.execute(sql, list(params))
            names = [d.name.upper() for d in cur.description]
            return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def _once(self, sim: int, step: int, key: Hashable, read: Callable[[], object]):
        """`read()`'s answer, read only the first time `key` is asked at `step`."""
        with self._lock:
            held = self._steps.get(sim)
            if held is None or held[0] != step:
                held = (step, {})
                self._steps[sim] = held
            found = held[1].get(key, _MISSING)
        if found is _MISSING:
            found = read()
            with self._lock:
                held[1][key] = found
        return found

    def sim(self, sim_id: int) -> dict:
        with self._lock:
            found = self._sims.get(sim_id)
        if found is None:
            rows = self._rows(
                "SELECT dataset, settings FROM sim.sims WHERE id = %s", [sim_id]
            )
            if not rows:
                raise UnknownSim(sim_id)
            found = rows[0]
            with self._lock:
                self._sims[sim_id] = found
        return found

    def snapshot(self, dataset: int, asset: str, step: int) -> dict:
        key = (dataset, asset, step)
        with self._lock:
            found = self._snapshots.get(key)
            if found is not None:
                self._snapshots.move_to_end(key)
                return found
        rows = self._rows(
            "SELECT a.asset_class, s.measurements, s.situation_text "
            "FROM features.snapshots s "
            "JOIN ref.assets a ON a.dataset = s.dataset AND a.masked_id = s.asset "
            "WHERE s.dataset = %s AND s.asset = %s AND s.step = %s",
            [dataset, asset, step],
        )
        if not rows:
            raise NoSnapshot(f"{asset} has no snapshot at step {step}")
        with self._lock:
            self._snapshots[key] = rows[0]
            while len(self._snapshots) > _SNAPSHOTS_KEPT:
                self._snapshots.popitem(last=False)
        return rows[0]

    @staticmethod
    def _filters(query: Query, current: dict) -> tuple[str, list]:
        """The search's narrowing, as SQL on `d` (the decision) and `a` (its asset)."""
        f = query.filters
        sql, params = [], []
        if f.asset == "same_asset":
            sql.append("d.asset = %s")
            params.append(query.asset)
        elif f.asset == "same_asset_class":
            sql.append("a.asset_class = %s")
            params.append(current["ASSET_CLASS"])
        if f.pattern != "any":
            sql.append(
                "EXISTS (SELECT 1 FROM features.patterns p WHERE p.dataset = d.dataset "
                "AND p.asset = d.asset AND p.bar_size = '15m' "
                f"AND p.step BETWEEN d.step - {PATTERN_WINDOW_STEPS - 1} AND d.step "
                "AND p.pattern = %s)"
            )
            params.append(f.pattern)
        if query.job == FULL_EVALUATION:
            if f.decided == "no_trade":
                sql.append(f"NOT {_TRADED}")
            elif f.decided != "any":
                sql.append(f"{_TRADED} AND split_part(d.pick, '_', 1) = %s")
                params.append(f.decided)
            return " AND ".join(sql), params
        sql.append("d.standing->>'direction' = %s")
        params.append(query.direction)
        if f.decided != "any":
            # An add the limits left nothing of did nothing: it reads "hold".
            sql.append(
                "(CASE WHEN d.action = 'nothing' THEN 'hold' ELSE d.action END) = %s"
            )
            params.append(f.decided)
        if f.standing == "in_profit":
            sql.append("(d.standing->>'profit')::float8 > 0")
        elif f.standing == "at_a_loss":
            sql.append("(d.standing->>'profit')::float8 < 0")
        return " AND ".join(sql), params

    def ranked(
        self, query: Query, current: dict, weights: Sequence[float], top: int
    ) -> tuple[list[Candidate], list[Candidate]]:
        weights = tuple(weights)
        return self._once(
            query.sim,
            query.step,
            ("ranked", query, weights, top),
            lambda: self._ranked(query, current, weights, top),
        )

    def _ranked(self, query, current, weights, top):
        narrowing, narrowing_params = self._filters(query, current)
        # The text ranking: closest first by cosine distance. A text whose numbers are all 0
        # has no direction; it counts as unrelated (similarity 0, distance 1), as in `store.py`.
        text_distance = "COALESCE(NULLIF(c.e <=> q.e, 'NaN'), 1)"
        rows = self._rows(
            "WITH q AS (SELECT feature_vector::real[] AS fv, embedding AS e "
            "FROM features.snapshots WHERE dataset = %s AND asset = %s AND step = %s), "
            "c AS (SELECT d.id, d.asset, d.step, s.feature_vector::real[] AS fv, "
            f"s.embedding AS e FROM memory.decisions d {_WITH_SNAPSHOT} "
            f"WHERE {_VISIBLE} AND d.kind = %s"
            + (f" AND {narrowing}" if narrowing else "")
            + "), "
            "v AS (SELECT c.id, SUM(POWER((u.x::float8 - u.y::float8) * u.w, 2)) AS distance "
            "FROM c, q, unnest(c.fv, q.fv, %s::float8[]) AS u(x, y, w) GROUP BY c.id), "
            "r AS (SELECT 'vector' AS ranking, c.id, c.asset, c.step, "
            "ROW_NUMBER() OVER (ORDER BY v.distance, c.id) AS rank "
            "FROM c JOIN v ON v.id = c.id "
            "UNION ALL "
            "SELECT 'text' AS ranking, c.id, c.asset, c.step, "
            f"ROW_NUMBER() OVER (ORDER BY {text_distance}, c.id) AS rank FROM c, q) "
            "SELECT ranking, id, asset, step, rank FROM r WHERE rank <= %s",
            [
                query.dataset,
                query.asset,
                query.step,
                query.sim,
                query.step,
                query.step,
                query.job,
                *narrowing_params,
                list(weights),
                top,
            ],
        )
        rankings: dict[str, list[dict]] = {"vector": [], "text": []}
        for row in rows:
            rankings[row["RANKING"]].append(row)
        return tuple(
            [
                Candidate(r["ID"], r["ASSET"], r["STEP"])
                for r in sorted(rankings[name], key=lambda r: r["RANK"])
            ]
            for name in ("vector", "text")
        )

    def decisions(self, sim: int, step: int, ids: Sequence[str]) -> list[dict]:
        if not ids:
            return []
        columns = ", ".join(f"d.{c}" for c in _DECISION_COLUMNS)
        return self._once(
            sim,
            step,
            ("decisions", tuple(ids)),
            lambda: self._rows(
                f"SELECT {columns}, a.asset_class, s.situation_text, s.measurements "
                f"FROM memory.decisions d {_WITH_SNAPSHOT} "
                f"WHERE {_VISIBLE} AND d.id = ANY(%s)",
                [sim, step, step, list(ids)],
            ),
        )

    def outcomes(self, sim: int, step: int, decisions: Sequence[str]) -> list[dict]:
        if not decisions:
            return []
        return self._once(
            sim,
            step,
            ("outcomes", tuple(decisions)),
            lambda: self._rows(
                "SELECT decision, kind, value, known_from FROM memory.outcomes "
                "WHERE sim = %s AND known_from <= %s AND decision = ANY(%s)",
                [sim, step, list(decisions)],
            ),
        )

    def position_rows(
        self, sim: int, step: int, positions: Sequence[int]
    ) -> list[dict]:
        if not positions:
            return []
        return self._once(
            sim,
            step,
            ("positions", tuple(positions)),
            lambda: self._rows(
                f"SELECT {', '.join(_POSITION_COLUMNS)} FROM memory.decisions "
                "WHERE sim = %s AND kind IN ('position_screen', 'position_review') "
                "AND step < %s AND position = ANY(%s)",
                [sim, step, list(positions)],
            ),
        )

    def closed_trades(self, sim: int, step: int, asset_class: str) -> list[dict]:
        return self._once(
            sim,
            step,
            ("closed trades", asset_class),
            lambda: self._rows(
                "SELECT d.id, d.step, d.pick, a.asset_class, s.situation_text, "
                "s.measurements, (o.value->>'profit')::float8 AS profit, "
                "o.known_from AS closed_step "
                "FROM memory.decisions d "
                "JOIN memory.outcomes o ON o.sim = d.sim AND o.decision = d.id "
                f"AND o.kind = 'position_closed' {_WITH_SNAPSHOT} "
                f"WHERE {_VISIBLE} AND d.kind = 'full_evaluation' "
                "AND o.known_from <= %s AND a.asset_class = %s",
                [sim, step, step, step, asset_class],
            ),
        )
