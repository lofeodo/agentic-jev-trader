"""The database a program reads and writes, picked by the `DATABASE_ENGINE` setting in `.env`.

While Snowflake's tables move to Postgres on AWS RDS (spec appendix 11, ADR 0018), each store
has a version for each: `snowflake` (the default until the move is done) or `postgres`. The
closing ticket of the move removes the setting and the Snowflake versions: one database at a
time. A program opens its database once, as its own login, and takes its stores from it:

    database = open_database("sim", "TRADING_AGENT")
    store, market = database.sim_store(), database.market()
    ...
    database.close()

Every store of one `Database` shares its one connection. On Postgres that connection is the
process's own (`postgres.connection`), always opened on first use. On Snowflake it is opened at
once, or on first use for the two servers (`on_first_use`), as before.
"""

import importlib
import os
from collections.abc import Mapping

from jev_trader.storage import LoginNotSet

SNOWFLAKE = "snowflake"
POSTGRES = "postgres"
ENGINES = (SNOWFLAKE, POSTGRES)
DEFAULT_ENGINE = SNOWFLAKE

# Each engine's version of each store, as "module:class", imported only when asked for.
_STORES = {
    SNOWFLAKE: {
        "dataset": "jev_trader.dataset.snowflake_store:SnowflakeStore",
        "sim": "jev_trader.sim.snowflake_store:SnowflakeSimStore",
        "market": "jev_trader.sim.snowflake_store:SnowflakeMarket",
        "memory": "jev_trader.memory.snowflake_store:SnowflakeMemoryStore",
        "api": "jev_trader.api.snowflake_store:SnowflakeApiStore",
    },
    POSTGRES: {
        "dataset": "jev_trader.dataset.postgres_store:PostgresStore",
        "sim": "jev_trader.sim.postgres_store:PostgresSimStore",
        "market": "jev_trader.sim.postgres_store:PostgresMarket",
        "memory": "jev_trader.memory.postgres_store:PostgresMemoryStore",
        "api": "jev_trader.api.postgres_store:PostgresApiStore",
    },
}


def engine(env: Mapping[str, str] = os.environ) -> str:
    """The engine `DATABASE_ENGINE` names; Snowflake if it is not set. LoginNotSet if it names
    neither."""
    named = (env.get("DATABASE_ENGINE") or "").strip().lower() or DEFAULT_ENGINE
    if named not in ENGINES:
        raise LoginNotSet(
            f"DATABASE_ENGINE is {named!r}; set it to one of {', '.join(ENGINES)} in .env."
        )
    return named


def _connection(engine_name, login, database, env, on_first_use):
    if engine_name == POSTGRES:
        from jev_trader.storage import postgres

        return postgres.connection(login, database, env)
    from jev_trader.storage import snowflake

    if on_first_use:
        return snowflake.ConnectionOnFirstUse(login, database, env)
    return snowflake.connect(login, database=database, env=env)


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
        self.connection = _connection(self.engine, login, database, env, on_first_use)

    def _store(self, kind: str):
        module, name = _STORES[self.engine][kind].split(":")
        return getattr(importlib.import_module(module), name)(self.connection)

    def dataset_store(self):
        """`jev_trader.dataset.store.DatasetStore`, as the builder writes it."""
        return self._store("dataset")

    def sim_store(self):
        """`jev_trader.sim.store.SimStore`."""
        return self._store("sim")

    def market(self):
        """`jev_trader.sim.market.Market`."""
        return self._store("market")

    def memory_store(self):
        """`jev_trader.memory.store.MemoryStore`, for the memory login."""
        return self._store("memory")

    def api_store(self):
        """`jev_trader.api.store.ApiStore`, for the API login."""
        return self._store("api")

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


def refuse_postgres_until(ticket: int, env: Mapping[str, str] = os.environ) -> None:
    """For a program still on Snowflake alone: NotBuiltYet naming `ticket` when
    `DATABASE_ENGINE` names Postgres, so it never reads Snowflake while Postgres is asked for."""
    from jev_trader.storage import NotBuiltYet

    if engine(env) == POSTGRES:
        raise NotBuiltYet(ticket)
