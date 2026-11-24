"""The API's reads from Snowflake, as the API login (the only program besides the dataset
builder that can read the asset key). The connection must use `?` placeholders.
"""

import json

from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.dataset.snowflake_store import MOST_BOUND_VALUES
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore

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
        rows = self._run(f"SELECT {', '.join(_SIM_COLUMNS)} FROM SIM.SIMS ORDER BY ID")
        return [dict(zip(_SIM_COLUMNS, row, strict=True)) for row in rows]

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
            "SELECT STEP, ASSET, KIND, TIER, SCREEN_ANSWER, SKIPPED_BECAUSE, ACTION "
            "FROM MEMORY.DECISIONS WHERE SIM = ? ORDER BY STEP DESC, ASSET LIMIT ?",
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
            "WHERE SIM = ? ORDER BY STEP, ASSET",
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

    def dataset(self, dataset_id):
        return SnowflakeMarket(self.con).dataset(dataset_id)

    def create(self, row):
        return SnowflakeSimStore(self.con).create(row)

    def update(self, sim_id, **columns):
        SnowflakeSimStore(self.con).update(sim_id, **columns)
