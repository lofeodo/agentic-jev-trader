"""The database a program reads and writes: Postgres (spec appendix 11, ADR 0018).

A program opens its database once, as its own login, and takes its stores from it:

    database = open_database("sim", DATABASE)
    store, market = database.sim_store(), database.market()
    ...
    database.close()

Every store of one `Database` shares its one connection: the process's own
(`postgres.connection`), opened on first use, so a server starts and answers its health address
before the database is reached.
"""

import os
from collections.abc import Mapping

from jev_trader.storage import postgres

# The names the commands take (`--database TRADING_AGENT_TEST`); Postgres's own are these in
# lower case.
DATABASE = postgres.DATABASE.upper()
TEST_DATABASE = postgres.TEST_DATABASE.upper()


class Database:
    """One login's connection to one database, and the stores that read and write through it."""

    def __init__(self, login: str, database: str, env: Mapping[str, str] = os.environ):
        self.connection = postgres.connection(login, database, env)

    def dataset_store(self):
        """`jev_trader.dataset.store.DatasetStore`, as the builder writes it."""
        from jev_trader.dataset.postgres_store import PostgresStore

        return PostgresStore(self.connection)

    def sim_store(self):
        """`jev_trader.sim.store.SimStore`."""
        from jev_trader.sim.postgres_store import PostgresSimStore

        return PostgresSimStore(self.connection)

    def market(self):
        """`jev_trader.sim.market.Market`."""
        from jev_trader.sim.postgres_store import PostgresMarket

        return PostgresMarket(self.connection)

    def memory_store(self):
        """`jev_trader.memory.store.MemoryStore`, for the memory login."""
        from jev_trader.memory.postgres_store import PostgresMemoryStore

        return PostgresMemoryStore(self.connection)

    def api_store(self):
        """`jev_trader.api.store.ApiStore`, for the API login."""
        from jev_trader.api.postgres_store import PostgresApiStore

        return PostgresApiStore(self.connection)

    def close(self) -> None:
        self.connection.close()


def open_database(
    login: str, database: str, *, env: Mapping[str, str] = os.environ
) -> Database:
    """`login`'s database. LoginNotSet names a setting that is missing or wrong."""
    return Database(login, database, env)
