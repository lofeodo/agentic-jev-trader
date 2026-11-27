"""The local Postgres the database tests use, and what they write into it and read back.

The tests run against a Postgres with `pgvector` on this computer, in Docker (ticket #276 adds
it, and the command that starts it): never RDS, whatever `.env` says, so they cost nothing. The
settings below are the ones that local Postgres is made with; nothing here reads `.env`.

Each login is the project's own role (`trading_agent_<login>`), with its own password, so the
tests also see what each login may and may not do. The tables are made by Alembic (#276) as the
setup login, which is also the one the tests write made-up rows and read them back with.
"""

import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from jev_trader.sim.clock import day_of
from jev_trader.storage import NotBuiltYet, postgres
from jev_trader.storage.database import open_database

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE = "TRADING_AGENT_TEST"
LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 5433

# What every program reads its database from, pointed at the local Postgres.
LOCAL_ENV = {
    "DATABASE_ENGINE": "postgres",
    "POSTGRES_HOST": LOCAL_HOST,
    "POSTGRES_PORT": str(LOCAL_PORT),
    "POSTGRES_SSL_MODE": "disable",
    **{
        postgres.password_variable(login): f"local-{login}" for login in postgres.LOGINS
    },
}


def env_through(port: int) -> dict:
    """`LOCAL_ENV`, reaching the database through `port` on this computer (a `wire.Line`)."""
    return {**LOCAL_ENV, "POSTGRES_PORT": str(port)}


def database(login: str, env: dict | None = None):
    """`login`'s `Database` on the test database, as the programs open it."""
    return open_database(login, TEST_DATABASE, env=env or LOCAL_ENV)


def connect(login: str, env: dict | None = None) -> psycopg.Connection:
    """A connection of its own as `login`, outside the stores: to write made-up rows, read
    rows back, or play a second program."""
    return psycopg.connect(
        **postgres.settings(login, TEST_DATABASE, env or LOCAL_ENV), autocommit=True
    )


def alembic_config():
    """Alembic's settings, for making every table from its first file on (#276).

    Alembic's settings file is `alembic.ini` at the repo root. The tests hand its `env.py` the
    settings to connect with through `config.attributes`: `env` (as `LOCAL_ENV`) and `database`.
    """
    ini = REPO_ROOT / "alembic.ini"
    try:
        from alembic.config import Config
    except ImportError:
        raise NotBuiltYet(276) from None
    if not ini.exists():
        raise NotBuiltYet(276)
    config = Config(str(ini))
    config.attributes["env"] = LOCAL_ENV
    config.attributes["database"] = TEST_DATABASE
    return config


def create_tables(config) -> None:
    """Every table, made by Alembic as the setup login."""
    from alembic import command

    command.upgrade(config, "head")


def empty_tables(con: psycopg.Connection) -> None:
    """Every row of every table thrown away: each test starts from empty tables."""
    tables = con.execute(
        "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
        "AND tablename <> 'alembic_version'"
    ).fetchall()
    if tables:
        names = ", ".join(name for (name,) in tables)
        con.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")


def _column_types(con, table: str) -> dict[str, tuple[str, str]]:
    schema, name = table.lower().split(".")
    found = con.execute(
        "SELECT column_name, data_type, udt_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, name),
    ).fetchall()
    return {column: (kind, udt) for column, kind, udt in found}


def _bound(value, kind: str, udt: str):
    """`value` as its column takes it, and the placeholder that does."""
    if value is None:
        return None, "%s"
    if udt == "vector":
        return "[" + ",".join(str(float(x)) for x in value) + "]", "%s::vector"
    if kind in ("json", "jsonb"):
        return Jsonb(value), f"%s::{kind}"
    return value, "%s"


def insert(con: psycopg.Connection, table: str, rows: list[dict]) -> None:
    """Made-up rows into `table` (Snowflake's names, such as `MEMORY.DECISIONS`), each value
    written the way its column holds it: lists into arrays or JSON, numbers into vectors."""
    if not rows:
        return
    types = _column_types(con, table)
    columns = sorted({c for r in rows for c in r})
    missing = [c for c in columns if c.lower() not in types]
    assert not missing, f"{table} has no column {missing}"
    with con.cursor() as cur:
        for row in rows:
            bound = [_bound(row.get(c), *types[c.lower()]) for c in columns]
            cur.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(mark for _, mark in bound)})",
                [value for value, _ in bound],
            )


def account_row(sim_id: int, step: int, value: float = 10_000.0) -> dict:
    """A sim's account at `step`: all cash, worth `value`."""
    return {
        "ID": f"{sim_id}-{step}",
        "SIM": sim_id,
        "STEP": step,
        "CASH": value,
        "LOAN": 0.0,
        "EXPOSURE": 0.0,
        "ACCOUNT_VALUE": value,
        "START_OF_DAY_VALUE": value,
        "DAILY_LOSS_REACHED": False,
    }


def records(con, sim_id: int) -> dict:
    """Every record of a sim but its events, table by table, without the sim's ID or the rows'
    IDs: comparable across sims."""
    from jev_trader.sim.store import TABLES

    found = {}
    for table in TABLES:
        if table == "SIM.SIM_EVENTS":
            continue
        with con.cursor() as cur:
            cur.execute(f"SELECT * FROM {table} WHERE SIM = %s", (sim_id,))
            names = [d.name for d in cur.description]
            rows = [
                {n: v for n, v in zip(names, row) if n not in ("id", "sim")}
                for row in cur.fetchall()
            ]
        found[table] = sorted(rows, key=repr)
    return found


def parsed(value):
    """A JSON value as Python, whether its column hands it back parsed or as text."""
    return json.loads(value) if isinstance(value, str) else value


def numbers(value) -> list[float]:
    """A vector column's numbers, whether handed back as a list or as `[1,2,3]` text."""
    return [float(x) for x in parsed(value)]


def bar_row(dataset_id, asset, step, day_bar, price):
    return {
        "DATASET": dataset_id,
        "ASSET": asset,
        "BAR_SIZE": "15m",
        "STEP": step,
        "DAY": day_of(step),
        "BAR_NUMBER": day_bar,
        "BARS_LEFT": None,
        "OPEN": price,
        "HIGH": price * 1.001,
        "LOW": price * 0.999,
        "CLOSE": price,
        "VOLUME": 100.0,
    }


def publish_made_up_dataset(store, days: int, assets: int = 1) -> int:
    """A published dataset of crypto assets with a bar at every step of `days` days, written
    through the dataset store. Day 1 is the warm-up. Each asset's price drifts up a little each
    step, so a holding sim ends above where it started."""
    last_step = days * 96
    dataset_id, _ = store.begin(
        "database test",
        {"FIRST_STEP": 1, "LAST_STEP": last_step, "DATA_PROVIDERS": ["made up"]},
    )
    names = [f"ASSET_{n:02d}" for n in range(1, assets + 1)]
    store.save(
        dataset_id,
        {
            "REF.DATASET_PERIODS": [
                {
                    "DATASET": dataset_id,
                    "KIND": "warm-up",
                    "NAME": "warm-up",
                    "FIRST_STEP": 1,
                    "LAST_STEP": 96,
                }
            ],
            "REF.ASSETS": [
                {"DATASET": dataset_id, "MASKED_ID": a, "ASSET_CLASS": "crypto"}
                for a in names
            ],
            "REF.INSTRUMENTS": [
                {
                    "DATASET": dataset_id,
                    "INSTRUMENT_ID": f"{a}_SPOT",
                    "ASSET": a,
                    "TYPE": "spot",
                }
                for a in names
            ],
            "RAW.BARS": [
                bar_row(
                    dataset_id,
                    a,
                    step,
                    (step - 1) % 96 + 1,
                    round(100 + 0.001 * step * (n + 1), 4),
                )
                for n, a in enumerate(names)
                for step in range(1, last_step + 1)
            ],
        },
    )
    store.publish(dataset_id, without_check=True)
    return dataset_id
