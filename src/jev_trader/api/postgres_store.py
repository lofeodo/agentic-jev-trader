"""The API's reads from Postgres, as the API login: the same tables as in Snowflake.

The skeleton of the Postgres slice (spec appendix 11): every method of `store.ApiStore` is here.
Ticket #280 fills in the API's own reads; what the API shares with the dataset builder and the
sim (adding and changing a dataset's or a sim's row, what the checker reads) goes through their
Postgres stores, as in Snowflake, and ticket #278 fills those in. `connection` is the process's
one connection (`jev_trader.storage.postgres.connection`), with `%s` placeholders.
"""

from jev_trader.dataset.postgres_store import PostgresStore as DatasetStore
from jev_trader.sim.market import DatasetInfo
from jev_trader.sim.postgres_store import PostgresMarket, PostgresSimStore
from jev_trader.storage import NotBuiltYet

_UNIT = 280


class PostgresApiStore:
    def __init__(self, connection):
        self.con = connection

    def total_spent(self) -> float:
        raise NotBuiltYet(_UNIT)

    def sims(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def sim(self, sim_id: int) -> dict | None:
        raise NotBuiltYet(_UNIT)

    def account_values_at(
        self, wanted: list[tuple[int, int]]
    ) -> dict[tuple[int, int], float]:
        raise NotBuiltYet(_UNIT)

    def account_steps(
        self, sim_ids: list[int], after_step: int | None = None
    ) -> dict[int, list[dict]]:
        raise NotBuiltYet(_UNIT)

    def account_at(self, sim_id: int, step: int) -> dict | None:
        raise NotBuiltYet(_UNIT)

    def orders(self, sim_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def events(self, sim_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def latest_decisions(self, sim_id: int, limit: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def closes_at(self, dataset: int, step: int) -> dict[str, float]:
        raise NotBuiltYet(_UNIT)

    def trades_by_sim(self) -> dict[int, int]:
        raise NotBuiltYet(_UNIT)

    def spent_by_sim(self) -> dict[int, float]:
        raise NotBuiltYet(_UNIT)

    def spent_on(self, sim_id: int) -> float:
        raise NotBuiltYet(_UNIT)

    def asset_key(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def charges(self, sim_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def decisions(self, sim_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def calls(self, sim_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def decision(self, sim_id: int, decision_id: str) -> dict | None:
        raise NotBuiltYet(_UNIT)

    def position_decisions(self, sim_id: int, position: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def jev_requests(self, sim_id: int, decision_ids: list[str]) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def llm_exchange(self, sim_id: int, decision_id: str) -> dict | None:
        raise NotBuiltYet(_UNIT)

    def closes(
        self, dataset: int, asset: str, first_step: int, last_step: int
    ) -> dict[int, float]:
        raise NotBuiltYet(_UNIT)

    def comparison_figures(self, sim_ids: list[int]) -> dict[int, dict]:
        raise NotBuiltYet(_UNIT)

    def entry_details(
        self, dataset: int, wanted: list[tuple[str, int]]
    ) -> dict[tuple[str, int], dict]:
        raise NotBuiltYet(_UNIT)

    def playbook(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def spending_by_item(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def datasets(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def dataset_rows(self, table: str, dataset_id: int) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def daily_bars(self, dataset_id: int, asset: str) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    # Shared with the dataset builder and the sim, through their stores.

    def begin_dataset(self, name: str, columns: dict) -> tuple[int, int]:
        return DatasetStore(self.con).begin(name, columns)

    def update_dataset(self, dataset_id: int, **columns) -> None:
        DatasetStore(self.con).update(dataset_id, **columns)

    def dataset(self, dataset_id: int) -> DatasetInfo:
        return PostgresMarket(self.con).dataset(dataset_id)

    def create(self, row: dict) -> int:
        return PostgresSimStore(self.con).create(row)

    def update(self, sim_id: int, **columns) -> None:
        PostgresSimStore(self.con).update(sim_id, **columns)

    def spent(self, sim_id: int) -> float:
        return self.spent_on(sim_id)

    def sims_in_progress(self) -> list[dict]:
        return PostgresSimStore(self.con).sims_in_progress()

    def latest_tier_2_share(self) -> float | None:
        return PostgresSimStore(self.con).latest_tier_2_share()

    def base_memory_sim(self, dataset: int) -> int | None:
        return PostgresSimStore(self.con).base_memory_sim(dataset)

    def memory_last_step(self, sim_id: int) -> int | None:
        return PostgresSimStore(self.con).memory_last_step(sim_id)

    def bar_count(self, dataset_id: int, first_step: int, last_step: int) -> int:
        return PostgresMarket(self.con).bar_count(dataset_id, first_step, last_step)
