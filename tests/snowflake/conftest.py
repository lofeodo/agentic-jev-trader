"""Logins and made-up datasets for the hand-run sim tests, against TRADING_AGENT_TEST.

The sim tests log in as two of the project's own logins, each with its own key in
`SNOWFLAKE_LOCAL_DIR`: the dataset builder, to publish a small made-up dataset, and the sim
login, which runs sims on it. Every test removes what it wrote.
"""

import os

import pytest
from dotenv import dotenv_values

from jev_trader.dataset.snowflake_store import SnowflakeStore
from jev_trader.sim.clock import day_of
from jev_trader.sim.store import TABLES
from jev_trader.storage.snowflake import TEST_DATABASE, connect, key_file

ENV = {**dotenv_values(".env"), **os.environ}


def login(name):
    if not key_file(name, ENV).exists():
        pytest.skip(f"no key for the {name} login at {key_file(name, ENV)}")
    return connect(name, database=TEST_DATABASE, env=ENV)


@pytest.fixture
def builder():
    con = login("builder")
    yield con
    con.close()


@pytest.fixture
def sim_login():
    con = login("sim")
    yield con
    con.close()


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


@pytest.fixture
def made_up_dataset(builder):
    """A factory: a published dataset of crypto assets with a bar at every step of `days` days.

    Day 1 is the warm-up. Each asset's price drifts up a little each step, so the holding sim
    ends above where it started. Thrown away (marked failed, rows deleted) after the test.
    """
    store = SnowflakeStore(builder)
    made = []

    def make(days, assets=1):
        last_step = days * 96
        dataset_id, _ = store.begin(
            "hand-run sim test",
            {"FIRST_STEP": 1, "LAST_STEP": last_step, "DATA_PROVIDERS": ["made up"]},
        )
        made.append(dataset_id)
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

    yield make
    for dataset_id in made:
        store.fail(dataset_id, "hand-run sim test finished")


@pytest.fixture
def remove_sims(sim_login):
    """Sim IDs appended here are deleted, with every record, after the test."""
    sims = []
    yield sims
    with sim_login.cursor() as cur:
        for sim_id in sims:
            for table in TABLES:
                cur.execute(f"DELETE FROM {table} WHERE SIM = ?", (sim_id,))
            cur.execute("DELETE FROM SIM.SIMS WHERE ID = ?", (sim_id,))


@pytest.fixture
def another_sim_login():
    """A second connection as the sim login: a second copy of a sim."""
    con = login("sim")
    yield con
    con.close()
