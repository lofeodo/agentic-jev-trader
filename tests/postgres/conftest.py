"""The database tests of the move to Postgres (spec appendix 11), against the local Postgres.

Every test here is `dormant` until the slice's closing ticket (#283) switches it on. Each starts
from empty tables, made once per run by Alembic; the stores are opened as the programs open
them (`open_database`), each as its own login.
"""

import psycopg
import pytest

from tests.postgres import helpers


@pytest.fixture(scope="session")
def tables():
    """Every table, made once per run (#276)."""
    helpers.create_tables()
    try:
        con = helpers.connect("setup")
    except psycopg.OperationalError as error:
        pytest.fail(
            f"No local Postgres at {helpers.LOCAL_HOST}:{helpers.LOCAL_PORT} ({error}). "
            "Start it as CLAUDE.md says (#276)."
        )
    yield con
    con.close()


@pytest.fixture
def setup_login(tables):
    """The setup login's own connection, with every table emptied first: for writing made-up
    rows and reading rows back."""
    helpers.empty_tables(tables)
    return tables


def _opened(login):
    database = helpers.database(login)
    yield database
    database.close()


@pytest.fixture
def builder(setup_login):
    """The dataset builder's database."""
    yield from _opened("builder")


@pytest.fixture
def sim_db(setup_login):
    """The sim login's database."""
    yield from _opened("sim")


@pytest.fixture
def memory_db(setup_login):
    """The memory server's database, whose login can only read."""
    yield from _opened("memory")


@pytest.fixture
def api_db(setup_login):
    """The API's database."""
    yield from _opened("api")


@pytest.fixture
def made_up_dataset(builder):
    """A factory: `made_up_dataset(days, assets=1)` publishes a made-up dataset of crypto
    assets with a bar at every step, and returns its ID."""

    def make(days, assets=1):
        return helpers.publish_made_up_dataset(builder.dataset_store(), days, assets)

    return make
