"""The API's real queries, read as the API login from what the sim login wrote."""

from datetime import date, timedelta

import pytest

from jev_trader.api.sims_list import sims_list
from jev_trader.api.snowflake_store import SnowflakeApiStore
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.store import now

from .conftest import login


@pytest.fixture
def api_login():
    con = login("api")
    yield con
    con.close()


def account_row(sim_id, step, value):
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


def entry_row(sim_id, number):
    return {
        "ID": f"{sim_id}-97-ASSET_01-{number}",
        "SIM": sim_id,
        "POSITION": number,
        "INSTRUMENT": "ASSET_01_SPOT",
        "KIND": "entry",
        "REASON": "jev",
        "STEP_DECIDED": 97,
        "STATUS": "carried out",
    }


def call_row(sim_id, cost):
    return {
        "ID": f"api-store-test-{sim_id}",
        "SIM": sim_id,
        "PURPOSE": "screen",
        "SERVICE": "jev",
        "COST_USD": cost,
    }


def test_the_sims_list_reads_real_tables(
    builder, sim_login, api_login, made_up_dataset, remove_sims
):
    dataset = made_up_dataset(days=3)
    with builder.cursor() as cur:
        cur.execute(
            "INSERT INTO KEYS.ASSET_KEY (DATASET, MASKED_ID, TICKER, PROVIDER_SYMBOL, "
            "NAME, PRICE_SCALE, VOLUME_SCALE, FIRST_DAY) "
            "VALUES (?, 'ASSET_01', 'BTC', 'BTCUSDT', 'Bitcoin', 1, 1, '2025-03-01')",
            (dataset,),
        )
    sims, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    api = SnowflakeApiStore(api_login)
    spent_before = api.total_spent()

    holding = create_sim(
        sims, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    remove_sims.append(holding)
    run_sim(sims, market, holding, steps_per_write=96)
    sim = sims.create(
        {
            "DATASET": dataset,
            "KIND": "free",
            "VARIANT": "memory_off",
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SPENDING_CAP": 1.5,
            "SETTINGS": {},
        }
    )
    remove_sims.append(sim)
    sims.update(sim, STATUS="running")
    sims.write_steps(
        sim,
        None,
        192,
        {
            "SIM.ACCOUNT_STEPS": [account_row(sim, 192, 10_250.0)],
            "SIM.ORDERS": [entry_row(sim, 1), entry_row(sim, 2)],
            "SIM.CALLS": [call_row(sim, 0.5)],
        },
        {},
    )

    lines = [
        line
        for line in sims_list(api, now(), timedelta(minutes=7)).sims
        if line.id in (holding, sim)
    ]

    assert [line.id for line in lines] == [sim]
    [line] = lines
    assert (line.days_done, line.days_total) == (1, 2)
    assert line.account_value == 10_250.0
    assert line.holding_value == api.account_values_at([(holding, 192)])[(holding, 192)]
    assert line.holding_value is not None
    assert line.trades == 2
    assert line.spent_usd == pytest.approx(0.5)
    assert line.first_day == date(2025, 3, 2)
    assert [(a.name, a.masked_id) for a in line.assets] == [("Bitcoin", "ASSET_01")]
    assert api.total_spent() == pytest.approx(spent_before + 0.5)
