"""What the API reads (spec appendix 8). `InMemoryApiStore` is the stand-in the unit tests use;
`snowflake_store.SnowflakeApiStore` reads the same things from Snowflake as the API login.
"""

from typing import Protocol

from jev_trader.sim.store import InMemorySimStore


class ApiStore(Protocol):
    def total_spent(self) -> float:
        """Dollars paid for every Jev and LLM call, those made outside a sim included."""

    def sims(self) -> list[dict]:
        """Every sim's row, by column name, the holding sims included (no settings or account)."""

    def sim(self, sim_id: int) -> dict | None:
        """One sim's whole row, its settings and saved account included; None if there is none."""

    def account_values_at(
        self, wanted: list[tuple[int, int]]
    ) -> dict[tuple[int, int], float]:
        """For each (sim, step): the account value at that step, or at the sim's last stored
        step before it. A pair with no stored step at or before it is left out."""

    def account_steps(
        self, sim_ids: list[int], after_step: int | None = None
    ) -> dict[int, list[dict]]:
        """Each sim's `SIM.ACCOUNT_STEPS` rows after `after_step` (all if None), in step order."""

    def account_at(self, sim_id: int, step: int) -> dict | None:
        """The sim's `SIM.ACCOUNT_STEPS` row at `step`, or its last one before it."""

    def orders(self, sim_id: int) -> list[dict]:
        """The sim's `SIM.ORDERS` rows, waiting and cancelled ones included."""

    def events(self, sim_id: int) -> list[dict]:
        """The sim's notable moments (`SIM.SIM_EVENTS`), in step order."""

    def closes_at(self, dataset: int, step: int) -> dict[str, float]:
        """Each asset's latest 15-minute close (rescaled) at or before `step`, by masked ID."""

    def trades_by_sim(self) -> dict[int, int]:
        """How many positions each sim has opened. A sim with none is left out."""

    def spent_by_sim(self) -> dict[int, float]:
        """Dollars paid for each sim's calls. A sim with none is left out."""

    def spent_on(self, sim_id: int) -> float:
        """Dollars paid for one sim's calls."""

    def asset_key(self) -> list[dict]:
        """The asset key's DATASET, MASKED_ID, TICKER, NAME, PRICE_SCALE and FIRST_DAY."""


# Left out of the list of every sim: large, and only the sim page needs them.
_LIST_LEAVES_OUT = ("SETTINGS", "ACCOUNT_STATE")


class InMemoryApiStore:
    """The API's reads over the in-memory sim store, plus a made-up asset key and closes.

    `closes` gives each dataset's rescaled 15-minute closes: dataset, then asset, then step.
    """

    def __init__(
        self,
        sims: InMemorySimStore,
        asset_key: list[dict],
        closes: dict[int, dict[str, dict[int, float]]] | None = None,
    ):
        self._sims = sims
        self._asset_key = asset_key
        self._closes = closes or {}

    def total_spent(self) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self._sims.tables["SIM.CALLS"])

    def sims(self) -> list[dict]:
        return [
            {k: v for k, v in row.items() if k not in _LIST_LEAVES_OUT}
            for _, row in sorted(self._sims.sims.items())
        ]

    def sim(self, sim_id):
        row = self._sims.sims.get(sim_id)
        return None if row is None else dict(row)

    def account_values_at(self, wanted):
        found = {}
        for sim_id, step in wanted:
            row = self.account_at(sim_id, step)
            if row is not None:
                found[(sim_id, step)] = row["ACCOUNT_VALUE"]
        return found

    def account_steps(self, sim_ids, after_step=None):
        return {
            sim_id: sorted(
                (
                    dict(r)
                    for r in self._sims.rows("SIM.ACCOUNT_STEPS", sim_id)
                    if after_step is None or r["STEP"] > after_step
                ),
                key=lambda r: r["STEP"],
            )
            for sim_id in sim_ids
        }

    def account_at(self, sim_id, step):
        stored = [
            r for r in self._sims.rows("SIM.ACCOUNT_STEPS", sim_id) if r["STEP"] <= step
        ]
        return dict(max(stored, key=lambda r: r["STEP"])) if stored else None

    def orders(self, sim_id):
        return [dict(r) for r in self._sims.rows("SIM.ORDERS", sim_id)]

    def events(self, sim_id):
        return sorted(
            (dict(r) for r in self._sims.rows("SIM.SIM_EVENTS", sim_id)),
            key=lambda r: (r["STEP"], r["ID"]),
        )

    def closes_at(self, dataset, step):
        found = {}
        for asset, closes in self._closes.get(dataset, {}).items():
            earlier = [s for s in closes if s <= step]
            if earlier:
                found[asset] = closes[max(earlier)]
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

    def spent_on(self, sim_id):
        return self.spent_by_sim().get(sim_id, 0.0)

    def asset_key(self) -> list[dict]:
        return [dict(row) for row in self._asset_key]
