"""The API's real queries, read as the API login from what the sim login wrote."""

import statistics
import time
from datetime import date, datetime, timedelta

import pytest

from jev_trader.api import sim_page
from jev_trader.api.measurements import measurements
from jev_trader.api.playbook import playbook
from jev_trader.api.scorecard import Split, scorecard
from jev_trader.api.sims_list import sims_list
from jev_trader.api.snowflake_store import SnowflakeApiStore
from jev_trader.api.spending import spending
from jev_trader.api.trades import Filters, trades_table
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


def test_the_sim_page_reports_read_real_tables(
    builder, sim_login, api_login, made_up_dataset, remove_sims
):
    """The trades table, the measurements and the scorecard of a finished holding sim."""
    dataset = made_up_dataset(days=3, assets=2)
    sims, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    api = SnowflakeApiStore(api_login)
    holding = create_sim(
        sims, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    remove_sims.append(holding)
    result = run_sim(sims, market, holding, steps_per_write=96)

    table = trades_table(api, holding, Filters(), page=1, page_size=50)
    report = measurements(api, holding)
    card = scorecard(api, holding, list(Split))

    assert table.total == 2
    assert {line.closing_reason for line in table.lines} == {"sim_ended"}
    assert all(line.held_overnight for line in table.lines)
    [money] = [g for g in report.groups if g.key == "money"]
    [value] = [f for f in money.figures if f.key == "ending_value"]
    assert value.sim == pytest.approx(result.ending_value)
    assert card.closed_trades == 2
    # The made-up dataset has no snapshots, so no trade has anything to be filed under.
    assert card.lines == []
    assert api.entry_details(dataset, [("ASSET_01", 97)]) == {}


def test_the_comparison_figures_read_real_tables(
    sim_login, api_login, made_up_dataset, remove_sims
):
    """A sim's own closer looks, its LLM dollars and seconds, and the names and versions that
    answered; a decision copied in with its memory is not its own."""
    dataset = made_up_dataset(days=3)
    sims, api = SnowflakeSimStore(sim_login), SnowflakeApiStore(api_login)
    sim = sims.create(
        {
            "DATASET": dataset,
            "KIND": "measurement",
            "VARIANT": "memory_on",
            "MARKET": "falling market",
            "REPEAT_NUMBER": 1,
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SETTINGS": {"llm": {"model": "anthropic:claude-haiku-5-5"}},
        }
    )
    remove_sims.append(sim)
    sims.update(sim, STATUS="running")

    def decision(number, kind, written_by=sim):
        return {
            "ID": f"{sim}-{number}",
            "SIM": sim,
            "FIRST_WRITTEN_BY": written_by,
            "DATASET": dataset,
            "ASSET": "ASSET_01",
            "STEP": 100 + number,
            "KIND": kind,
            "TIER": 2,
            "JEV_VERSION": f"jev-1.{number}.0",
            "ACTION": "nothing",
        }

    def call(number, service, cost, seconds, model=None):
        return {
            "ID": f"comparison-test-{sim}-{number}-{service}",
            "SIM": sim,
            "PURPOSE": "pick",
            "DECISION": f"{sim}-{number}",
            "SERVICE": service,
            "MODEL": model,
            "COST_USD": cost,
            "LATENCY_SECONDS": seconds,
        }

    sims.write_steps(
        sim,
        None,
        192,
        {
            "MEMORY.DECISIONS": [
                decision(1, "full_evaluation"),
                decision(2, "position_review"),
                decision(3, "full_evaluation", written_by=sim + 100_000),
            ],
            "SIM.CALLS": [
                call(1, "jev", 0.01, 2.0),
                call(1, "anthropic", 0.002, 3.0, "claude-haiku-5-5-20261001"),
                call(2, "anthropic", 0.003, 7.0, "claude-haiku-5-5-20261001"),
            ],
        },
        {},
    )

    [row] = [s for s in api.sims() if s["ID"] == sim]
    figures = api.comparison_figures([sim])[sim]

    assert row["LLM_MODEL"] == "claude-haiku-5-5"
    assert figures == {
        "FULL_EVALUATIONS": 1,
        "POSITION_REVIEWS": 1,
        "MODEL_USD": pytest.approx(0.015),
        "FULL_EVALUATION_SECONDS": pytest.approx(5.0),
        "LLM_MODELS": ["claude-haiku-5-5-20261001"],
        "JEV_VERSIONS": ["jev-1.1.0", "jev-1.2.0"],
    }


def result_step(header):
    """The page's usual question: nothing new since the step it last saw."""
    return header.step_reached
