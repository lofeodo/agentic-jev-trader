"""What the API reads (spec appendix 8). `InMemoryApiStore` is the stand-in the unit tests use;
`snowflake_store.SnowflakeApiStore` reads the same things from Snowflake as the API login.
"""

from typing import Protocol

from jev_trader.sim.store import InMemorySimStore


class ApiStore(Protocol):
    def total_spent(self) -> float:
        """Dollars paid for every Jev and LLM call, those made outside a sim included."""

    def sims(self) -> list[dict]:
        """Every sim's row, by column name, the holding sims included."""

    def account_values_at(
        self, wanted: list[tuple[int, int]]
    ) -> dict[tuple[int, int], float]:
        """For each (sim, step): the account value at that step, or at the sim's last stored
        step before it. A pair with no stored step at or before it is left out."""

    def trades_by_sim(self) -> dict[int, int]:
        """How many positions each sim has opened. A sim with none is left out."""

    def spent_by_sim(self) -> dict[int, float]:
        """Dollars paid for each sim's calls. A sim with none is left out."""

    def asset_key(self) -> list[dict]:
        """The asset key's DATASET, MASKED_ID, NAME and FIRST_DAY, one row per asset."""


class InMemoryApiStore:
    """The API's reads over the in-memory sim store, plus a made-up asset key."""

    def __init__(self, sims: InMemorySimStore, asset_key: list[dict]):
        self._sims = sims
        self._asset_key = asset_key

    def total_spent(self) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self._sims.tables["SIM.CALLS"])

    def sims(self) -> list[dict]:
        return [dict(row) for _, row in sorted(self._sims.sims.items())]

    def account_values_at(self, wanted):
        found = {}
        for sim_id, step in wanted:
            stored = [
                r
                for r in self._sims.rows("SIM.ACCOUNT_STEPS", sim_id)
                if r["STEP"] <= step
            ]
            if stored:
                latest = max(stored, key=lambda r: r["STEP"])
                found[(sim_id, step)] = latest["ACCOUNT_VALUE"]
        return found

    def trades_by_sim(self) -> dict[int, int]:
        positions: dict[int, set] = {}
        for row in self._sims.tables["SIM.ORDERS"]:
            if row["KIND"] == "entry" and row["STATUS"] == "carried out":
                positions.setdefault(row["SIM"], set()).add(row["POSITION"])
        return {sim_id: len(found) for sim_id, found in positions.items()}

    def spent_by_sim(self) -> dict[int, float]:
        spent: dict[int, float] = {}
        for row in self._sims.tables["SIM.CALLS"]:
            if row["SIM"] is not None:
                spent[row["SIM"]] = spent.get(row["SIM"], 0.0) + (
                    row["COST_USD"] or 0.0
                )
        return spent

    def asset_key(self) -> list[dict]:
        return [dict(row) for row in self._asset_key]
