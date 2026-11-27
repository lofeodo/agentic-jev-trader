"""The database a program reads and writes, picked by the `DATABASE_ENGINE` setting in `.env`.

While Snowflake's tables move to Postgres on AWS RDS (spec appendix 11, ADR 0018), each store
has a version for each: `snowflake` (the default until the move is done) or `postgres`. A
program opens its database once, as its own login, and takes its stores from it:

    database = open_database("sim", "TRADING_AGENT")
    store, market = database.sim_store(), database.market()
    ...
    database.close()

Every store of one `Database` shares its one connection. On Postgres that connection is the
process's own (`postgres.connection`), opened on first use. On Snowflake it is opened at once,
or on first use for the two servers (`on_first_use`), as before.
"""

import os
from collections.abc import Mapping

from jev_trader.storage import LoginNotSet

SNOWFLAKE = "snowflake"
POSTGRES = "postgres"
ENGINES = (SNOWFLAKE, POSTGRES)
DEFAULT_ENGINE = SNOWFLAKE


def engine(env: Mapping[str, str] = os.environ) -> str:
    """The engine `DATABASE_ENGINE` names; Snowflake if it is not set."""
    named = (env.get("DATABASE_ENGINE") or "").strip().lower() or DEFAULT_ENGINE
    if named not in ENGINES:
        raise LoginNotSet(
            f"DATABASE_ENGINE is {named!r}; set it to one of {', '.join(ENGINES)} in .env."
        )
    return named


class Database:
    """One login's connection to one database, and the stores that read and write through it."""

    def __init__(
        self,
        login: str,
        database: str,
        env: Mapping[str, str] = os.environ,
        on_first_use: bool = False,
    ):
        self.engine = engine(env)
        if self.engine == POSTGRES:
            from jev_trader.storage import postgres

            self.connection = postgres.connection(login, database, env)
        else:
            from jev_trader.storage import snowflake

            self.connection = (
                snowflake.ConnectionOnFirstUse(login, database, env)
                if on_first_use
                else snowflake.connect(login, database=database, env=env)
            )

    def dataset_store(self):
        """`jev_trader.dataset.store.DatasetStore`, as the builder writes it."""
        if self.engine == POSTGRES:
            from jev_trader.dataset.postgres_store import PostgresStore

            return PostgresStore(self.connection)
        from jev_trader.dataset.snowflake_store import SnowflakeStore

        return SnowflakeStore(self.connection)

    def sim_store(self):
        """`jev_trader.sim.store.SimStore`."""
        if self.engine == POSTGRES:
            from jev_trader.sim.postgres_store import PostgresSimStore

            return PostgresSimStore(self.connection)
        from jev_trader.sim.snowflake_store import SnowflakeSimStore

        return SnowflakeSimStore(self.connection)

    def market(self):
        """`jev_trader.sim.market.Market`."""
        if self.engine == POSTGRES:
            from jev_trader.sim.postgres_store import PostgresMarket

            return PostgresMarket(self.connection)
        from jev_trader.sim.snowflake_store import SnowflakeMarket

        return SnowflakeMarket(self.connection)

    def memory_store(self):
        """`jev_trader.memory.store.MemoryStore`, for the memory login."""
        if self.engine == POSTGRES:
            from jev_trader.memory.postgres_store import PostgresMemoryStore

            return PostgresMemoryStore(self.connection)
        from jev_trader.memory.snowflake_store import SnowflakeMemoryStore

        return SnowflakeMemoryStore(self.connection)

    def api_store(self):
        """`jev_trader.api.store.ApiStore`, for the API login."""
        if self.engine == POSTGRES:
            from jev_trader.api.postgres_store import PostgresApiStore

            return PostgresApiStore(self.connection)
        from jev_trader.api.snowflake_store import SnowflakeApiStore

        return SnowflakeApiStore(self.connection)

    def close(self) -> None:
        self.connection.close()


def open_database(
    login: str,
    database: str,
    *,
    on_first_use: bool = False,
    env: Mapping[str, str] = os.environ,
) -> Database:
    """`login`'s database, on the engine `DATABASE_ENGINE` names. LoginNotSet names a setting
    that is missing or wrong."""
    return Database(login, database, env, on_first_use)
