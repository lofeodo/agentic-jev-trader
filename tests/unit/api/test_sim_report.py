"""The Trading sim page's report sections (spec appendix 7 section 5, appendix 8 section 8.2):
the trades table, the measurements and the scorecard, read over real HTTP requests from the
in-memory store. Nothing here is stored: each is worked out when asked for.

The made-up dataset 7 starts on 1 March 2025: step 96 ends at midnight UTC on 2 March, and each
step is 15 minutes later. Apple's prices were rescaled by 0.5 (a real $200 is stored as 100);
Bitcoin's by 0.001.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInLauncher

NOW = datetime(2026, 11, 23, 12, 0)
RISK = {
    "trade_risk_limit": 0.01,
    "size_buckets": [0.2, 0.4, 0.8, 1.2, 2.0],
    "daily_loss_limit": 0.05,
    "exposure_limit": 2.0,
}


def key_row(masked_id, name, scale):
    return {
        "DATASET": 7,
        "MASKED_ID": masked_id,
        "TICKER": name[:4].upper(),
        "NAME": name,
        "PRICE_SCALE": scale,
        "FIRST_DAY": date(2025, 3, 1),
    }


@pytest.fixture
def sims():
    return InMemorySimStore()


@pytest.fixture
def entries():
    """What the dataset measured at each (asset, step): filled in by the scorecard tests."""
    return {}


@pytest.fixture
def store(sims, entries):
    return InMemoryApiStore(
        sims,
        asset_key=[
            key_row("ASSET_01", "Apple", 0.5),
            key_row("ASSET_02", "Bitcoin", 0.001),
        ],
        entry_details={7: entries},
    )


@pytest.fixture
def api(store):
    return TestClient(
        create_app(
            store,
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            launcher=StandInLauncher(),
            clock=lambda: NOW,
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def add_sim(sims, variant="memory_off", status="finished", reached=288, **columns):
    """A sim over two days (steps 97 to 288) of dataset 7, with $10,000."""
    sim = sims.create(
        {
            "DATASET": 7,
            "KIND": "free",
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
    sims.update(sim, STATUS=status, LAST_COMPLETED_STEP=reached, LAST_WRITTEN_AT=NOW)
    return sim


def order(
    sims,
    sim_id,
    position,
    kind,
    side,
    step,
    units,
    price,
    asset="ASSET_01",
    reason="jev",
    fee=1.0,
    chosen=None,
    limited_by=None,
):
    """A carried-out order, decided at the step before it was carried out."""
    decided = step - 1
    sims.tables["SIM.ORDERS"].append(
        {
            "ID": f"{sim_id}-{decided}-{asset}-{len(sims.tables['SIM.ORDERS'])}",
            "SIM": sim_id,
            "POSITION": position,
            "INSTRUMENT": f"{asset}_SPOT",
            "DECISION": f"{sim_id}-{decided}-{asset}" if reason == "jev" else None,
            "KIND": kind,
            "REASON": reason,
            "SIDE": side,
            "STEP_DECIDED": decided,
            "STEP_CARRIED_OUT": step,
            "STATUS": "carried out",
            "UNITS": units,
            "PRICE": price,
            "VALUE": units * price,
            "COMMISSION_OR_TRADING_FEE": fee,
            "AMOUNT_CHOSEN": chosen if chosen is not None else units * price,
            "LIMITED_BY": limited_by,
        }
    )


def charge(sims, sim_id, step, kind, amount, position=None):
    sims.tables["SIM.CHARGES"].append(
        {
            "ID": f"{sim_id}-{step}-{kind}-{position or 'loan'}",
            "SIM": sim_id,
            "STEP": step,
            "KIND": kind,
            "POSITION": position,
            "CHARGED_ON": 1_000.0,
            "YEARLY_RATE": 0.05,
            "AMOUNT": amount,
        }
    )


def two_trades(sims):
    """A long in Apple that made money the same day, and a Bitcoin short kept overnight.

    Apple: 10 rescaled units bought at 100 ($1,000) and sold at 110 ($1,100), each with a $1
    commission: +$98. Bitcoin: 1 unit sold short at 60 ($60, trimmed by the trade risk limit from
    $2,000), bought back the next day at its stop price, 66, with fees of 6 cents each way and a
    1-cent borrow fee for the night: -$6.13.
    """
    sim = add_sim(sims)
    order(sims, sim, 1, "entry", "buy", 98, 10.0, 100.0)
    order(sims, sim, 1, "close", "sell", 120, 10.0, 110.0)
    order(
        sims,
        sim,
        2,
        "entry",
        "sell",
        130,
        1.0,
        60.0,
        asset="ASSET_02",
        fee=0.06,
        chosen=2_000.0,
        limited_by="trade_risk",
    )
    charge(sims, sim, 192, "borrow_fee", 0.01, position=2)
    order(
        sims,
        sim,
        2,
        "close",
        "buy",
        201,
        1.0,
        66.0,
        asset="ASSET_02",
        fee=0.06,
        reason="stop_price",
    )
    return sim


def test_the_trades_table_has_one_line_per_trade_with_its_result(sims, api):
    sim = two_trades(sims)

    table = api.get(f"/sims/{sim}/trades").json()

    assert table["total"] == 2
    apple, bitcoin = table["lines"]
    assert apple["kind"] == "trade"
    assert apple["decision"] == f"{sim}-97-ASSET_01"
    assert apple["asset"] == {"name": "Apple", "masked_id": "ASSET_01"}
    assert apple["direction"] == "long"
    assert apple["opened_at"] == "2025-03-02T00:30:00"
    assert apple["closed_at"] == "2025-03-02T06:00:00"
    assert apple["units"] == 5.0  # real shares: 10 rescaled units at a scale of 0.5
    assert apple["entry_price"] == {"real": 200.0, "rescaled": 100.0}
    assert apple["exit_price"] == {"real": 220.0, "rescaled": 110.0}
    assert apple["put_in_usd"] == 1_000.0
    assert apple["profit_usd"] == pytest.approx(98.0)
    assert apple["closing_reason"] == "jev"
    assert (apple["trimmed"], apple["held_overnight"]) == (False, False)

    assert bitcoin["direction"] == "short"
    assert bitcoin["profit_usd"] == pytest.approx(-6.13)
    assert bitcoin["trading_costs_usd"] == pytest.approx(0.13)
    assert bitcoin["closing_reason"] == "stop_price"
    assert (bitcoin["amount_chosen"], bitcoin["limited_by"]) == (2_000.0, "trade_risk")
    assert (bitcoin["trimmed"], bitcoin["held_overnight"]) == (True, True)


@pytest.mark.parametrize(
    ("ask", "kept"),
    [
        ({}, ["Apple", "Bitcoin"]),
        ({"lost_money": True}, ["Bitcoin"]),
        ({"trimmed": True}, ["Bitcoin"]),
        ({"stop_price": True}, ["Bitcoin"]),
        ({"overnight": True}, ["Bitcoin"]),
    ],
)
def test_each_filter_keeps_the_trades_it_names(sims, api, ask, kept):
    sim = two_trades(sims)

    table = api.get(f"/sims/{sim}/trades", params=ask).json()

    assert [line["asset"]["name"] for line in table["lines"]] == kept
    assert table["counts"] == {
        "trades": 2,
        "lost_money": 1,
        "trimmed": 1,
        "stop_price": 1,
        "overnight": 1,
        "no_trade": 0,
    }


def full_evaluation(
    sims, sim_id, step, asset, pick, action="nothing", limited_by=None, answers=None
):
    sims.tables["MEMORY.DECISIONS"].append(
        {
            "ID": f"{sim_id}-{step}-{asset}",
            "SIM": sim_id,
            "FIRST_WRITTEN_BY": sim_id,
            "DATASET": 7,
            "ASSET": asset,
            "STEP": step,
            "KIND": "full_evaluation",
            "TIER": 2,
            "SCREEN_ANSWER": 0.8,
            "SKIPPED_BECAUSE": None,
            "JEV_VERSION": "jev-1",
            "CANDIDATE_TRADES": [],
            "ANSWERS": answers or {},
            "PICK": pick,
            "RATING": 2.5,
            "SIZE_CHOSEN": None if pick == "no_trade" else 2_000.0,
            "SIZE_AFTER_TRIMMING": None if pick == "no_trade" else 0.0,
            "LIMITED_BY": limited_by,
            "ACTION": action,
        }
    )


def test_a_filter_adds_the_full_evaluations_that_ended_in_no_trade(sims, api):
    sim = two_trades(sims)
    full_evaluation(sims, sim, 97, "ASSET_01", "long_tight_stop", action="entry")
    full_evaluation(sims, sim, 110, "ASSET_02", "no_trade")
    full_evaluation(
        sims, sim, 125, "ASSET_01", "short_wide_stop", limited_by="daily_loss"
    )

    without = api.get(f"/sims/{sim}/trades").json()
    table = api.get(f"/sims/{sim}/trades", params={"no_trade": True}).json()

    assert without["total"] == 2
    assert without["counts"]["no_trade"] == 2
    assert [(line["kind"], line["decided_step"]) for line in table["lines"]] == [
        ("trade", 97),
        ("no trade", 110),
        ("no trade", 125),
        ("trade", 129),
    ]
    picked_nothing, limits_left_nothing = table["lines"][1], table["lines"][2]
    assert picked_nothing["pick"] == "no_trade"
    assert picked_nothing["direction"] is None
    assert picked_nothing["decision"] == f"{sim}-110-ASSET_02"
    assert picked_nothing["screen_answer"] == 0.8
    assert limits_left_nothing["direction"] == "short"
    assert limits_left_nothing["limited_by"] == "daily_loss"
    assert limits_left_nothing["amount_chosen"] == 2_000.0


def test_the_trades_table_comes_a_page_at_a_time(sims, api):
    sim = add_sim(sims)
    for n in range(1, 6):
        order(sims, sim, n, "entry", "buy", 100 + n, 1.0, 100.0)

    second = api.get(f"/sims/{sim}/trades", params={"page": 2, "page_size": 2}).json()

    assert second["total"] == 5
    assert [line["position"] for line in second["lines"]] == [3, 4]
    assert api.get(f"/sims/{sim}/trades", params={"page": 0}).status_code == 422


def test_an_open_trade_has_no_profit_and_counts_overnight_up_to_the_step_reached(
    sims, api
):
    sim = add_sim(sims, status="running", reached=150)
    order(sims, sim, 1, "entry", "buy", 98, 10.0, 100.0)  # day 2
    later = add_sim(sims, status="running", reached=200)  # day 3
    order(sims, later, 1, "entry", "buy", 98, 10.0, 100.0)

    [line] = api.get(f"/sims/{sim}/trades").json()["lines"]
    [kept_overnight] = api.get(f"/sims/{later}/trades").json()["lines"]

    assert (line["closed_step"], line["profit_usd"], line["exit_price"]) == (
        None,
        None,
        None,
    )
    assert line["held_overnight"] is False
    assert kept_overnight["held_overnight"] is True


def account(sims, sim_id, step, value, exposure=0.0, loss_reached=False):
    sims.tables["SIM.ACCOUNT_STEPS"].append(
        {
            "ID": f"{sim_id}-{step}",
            "SIM": sim_id,
            "STEP": step,
            "CASH": value,
            "LOAN": 0.0,
            "EXPOSURE": exposure,
            "ACCOUNT_VALUE": value,
            "START_OF_DAY_VALUE": 10_000.0,
            "DAILY_LOSS_REACHED": loss_reached,
        }
    )


def test_the_page_marks_loss_limit_days_loan_interest_and_forced_closes(sims, api):
    sim = add_sim(sims)
    for step, reached in ((110, False), (111, True), (112, True), (200, True)):
        account(sims, sim, step, 9_400.0, loss_reached=reached)
    charge(sims, sim, 192, "loan_interest", 1.37)
    order(sims, sim, 1, "entry", "buy", 98, 10.0, 100.0)
    order(sims, sim, 1, "close", "sell", 150, 10.0, 80.0, reason="forced_close")

    marks = api.get(f"/sims/{sim}/trades").json()["marks"]

    assert [(m["step"], m["kind"], m["amount_usd"]) for m in marks] == [
        (111, "daily loss limit reached", None),  # once a day
        (150, "forced close", None),
        (192, "loan interest paid", 1.37),
        (200, "daily loss limit reached", None),
    ]
    assert marks[0]["at"] == "2025-03-02T03:45:00"


def measured(asset_class, patterns, trend=0.5, volume=1.0, bar=10, bars_left=16):
    """What the dataset measured about an asset at the step a trade was decided."""
    return {
        "ASSET_CLASS": asset_class,
        "PATTERNS": patterns,
        "LONG_TERM_TREND": trend,
        "VOLUME_AGAINST_NORMAL": volume,
        "BAR_NUMBER": bar,
        "BARS_LEFT": None if asset_class == "crypto" else bars_left,
    }


def test_the_scorecard_counts_closed_trades_by_pattern_direction_and_asset_class(
    sims, entries, api
):
    sim = two_trades(sims)  # Apple decided at step 97, Bitcoin at 129
    entries[("ASSET_01", 97)] = measured("stock", ["bullish engulfing", "hammer"])
    entries[("ASSET_02", 129)] = measured("crypto", [])

    card = api.get(f"/sims/{sim}/scorecard").json()

    assert card["minimum_sample"] == 10
    assert card["closed_trades"] == 2
    lines = {(x["pattern"], x["direction"], x["asset_class"]): x for x in card["lines"]}
    assert set(lines) == {
        (
            "bullish engulfing",
            "long",
            "stock",
        ),  # one trade counts in each of its patterns
        ("hammer", "long", "stock"),
        ("none", "short", "crypto"),
    }
    engulfing = lines[("bullish engulfing", "long", "stock")]
    assert (engulfing["trades"], engulfing["made_money"]) == (1, 1)
    assert engulfing["share_made_money"] == 1.0
    assert engulfing["average_gain"] == pytest.approx(98.0)
    assert engulfing["average_loss"] is None
    assert engulfing["shown_to_agent"] is False  # under 10 closed trades
    assert lines[("none", "short", "crypto")]["average_loss"] == pytest.approx(-6.13)


def test_a_group_of_ten_closed_trades_is_shown_to_the_agent(sims, entries, api):
    sim = add_sim(sims)
    for n in range(11):  # ten closed, and one still open that does not count yet
        order(sims, sim, n, "entry", "buy", 100 + 2 * n, 1.0, 100.0)
        if n < 10:
            order(sims, sim, n, "close", "sell", 101 + 2 * n, 1.0, 100.0 + n)
        entries[("ASSET_01", 99 + 2 * n)] = measured("stock", ["hammer"])

    [line] = api.get(f"/sims/{sim}/scorecard").json()["lines"]

    assert line["trades"] == 10
    assert line["shown_to_agent"] is True
    # Bought at 100, sold at 100 to 109, less $2 of commissions: -$2 to +$7; 7 made money.
    assert line["made_money"] == 7
    assert line["total_profit"] == pytest.approx(25.0)


def test_a_group_under_ten_shows_the_broader_group_the_agent_reads_instead(
    sims, entries, api
):
    sim = add_sim(sims)
    for n in range(12):  # 11 longs above the 20-day average, one below it
        order(sims, sim, n, "entry", "buy", 100 + 2 * n, 1.0, 100.0)
        order(sims, sim, n, "close", "sell", 101 + 2 * n, 1.0, 105.0)
        trend = -0.5 if n == 0 else 0.5
        entries[("ASSET_01", 99 + 2 * n)] = measured("stock", ["hammer"], trend=trend)

    card = api.get(f"/sims/{sim}/scorecard", params={"split": ["trend"]}).json()

    assert card["on_ladder"] is True
    lines = {x["trend"]: x for x in card["lines"]}
    with_trend, against = lines["with the trend"], lines["against the trend"]
    assert (with_trend["trades"], with_trend["shown_to_agent"]) == (11, True)
    assert with_trend["falls_back_to"] is None
    # One trade against the trend: the agent reads hammer, long, stock (12 trades) instead.
    assert (against["trades"], against["shown_to_agent"]) == (1, False)
    assert against["falls_back_to"] == {"split": [], "trades": 12}
    # A split the agent's ladder never forms has no fallback to show.
    by_volume = api.get(f"/sims/{sim}/scorecard", params={"split": ["volume"]}).json()
    assert by_volume["on_ladder"] is False
    assert {x["falls_back_to"] for x in by_volume["lines"]} == {None}


def test_with_fewer_than_ten_at_every_level_the_agent_reads_only_the_count(
    sims, entries, api
):
    sim = two_trades(sims)
    entries[("ASSET_01", 97)] = measured("stock", ["hammer"])
    entries[("ASSET_02", 129)] = measured("crypto", [])

    card = api.get(
        f"/sims/{sim}/scorecard", params={"split": ["trend", "volume"]}
    ).json()

    assert {x["falls_back_to"] is None for x in card["lines"]} == {True}
    assert {x["shown_to_agent"] for x in card["lines"]} == {False}


def test_a_scorecard_line_can_be_split_by_trend_volume_and_part_of_day(
    sims, entries, api
):
    sim = two_trades(sims)
    entries[("ASSET_01", 97)] = measured(
        "stock", ["hammer"], trend=0.4, volume=1.2, bar=2
    )
    entries[("ASSET_02", 129)] = measured(
        "crypto", ["doji"], trend=0.3, volume=0.95, bar=33
    )

    card = api.get(
        f"/sims/{sim}/scorecard", params={"split": ["trend", "volume", "part_of_day"]}
    ).json()

    assert card["split"] == ["trend", "volume", "part_of_day"]
    details = {
        x["pattern"]: (x["trend"], x["volume_level"], x["part_of_day"])
        for x in card["lines"]
    }
    # A long above its 20-day average is with the trend; a short above it is against it.
    assert details == {
        "hammer": ("with the trend", "high", "first hour"),
        "doji": ("against the trend", "average", "European hours"),
    }
    plain = api.get(f"/sims/{sim}/scorecard").json()["lines"]
    assert {(x["trend"], x["volume_level"], x["part_of_day"]) for x in plain} == {
        (None, None, None)
    }


def two_days(sims, sim, holding):
    """Day 2 (steps 97 to 192) and day 3 (193 to 288).

    The sim: $10,000, up to $10,300, $10,200 at midnight (+$200 on the day), down to $9,900,
    and $10,100 at the end (-$100 on the day). Holding: $10,100, then $10,050.
    """
    for step, value, exposure in (
        (97, 10_000.0, 0.0),
        (150, 10_300.0, 5_000.0),
        (192, 10_200.0, 0.0),
        (250, 9_900.0, 1_000.0),
        (288, 10_100.0, 0.0),
    ):
        account(sims, sim, step, value, exposure=exposure)
    for step, value in ((97, 10_000.0), (192, 10_100.0), (288, 10_050.0)):
        account(sims, holding, step, value, exposure=value)


def figure(measurements, group, key):
    [found] = [
        f
        for g in measurements["groups"]
        if g["key"] == group
        for f in g["figures"]
        if f["key"] == key
    ]
    return found


def breakdown(measurements, group, key):
    [found] = [
        b
        for g in measurements["groups"]
        if g["key"] == group
        for b in g["breakdowns"]
        if b["key"] == key
    ]
    return {row["label"]: (row["trades"], row["value"]) for row in found["rows"]}


def test_the_measurements_come_in_six_groups_each_beside_holding(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = add_sim(sims)
    two_days(sims, sim, holding)

    m = api.get(f"/sims/{sim}/measurements").json()

    assert m["holding_sim_id"] == holding
    assert [g["key"] for g in m["groups"]] == [
        "money",
        "ride",
        "trader",
        "trades",
        "confidence",
        "memory",
    ]
    profit = figure(m, "money", "profit")
    assert (profit["sim"], profit["holding"]) == (100.0, 50.0)
    assert profit["says"] == (
        "Since the start the account is +$100: from $10,000 to $10,100."
    )
    assert profit["name"] == "Profit"  # the trader's term, shown in small type


def test_how_wild_the_ride_is(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = add_sim(sims)
    two_days(sims, sim, holding)

    m = api.get(f"/sims/{sim}/measurements").json()

    def sim_value(key):
        return figure(m, "ride", key)["sim"]

    assert (sim_value("best_day"), sim_value("worst_day")) == (200.0, -100.0)
    assert (sim_value("highest"), sim_value("lowest")) == (10_300.0, 9_900.0)
    # From its high of $10,300 down to $9,900, and not yet back above it.
    assert sim_value("biggest_drop") == -400.0
    assert sim_value("days_to_climb_back") is None
    assert sim_value("share_of_days_up") == 0.5
    # Daily changes of +$200 and -$100 spread 212 dollars apart (standard deviation).
    assert sim_value("daily_swing") == pytest.approx(212.13, abs=0.01)
    assert figure(m, "ride", "best_day")["holding"] == 100.0


def test_the_days_taken_to_climb_back_after_the_biggest_drop(sims, api):
    sim = add_sim(sims)
    # A high of $10,300 on day 2, down to $9,800, back above it on day 3, then a smaller dip.
    for step, value in (
        (97, 10_000.0),
        (150, 10_300.0),
        (180, 9_800.0),
        (250, 10_400.0),
        (280, 10_200.0),
    ):
        account(sims, sim, step, value)

    m = api.get(f"/sims/{sim}/measurements").json()

    assert figure(m, "ride", "biggest_drop")["sim"] == -500.0
    assert figure(m, "ride", "days_to_climb_back")["sim"] == 1
    assert m["holding_sim_id"] is None
    assert figure(m, "ride", "best_day")["holding"] is None


def test_what_kind_of_trader_it_is(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = two_trades(sims)
    two_days(sims, sim, holding)
    for step in (100, 101, 102):
        decision_row = {
            "ID": f"{sim}-{step}-ASSET_01",
            "SIM": sim,
            "FIRST_WRITTEN_BY": sim,
            "DATASET": 7,
            "ASSET": "ASSET_01",
            "STEP": step,
            "KIND": "screen",
            "TIER": 1,
            "SCREEN_ANSWER": 0.2,
            "SKIPPED_BECAUSE": None,
            "ACTION": "nothing",
        }
        sims.tables["MEMORY.DECISIONS"].append(decision_row)
    full_evaluation(sims, sim, 97, "ASSET_01", "long_tight_stop", action="entry")
    full_evaluation(sims, sim, 129, "ASSET_02", "short_wide_stop", action="entry")

    m = api.get(f"/sims/{sim}/measurements").json()

    assert figure(m, "trader", "trades_per_day")["sim"] == 1.0  # 2 trades in 2 days
    assert figure(m, "trader", "share_long")["sim"] == 0.5
    # Apple held 22 steps (5.5 hours), Bitcoin 71 (17.75 hours).
    assert figure(m, "trader", "average_hold_hours")["sim"] == pytest.approx(11.625)
    assert figure(m, "trader", "share_closed_same_day")["sim"] == 0.5
    assert figure(m, "trader", "average_trade_size")["sim"] == pytest.approx(530.0)
    # 5 screens answered, 2 led to a full evaluation, both to a trade.
    assert figure(m, "trader", "screens_to_full_evaluation")["sim"] == 0.4
    assert figure(m, "trader", "full_evaluations_to_trade")["sim"] == 1.0
    assert figure(m, "trader", "trades_trimmed")["sim"] == 1
    # Time invested: 2 of the 5 stored steps held something.
    assert figure(m, "trader", "share_of_time_invested")["sim"] == 0.4
    assert breakdown(m, "trader", "how_trades_end") == {
        "Jev chose to close it": (1, None),
        "Its stop price was reached": (1, None),
    }
    assert breakdown(m, "trader", "time_of_day") == {
        "00:00 UTC": (1, None),
        "08:00 UTC": (1, None),
    }


def test_the_trades_measurements_and_jev_s_confidence(sims, entries, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = two_trades(sims)
    two_days(sims, sim, holding)
    entries[("ASSET_01", 97)] = measured("stock", ["hammer"])
    entries[("ASSET_02", 129)] = measured("crypto", [])
    # Jev put 75% on a rise for Apple (it made money), 62% on a fall for Bitcoin (it lost).
    pick_long = {"long_tight_stop": 0.5, "long_medium_stop": 0.25, "no_trade": 0.25}
    pick_short = {"short_wide_stop": 0.62, "long_tight_stop": 0.38}
    full_evaluation(
        sims,
        sim,
        97,
        "ASSET_01",
        "long_tight_stop",
        action="entry",
        answers={"pick_1": pick_long, "pick_2": pick_long},
    )
    full_evaluation(
        sims,
        sim,
        129,
        "ASSET_02",
        "short_wide_stop",
        action="entry",
        answers={"pick_1": pick_short},
    )

    m = api.get(f"/sims/{sim}/measurements").json()

    assert figure(m, "trades", "trades")["sim"] == 2
    assert figure(m, "trades", "share_made_money")["sim"] == 0.5
    assert figure(m, "trades", "average_gain")["sim"] == pytest.approx(98.0)
    assert figure(m, "trades", "average_loss")["sim"] == pytest.approx(-6.13)
    assert figure(m, "trades", "gains_over_losses")["sim"] == pytest.approx(98 / 6.13)
    assert breakdown(m, "trades", "by_asset") == {
        "Apple": (1, pytest.approx(98.0)),
        "Bitcoin": (1, pytest.approx(-6.13)),
    }
    assert breakdown(m, "trades", "by_pattern") == {
        "hammer": (1, pytest.approx(98.0)),
        "none": (1, pytest.approx(-6.13)),
    }
    assert breakdown(m, "confidence", "calibration") == {
        "60-70%": (1, 0.0),
        "70-80%": (1, 1.0),
    }
    assert figure(m, "confidence", "average_confidence")["sim"] == pytest.approx(0.685)


def test_the_memory_measurements_wait_for_a_sim_with_memory(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = add_sim(sims)
    two_days(sims, sim, holding)

    m = api.get(f"/sims/{sim}/measurements").json()

    took_top = figure(m, "memory", "took_top_results")
    assert took_top["sim"] is None
    assert "no memory" in took_top["says"]
    assert figure(m, "memory", "profit_per_day")["sim"] == 50.0


def test_holding_is_measured_only_as_far_as_the_sim_has_reached(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = add_sim(sims, status="running", reached=192)
    two_days(sims, sim, holding)

    m = api.get(f"/sims/{sim}/measurements").json()

    assert m["through_step"] == 192
    assert figure(m, "money", "ending_value")["holding"] == 10_100.0


def test_a_finished_sim_s_report_is_worked_out_once(sims, api):
    sim = two_trades(sims)
    running = add_sim(sims, status="running", reached=150)
    first = api.get(f"/sims/{sim}/trades").json()
    api.get(f"/sims/{running}/trades")

    order(sims, sim, 3, "entry", "buy", 250, 1.0, 100.0)  # cannot happen: it finished
    order(sims, running, 1, "entry", "buy", 140, 1.0, 100.0)

    assert api.get(f"/sims/{sim}/trades").json() == first
    assert api.get(f"/sims/{running}/trades").json()["total"] == 1


def test_a_report_worked_out_while_the_sim_finished_is_not_kept(
    sims, store, api, monkeypatch
):
    sim = add_sim(sims, status="running", reached=280)
    read_orders = store.orders

    def orders_as_it_finishes(sim_id):
        found = read_orders(sim_id)
        sims.update(
            sim, STATUS="finished"
        )  # it finishes while the report is worked out
        return found

    monkeypatch.setattr(store, "orders", orders_as_it_finishes)
    api.get(f"/sims/{sim}/trades")
    monkeypatch.setattr(store, "orders", read_orders)
    order(sims, sim, 1, "entry", "buy", 285, 1.0, 100.0)  # its last steps' records

    assert api.get(f"/sims/{sim}/trades").json()["total"] == 1


def test_a_sim_that_never_fell_has_no_recovery_time(sims, api):
    sim = add_sim(sims)
    for step, value in ((97, 10_000.0), (150, 10_100.0), (288, 10_200.0)):
        account(sims, sim, step, value)

    m = api.get(f"/sims/{sim}/measurements").json()

    recovery = figure(m, "ride", "days_to_climb_back")
    assert recovery["sim"] is None
    assert recovery["says"] == "It never fell below a high it had reached."


def test_only_the_track_record_s_own_groups_are_shown_to_the_agent(sims, entries, api):
    """The agent reads groups narrowed in one order: trend, then volume, then part of day."""
    sim = add_sim(sims)
    for n in range(10):
        order(sims, sim, n, "entry", "buy", 100 + 2 * n, 1.0, 100.0)
        order(sims, sim, n, "close", "sell", 101 + 2 * n, 1.0, 101.0)
        entries[("ASSET_01", 99 + 2 * n)] = measured("stock", ["hammer"])

    def shown(split):
        [line] = api.get(f"/sims/{sim}/scorecard", params={"split": split}).json()[
            "lines"
        ]
        return line["shown_to_agent"]

    assert shown(["trend"]) is True
    assert shown(["trend", "volume"]) is True
    assert shown(["volume"]) is False  # not a group the agent is ever shown
    assert shown(["trend", "part_of_day"]) is False


def test_trades_per_asset_are_counted_per_day(sims, api):
    holding = add_sim(sims, variant="buy_hold")
    sim = two_trades(sims)
    two_days(sims, sim, holding)

    m = api.get(f"/sims/{sim}/measurements").json()

    # One trade each over two days: half a trade a day.
    assert breakdown(m, "trader", "trades_per_asset") == {
        "Apple": (1, 0.5),
        "Bitcoin": (1, 0.5),
    }
