"""How a program logs in to Postgres, and the stores it gets. Nothing here connects: a
Postgres connection opens on first use, and these tests never use one."""

import inspect

import pytest

from jev_trader.api.postgres_store import PostgresApiStore
from jev_trader.api.store import ApiStore
from jev_trader.dataset.postgres_store import PostgresStore
from jev_trader.dataset.store import DatasetStore
from jev_trader.memory.postgres_store import PostgresMemoryStore
from jev_trader.memory.store import MemoryStore
from jev_trader.sim.market import Market
from jev_trader.sim.postgres_store import PostgresMarket, PostgresSimStore
from jev_trader.sim.store import SimStore
from jev_trader.storage import LoginNotSet, postgres
from jev_trader.storage.database import open_database

POSTGRES_ENV = {
    "POSTGRES_HOST": "db.example.invalid",
    **{
        postgres.password_variable(login): f"{login}-made-up"
        for login in postgres.LOGINS
    },
}


@pytest.mark.parametrize("login", postgres.LOGINS)
def test_each_login_has_its_own_role_and_password(login):
    settings = postgres.settings(login, "TRADING_AGENT_TEST", POSTGRES_ENV)

    assert settings["user"] == f"trading_agent_{login}"
    assert settings["password"] == f"{login}-made-up"
    assert settings["dbname"] == "trading_agent_test"
    assert settings["port"] == 5432
    assert settings["sslmode"] == "require"


def test_a_missing_password_is_named():
    env = {**POSTGRES_ENV, "POSTGRES_SIM_PASSWORD": " "}

    with pytest.raises(LoginNotSet, match="POSTGRES_SIM_PASSWORD"):
        open_database("sim", "TRADING_AGENT", env=env)


def test_the_local_database_can_go_unencrypted_on_its_own_port():
    env = {**POSTGRES_ENV, "POSTGRES_PORT": "5433", "POSTGRES_SSL_MODE": "disable"}

    settings = postgres.settings("api", "TRADING_AGENT", env)

    assert (settings["port"], settings["sslmode"]) == (5433, "disable")


def test_a_process_reuses_one_connection_per_login_and_database():
    sim = open_database("sim", "TRADING_AGENT_TEST", env=POSTGRES_ENV)
    again = open_database("sim", "trading_agent_test", env=POSTGRES_ENV)
    api = open_database("api", "TRADING_AGENT_TEST", env=POSTGRES_ENV)

    assert sim.connection is again.connection
    assert api.connection is not sim.connection
    store, market = sim.sim_store(), sim.market()
    assert store.con is market.con is sim.connection


@pytest.mark.parametrize(
    "make, kind, interface",
    [
        (lambda d: d.dataset_store(), PostgresStore, DatasetStore),
        (lambda d: d.sim_store(), PostgresSimStore, SimStore),
        (lambda d: d.market(), PostgresMarket, Market),
        (lambda d: d.memory_store(), PostgresMemoryStore, MemoryStore),
        (lambda d: d.api_store(), PostgresApiStore, ApiStore),
    ],
)
def test_the_database_has_every_store_with_its_whole_interface(make, kind, interface):
    store = make(open_database("sim", "TRADING_AGENT", env=POSTGRES_ENV))

    assert isinstance(store, kind)
    for name, method in vars(interface).items():
        if inspect.isfunction(method) and not name.startswith("_"):
            assert inspect.signature(getattr(kind, name)) == inspect.signature(method)


def test_other_settings_get_their_own_connection():
    moved = {**POSTGRES_ENV, "POSTGRES_HOST": "elsewhere.example.invalid"}

    first = open_database("api", "TRADING_AGENT", env=POSTGRES_ENV)
    other = open_database("api", "TRADING_AGENT", env=moved)

    assert first.connection is not other.connection
