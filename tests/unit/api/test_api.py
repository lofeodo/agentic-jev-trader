"""The API as the web app sees it: real HTTP requests, answered from the in-memory store."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInLauncher

ON_THIS_COMPUTER = ("127.0.0.1", 50000)
ON_ANOTHER_COMPUTER = ("192.168.1.20", 50000)
NOW = datetime(2026, 11, 23, 12, 0)


@pytest.fixture
def sims():
    return InMemorySimStore()


@pytest.fixture
def store(sims):
    return InMemoryApiStore(
        sims,
        asset_key=[
            {
                "DATASET": 7,
                "MASKED_ID": "ASSET_02",
                "NAME": "Bitcoin",
                "FIRST_DAY": date(2025, 3, 1),
            },
            {
                "DATASET": 7,
                "MASKED_ID": "ASSET_01",
                "NAME": "Apple",
                "FIRST_DAY": date(2025, 3, 1),
            },
        ],
    )


def paid_call(sims, sim_id, cost):
    sims.tables["SIM.CALLS"].append(
        {"ID": f"call-{len(sims.tables['SIM.CALLS'])}", "SIM": sim_id, "COST_USD": cost}
    )


def client_for(store, client=ON_THIS_COMPUTER, host="localhost"):
    return TestClient(
        create_app(
            store,
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            clock=lambda: NOW,
            launcher=StandInLauncher(),
        ),
        base_url=f"http://{host}",
        client=client,
    )


def add_sim(sims, variant="memory_off", kind="free", **columns):
    """A sim over two days (steps 97 to 288) of dataset 7, with $10,000."""
    return sims.create(
        {
            "DATASET": 7,
            "KIND": kind,
            "VARIANT": variant,
            "REPEAT_NUMBER": None,
            "MARKET": None,
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SPENDING_CAP": None,
            "SETTINGS": {},
            **columns,
        }
    )


def account_at(sims, sim_id, step, value):
    sims.tables["SIM.ACCOUNT_STEPS"].append(
        {"ID": f"{sim_id}-{step}", "SIM": sim_id, "STEP": step, "ACCOUNT_VALUE": value}
    )


def order(sims, sim_id, number, kind, status="carried out"):
    sims.tables["SIM.ORDERS"].append(
        {
            "ID": f"{sim_id}-{number}",
            "SIM": sim_id,
            "POSITION": number,
            "KIND": kind,
            "STATUS": status,
        }
    )


def listed(store):
    return client_for(store).get("/sims").json()["sims"]


def test_health_says_the_api_is_up(store):
    answer = client_for(store).get("/health")

    assert answer.status_code == 200
    assert answer.json() == {"status": "up"}


def test_a_request_from_another_computer_is_refused(store):
    answer = client_for(store, client=ON_ANOTHER_COMPUTER).get("/health")

    assert answer.status_code == 403


def test_a_web_page_reaching_in_under_another_address_is_refused(store):
    answer = client_for(store, host="evil.example").get("/health")

    assert answer.status_code == 400


def test_spending_total_is_zero_before_any_paid_call(store):
    answer = client_for(store).get("/spending/total")

    assert answer.json() == {"spent_usd": 0.0, "ceiling_usd": 75.0}


def test_spending_total_counts_calls_made_outside_any_sim(sims, store):
    paid_call(sims, 1, 1.25)
    paid_call(sims, 2, 0.50)
    paid_call(sims, None, 0.25)  # the benchmark: a paid call with no sim

    answer = client_for(store).get("/spending/total")

    assert answer.json() == {"spent_usd": 2.0, "ceiling_usd": 75.0}


def test_no_sims_gives_an_empty_list(store):
    assert listed(store) == []


def test_the_holding_sim_is_never_a_line(sims, store):
    add_sim(sims, variant="buy_hold")

    assert listed(store) == []


def test_a_sim_halfway_is_shown_against_holding_at_the_same_moment(sims, store):
    holding = add_sim(sims, variant="buy_hold")
    sims.update(holding, STATUS="finished", LAST_COMPLETED_STEP=288)
    account_at(sims, holding, 192, 10_100.0)
    account_at(sims, holding, 288, 10_400.0)  # later than the sim has reached
    sim = add_sim(sims, SPENDING_CAP=1.50)
    sims.update(sim, STATUS="running", LAST_COMPLETED_STEP=192, LAST_WRITTEN_AT=NOW)
    account_at(sims, sim, 97, 10_000.0)
    account_at(sims, sim, 192, 10_250.0)
    order(sims, sim, 1, "entry")
    order(sims, sim, 1, "close")
    order(sims, sim, 2, "entry")
    order(sims, sim, 3, "entry", status="waiting")  # not carried out: not a trade yet
    paid_call(sims, sim, 0.30)
    paid_call(sims, sim, 0.20)

    [line] = listed(store)

    assert line["id"] == sim
    assert line["kind"] == "free"
    assert line["status"] == "running"
    assert (line["days_done"], line["days_total"]) == (1, 2)
    assert line["account_value"] == 10_250.0
    assert line["holding_value"] == 10_100.0
    assert line["trades"] == 2
    assert line["spent_usd"] == pytest.approx(0.50)
    assert line["spending_cap_usd"] == 1.50


def test_a_sim_shows_real_dates_and_real_names_with_masked_ids(sims, store):
    add_sim(sims)

    [line] = listed(store)

    # Step 1 is 1 March, so step 97 opens 2 March and step 288 ends 3 March.
    assert (line["first_day"], line["last_day"]) == ("2025-03-02", "2025-03-03")
    assert line["assets"] == [
        {"name": "Apple", "masked_id": "ASSET_01"},
        {"name": "Bitcoin", "masked_id": "ASSET_02"},
    ]


def running_at_192(sims, **columns):
    sim = add_sim(sims, **columns)
    sims.update(sim, STATUS="running", LAST_COMPLETED_STEP=192, LAST_WRITTEN_AT=NOW)
    account_at(sims, sim, 192, 10_250.0)
    return sim


def test_holding_that_has_not_reached_the_sim_shows_no_figure(sims, store):
    holding = add_sim(sims, variant="buy_hold")
    sims.update(holding, STATUS="running", LAST_COMPLETED_STEP=150)
    account_at(sims, holding, 150, 10_050.0)
    running_at_192(sims)

    assert listed(store)[0]["holding_value"] is None


def test_the_holding_sim_that_got_furthest_is_the_one_compared(sims, store):
    stopped = add_sim(sims, variant="buy_hold")
    sims.update(stopped, STATUS="stopped", LAST_COMPLETED_STEP=150)
    account_at(sims, stopped, 150, 10_050.0)
    finished = add_sim(sims, variant="buy_hold")
    sims.update(finished, STATUS="finished", LAST_COMPLETED_STEP=288)
    account_at(sims, finished, 192, 10_100.0)
    running_at_192(sims)

    assert listed(store)[0]["holding_value"] == 10_100.0


def test_holding_with_another_starting_amount_is_not_compared(sims, store):
    holding = add_sim(sims, variant="buy_hold", STARTING_VALUE=20_000.0)
    sims.update(holding, STATUS="finished", LAST_COMPLETED_STEP=288)
    account_at(sims, holding, 192, 20_200.0)
    running_at_192(sims)

    assert listed(store)[0]["holding_value"] is None


def test_a_line_carries_its_step_numbers(sims, store):
    add_sim(sims)

    [line] = listed(store)

    assert (line["first_step"], line["last_step"]) == (97, 288)


def test_days_are_utc_days_for_a_sim_starting_mid_day(sims, store):
    # Steps 90 to 200 touch days 1, 2 and 3; step 96 ends day 1.
    sim = add_sim(sims, FIRST_STEP=90, LAST_STEP=200)
    sims.update(sim, STATUS="running", LAST_COMPLETED_STEP=96, LAST_WRITTEN_AT=NOW)

    [line] = listed(store)

    assert (line["days_done"], line["days_total"]) == (1, 3)


def test_a_sim_not_started_is_worth_its_starting_value(sims, store):
    add_sim(sims)

    [line] = listed(store)

    assert line["account_value"] == 10_000.0
    assert line["holding_value"] is None
    assert line["days_done"] == 0


@pytest.mark.parametrize(
    ("quiet_for", "not_responding"),
    [(timedelta(minutes=6), False), (timedelta(minutes=8), True)],
)
def test_a_running_sim_quiet_for_7_minutes_is_not_responding(
    sims, store, quiet_for, not_responding
):
    sim = add_sim(sims)
    sims.update(sim, STATUS="running", LAST_WRITTEN_AT=NOW - quiet_for)

    [line] = listed(store)

    assert line["status"] == "running"
    assert line["not_responding"] is not_responding


def test_a_stopped_sim_is_never_not_responding(sims, store):
    sim = add_sim(sims)
    sims.update(sim, STATUS="stopped", LAST_WRITTEN_AT=NOW - timedelta(days=2))

    assert listed(store)[0]["not_responding"] is False


@pytest.mark.parametrize(
    ("restarted", "not_responding"),
    [(timedelta(minutes=1), False), (timedelta(minutes=8), True)],
)
def test_a_resumed_sim_is_quiet_from_when_its_job_restarted(
    sims, store, restarted, not_responding
):
    """Its last stored step is hours old; its job started again a moment ago."""
    sim = add_sim(sims)
    sims.update(
        sim,
        STATUS="running",
        LAST_WRITTEN_AT=NOW - timedelta(hours=2),
        STARTED_AT=NOW - restarted,
    )

    assert listed(store)[0]["not_responding"] is not_responding


def test_sims_come_in_kind_order(sims, store):
    for kind in ("practice", "free", "tuning", "build-up", "measurement"):
        add_sim(sims, kind=kind)

    assert [line["kind"] for line in listed(store)] == [
        "measurement",
        "build-up",
        "free",
        "tuning",
        "practice",
    ]
