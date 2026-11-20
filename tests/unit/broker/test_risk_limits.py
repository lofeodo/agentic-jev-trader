"""The broker under the medium risk profile (spec appendix 1, section 5).

No trading costs here, so the dollar figures are the spec's own, on a $10,000 account.
ASSET_01 is a stock, ASSET_02 crypto.
"""

import pytest

from jev_trader.broker import (
    AssetClass,
    Bar,
    BlockedByRiskLimit,
    Broker,
    ClosingReason,
    Direction,
    StopPriceSettings,
    TradingCosts,
)
from jev_trader.risk import RiskLimit, load_risk_profile

NO_COSTS = TradingCosts(
    slippage=0.0,
    stock_commission=0.0,
    crypto_trading_fee=0.0,
    stock_borrow_fee_yearly=0.0,
    crypto_borrow_fee_yearly=0.0,
    loan_interest_yearly=0.0,
)
STOPS = StopPriceSettings(multiples=(1.0, 2.0, 3.0), distance_cap=0.05)
STOCK, CRYPTO = "ASSET_01", "ASSET_02"
MID_SESSION = 10  # bars left in the stock's session


def make_broker(risk=None):
    broker = Broker(
        cash=10_000.0,
        asset_classes={STOCK: AssetClass.STOCK, CRYPTO: AssetClass.CRYPTO},
        costs=NO_COSTS,
        stop_settings=STOPS,
        risk=risk or load_risk_profile(),
    )
    broker.on_bar(STOCK, bar(1, 100.0))
    broker.on_bar(CRYPTO, bar(1, 100.0))
    return broker


def bar(step, open_, low=None, close=None):
    return Bar(
        step=step,
        open=open_,
        high=max(open_, close or open_),
        low=open_ if low is None else low,
        close=open_ if close is None else close,
    )


def enter_stock(broker, amount, stop_price, step=1, bars_left=MID_SESSION):
    return broker.enter(
        STOCK, Direction.LONG, amount, stop_price, step, bars_left=bars_left
    )


# Making a trade smaller


def test_an_entry_above_the_trade_risk_limit_is_made_smaller_and_recorded_so():
    broker = make_broker()
    # $20,000 with a stop price 0.95% away would lose $190: about $10,500 loses $100.
    enter_stock(broker, 20_000.0, stop_price=99.05)
    [fill] = broker.on_bar(STOCK, bar(2, 100.0))

    assert fill.value == pytest.approx(10_526.32, abs=0.01)
    assert fill.amount_chosen == 20_000.0
    assert fill.limited_by is RiskLimit.TRADE_RISK

    broker.close(STOCK, step=2)
    broker.on_bar(STOCK, bar(3, 100.0))
    [trade] = broker.closed_trades
    assert trade.amount_chosen == 20_000.0
    assert trade.amount_entered == pytest.approx(10_526.32, abs=0.01)
    assert trade.limited_by is RiskLimit.TRADE_RISK


def test_an_entry_under_every_limit_is_left_alone():
    broker = make_broker()
    enter_stock(broker, 6_000.0, stop_price=99.0)
    [fill] = broker.on_bar(STOCK, bar(2, 100.0))
    assert fill.value == pytest.approx(6_000.0)
    assert fill.limited_by is None


def test_the_limits_are_applied_again_when_the_order_is_carried_out():
    broker = make_broker()
    # Each fits alone; together they would hold $30,000 against a $20,000 exposure limit.
    enter_stock(broker, 15_000.0, stop_price=99.7)
    broker.enter(CRYPTO, Direction.SHORT, 15_000.0, stop_price=100.3, step=1)
    broker.on_bar(STOCK, bar(2, 100.0))
    [fill] = broker.on_bar(CRYPTO, bar(2, 100.0))

    assert fill.value == pytest.approx(5_000.0)
    assert fill.limited_by is RiskLimit.EXPOSURE
    assert broker.exposure() == pytest.approx(20_000.0)


def test_an_add_is_made_smaller_so_the_whole_position_fits():
    broker = make_broker()
    enter_stock(broker, 5_000.0, stop_price=99.0)
    broker.on_bar(STOCK, bar(2, 100.0))
    # $5,000 at risk of $50: $5,000 more reaches $100.
    broker.add(STOCK, 8_000.0, step=2, bars_left=MID_SESSION)
    [fill] = broker.on_bar(STOCK, bar(3, 100.0))

    assert fill.value == pytest.approx(5_000.0)
    assert fill.limited_by is RiskLimit.TRADE_RISK
    assert broker.exposure() == pytest.approx(10_000.0)


def test_an_order_the_limits_leave_nothing_of_is_cancelled_and_recorded():
    broker = make_broker()
    enter_stock(broker, 10_000.0, stop_price=99.0)
    broker.on_bar(STOCK, bar(2, 100.0))
    # The position already risks the whole $100.
    order_id = broker.add(STOCK, 2_000.0, step=2, bars_left=MID_SESSION)

    assert broker.on_bar(STOCK, bar(3, 100.0)) == []
    assert order_id in broker.cancelled_order_ids
    assert broker.blocked_orders[order_id] is RiskLimit.TRADE_RISK


# Every position has a stop price


def test_under_a_risk_profile_every_position_has_a_stop_price():
    broker = make_broker()
    with pytest.raises(ValueError, match="stop price"):
        broker.buy_and_hold(STOCK, 2_000.0, step=1)


# No new stock trade in a session's last two bars


def test_no_new_stock_trade_in_the_sessions_last_two_bars():
    broker = make_broker()
    assert broker.entry_blocked_by(STOCK, bars_left=1) is RiskLimit.SESSION_END
    with pytest.raises(BlockedByRiskLimit):
        enter_stock(broker, 2_000.0, stop_price=99.0, bars_left=1)
    # Crypto has no session.
    assert broker.entry_blocked_by(CRYPTO) is None


def test_an_add_is_allowed_at_the_second_to_last_bar_but_not_the_last():
    broker = make_broker()
    enter_stock(broker, 2_000.0, stop_price=99.0)
    broker.on_bar(STOCK, bar(2, 100.0))
    assert broker.add_blocked_by(STOCK, bars_left=1) is None
    assert broker.add_blocked_by(STOCK, bars_left=0) is RiskLimit.SESSION_END
    with pytest.raises(BlockedByRiskLimit):
        broker.add(STOCK, 2_000.0, step=2, bars_left=0)


def test_a_stock_order_must_say_how_many_bars_are_left():
    broker = make_broker()
    with pytest.raises(ValueError, match="bars left"):
        broker.enter(STOCK, Direction.LONG, 2_000.0, stop_price=99.0, step=1)


# The daily loss limit


def lose_on_the_stock(broker):
    """Stock with a stop price 0.5% away opens 3% lower: closed at $97, 3% of it lost."""
    enter_stock(broker, 20_000.0, stop_price=99.5)
    broker.on_bar(STOCK, bar(2, 100.0))
    broker.on_bar(STOCK, bar(3, 97.0))
    broker.check_account(step=3)


def test_the_daily_loss_limit_blocks_entries_and_adds_but_closes_nothing():
    broker = make_broker()
    broker.enter(CRYPTO, Direction.LONG, 2_000.0, stop_price=96.0, step=1)
    broker.on_bar(CRYPTO, bar(2, 100.0))
    # The crypto's $2,000 uses exposure room: the stock gets $18,000, and $540 is lost.
    lose_on_the_stock(broker)

    assert broker.account_value() < 9_500.0
    assert broker.entry_blocked_by(CRYPTO) is RiskLimit.DAILY_LOSS
    assert broker.add_blocked_by(CRYPTO) is RiskLimit.DAILY_LOSS
    with pytest.raises(BlockedByRiskLimit):
        broker.add(CRYPTO, 1_000.0, step=3)
    # The open crypto position stays open, and Jev may still close it.
    assert CRYPTO in broker.positions
    broker.close(CRYPTO, step=3)


def test_the_daily_loss_limit_stays_reached_until_midnight_even_if_the_account_recovers():
    broker = make_broker()
    broker.enter(CRYPTO, Direction.LONG, 2_000.0, stop_price=96.0, step=1)
    broker.on_bar(CRYPTO, bar(2, 100.0))
    lose_on_the_stock(broker)
    # The crypto rises 30%: $600 back.
    broker.on_bar(CRYPTO, bar(4, 100.0, close=130.0))
    broker.check_account(step=4)
    assert broker.account_value() > 9_500.0
    assert broker.entry_blocked_by(CRYPTO) is RiskLimit.DAILY_LOSS

    broker.charge_overnight(step=96)
    assert broker.entry_blocked_by(CRYPTO) is None


def test_an_order_placed_before_the_daily_loss_limit_is_reached_is_not_carried_out():
    broker = make_broker()
    order_id = broker.enter(CRYPTO, Direction.LONG, 2_000.0, stop_price=96.0, step=2)
    lose_on_the_stock(broker)
    assert broker.on_bar(CRYPTO, bar(4, 100.0)) == []
    assert order_id in broker.cancelled_order_ids
    assert broker.blocked_orders == {order_id: RiskLimit.DAILY_LOSS}


# Forced close


def test_a_forced_close_closes_every_position_at_the_next_bar():
    broker = make_broker()
    # $10,000 of each, stop prices 1% away.
    enter_stock(broker, 10_000.0, stop_price=99.0)
    broker.enter(CRYPTO, Direction.LONG, 10_000.0, stop_price=99.0, step=1)
    broker.on_bar(STOCK, bar(2, 100.0))
    broker.on_bar(CRYPTO, bar(2, 100.0))
    # The stock opens 80% lower overnight, past its stop price: $8,000 lost. Account value
    # $2,000 holds $10,000 of crypto, below a quarter of it ($2,500).
    broker.on_bar(STOCK, bar(3, 20.0))
    assert broker.check_account(step=3) != []
    assert CRYPTO in broker.positions  # carried out at the next bar

    [fill] = broker.on_bar(CRYPTO, bar(4, 100.0))
    assert fill.reason is ClosingReason.FORCED_CLOSE
    assert broker.positions == {}
    assert broker.closed_trades[-1].closing_reason is ClosingReason.FORCED_CLOSE
    # The sim carries on with what is left.
    assert broker.cash == pytest.approx(2_000.0)


def test_no_forced_close_while_account_value_is_above_a_quarter_of_what_is_held():
    broker = make_broker()
    enter_stock(broker, 10_000.0, stop_price=99.0)
    broker.on_bar(STOCK, bar(2, 100.0))
    assert broker.check_account(step=2) == []
