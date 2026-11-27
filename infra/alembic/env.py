"""How Alembic reaches Postgres: as the setup login, the one that makes and owns the tables.

The connection settings are the programs' own (`jev_trader.storage.postgres.settings`), read
from `.env` at the repo root, or from `config.attributes["env"]` when a caller hands them over
(the database tests hand the local Postgres's). The database is `config.attributes["database"]`,
else `-x database=...` on the command line, else the real one (`TRADING_AGENT`).
"""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from jev_trader.storage import postgres

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env():
    given = context.config.attributes.get("env")
    if given is not None:
        return given
    load_dotenv(REPO_ROOT / ".env")
    return os.environ


def _database() -> str:
    given = context.config.attributes.get("database")
    if given:
        return given
    return context.get_x_argument(as_dictionary=True).get("database", postgres.DATABASE)


def run_migrations_online() -> None:
    settings = postgres.settings("setup", _database(), _env())
    engine = create_engine(
        "postgresql+psycopg://", connect_args=settings, poolclass=NullPool
    )
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.config.config_file_name:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)
if context.is_offline_mode():
    raise SystemExit("Only online upgrades: Alembic connects to the database itself.")
run_migrations_online()
