"""The Trading sim page's reads (spec appendix 7 section 5, appendix 8 sections 8.2 and 8.9),
as the web app sees them: real HTTP requests, answered from the in-memory store.

The made-up dataset 7 starts on 1 March 2025, so step 96 ends at midnight UTC on 2 March and
each step is 15 minutes later. Apple's prices were rescaled by 0.5 (a real $200 is stored as
100); Bitcoin's by 0.001.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.sim.store import InMemorySimStore

NOW = datetime(2026, 11, 23, 12, 0)
RISK = {"daily_loss_limit": 0.05, "exposure_limit": 2.0}


@pytest.fixture
def sims():
    return InMemorySimStore()


def key_row(masked_id, name, ticker, scale):
    return {
        "DATASET": 7,
        "MASKED_ID": masked_id,
        "TICKER": ticker,
        "NAME": name,
        "PRICE_SCALE": scale,
        "FIRST_DAY": date(2025, 3, 1),
    }


@pytest.fixture
def store(sims):
    return InMemoryApiStore(
        sims,
        asset_key=[
            key_row("ASSET_01", "Apple", "AAPL", 0.5),
            key_row("ASSET_02", "Bitcoin", "BTC", 0.001),
        ],
        closes={
            7: {
                "ASSET_01": {100: 100.0, 140: 110.0},
                "ASSET_02": {100: 60.0, 140: 66.0},
            }
        },
    )


@pytest.fixture
def api(store):
    return TestClient(
        create_app(
            store,
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            clock=lambda: NOW,
            moment_window_steps=4,
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
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
            "SPENDING_CAP": 1.5,
            "ESTIMATED_COST": 1.0,
            "SETTINGS": {"starting_value": 10_000.0, "risk_profile": RISK},
            **columns,
        }
    )


def test_a_sim_s_header_has_its_name_status_days_and_settings(sims, api):
    sim = add_sim(sims)
    sims.update(sim, STATUS="running", LAST_COMPLETED_STEP=140, LAST_WRITTEN_AT=NOW)

    header = api.get(f"/sims/{sim}").json()

    assert header["name"] == f"Sim {sim} / without memory"
    assert header["status"] == "running"
    assert header["in_progress"] is True
    assert (header["first_day"], header["last_day"]) == ("2025-03-02", "2025-03-03")
    # Step 0 ends at midnight on the dataset's first day; step 140 ends at 11:00 on 2 March.
    assert header["steps_start_at"] == "2025-03-01T00:00:00"
    assert header["step_reached"] == 140
    assert header["replayed_at"] == "2025-03-02T11:00:00"
    assert header["settings"]["risk_profile"] == RISK
    assert header["spending_cap_usd"] == 1.5
    assert [a["name"] for a in header["assets"]] == ["Apple", "Bitcoin"]


def test_an_unknown_sim_is_not_found(api):
    assert api.get("/sims/99").status_code == 404


def account(sims, sim_id, step, value, **columns):
    sims.tables["SIM.ACCOUNT_STEPS"].append(
        {
            "ID": f"{sim_id}-{step}",
            "SIM": sim_id,
            "STEP": step,
            "CASH": value,
            "LOAN": 0.0,
            "EXPOSURE": 0.0,
            "ACCOUNT_VALUE": value,
            "START_OF_DAY_VALUE": 10_000.0,
            "DAILY_LOSS_REACHED": False,
            **columns,
        }
    )


def fill(sims, sim_id, position, kind, side, step, units, price, asset="ASSET_01"):
    """A carried-out order, decided at the step before it was carried out."""
    sims.tables["SIM.ORDERS"].append(
        {
            "ID": f"{sim_id}-{step - 1}-{asset}-{len(sims.tables['SIM.ORDERS'])}",
            "SIM": sim_id,
            "POSITION": position,
            "INSTRUMENT": f"{asset}_SPOT",
            "KIND": kind,
            "REASON": "jev",
            "SIDE": side,
            "STEP_DECIDED": step - 1,
            "STEP_CARRIED_OUT": step,
            "STATUS": "carried out",
            "UNITS": units,
            "PRICE": price,
            "VALUE": units * price,
            "AMOUNT_CHOSEN": units * price,
            "LIMITED_BY": None,
        }
    )


def test_the_chart_draws_the_sim_holding_and_the_sim_over_the_same_days(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    account(sims, holding, 97, 10_000.0)
    account(sims, holding, 98, 10_010.0)
    sim = add_sim(sims)
    account(sims, sim, 97, 10_000.0)
    account(sims, sim, 98, 9_990.0)
    partner = add_sim(sims, variant="memory_on")
    account(sims, partner, 97, 10_000.0)
    add_sim(sims, FIRST_STEP=193)  # other days: not drawn
    fill(sims, sim, 1, "entry", "buy", 98, 10.0, 100.0)
    fill(sims, sim, 1, "close", "sell", 120, 10.0, 101.0)
    fill(sims, sim, 2, "entry", "sell", 130, 1.0, 60.0, asset="ASSET_02")

    chart = api.get(f"/sims/{sim}/chart").json()

    lines = {line["role"]: line for line in chart["lines"]}
    assert set(lines) == {"sim", "holding", "same days"}
    assert lines["sim"]["points"] == [
        {"step": 97, "value": 10_000.0},
        {"step": 98, "value": 9_990.0},
    ]
    assert lines["holding"]["sim_id"] == holding
    assert lines["holding"]["label"] == "Holding the five assets"
    assert lines["same days"]["sim_id"] == partner
    assert lines["same days"]["label"] == "With memory"
    assert chart["starting_value"] == 10_000.0
    assert chart["window_steps"] == 4  # what "nearby" means when hovering
    assert chart["ticks"] == [
        {
            "position": 1,
            "asset": {"name": "Apple", "masked_id": "ASSET_01"},
            "direction": "long",
            "opened_step": 98,
            "closed_step": 120,
        },
        {
            "position": 2,
            "asset": {"name": "Bitcoin", "masked_id": "ASSET_02"},
            "direction": "short",
            "opened_step": 130,
            "closed_step": None,
        },
    ]


def held_apple(units=10.0, average=100.0, cash_flow=-1_001.0):
    """A long position in Apple, as the saved account holds it (rescaled prices)."""
    return {
        "position_id": 1,
        "asset": "ASSET_01",
        "direction": "long",
        "stop_price": 97.0,
        "step_opened": 98,
        "entry_price": average,
        "average_price": average,
        "units": units,
        "cash_flow": cash_flow,  # paid $1,000 and a $1 commission
        "trading_costs": 1.0,
        "amount_chosen": 2_000.0,
        "amount_entered": 1_000.0,
        "limited_by": "trade_risk",
    }


def running_sim_at_140(sims):
    """A sim that has stored up to step 140 (11:00 on 2 March), holding one Apple position."""
    holding = add_sim(sims, variant="buy_hold")
    sims.update(holding, STATUS="running", LAST_COMPLETED_STEP=140)
    account(sims, holding, 120, 10_050.0)
    account(sims, holding, 140, 10_100.0)
    sim = add_sim(sims)
    sims.update(
        sim,
        STATUS="running",
        LAST_COMPLETED_STEP=140,
        LAST_WRITTEN_AT=NOW,
        ACCOUNT_STATE={
            "cash": 9_200.0,
            "positions": [held_apple()],
            "last_prices": {"ASSET_01": 110.0},
            "start_of_day_value": 10_000.0,
            "daily_loss_reached": False,
        },
    )
    account(sims, sim, 120, 10_000.0)
    account(sims, sim, 140, 10_300.0, EXPOSURE=4_000.0, START_OF_DAY_VALUE=10_000.0)
    fill(sims, sim, 1, "entry", "buy", 98, 10.0, 100.0)
    fill(sims, sim, 2, "entry", "sell", 130, 1.0, 60.0, asset="ASSET_02")
    fill(sims, sim, 2, "close", "buy", 135, 1.0, 59.0, asset="ASSET_02")
    sims.tables["SIM.CALLS"].append({"ID": "c1", "SIM": sim, "COST_USD": 0.5})
    sims.tables["SIM.SIM_EVENTS"].append(
        {
            "ID": f"{sim}-139-restarted-1",
            "SIM": sim,
            "STEP": 139,
            "KIND": "restarted",
            "DETAILS": {"after_step": 138},
        }
    )
    return sim, holding


def test_the_live_figures_carry_the_key_figures_and_the_three_meters(sims, api):
    sim, _ = running_sim_at_140(sims)

    live = api.get(f"/sims/{sim}/live").json()

    assert live["status"] == "running"
    assert live["in_progress"] is True
    assert live["step_reached"] == 140
    assert live["replayed_at"] == "2025-03-02T11:00:00"
    assert live["account_value"] == 10_300.0
    assert live["holding_value"] == 10_100.0
    assert live["trades"] == 2
    assert live["spent_usd"] == 0.5
    assert live["spending_cap_usd"] == 1.5
    assert [(t["position"], t["closed_step"]) for t in live["ticks"]] == [
        (1, None),
        (2, 135),
    ]
    # Up $300 since midnight; the daily loss limit is 5% of $10,000, so $500 may be lost.
    assert live["meters"] == {
        "day_change": 300.0,
        "daily_loss_limit_usd": 500.0,
        "daily_loss_reached": False,
        "held_usd": 4_000.0,
        "exposure_limit_usd": 20_600.0,
    }


def test_the_live_figures_carry_the_open_positions_in_real_prices(sims, api):
    sim, _ = running_sim_at_140(sims)

    [position] = api.get(f"/sims/{sim}/live").json()["open_positions"]

    # Apple's scale is 0.5: 10 rescaled units at 100 are 5 real shares at $200.
    assert position == {
        "position": 1,
        "asset": {"name": "Apple", "masked_id": "ASSET_01"},
        "direction": "long",
        "units": 5.0,
        "entry_price": {"real": 200.0, "rescaled": 100.0},
        "price_now": {"real": 220.0, "rescaled": 110.0},
        "stop_price": {"real": 194.0, "rescaled": 97.0},
        "value_usd": 1_100.0,
        "profit_so_far": 99.0,  # worth $1,100 now, after paying $1,001
        "opened_step": 98,
        "opened_at": "2025-03-02T00:30:00",
        "amount_chosen": 2_000.0,
        "limited_by": "trade_risk",
    }


def test_the_live_figures_carry_the_latest_orders_and_notable_moments(sims, api):
    sim, _ = running_sim_at_140(sims)

    live = api.get(f"/sims/{sim}/live").json()

    assert [(o["kind"], o["asset"]["name"]) for o in live["latest_orders"]] == [
        ("close", "Bitcoin"),
        ("entry", "Bitcoin"),
        ("entry", "Apple"),
    ]
    assert live["latest_orders"][0]["decided_at"] == "2025-03-02T09:30:00"
    assert live["notable_moments"] == [
        {
            "step": 139,
            "at": "2025-03-02T10:45:00",
            "kind": "restarted",
            "details": {"after_step": 138},
        }
    ]


def decision(sims, sim_id, step, asset, answer=None, skipped_because=None):
    sims.tables["MEMORY.DECISIONS"].append(
        {
            "ID": f"{sim_id}-{step}-{asset}",
            "SIM": sim_id,
            "FIRST_WRITTEN_BY": sim_id,
            "DATASET": 7,
            "ASSET": asset,
            "STEP": step,
            "KIND": "screen",
            "TIER": 0 if answer is None else 1,
            "SCREEN_ANSWER": answer,
            "SKIPPED_BECAUSE": skipped_because,
            "JEV_VERSION": None,
            "ACTION": "nothing",
        }
    )


def test_the_live_figures_carry_the_latest_decisions_newest_first(sims, api):
    sim, _ = running_sim_at_140(sims)
    decision(sims, sim, 139, "ASSET_01", answer=0.12)
    decision(sims, sim, 140, "ASSET_02", answer=0.31)
    decision(sims, sim, 140, "ASSET_01", skipped_because="session_end")

    latest = api.get(f"/sims/{sim}/live").json()["latest_decisions"]

    assert [(d["step"], d["asset"]["name"]) for d in latest] == [
        (140, "Apple"),
        (140, "Bitcoin"),
        (139, "Apple"),
    ]
    assert latest[0] == {
        "step": 140,
        "at": "2025-03-02T11:00:00",
        "asset": {"name": "Apple", "masked_id": "ASSET_01"},
        "kind": "screen",
        "tier": 0,
        "screen_answer": None,
        "skipped_because": "session_end",
        "action": "nothing",
    }
    assert latest[1]["screen_answer"] == 0.31


def test_the_live_figures_carry_only_the_chart_points_after_the_last_asked(sims, api):
    sim, holding = running_sim_at_140(sims)

    live = api.get(f"/sims/{sim}/live", params={"after_step": 120}).json()

    assert {(p["sim_id"], p["step"], p["value"]) for p in live["new_points"]} == {
        (sim, 140, 10_300.0),
        (holding, 140, 10_100.0),
    }


def test_a_finished_sim_is_not_in_progress(sims, api):
    sim = add_sim(sims)
    sims.update(sim, STATUS="finished", LAST_COMPLETED_STEP=288)

    live = api.get(f"/sims/{sim}/live").json()

    assert live["in_progress"] is False
    assert live["open_positions"] == []


def test_a_sim_with_no_risk_profile_has_no_limits_on_its_meters(sims, api):
    sim = add_sim(sims, SETTINGS={"risk_profile": None})

    meters = api.get(f"/sims/{sim}/live").json()["meters"]

    assert meters["daily_loss_limit_usd"] is None
    assert meters["exposure_limit_usd"] is None


def test_a_moment_shows_the_account_and_the_positions_it_held_then(sims, api):
    sim, _ = running_sim_at_140(sims)

    # 08:20 falls inside step 130, so the moment is step 129, which ends at 08:15.
    moment = api.get(f"/sims/{sim}/moment", params={"at": "2025-03-02T08:20:00"}).json()

    assert moment["step"] == 129
    assert moment["at"] == "2025-03-02T08:15:00"
    assert moment["account"]["account_value"] == 10_000.0  # last stored at step 120
    assert moment["holding_value"] == 10_050.0
    assert moment["since_start"] == 0.0
    [apple] = moment["positions"]  # the Bitcoin short opens at step 130, after it
    assert apple["asset"]["name"] == "Apple"
    assert apple["direction"] == "long"
    assert apple["units"] == 5.0
    assert apple["price_then"] == {"real": 200.0, "rescaled": 100.0}
    assert apple["value_usd"] == 1_000.0


def test_a_moment_lists_the_trades_opened_or_closed_around_then(sims, api):
    sim, _ = running_sim_at_140(sims)

    moment = api.get(f"/sims/{sim}/moment", params={"at": "2025-03-02T08:20:00"}).json()

    # 4 steps either side of step 129: the Bitcoin short opened at 130; it closed at 135.
    assert moment["window_steps"] == 4
    assert [(t["kind"], t["step_carried_out"]) for t in moment["nearby"]] == [
        ("entry", 130)
    ]


def test_a_moment_before_the_sim_starts_is_its_first_step(sims, api):
    sim, _ = running_sim_at_140(sims)

    moment = api.get(f"/sims/{sim}/moment", params={"at": "2025-03-01T05:00:00"}).json()

    assert moment["step"] == 97
    assert moment["positions"] == []


def test_a_moment_after_the_step_reached_is_the_step_reached(sims, api):
    sim, _ = running_sim_at_140(sims)

    moment = api.get(f"/sims/{sim}/moment", params={"at": "2025-03-03T12:00:00"}).json()

    assert moment["step"] == 140  # the replay has not got further: no later prices


def test_a_moment_shows_no_holding_figure_before_holding_reaches_it(sims, api):
    sim, holding = running_sim_at_140(sims)
    sims.update(holding, LAST_COMPLETED_STEP=125)  # holding has stored only up to 125

    moment = api.get(f"/sims/{sim}/moment", params={"at": "2025-03-02T08:20:00"}).json()

    assert moment["holding_value"] is None


def test_a_moment_can_be_asked_for_with_a_time_zone(sims, api):
    sim, _ = running_sim_at_140(sims)

    moment = api.get(
        f"/sims/{sim}/moment", params={"at": "2025-03-02T08:20:00Z"}
    ).json()

    assert moment["step"] == 129


def test_a_measurement_sim_is_drawn_beside_the_other_two_of_its_repeat(sims, api):
    def measurement(variant, repeat):
        return add_sim(
            sims,
            variant=variant,
            kind="measurement",
            MARKET="falling market",
            REPEAT_NUMBER=repeat,
        )

    sim = measurement("memory_on", 1)
    same_repeat = [measurement("memory_on", 1), measurement("memory_off", 1)]
    measurement("memory_off", 2)  # another repeat: not drawn

    chart = api.get(f"/sims/{sim}/chart").json()

    drawn = [line["sim_id"] for line in chart["lines"] if line["role"] == "same days"]
    assert drawn == same_repeat
