"""The dataset store in Postgres, as the builder login: the same tables as in Snowflake.

The skeleton of the Postgres slice (spec appendix 11): every method of `store.DatasetStore` is
here, and ticket #278 fills each in. `connection` is the process's one connection
(`jev_trader.storage.postgres.connection`), with `%s` placeholders. Snapshots keep their two
steps (staged, then embedded); ticket #277 brings the text-to-numbers model to this computer.
"""

from jev_trader.storage import NotBuiltYet

_TICKET = 278


class PostgresStore:
    def __init__(self, connection):
        self.con = connection

    def begin(self, name: str, columns: dict) -> tuple[int, int]:
        raise NotBuiltYet(_TICKET)

    def carry_on(self, dataset_id: int, columns: dict) -> int:
        raise NotBuiltYet(_TICKET)

    def status(self, dataset_id: int) -> tuple[str, str | None]:
        raise NotBuiltYet(_TICKET)

    def clear_failed(self) -> None:
        raise NotBuiltYet(_TICKET)

    def update(self, dataset_id: int, **columns) -> None:
        raise NotBuiltYet(_TICKET)

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        raise NotBuiltYet(_TICKET)

    def save_playbook(self, rows: list[dict]) -> None:
        raise NotBuiltYet(_TICKET)

    def stage_snapshots(self, dataset_id: int, rows: list[dict]) -> None:
        raise NotBuiltYet(_TICKET)

    def embed_snapshots(self, dataset_id: int, asset: str) -> int:
        raise NotBuiltYet(_TICKET)

    def publish(self, dataset_id: int, without_check: bool) -> None:
        raise NotBuiltYet(_TICKET)

    def fail(self, dataset_id: int, reason: str) -> None:
        raise NotBuiltYet(_TICKET)
