"""The API's reads from Snowflake, as the API login (the only program besides the dataset
builder that can read the asset key). The connection must use `?` placeholders.
"""

from jev_trader.dataset.snowflake_store import MOST_BOUND_VALUES

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
        columns = ("DATASET", "MASKED_ID", "NAME", "FIRST_DAY")
        rows = self._run(f"SELECT {', '.join(columns)} FROM KEYS.ASSET_KEY")
        return [dict(zip(columns, row, strict=True)) for row in rows]
