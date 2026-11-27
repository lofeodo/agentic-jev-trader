"""The memory server's reads from Postgres, as the memory login, whose role can only read.

The skeleton of the Postgres slice (spec appendix 11): every method of `store.MemoryStore` is
here, and ticket #279 fills each in, the search with `pgvector` in place of Snowflake's vector
functions (ADR 0018). `connection` is the process's one connection
(`jev_trader.storage.postgres.connection`), with `%s` placeholders. What each read returns, and
the rule they all follow, is in `store.py`.
"""

from collections.abc import Sequence

from jev_trader.memory.search import Candidate, Query
from jev_trader.storage import NotBuiltYet

_UNIT = 279


class PostgresMemoryStore:
    def __init__(self, connection):
        self.con = connection

    def sim(self, sim_id: int) -> dict:
        raise NotBuiltYet(_UNIT)

    def snapshot(self, dataset: int, asset: str, step: int) -> dict:
        raise NotBuiltYet(_UNIT)

    def ranked(
        self, query: Query, current: dict, weights: Sequence[float], top: int
    ) -> tuple[list[Candidate], list[Candidate]]:
        raise NotBuiltYet(_UNIT)

    def decisions(self, sim: int, step: int, ids: Sequence[str]) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def outcomes(self, sim: int, step: int, decisions: Sequence[str]) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def position_rows(
        self, sim: int, step: int, positions: Sequence[int]
    ) -> list[dict]:
        raise NotBuiltYet(_UNIT)

    def closed_trades(self, sim: int, step: int, asset_class: str) -> list[dict]:
        raise NotBuiltYet(_UNIT)
