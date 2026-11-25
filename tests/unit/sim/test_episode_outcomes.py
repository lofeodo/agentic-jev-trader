"""Episode outcomes: what happened after each full evaluation and position review (spec appendix 5
section 1; appendix 6 section 3.5).

Runs a practice sim (day 2, steps 97 to 192) on the in-memory store. The crypto's price climbs 10
cents a bar from $100 at step 97 ($100.10 at step 98, $109.50 at step 192), each bar opening and
closing at the same price, so every outcome has its own number. The crypto is bought at step 97
and carried out at step 98's open: $4,000 at $100.15005 (slippage), plus a $4 fee.
"""

import pytest

from jev_trader.broker import Bar
from jev_trader.memory.outcomes import searchable
from jev_trader.sim.market import InMemoryMarket
from jev_trader.sim.runner import run_sim
from jev_trader.sim.store import InMemorySimStore
from tests.unit.sim.conftest import CRYPTO, DATASET, LAST_STEP, STOCK
from tests.unit.sim.test_agent_without_memory import (
    SCREENS_ASKED,
    crypto_decisions,
    fake_jev,
    practice,
    with_snapshots,
)


def price(step: int) -> float:
    return 100.0 + 0.1 * (step - 97) if step >= 97 else 100.0


@pytest.fixture
def rising_market(market):
    bars = dict(market.bars_by_asset[DATASET])
    bars[CRYPTO] = [
        Bar(step=s, open=price(s), high=price(s), low=price(s), close=price(s))
        for s in range(1, LAST_STEP + 1)
    ]
    return with_snapshots(InMemoryMarket(market.datasets, {DATASET: bars}))


def outcomes_of(store, sim_id, decision):
    return {
        o["KIND"]: o
        for o in store.rows("MEMORY.OUTCOMES", sim_id)
        if o["DECISION"] == decision["ID"]
    }


def reviewing_twice():
    """Opens a long in the crypto at step 97; reviews it at step 98 (hold) and step 102 (close).

    The close is carried out at step 103's open."""
    return fake_jev(
        lambda n: 0.9 if n == 1 else 0.3,
        pick={"long_tight_stop": 1.0},
        position_screen=lambda n: 0.9 if n in (1, 5) else 0.3,
        action=lambda n: {"hold": 1.0} if n == 1 else {"close": 1.0},
    )[0]


def test_a_position_reviews_outcomes_are_where_the_price_went_and_how_the_trade_ended(
    rising_market,
):
    store = InMemorySimStore()
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=reviewing_twice())

    review = crypto_decisions(store, sim_id)[98]
    found = outcomes_of(store, sim_id, review)
    # Reviewed at $100.10: one bar later $100.20, four bars later $100.50, and the UTC day's
    # last bar (step 192) closed at $109.50.
    after_1, after_4, end_of_day = (
        found["price_after_1_bar"],
        found["price_after_4_bars"],
        found["price_at_end_of_day"],
    )
    assert (after_1["KNOWN_FROM"], after_1["VALUE"]["price"]) == (
        99,
        pytest.approx(100.2),
    )
    assert after_1["VALUE"]["change"] == pytest.approx(0.1 / 100.1)
    assert (after_4["KNOWN_FROM"], after_4["VALUE"]["price"]) == (
        102,
        pytest.approx(100.5),
    )
    assert (end_of_day["KNOWN_FROM"], end_of_day["VALUE"]["price"]) == (
        192,
        pytest.approx(109.5),
    )
    # The trade was closed by the later review, carried out at step 103's open: 5 bars after
    # this review. $4,000 in, sold at $100.5497 (slippage), less $4 and $4.02 of fees: +$7.95.
    closed = found["position_closed"]
    assert closed["KNOWN_FROM"] == 103
    assert closed["VALUE"]["closing_reason"] == "jev"
    assert closed["VALUE"]["step_closed"] == 103
    assert closed["VALUE"]["bars_after"] == 5
    assert closed["VALUE"]["closed_at_this_review"] is False
    assert closed["VALUE"]["profit"] == pytest.approx(7.95, abs=0.01)
    # Searchable only once the trade has closed and that day has ended.
    assert review["OUTCOMES_KNOWN_FROM"] == 192


def test_a_review_that_closes_reads_closed_at_this_review(rising_market):
    store = InMemorySimStore()
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=reviewing_twice())

    closing = crypto_decisions(store, sim_id)[102]
    closed = outcomes_of(store, sim_id, closing)["position_closed"]
    assert closed["VALUE"]["closed_at_this_review"] is True
    assert closed["VALUE"]["bars_after"] == 1


def test_a_full_evaluation_that_traded_is_complete_once_its_position_closed(
    rising_market,
):
    store = InMemorySimStore()
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=reviewing_twice())

    evaluation = crypto_decisions(store, sim_id)[97]
    found = outcomes_of(store, sim_id, evaluation)
    entry = found["order_carried_out"]
    assert (entry["KNOWN_FROM"], entry["VALUE"]["carried_out"]) == (98, True)
    assert entry["VALUE"]["price"] == pytest.approx(100.15005)
    closed = found["position_closed"]
    assert (closed["KNOWN_FROM"], closed["VALUE"]["bars_after"]) == (103, 6)
    # What memory needs to write the trade without reading the orders: which position it was
    # (to follow its bars), the money put in, and its best and worst point.
    position = entry["VALUE"]["position"]
    assert evaluation["STEP"] < 98 and isinstance(position, int)
    assert closed["VALUE"]["amount_entered"] == pytest.approx(entry["VALUE"]["value"])
    best, worst = closed["VALUE"]["best"], closed["VALUE"]["worst"]
    assert worst <= closed["VALUE"]["profit"] <= best
    assert "closed_at_this_review" not in closed["VALUE"]
    # Searchable from the close, before the day has ended.
    assert evaluation["OUTCOMES_KNOWN_FROM"] == 103


def test_a_trade_still_open_at_the_sims_end_closes_with_the_sim_ended(
    rising_market,
):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9 if n == 1 else 0.3, pick={"long_tight_stop": 1.0})
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=jev)

    evaluation = crypto_decisions(store, sim_id)[97]
    closed = outcomes_of(store, sim_id, evaluation)["position_closed"]
    # Bought at step 98's open, closed at the last close ($109.50) at step 192 (ADR 0009).
    assert closed["VALUE"]["closing_reason"] == "sim_ended"
    assert (closed["KNOWN_FROM"], closed["VALUE"]["bars_after"]) == (192, 95)
    assert evaluation["OUTCOMES_KNOWN_FROM"] == 192


def test_an_entry_cancelled_at_the_sims_end_never_becomes_searchable(rising_market):
    store = InMemorySimStore()
    # Only the last screen says yes: the crypto's at step 192, the sim's last step.
    jev, _ = fake_jev(
        lambda n: 0.9 if n == SCREENS_ASKED else 0.3, pick={"long_tight_stop": 1.0}
    )
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=jev)

    evaluation = crypto_decisions(store, sim_id)[192]
    assert evaluation["ACTION"] == "entry"
    entry = outcomes_of(store, sim_id, evaluation)["order_carried_out"]
    assert (entry["KNOWN_FROM"], entry["VALUE"]) == (192, {"carried_out": False})
    assert evaluation["OUTCOMES_KNOWN_FROM"] is None
    assert not searchable(evaluation, 10_000)


def test_a_no_trade_episode_is_complete_once_its_three_prices_are_in(rising_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)  # every screen says yes; every pick is no trade
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=jev)

    decisions = {
        (d["ASSET"], d["STEP"]): d for d in store.rows("MEMORY.DECISIONS", sim_id)
    }
    crypto = decisions[(CRYPTO, 150)]
    assert (crypto["KIND"], crypto["ACTION"]) == ("full_evaluation", "nothing")
    found = outcomes_of(store, sim_id, crypto)
    assert set(found) == {
        "price_after_1_bar",
        "price_after_4_bars",
        "price_at_end_of_day",
    }
    assert crypto["OUTCOMES_KNOWN_FROM"] == 192
    # The stock's day ends at its last bar of the session, step 176.
    stock = decisions[(STOCK, 160)]
    end_of_day = outcomes_of(store, sim_id, stock)["price_at_end_of_day"]
    assert end_of_day["KNOWN_FROM"] == 176
    assert stock["OUTCOMES_KNOWN_FROM"] == 176
    assert searchable(stock, 176) and not searchable(stock, 175)
    # Four bars after these lie past the sim's last step: never complete, never searchable.
    for late in (decisions[(CRYPTO, 189)], decisions[(STOCK, 174)]):
        assert late["OUTCOMES_KNOWN_FROM"] is None
        assert not searchable(late, 10_000)
    # A decision at its day's last bar has its end-of-day price at once: its own close.
    last = outcomes_of(store, sim_id, decisions[(CRYPTO, 192)])
    assert last["price_at_end_of_day"]["KNOWN_FROM"] == 192
    assert last["price_at_end_of_day"]["VALUE"]["change"] == 0


def test_a_screen_alone_is_never_an_episode(rising_market):
    store = InMemorySimStore()
    jev, _ = fake_jev()  # every screen says no
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=jev)

    assert store.rows("MEMORY.OUTCOMES", sim_id) == []
    assert not any(
        searchable(d, 10_000) for d in store.rows("MEMORY.DECISIONS", sim_id)
    )


def test_outcomes_hold_only_numbers_and_codes_from_code(rising_market):
    """ADR 0001: memory holds records and numbers computed by code, never a model's words."""
    store = InMemorySimStore()
    sim_id = practice(store, rising_market)

    run_sim(store, rising_market, sim_id, jev=reviewing_twice())

    reasons = {"jev", "stop_price", "forced_close", "sim_ended"}
    for outcome in store.rows("MEMORY.OUTCOMES", sim_id):
        for name, value in outcome["VALUE"].items():
            if name == "closing_reason":
                assert value in reasons
            else:
                assert isinstance(value, int | float | bool), (name, value)
