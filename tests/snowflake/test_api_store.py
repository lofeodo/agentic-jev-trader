"""The API's real queries, read as the API login from what the sim login wrote."""

import statistics
import time
from datetime import date, datetime, timedelta

import pytest

from jev_trader.api import sim_page
from jev_trader.api.playbook import playbook
from jev_trader.api.sims_list import sims_list
from jev_trader.api.snowflake_store import SnowflakeApiStore
from jev_trader.api.spending import spending
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

    [item] = [i for i in spending(api, 75.0).items if i.sim_id == sim]
    assert (item.kind, item.jev_usd, item.llm_usd, item.calls) == ("free", 0.5, 0.0, 1)


def test_the_playbook_reads_the_real_table(api_login):
    """The playbook is filled by the first dataset build; an empty one is still a good read."""
    read = playbook(SnowflakeApiStore(api_login))

    if read.patterns:
        assert read.talib_version
        assert {p.lean for p in read.patterns} <= {"bullish", "bearish", "neutral"}


def test_the_sim_page_reads_real_tables_and_times_the_one_second_call(
    builder, sim_login, api_login, made_up_dataset, remove_sims
):
    """The sim page's four reads on a finished holding sim, and how long `/live` takes.

    Run with `-s` to see the timing: the median of 10 calls of the live figures, each a round
    of the queries the page sends every second (spec appendix 8, section 8.9).
    """
    dataset = made_up_dataset(days=3, assets=2)
    with builder.cursor() as cur:
        for masked_id, name in (("ASSET_01", "Bitcoin"), ("ASSET_02", "Ether")):
            cur.execute(
                "INSERT INTO KEYS.ASSET_KEY (DATASET, MASKED_ID, TICKER, "
                "PROVIDER_SYMBOL, NAME, PRICE_SCALE, VOLUME_SCALE, FIRST_DAY) "
                "VALUES (?, ?, ?, ?, ?, 0.5, 1, '2025-03-01')",
                (dataset, masked_id, name[:3].upper(), name, name),
            )
    sims, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    api = SnowflakeApiStore(api_login)
    holding = create_sim(
        sims, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    remove_sims.append(holding)
    result = run_sim(sims, market, holding, steps_per_write=96)
    quiet = timedelta(minutes=7)

    header = sim_page.header(api, holding, now(), quiet)
    chart = sim_page.chart(api, holding, 8)
    live = sim_page.live(api, holding, now(), quiet, after_step=200)
    moment = sim_page.moment(api, holding, datetime(2025, 3, 2, 12, 0), 8)

    assert header.replayed_at == datetime(2025, 3, 4, 0, 0)  # step 288 ends 3 days in
    assert [a.name for a in header.assets] == ["Bitcoin", "Ether"]
    [line] = chart.lines
    assert line.points[-1].value == pytest.approx(result.ending_value)
    assert [(t.asset.name, t.closed_step) for t in chart.ticks] == [
        ("Bitcoin", 288),
        ("Ether", 288),
    ]
    assert live.account_value == pytest.approx(result.ending_value)
    assert live.in_progress is False
    assert live.new_points and all(p.step > 200 for p in live.new_points)
    assert [p.asset.name for p in moment.positions] == ["Bitcoin", "Ether"]
    for position in moment.positions:
        assert position.price_then.real == pytest.approx(
            position.price_then.rescaled * 2
        )

    timings = []
    for _ in range(10):
        started = time.perf_counter()
        sim_page.live(api, holding, now(), quiet, after_step=result_step(header))
        timings.append(time.perf_counter() - started)
    print(
        f"\nlive figures: median {statistics.median(timings):.3f} s, "
        f"slowest {max(timings):.3f} s over {len(timings)} calls"
    )


def result_step(header):
    """The page's usual question: nothing new since the step it last saw."""
    return header.step_reached
