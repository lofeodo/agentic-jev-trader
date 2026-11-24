"""The memory server's reads from Snowflake, as the memory login, whose role can only read
(`MEMORY`, `FEATURES`, `REF`, and the sims table for a sim's settings). The connection must use
`?` placeholders. What each read returns, and the rule they all follow, is in `store.py`.

A search is one query: both rankings are worked out in Snowflake, the feature vector's weighted
straight-line distance number by number, the situation texts' by `VECTOR_COSINE_SIMILARITY`.
Nothing is embedded here; the texts were embedded when the dataset was built.
"""

import json
import threading
from collections.abc import Sequence

from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.memory.search import FULL_EVALUATION, Candidate, Query
from jev_trader.memory.store import NoSnapshot, UnknownSim

# The one rule, for the episodes read through `D`: of this sim's memory, decided before now,
# with every outcome known by now. Its three `?` are the sim, the step and the step.
_VISIBLE = (
    "D.SIM = ? AND D.KIND IN ('full_evaluation', 'position_review') "
    "AND D.STEP < ? AND D.OUTCOMES_KNOWN_FROM <= ?"
)
_WITH_SNAPSHOT = (
    "JOIN FEATURES.SNAPSHOTS S ON S.DATASET = D.DATASET AND S.ASSET = D.ASSET "
    "AND S.STEP = D.STEP "
    "JOIN REF.ASSETS A ON A.DATASET = D.DATASET AND A.MASKED_ID = D.ASSET"
)
# A full evaluation that traded: its entry was carried out (one cancelled shows as no trade).
_TRADED = (
    "(D.ACTION = 'entry' AND EXISTS (SELECT 1 FROM MEMORY.OUTCOMES O "
    "WHERE O.SIM = D.SIM AND O.DECISION = D.ID AND O.KIND = 'order_carried_out' "
    "AND O.VALUE:carried_out::BOOLEAN))"
)
_DECISION_COLUMNS = (
    "ID",
    "SIM",
    "DATASET",
    "ASSET",
    "STEP",
    "KIND",
    "ACTION",
    "PICK",
    "CANDIDATE_TRADES",
    "SIZE_AFTER_TRIMMING",
    "REDUCE_SHARE",
    "STANDING",
    "END_OF_SESSION",
    "POSITION",
    "OUTCOMES_KNOWN_FROM",
)
_JSON_COLUMNS = ("CANDIDATE_TRADES", "STANDING", "MEASUREMENTS", "SETTINGS", "VALUE")
_POSITION_COLUMNS = (
    "STEP",
    "ACTION",
    "REDUCE_SHARE",
    "STANDING",
    "SIZE_AFTER_TRIMMING",
    "POSITION",
)


def _marks(values: Sequence) -> str:
    return ", ".join("?" for _ in values)


def _parsed(row: dict) -> dict:
    for column in _JSON_COLUMNS:
        if isinstance(row.get(column), str):
            row[column] = json.loads(row[column])
    return row


class SnowflakeMemoryStore:
    def __init__(self, connection):
        self.con = connection
        # The server answers calls side by side; one connection serves them one at a time.
        self._lock = threading.Lock()

    def _rows(self, sql: str, params: Sequence = ()) -> list[dict]:
        with self._lock, self.con.cursor() as cur:
            cur.execute(sql, list(params))
            names = [d[0] for d in cur.description]
            return [
                _parsed(dict(zip(names, row, strict=True))) for row in cur.fetchall()
            ]

    def sim(self, sim_id):
        found = self._rows(
            "SELECT DATASET, SETTINGS FROM SIM.SIMS WHERE ID = ?", [sim_id]
        )
        if not found:
            raise UnknownSim(sim_id)
        return found[0]

    def snapshot(self, dataset, asset, step):
        found = self._rows(
            "SELECT A.ASSET_CLASS, S.MEASUREMENTS, S.SITUATION_TEXT "
            "FROM FEATURES.SNAPSHOTS S "
            "JOIN REF.ASSETS A ON A.DATASET = S.DATASET AND A.MASKED_ID = S.ASSET "
            "WHERE S.DATASET = ? AND S.ASSET = ? AND S.STEP = ?",
            [dataset, asset, step],
        )
        if not found:
            raise NoSnapshot(f"{asset} has no snapshot at step {step}")
        return found[0]

    @staticmethod
    def _filters(query: Query, current: dict) -> tuple[str, list]:
        """The search's narrowing, as SQL on `D` (the decision) and `A` (its asset)."""
        f = query.filters
        sql, params = [], []
        if f.asset == "same_asset":
            sql.append("D.ASSET = ?")
            params.append(query.asset)
        elif f.asset == "same_asset_class":
            sql.append("A.ASSET_CLASS = ?")
            params.append(current["ASSET_CLASS"])
        if f.pattern != "any":
            sql.append(
                "EXISTS (SELECT 1 FROM FEATURES.PATTERNS P WHERE P.DATASET = D.DATASET "
                "AND P.ASSET = D.ASSET AND P.BAR_SIZE = '15m' "
                f"AND P.STEP BETWEEN D.STEP - {PATTERN_WINDOW_STEPS - 1} AND D.STEP "
                "AND P.PATTERN = ?)"
            )
            params.append(f.pattern)
        if query.job == FULL_EVALUATION:
            if f.decided == "no_trade":
                sql.append(f"NOT ({_TRADED})")
            elif f.decided != "any":
                sql.append(f"{_TRADED} AND SPLIT_PART(D.PICK, '_', 1) = ?")
                params.append(f.decided)
            return " AND ".join(sql), params
        sql.append("D.STANDING:direction::VARCHAR = ?")
        params.append(query.direction)
        if f.decided != "any":
            # An add the limits left nothing of did nothing: it reads "hold".
            sql.append("IFF(D.ACTION = 'nothing', 'hold', D.ACTION) = ?")
            params.append(f.decided)
        if f.standing == "in_profit":
            sql.append("D.STANDING:profit::FLOAT > 0")
        elif f.standing == "at_a_loss":
            sql.append("D.STANDING:profit::FLOAT < 0")
        return " AND ".join(sql), params

    def ranked(self, query, current, weights, top):
        narrowing, narrowing_params = self._filters(query, current)
        rows = self._rows(
            "WITH Q AS (SELECT FEATURE_VECTOR::ARRAY AS FV, EMBEDDING AS E "
            "FROM FEATURES.SNAPSHOTS WHERE DATASET = ? AND ASSET = ? AND STEP = ?), "
            "W AS (SELECT PARSE_JSON(?) AS W), "
            "C AS (SELECT D.ID, D.ASSET, D.STEP, S.FEATURE_VECTOR::ARRAY AS FV, "
            f"S.EMBEDDING AS E FROM MEMORY.DECISIONS D {_WITH_SNAPSHOT} "
            f"WHERE {_VISIBLE} AND D.KIND = ?"
            + (f" AND {narrowing}" if narrowing else "")
            + "), "
            "V AS (SELECT C.ID, SUM(POWER((F.VALUE::FLOAT - GET(Q.FV, F.INDEX)::FLOAT) "
            "* GET(W.W, F.INDEX)::FLOAT, 2)) AS DISTANCE "
            "FROM C, Q, W, LATERAL FLATTEN(INPUT => C.FV) F GROUP BY C.ID) "
            "SELECT 'vector' AS RANKING, C.ID, C.ASSET, C.STEP, "
            "ROW_NUMBER() OVER (ORDER BY V.DISTANCE, C.ID) AS RANK "
            "FROM C JOIN V ON V.ID = C.ID QUALIFY RANK <= ? "
            "UNION ALL "
            "SELECT 'text' AS RANKING, C.ID, C.ASSET, C.STEP, "
            "ROW_NUMBER() OVER (ORDER BY VECTOR_COSINE_SIMILARITY(C.E, Q.E) DESC, C.ID) "
            "AS RANK FROM C, Q QUALIFY RANK <= ?",
            [
                query.dataset,
                query.asset,
                query.step,
                json.dumps(list(weights)),
                query.sim,
                query.step,
                query.step,
                query.job,
                *narrowing_params,
                top,
                top,
            ],
        )
        rankings: dict[str, list[dict]] = {"vector": [], "text": []}
        for row in rows:
            rankings[row["RANKING"]].append(row)
        return tuple(
            [
                Candidate(r["ID"], r["ASSET"], int(r["STEP"]))
                for r in sorted(rankings[name], key=lambda r: r["RANK"])
            ]
            for name in ("vector", "text")
        )

    def decisions(self, sim, step, ids):
        if not ids:
            return []
        columns = ", ".join(f"D.{c}" for c in _DECISION_COLUMNS)
        return self._rows(
            f"SELECT {columns}, A.ASSET_CLASS, S.SITUATION_TEXT, S.MEASUREMENTS "
            f"FROM MEMORY.DECISIONS D {_WITH_SNAPSHOT} "
            f"WHERE {_VISIBLE} AND D.ID IN ({_marks(ids)})",
            [sim, step, step, *ids],
        )

    def outcomes(self, sim, step, decisions):
        if not decisions:
            return []
        return self._rows(
            "SELECT DECISION, KIND, VALUE, KNOWN_FROM FROM MEMORY.OUTCOMES "
            f"WHERE SIM = ? AND KNOWN_FROM <= ? AND DECISION IN ({_marks(decisions)})",
            [sim, step, *decisions],
        )

    def position_rows(self, sim, step, positions):
        if not positions:
            return []
        return self._rows(
            f"SELECT {', '.join(_POSITION_COLUMNS)} FROM MEMORY.DECISIONS "
            "WHERE SIM = ? AND KIND IN ('position_screen', 'position_review') "
            f"AND STEP < ? AND POSITION IN ({_marks(positions)})",
            [sim, step, *positions],
        )

    def closed_trades(self, sim, step, asset_class):
        return self._rows(
            "SELECT D.ID, D.STEP, D.PICK, A.ASSET_CLASS, S.SITUATION_TEXT, S.MEASUREMENTS, "
            "O.VALUE:profit::FLOAT AS PROFIT, O.KNOWN_FROM AS CLOSED_STEP "
            "FROM MEMORY.DECISIONS D "
            "JOIN MEMORY.OUTCOMES O ON O.SIM = D.SIM AND O.DECISION = D.ID "
            f"AND O.KIND = 'position_closed' {_WITH_SNAPSHOT} "
            f"WHERE {_VISIBLE} AND D.KIND = 'full_evaluation' "
            "AND O.KNOWN_FROM <= ? AND A.ASSET_CLASS = ?",
            [sim, step, step, step, asset_class],
        )
