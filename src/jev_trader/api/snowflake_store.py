"""The API's reads from Snowflake, as the API login (the only program besides the dataset
builder that can read the asset key). The connection must use `?` placeholders.
"""

import json

from jev_trader.api.llm_names import llm_model_of
from jev_trader.api.store import DATASET_COLUMNS, DATASET_READS, JEV_SERVICE
from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.dataset.snowflake_store import MOST_BOUND_VALUES
from jev_trader.dataset.snowflake_store import SnowflakeStore as DatasetStore
from jev_trader.sim.snowflake_store import OWN_ROWS, SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.store import KIND_FULL_EVALUATION, KIND_POSITION_REVIEW

_LONG_TERM_TREND = MEASUREMENT_NAMES.index("long_term_trend")
_VOLUME_AGAINST_NORMAL = MEASUREMENT_NAMES.index("volume_against_normal")

# Every column of a decision but its candidate trades, which no report needs.
_DECISION_COLUMNS = (
    "ID",
    "STEP",
    "ASSET",
    "KIND",
    "TIER",
    "SCREEN_ANSWER",
    "SKIPPED_BECAUSE",
    "ACTION",
    "PICK",
    "RATING",
    "SIZE_CHOSEN",
    "SIZE_AFTER_TRIMMING",
    "LIMITED_BY",
    "ANSWERS",
)

_ACCOUNT_COLUMNS = (
    "SIM",
    "STEP",
    "CASH",
    "LOAN",
    "EXPOSURE",
    "ACCOUNT_VALUE",
    "START_OF_DAY_VALUE",
    "DAILY_LOSS_REACHED",
)

_SIM_COLUMNS = (
    "ID",
    "DATASET",
    "KIND",
    "VARIANT",
    "REPEAT_NUMBER",
    "MARKET",
    "FIRST_STEP",
    "LAST_STEP",
    "STARTING_VALUE",
    "SPENDING_CAP",
    "STATUS",
    "STOP_REASON",
    "LAST_COMPLETED_STEP",
    "STARTED_AT",
    "LAST_WRITTEN_AT",
)


# A decision's columns stored as JSON (VARIANT), which the connector hands over as text.
_DECISION_JSON = (
    "CANDIDATE_TRADES",
    "ANSWERS",
    "STANDING",
    "SELECTED",
    "EPISODES_SHOWN",
    "LOOKUPS",
)


def _read_json(row: dict, columns: tuple[str, ...]) -> dict:
    """The row with each of `columns` it holds read from JSON text."""
    for name in columns:
        if isinstance(row.get(name), str):
            row[name] = json.loads(row[name])
    return row


def _array(value) -> list[str]:
    """A Snowflake array as a sorted list, NULLs dropped (the connector hands it over as
    JSON)."""
    items = json.loads(value) if isinstance(value, str) else (value or [])
    return sorted(item for item in items if item is not None)


class SnowflakeApiStore:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()) -> list[tuple]:
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def total_spent(self) -> float:
        [(spent,)] = self._run("SELECT COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS")
        return float(spent)

    def sims(self) -> list[dict]:
        rows = self._run(
            f"SELECT {', '.join(_SIM_COLUMNS)}, SETTINGS:llm:model::STRING "
            "FROM SIM.SIMS ORDER BY ID"
        )
        found = []
        for *columns, model in rows:
            row = dict(zip(_SIM_COLUMNS, columns, strict=True))
            row["LLM_MODEL"] = llm_model_of({"llm": {"model": model}})
            found.append(row)
        return found

    def account_values_at(self, wanted):
        found = {}
        pairs = sorted(set(wanted))
        batch = MOST_BOUND_VALUES // 2
        for i in range(0, len(pairs), batch):
            part = pairs[i : i + batch]
            marks = ", ".join("(?, ?)" for _ in part)
            rows = self._run(
                "SELECT W.COLUMN1, W.COLUMN2, A.ACCOUNT_VALUE "
                f"FROM (VALUES {marks}) AS W "
                "JOIN SIM.ACCOUNT_STEPS A ON A.SIM = W.COLUMN1 AND A.STEP <= W.COLUMN2 "
                "QUALIFY ROW_NUMBER() OVER "
                "(PARTITION BY W.COLUMN1, W.COLUMN2 ORDER BY A.STEP DESC) = 1",
                [value for pair in part for value in pair],
            )
            for sim_id, step, value in rows:
                found[(int(sim_id), int(step))] = value
        return found

    def _rows(self, sql: str, params=()) -> list[dict]:
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def sim(self, sim_id):
        try:
            return SnowflakeSimStore(self.con).sim(sim_id)
        except KeyError:
            return None

    def account_steps(self, sim_ids, after_step=None):
        found: dict[int, list[dict]] = {sim_id: [] for sim_id in sim_ids}
        if not sim_ids:
            return found
        marks = ", ".join("?" for _ in sim_ids)
        rows = self._rows(
            f"SELECT {', '.join(_ACCOUNT_COLUMNS)} FROM SIM.ACCOUNT_STEPS "
            f"WHERE SIM IN ({marks}) AND STEP > ? ORDER BY SIM, STEP",
            [*sim_ids, -1 if after_step is None else after_step],
        )
        for row in rows:
            found[int(row["SIM"])].append(row)
        return found

    def account_at(self, sim_id, step):
        rows = self._rows(
            f"SELECT {', '.join(_ACCOUNT_COLUMNS)} FROM SIM.ACCOUNT_STEPS "
            "WHERE SIM = ? AND STEP <= ? ORDER BY STEP DESC LIMIT 1",
            (sim_id, step),
        )
        return rows[0] if rows else None

    def orders(self, sim_id):
        return self._rows("SELECT * FROM SIM.ORDERS WHERE SIM = ?", (sim_id,))

    def events(self, sim_id):
        rows = self._rows(
            "SELECT ID, SIM, STEP, KIND, DETAILS FROM SIM.SIM_EVENTS "
            "WHERE SIM = ? ORDER BY STEP, ID",
            (sim_id,),
        )
        for row in rows:
            if isinstance(row["DETAILS"], str):
                row["DETAILS"] = json.loads(row["DETAILS"])
        return rows

    def latest_decisions(self, sim_id, limit):
        return self._rows(
            "SELECT ID, STEP, ASSET, KIND, TIER, SCREEN_ANSWER, SKIPPED_BECAUSE, ACTION "
            f"FROM MEMORY.DECISIONS WHERE {OWN_ROWS} "
            "ORDER BY STEP DESC, ASSET LIMIT ?",
            (sim_id, limit),
        )

    def closes_at(self, dataset, step):
        rows = self._run(
            "SELECT ASSET, CLOSE FROM RAW.BARS "
            "WHERE DATASET = ? AND BAR_SIZE = '15m' AND STEP <= ? "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY ASSET ORDER BY STEP DESC) = 1",
            (dataset, step),
        )
        return {asset: float(close) for asset, close in rows}

    def spent_on(self, sim_id):
        [(spent,)] = self._run(
            "SELECT COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS WHERE SIM = ?", (sim_id,)
        )
        return float(spent)

    def trades_by_sim(self) -> dict[int, int]:
        rows = self._run(
            "SELECT SIM, COUNT(DISTINCT POSITION) FROM SIM.ORDERS "
            "WHERE KIND = 'entry' AND STATUS = 'carried out' GROUP BY SIM"
        )
        return {int(sim_id): int(count) for sim_id, count in rows}

    def spent_by_sim(self) -> dict[int, float]:
        rows = self._run(
            "SELECT SIM, COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS "
            "WHERE SIM IS NOT NULL GROUP BY SIM"
        )
        return {int(sim_id): float(spent) for sim_id, spent in rows}

    def asset_key(self) -> list[dict]:
        columns = ("DATASET", "MASKED_ID", "TICKER", "NAME", "PRICE_SCALE", "FIRST_DAY")
        rows = self._run(f"SELECT {', '.join(columns)} FROM KEYS.ASSET_KEY")
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def charges(self, sim_id):
        return self._rows(
            "SELECT * FROM SIM.CHARGES WHERE SIM = ? ORDER BY STEP, ID", (sim_id,)
        )

    def decisions(self, sim_id):
        rows = self._rows(
            f"SELECT {', '.join(_DECISION_COLUMNS)} FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} ORDER BY STEP, ASSET",
            (sim_id,),
        )
        for row in rows:
            if isinstance(row["ANSWERS"], str):
                row["ANSWERS"] = json.loads(row["ANSWERS"])
        return rows

    def calls(self, sim_id):
        return self._rows(
            "SELECT DECISION, PURPOSE, COST_USD, LATENCY_SECONDS FROM SIM.CALLS "
            "WHERE SIM = ?",
            (sim_id,),
        )

    def decision(self, sim_id, decision_id):
        rows = self._rows(
            f"SELECT * FROM MEMORY.DECISIONS WHERE {OWN_ROWS} AND ID = ?",
            (sim_id, decision_id),
        )
        return _read_json(rows[0], _DECISION_JSON) if rows else None

    def position_decisions(self, sim_id, position):
        rows = self._rows(
            f"SELECT * EXCLUDE (CANDIDATE_TRADES) FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} AND POSITION = ? ORDER BY STEP",
            (sim_id, position),
        )
        return [_read_json(row, _DECISION_JSON) for row in rows]

    def jev_requests(self, sim_id, decision_ids):
        if not decision_ids:
            return []
        marks = ", ".join("?" for _ in decision_ids)
        rows = self._rows(
            "SELECT R.*, J.OPENING FROM SIM.JEV_REQUESTS R "
            "LEFT JOIN SIM.JEV_READINGS J ON J.READING_VERSION = R.READING_VERSION "
            f"WHERE R.SIM = ? AND R.DECISION IN ({marks}) ORDER BY R.ID",
            [sim_id, *decision_ids],
        )
        return [_read_json(row, ("QUESTIONS",)) for row in rows]

    def llm_exchange(self, sim_id, decision_id):
        rows = self._rows(
            "SELECT E.*, P.SYSTEM_PROMPT AS SYSTEM_PROMPTS, P.TOOLS "
            "FROM SIM.LLM_EXCHANGES E "
            "LEFT JOIN SIM.LLM_PROMPTS P ON P.PROMPT_VERSION = E.PROMPT_VERSION "
            "WHERE E.SIM = ? AND E.DECISION = ?",
            (sim_id, decision_id),
        )
        if not rows:
            return None
        row = _read_json(
            rows[0], ("MESSAGES", "FAILED_REPLIES", "SLIPS", "SYSTEM_PROMPTS", "TOOLS")
        )
        row["SYSTEM_PROMPTS"] = row["SYSTEM_PROMPTS"] or {}
        row["TOOLS"] = row["TOOLS"] or {}
        return row

    def closes(self, dataset, asset, first_step, last_step):
        rows = self._run(
            "SELECT STEP, CLOSE FROM RAW.BARS WHERE DATASET = ? AND ASSET = ? "
            "AND BAR_SIZE = '15m' AND STEP BETWEEN ? AND ? ORDER BY STEP",
            (dataset, asset, first_step, last_step),
        )
        return {int(step): float(close) for step, close in rows}

    def comparison_figures(self, sim_ids):
        found = {
            sim_id: {
                "FULL_EVALUATIONS": 0,
                "POSITION_REVIEWS": 0,
                "MODEL_USD": 0.0,
                "FULL_EVALUATION_SECONDS": 0.0,
                "LLM_MODELS": [],
                "JEV_VERSIONS": [],
            }
            for sim_id in sim_ids
        }
        if not sim_ids:
            return found
        marks = ", ".join("?" for _ in sim_ids)
        # A sim's own decisions: rows copied in with its memory were written by another sim.
        for sim_id, evaluations, reviews, versions in self._run(
            "SELECT SIM, COUNT_IF(KIND = ?), COUNT_IF(KIND = ?), "
            "ARRAY_AGG(DISTINCT JEV_VERSION) "
            f"FROM MEMORY.DECISIONS WHERE SIM IN ({marks}) AND FIRST_WRITTEN_BY = SIM "
            "GROUP BY SIM",
            [KIND_FULL_EVALUATION, KIND_POSITION_REVIEW, *sim_ids],
        ):
            figures = found[int(sim_id)]
            figures["FULL_EVALUATIONS"] = int(evaluations)
            figures["POSITION_REVIEWS"] = int(reviews)
            figures["JEV_VERSIONS"] = _array(versions)
        for sim_id, model_usd, seconds, models in self._run(
            "SELECT C.SIM, COALESCE(SUM(C.COST_USD), 0), "
            "COALESCE(SUM(IFF(D.KIND = ?, COALESCE(C.LATENCY_SECONDS, 0), 0)), 0), "
            "ARRAY_AGG(DISTINCT IFF(C.SERVICE <> ?, C.MODEL, NULL)) "
            "FROM SIM.CALLS C LEFT JOIN MEMORY.DECISIONS D "
            "ON D.SIM = C.SIM AND D.ID = C.DECISION AND D.FIRST_WRITTEN_BY = C.SIM "
            f"WHERE C.SIM IN ({marks}) GROUP BY C.SIM",
            [KIND_FULL_EVALUATION, JEV_SERVICE, *sim_ids],
        ):
            figures = found[int(sim_id)]
            figures["MODEL_USD"] = float(model_usd)
            figures["FULL_EVALUATION_SECONDS"] = float(seconds)
            figures["LLM_MODELS"] = _array(models)
        return found

    def entry_details(self, dataset, wanted):
        found: dict[tuple[str, int], dict] = {}
        pairs = sorted(set(wanted))
        batch = MOST_BOUND_VALUES // 2 - 1
        for i in range(0, len(pairs), batch):
            part = pairs[i : i + batch]
            marks = ", ".join("(?, ?)" for _ in part)
            values = [value for pair in part for value in pair]
            for asset, step, asset_class, trend, volume, bar, left in self._run(
                "SELECT W.COLUMN1, W.COLUMN2, A.ASSET_CLASS, "
                f"S.MEASUREMENTS[{_LONG_TERM_TREND}]::FLOAT, "
                f"S.MEASUREMENTS[{_VOLUME_AGAINST_NORMAL}]::FLOAT, "
                "B.BAR_NUMBER, B.BARS_LEFT "
                f"FROM (VALUES {marks}) AS W "
                "JOIN FEATURES.SNAPSHOTS S ON S.DATASET = ? AND S.ASSET = W.COLUMN1 "
                "AND S.STEP = W.COLUMN2 "
                "JOIN RAW.BARS B ON B.DATASET = S.DATASET AND B.ASSET = S.ASSET "
                "AND B.STEP = S.STEP AND B.BAR_SIZE = '15m' "
                "JOIN REF.ASSETS A ON A.DATASET = S.DATASET AND A.MASKED_ID = S.ASSET",
                [*values, dataset],
            ):
                found[(asset, int(step))] = {
                    "ASSET_CLASS": asset_class,
                    "PATTERNS": [],
                    "LONG_TERM_TREND": trend,
                    "VOLUME_AGAINST_NORMAL": volume,
                    "BAR_NUMBER": int(bar),
                    "BARS_LEFT": None if left is None else int(left),
                }
            # Newest bar first, as the situation text lists them.
            for asset, step, pattern in self._run(
                "SELECT W.COLUMN1, W.COLUMN2, P.PATTERN "
                f"FROM (VALUES {marks}) AS W "
                "JOIN FEATURES.PATTERNS P ON P.DATASET = ? AND P.ASSET = W.COLUMN1 "
                "AND P.BAR_SIZE = '15m' "
                f"AND P.STEP BETWEEN W.COLUMN2 - {PATTERN_WINDOW_STEPS - 1} "
                "AND W.COLUMN2 "
                "ORDER BY W.COLUMN1, W.COLUMN2, P.STEP DESC, P.PATTERN",
                [*values, dataset],
            ):
                names = found.get((asset, int(step)), {}).get("PATTERNS")
                if names is not None and pattern not in names:
                    names.append(pattern)
        return found

    def spending_by_item(self) -> list[dict]:
        rows = self._rows(
            "SELECT SIM, IFF(SIM IS NULL, PURPOSE, NULL) AS PURPOSE, SERVICE, "
            "COALESCE(SUM(COST_USD), 0) AS COST_USD, COUNT(*) AS CALLS "
            "FROM SIM.CALLS GROUP BY 1, 2, 3"
        )
        return [
            {
                "SIM": None if r["SIM"] is None else int(r["SIM"]),
                "PURPOSE": r["PURPOSE"],
                "SERVICE": r["SERVICE"],
                "COST_USD": float(r["COST_USD"]),
                "CALLS": int(r["CALLS"]),
            }
            for r in rows
        ]

    def playbook(self) -> list[dict]:
        return self._rows(
            "SELECT TALIB_VERSION, PATTERN, LEAN, NAME, SHAPE FROM REF.PLAYBOOK"
        )

    def datasets(self) -> list[dict]:
        rows = self._rows(
            f"SELECT {', '.join(DATASET_COLUMNS)} FROM REF.DATASETS ORDER BY ID DESC"
        )
        for row in rows:
            if isinstance(row["CHECK_RESULT"], str):
                row["CHECK_RESULT"] = json.loads(row["CHECK_RESULT"])
        return rows

    def dataset_rows(self, table, dataset_id):
        if table not in DATASET_READS:
            raise ValueError(f"the API does not read {table} whole")
        return self._rows(f"SELECT * FROM {table} WHERE DATASET = ?", (dataset_id,))

    def daily_bars(self, dataset_id, asset):
        return self._rows(
            "SELECT STEP, DAY, CLOSE FROM RAW.BARS "
            "WHERE DATASET = ? AND ASSET = ? AND BAR_SIZE = '1d' ORDER BY STEP",
            (dataset_id, asset),
        )

    def begin_dataset(self, name, columns):
        return DatasetStore(self.con).begin(name, columns)

    def update_dataset(self, dataset_id, **columns):
        DatasetStore(self.con).update(dataset_id, **columns)

    def dataset(self, dataset_id):
        return SnowflakeMarket(self.con).dataset(dataset_id)

    def create(self, row):
        return SnowflakeSimStore(self.con).create(row)

    def update(self, sim_id, **columns):
        SnowflakeSimStore(self.con).update(sim_id, **columns)

    def spent(self, sim_id):
        return self.spent_on(sim_id)

    def sims_in_progress(self):
        return SnowflakeSimStore(self.con).sims_in_progress()

    def latest_tier_2_share(self):
        return SnowflakeSimStore(self.con).latest_tier_2_share()

    def base_memory_sim(self, dataset):
        return SnowflakeSimStore(self.con).base_memory_sim(dataset)

    def memory_last_step(self, sim_id):
        return SnowflakeSimStore(self.con).memory_last_step(sim_id)

    def bar_count(self, dataset_id, first_step, last_step):
        return SnowflakeMarket(self.con).bar_count(dataset_id, first_step, last_step)
