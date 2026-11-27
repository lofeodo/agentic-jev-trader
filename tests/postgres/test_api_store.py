"""The API's reads on Postgres, as the API login, from what the sim login wrote (spec appendix 8;
appendix 11, section 1). What the API answers does not change with the database."""

from datetime import date, datetime, timedelta

import psycopg
import pytest

from jev_trader.api import sim_page
from jev_trader.api.measurements import measurements
from jev_trader.api.playbook import playbook
from jev_trader.api.scorecard import Split, scorecard
from jev_trader.api.sims_list import sims_list
from jev_trader.api.spending import spending
from jev_trader.api.trades import Filters, trades_table
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import now
from tests.postgres.helpers import account_row, connect, insert


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


def asset_key(dataset, masked_id, name, price_scale=1.0):
    return {
        "DATASET": dataset,
        "MASKED_ID": masked_id,
        "TICKER": name[:3].upper(),
        "PROVIDER_SYMBOL": name,
        "NAME": name,
        "PRICE_SCALE": price_scale,
        "VOLUME_SCALE": 1.0,
        "FIRST_DAY": date(2025, 3, 1),
    }


@pytest.fixture
def sims(sim_db):
    return sim_db.sim_store(), sim_db.market()


def test_the_sims_list_reads_real_tables(sims, api_db, setup_login, made_up_dataset):
    dataset = made_up_dataset(days=3)
    insert(setup_login, "KEYS.ASSET_KEY", [asset_key(dataset, "ASSET_01", "Bitcoin")])
    store, market = sims
    api = api_db.api_store()

    holding = create_sim(
        store, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    run_sim(store, market, holding, steps_per_write=96)
    sim = store.create(
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
    store.update(sim, STATUS="running")
    store.write_steps(
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
    assert api.total_spent() == pytest.approx(0.5)

    [item] = [i for i in spending(api, 75.0).items if i.sim_id == sim]
    assert (item.kind, item.jev_usd, item.llm_usd, item.calls) == ("free", 0.5, 0.0, 1)


def test_the_playbook_reads_the_real_table(api_db, setup_login):
    row = {"TALIB_VERSION": "0.0-test", "SHAPE": "made up"}
    insert(
        setup_login,
        "REF.PLAYBOOK",
        [
            {**row, "PATTERN": "CDLHAMMER", "LEAN": "bullish", "NAME": "hammer"},
            {**row, "PATTERN": "CDLDOJI", "LEAN": "neutral", "NAME": "doji"},
        ],
    )

    read = playbook(api_db.api_store())

    assert read.talib_version == "0.0-test"
    assert {p.lean for p in read.patterns} == {"bullish", "neutral"}


def test_the_sim_page_reads_real_tables(sims, api_db, setup_login, made_up_dataset):
    """The sim page's four reads on a finished holding sim."""
    dataset = made_up_dataset(days=3, assets=2)
    insert(
        setup_login,
        "KEYS.ASSET_KEY",
        [
            asset_key(dataset, "ASSET_01", "Bitcoin", 0.5),
            asset_key(dataset, "ASSET_02", "Ether", 0.5),
        ],
    )
    store, market = sims
    api = api_db.api_store()
    holding = create_sim(
        store, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    result = run_sim(store, market, holding, steps_per_write=96)
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


def test_the_sim_page_reports_read_real_tables(sims, api_db, made_up_dataset):
    """The trades table, the measurements and the scorecard of a finished holding sim."""
    dataset = made_up_dataset(days=3, assets=2)
    store, market = sims
    api = api_db.api_store()
    holding = create_sim(
        store, market, SimRequest(dataset, "buy_hold", "practice", 97, 288)
    )
    result = run_sim(store, market, holding, steps_per_write=96)

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


def test_the_comparison_figures_read_real_tables(sims, api_db, made_up_dataset):
    """A sim's own closer looks, its LLM dollars and seconds, and the names and versions that
    answered; a decision copied in with its memory is not its own."""
    dataset = made_up_dataset(days=3)
    store, _market = sims
    api = api_db.api_store()
    sim = store.create(
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
    store.update(sim, STATUS="running")

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

    store.write_steps(
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


def test_the_api_adds_and_changes_only_its_two_rows(api_db, setup_login):
    """The API's only writes: a dataset's row (a build from the app) and a sim's row (start,
    Stop, Resume). Every other table it can only read."""
    api = api_db.api_store()

    dataset, version = api.begin_dataset("api test", {"FIRST_STEP": 1})
    api.update_dataset(dataset, BUILD_PROGRESS=0.5)
    sim = api.create(
        {
            "DATASET": dataset,
            "KIND": "free",
            "VARIANT": "buy_hold",
            "FIRST_STEP": 97,
            "LAST_STEP": 192,
            "STARTING_VALUE": 10_000.0,
            "SETTINGS": {},
        }
    )
    api.update(sim, STATUS="stopped", STOP_REASON="stopped by hand")

    assert version == 1
    assert api.sim(sim)["STATUS"] == "stopped"
    assert setup_login.execute(
        "SELECT BUILD_PROGRESS FROM REF.DATASETS WHERE ID = %s", (dataset,)
    ).fetchone() == (0.5,)
    with connect("api") as con:
        assert con.execute("SELECT COUNT(*) FROM SIM.ORDERS").fetchone() == (0,)
        for statement in (
            "DELETE FROM SIM.ORDERS",
            "DELETE FROM MEMORY.DECISIONS",
            "DELETE FROM RAW.BARS",
            "DELETE FROM SIM.SIMS",
            "DELETE FROM REF.DATASETS",
            "INSERT INTO SIM.SIM_EVENTS (ID, SIM, STEP, KIND) VALUES ('x', 1, 1, 'x')",
            "INSERT INTO RAW.BARS (DATASET) VALUES (1)",
            "UPDATE MEMORY.DECISIONS SET ACTION = 'close'",
            "UPDATE SIM.ORDERS SET STATUS = 'cancelled'",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                con.execute(statement)
