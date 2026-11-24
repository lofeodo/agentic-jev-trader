"""The API's reads from Snowflake, as the API login (the only program besides the dataset
builder that can read the asset key). The connection must use `?` placeholders.
"""

import json

from jev_trader.dataset.snowflake_store import MOST_BOUND_VALUES
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore

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

    def dataset(self, dataset_id):
        return SnowflakeMarket(self.con).dataset(dataset_id)

    def create(self, row):
        return SnowflakeSimStore(self.con).create(row)

    def update(self, sim_id, **columns):
        SnowflakeSimStore(self.con).update(sim_id, **columns)
