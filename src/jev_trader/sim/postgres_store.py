"""The sim's store and market in Postgres, as the sim login: the same tables as in Snowflake.

The skeleton of the Postgres slice (spec appendix 11): every method of `store.SimStore` and
`market.Market` is here, and ticket #278 fills each in. `connection` is the process's one
connection (`jev_trader.storage.postgres.connection`), with `%s` placeholders; the store and
the market share it. A save (`write_steps`) is one transaction sent in one round trip, with
psycopg's pipeline mode (spec appendix 11, section 4).
"""

from jev_trader.sim.market import BarsByStep, DatasetInfo, Playbook, SnapshotsByStep
from jev_trader.storage import NotBuiltYet

_UNIT = 278


class _Connection:
    def __init__(self, connection):
        self.con = connection


class PostgresSimStore(_Connection):
    def create(self, row: dict) -> int:
        raise NotBuiltYet(_UNIT)

    def sim(self, sim_id: int) -> dict:
        raise NotBuiltYet(_UNIT)

    def update(self, sim_id: int, **columns) -> None:
        raise NotBuiltYet(_UNIT)

    def write_steps(
        self,
        sim_id: int,
        after_step: int | None,
        through_step: int,
        rows: dict[str, list[dict]],
        state: dict,
        outcomes_known: dict[str, int] | None = None,
    ) -> None:
        raise NotBuiltYet(_UNIT)

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        raise NotBuiltYet(_UNIT)

    def base_memory_sim(self, dataset: int) -> int | None:
        raise NotBuiltYet(_UNIT)

    def memory_last_step(self, sim_id: int) -> int | None:
        raise NotBuiltYet(_UNIT)

    def start_with_memory(self, sim_id: int, memory_from: int, **columns) -> None:
        raise NotBuiltYet(_UNIT)

    def save_reading(self, version: str, opening: str) -> None:
        raise NotBuiltYet(_UNIT)

    def save_prompt(
        self,
        version: str,
        system_prompts: dict[str, str],
        tools: dict[str, list[dict]],
    ) -> None:
        raise NotBuiltYet(_UNIT)

    def spent(self, sim_id: int) -> float:
        raise NotBuiltYet(_UNIT)

    def total_spent(self) -> float:
        raise NotBuiltYet(_UNIT)

    def sims_in_progress(self) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def latest_tier_2_share(self) -> float | None:
        raise NotBuiltYet(_UNIT)

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        raise NotBuiltYet(_UNIT)

    def full_evaluation_counts(self, sim_id: int) -> tuple[int, int]:
        raise NotBuiltYet(_UNIT)

    def position_screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        raise NotBuiltYet(_UNIT)

    def position_review_counts(self, sim_id: int) -> dict[str, int]:
        raise NotBuiltYet(_UNIT)


class PostgresMarket(_Connection):
    def dataset(self, dataset_id: int) -> DatasetInfo:
        raise NotBuiltYet(_UNIT)

    def bars(self, dataset_id: int, first_step: int, last_step: int) -> BarsByStep:
        raise NotBuiltYet(_UNIT)

    def bar_count(self, dataset_id: int, first_step: int, last_step: int) -> int:
        raise NotBuiltYet(_UNIT)

    def snapshots(
        self, dataset_id: int, first_step: int, last_step: int
    ) -> SnapshotsByStep:
        raise NotBuiltYet(_UNIT)

    def playbook(self, dataset_id: int) -> Playbook:
        raise NotBuiltYet(_UNIT)
