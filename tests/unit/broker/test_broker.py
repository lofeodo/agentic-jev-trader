"""The pretend broker's money rules (spec appendix 1, sections 3 and 4; ADR 0009).

Dollar figures are worked by hand from the spec's own examples, on a $10,000 account.
"""

import pytest

from jev_trader.broker import (
    AssetClass,
    Bar,
    Broker,
    ChargeKind,
    ClosingReason,
    Direction,
    OrderKind,
    StopPriceSettings,
    TradingCosts,
    load_trading_costs,
)

COSTS = TradingCosts(
    slippage=0.0005,
    stock_commission=1.0,
    crypto_trading_fee=0.001,
    stock_borrow_fee_yearly=0.0025,
    crypto_borrow_fee_yearly=0.05,
    loan_interest_yearly=0.05,
)
STOPS = StopPriceSettings(multiples=(1.0, 2.0, 3.0), distance_cap=0.05)


def make_broker(cash=10_000.0, costs=COSTS):
    return Broker(
        cash=cash,
        asset_classes={"ASSET_01": AssetClass.STOCK, "ASSET_02": AssetClass.CRYPTO},
        costs=costs,
        stop_settings=STOPS,
    )


def bar(step, open_, high=None, low=None, close=None):
    """A bar whose high, low and close default to its open: a bar where the price stood still."""
    return Bar(
        step=step,
        open=open_,
        high=open_ if high is None else high,
        low=open_ if low is None else low,
        close=open_ if close is None else close,
    )


def test_trading_costs_come_from_config():
    assert load_trading_costs() == COSTS


# Orders and fills


def test_a_buy_is_carried_out_at_the_next_bars_open_plus_slippage_with_the_commission_on_top():
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 99.0))
    broker.enter("ASSET_01", Direction.LONG, amount=2_000.0, stop_price=97.0, step=1)

    assert broker.cash == 10_000.0  # nothing happens until the next bar
    [fill] = broker.on_bar("ASSET_01", bar(2, 100.0))

    assert fill.price_before_slippage == 100.0
    assert fill.price == pytest.approx(100.05)
    # Fractions of a unit are allowed.
    assert fill.units == pytest.approx(19.99, abs=0.001)
    assert fill.value == pytest.approx(2_000.0)
    assert fill.commission_or_trading_fee == 1.0
    assert fill.step_decided == 1
    assert fill.step_carried_out == 2
    assert broker.cash == pytest.approx(7_999.0)  # $2,000 of stock takes $2,001
    assert broker.positions["ASSET_01"].stop_price == 97.0


NO_COSTS = TradingCosts(
    slippage=0.0,
    stock_commission=0.0,
    crypto_trading_fee=0.0,
    stock_borrow_fee_yearly=0.0,
    crypto_borrow_fee_yearly=0.0,
    loan_interest_yearly=0.0,
)


def round_trip(direction, open_in, open_out, asset="ASSET_01", costs=COSTS):
    """Open $2,000 at one bar's open and close it, by Jev's decision, at a later bar's open."""
    broker = make_broker(costs=costs)
    broker.on_bar(asset, bar(1, open_in))
    stop = open_in * (0.97 if direction is Direction.LONG else 1.03)
    broker.enter(asset, direction, amount=2_000.0, stop_price=stop, step=1)
    broker.on_bar(asset, bar(2, open_in, close=open_out))
    broker.close(asset, step=2)
    broker.on_bar(asset, bar(3, open_out))
    return broker


def test_a_long_gains_when_the_price_rises():
    broker = round_trip(Direction.LONG, 100.0, 101.0, costs=NO_COSTS)
    [trade] = broker.closed_trades
    assert trade.profit == pytest.approx(20.0)  # buy $2,000, the price rises 1%
    assert trade.closing_reason is ClosingReason.JEV
    assert broker.cash == pytest.approx(10_020.0)
    assert broker.positions == {}


def test_a_short_gains_when_the_price_falls():
    broker = round_trip(Direction.SHORT, 100.0, 99.0, costs=NO_COSTS)
    [trade] = broker.closed_trades
    assert trade.direction is Direction.SHORT
    # Sell $2,000 borrowed, the price falls 1%.
    assert trade.profit == pytest.approx(20.0)
    assert broker.cash == pytest.approx(10_020.0)


def test_a_short_sells_low_and_buys_back_high():
    broker = round_trip(Direction.SHORT, 100.0, 100.0)
    sell, buy = broker.fills
    assert sell.price == pytest.approx(99.95)
    assert buy.price == pytest.approx(100.05)


def test_a_2000_stock_trade_in_and_out_costs_about_4_dollars():
    # Spec appendix 1 section 4: $1 commission each way and about $1 of slippage each way.
    for direction in Direction:
        [trade] = round_trip(direction, 100.0, 100.0).closed_trades
        assert trade.trading_costs == pytest.approx(4.0, abs=0.01)
        assert trade.profit == pytest.approx(-4.0, abs=0.01)


def test_a_2000_bitcoin_trade_in_and_out_costs_about_6_dollars():
    # 0.1% trading fee each way ($2) and about $1 of slippage each way.
    [trade] = round_trip(Direction.LONG, 100.0, 100.0, asset="ASSET_02").closed_trades
    assert trade.trading_costs == pytest.approx(6.0, abs=0.01)
    assert trade.profit == pytest.approx(-6.0, abs=0.01)


def long_2000_at_100(stop_price=97.0, asset="ASSET_01", costs=COSTS):
    """A $2,000 long carried out at step 2's open of $100: 19.99 units at $100.05."""
    broker = make_broker(costs=costs)
    broker.on_bar(asset, bar(1, 100.0))
    broker.enter(asset, Direction.LONG, amount=2_000.0, stop_price=stop_price, step=1)
    broker.on_bar(asset, bar(2, 100.0))
    return broker


def short_2000_at_100(stop_price=103.0, asset="ASSET_01", costs=COSTS):
    """A $2,000 short carried out at step 2's open of $100: 20.01 units sold at $99.95."""
    broker = make_broker(costs=costs)
    broker.on_bar(asset, bar(1, 100.0))
    broker.enter(asset, Direction.SHORT, amount=2_000.0, stop_price=stop_price, step=1)
    broker.on_bar(asset, bar(2, 100.0))
    return broker


# Stop prices


def test_an_entry_whose_stop_price_is_more_than_5_percent_away_is_refused():
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    with pytest.raises(ValueError):
        broker.enter(
            "ASSET_01", Direction.LONG, amount=2_000.0, stop_price=94.0, step=1
        )
    assert broker.positions == {}


def test_a_long_closes_at_its_stop_price_when_a_bar_reaches_it():
    broker = long_2000_at_100()
    broker.on_bar("ASSET_01", bar(3, 99.0, low=98.0))  # not reached: still open
    assert "ASSET_01" in broker.positions

    [fill] = broker.on_bar("ASSET_01", bar(4, 98.0, low=96.5))
    assert fill.price_before_slippage == 97.0
    assert fill.price == pytest.approx(96.9515)
    [trade] = broker.closed_trades
    assert trade.closing_reason is ClosingReason.STOP_PRICE
    assert trade.step_closed == 4
    # About $3 a unit on 19.99 units, plus $2 of commission and about $2 of slippage.
    assert trade.profit == pytest.approx(-63.94, abs=0.01)


def test_a_long_closes_at_the_open_when_the_bar_opens_beyond_its_stop_price():
    broker = long_2000_at_100()
    [fill] = broker.on_bar("ASSET_01", bar(3, 95.0, low=94.0))  # a night's jump down
    assert fill.price_before_slippage == 95.0
    [trade] = broker.closed_trades
    assert trade.profit == pytest.approx(-103.90, abs=0.01)


def test_a_short_closes_at_its_stop_price_when_a_bar_high_reaches_it():
    broker = short_2000_at_100()
    [fill] = broker.on_bar("ASSET_01", bar(3, 101.0, high=103.5))
    assert fill.price_before_slippage == 103.0
    assert fill.price == pytest.approx(103.0515)
    [trade] = broker.closed_trades
    assert trade.closing_reason is ClosingReason.STOP_PRICE
    assert trade.profit == pytest.approx(-64.06, abs=0.01)


def test_a_short_closes_at_the_open_when_the_bar_opens_above_its_stop_price():
    broker = short_2000_at_100()
    [fill] = broker.on_bar("ASSET_01", bar(3, 105.0, high=106.0))
    assert fill.price_before_slippage == 105.0


def test_the_bar_an_entry_is_carried_out_in_can_reach_its_stop_price():
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    broker.enter("ASSET_01", Direction.LONG, amount=2_000.0, stop_price=97.0, step=1)
    entry, stop = broker.on_bar("ASSET_01", bar(2, 100.0, low=96.0))
    assert entry.kind is OrderKind.ENTRY
    assert stop.reason is ClosingReason.STOP_PRICE
    assert broker.positions == {}


def test_an_add_keeps_the_positions_stop_price():
    broker = long_2000_at_100()
    broker.on_bar("ASSET_01", bar(3, 102.0))
    broker.add("ASSET_01", amount=1_000.0, step=3)
    broker.on_bar("ASSET_01", bar(4, 102.0))

    position = broker.positions["ASSET_01"]
    assert position.stop_price == 97.0
    assert position.units == pytest.approx(19.990005 + 1_000.0 / 102.051, rel=1e-6)
    assert broker.cash == pytest.approx(10_000.0 - 2_001.0 - 1_001.0)


def test_a_reduce_sells_part_and_the_position_stays_open():
    broker = long_2000_at_100()
    broker.reduce("ASSET_01", units=10.0, step=2)
    [fill] = broker.on_bar("ASSET_01", bar(3, 100.0))

    assert fill.kind is OrderKind.REDUCE
    assert fill.price == pytest.approx(99.95)
    assert broker.positions["ASSET_01"].units == pytest.approx(9.990005)
    assert broker.cash == pytest.approx(7_999.0 + 999.5 - 1.0)  # $999.50 in, less $1
    assert broker.closed_trades == []


# Nightly charges


def test_a_stock_short_held_friday_to_monday_pays_three_nights_of_borrow_fee():
    broker = short_2000_at_100()
    for night in (96, 192, 288):  # every calendar day counts, weekend included
        [charge] = broker.charge_overnight(step=night)
        assert charge.kind is ChargeKind.BORROW_FEE
        # About 1.4 cents a night.
        assert charge.amount == pytest.approx(0.0137, abs=0.0001)
    broker.close("ASSET_01", step=300)
    broker.on_bar("ASSET_01", bar(301, 100.0))

    [trade] = broker.closed_trades
    assert trade.profit == pytest.approx(-4.0 - 3 * 0.0137, abs=0.01)
    assert len(broker.charges) == 3


def test_a_bitcoin_short_pays_its_own_borrow_fee_rate():
    broker = short_2000_at_100(asset="ASSET_02")
    [charge] = broker.charge_overnight(step=96)
    assert charge.yearly_rate == 0.05
    assert charge.amount == pytest.approx(0.27, abs=0.01)  # about 27 cents a night


def test_the_borrow_fee_is_one_days_share_of_the_yearly_rate():
    # Spec appendix 1 section 4: at 10% a year a $2,000 short pays about $0.55 a day.
    costs = TradingCosts(**{**COSTS.__dict__, "stock_borrow_fee_yearly": 0.10})
    broker = short_2000_at_100(costs=costs)
    [charge] = broker.charge_overnight(step=96)
    assert charge.amount == pytest.approx(0.55, abs=0.01)


def test_a_short_opened_and_closed_within_the_day_pays_no_borrow_fee():
    broker = short_2000_at_100()
    broker.close("ASSET_01", step=2)
    broker.on_bar("ASSET_01", bar(3, 100.0))
    assert broker.charge_overnight(step=96) == []


def test_money_owed_at_midnight_pays_one_days_loan_interest():
    # Buying $20,000 with $10,000 owes about $10,000, which costs about $1.37 a day at 5% a year.
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    broker.enter("ASSET_01", Direction.LONG, amount=20_000.0, stop_price=97.0, step=1)
    broker.on_bar("ASSET_01", bar(2, 100.0))
    assert broker.loan() == pytest.approx(10_001.0)

    [charge] = broker.charge_overnight(step=96)
    assert charge.kind is ChargeKind.LOAN_INTEREST
    assert charge.position_id is None
    assert charge.amount == pytest.approx(1.37, abs=0.01)
    [charge] = broker.charge_overnight(step=192)  # the next night, on what is owed then
    assert charge.charged_on == pytest.approx(10_001.0 + 1.37, abs=0.01)


def test_a_loan_paid_back_within_the_day_costs_nothing():
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    broker.enter("ASSET_01", Direction.LONG, amount=16_000.0, stop_price=97.0, step=1)
    broker.on_bar("ASSET_01", bar(2, 100.0))
    broker.close("ASSET_01", step=2)
    broker.on_bar("ASSET_01", bar(3, 100.0))
    assert broker.charge_overnight(step=96) == []


def test_a_short_sale_is_not_a_loan():
    broker = short_2000_at_100()
    assert broker.loan() == 0.0
    [charge] = broker.charge_overnight(step=96)
    assert charge.kind is ChargeKind.BORROW_FEE


def test_short_sale_money_does_not_pay_down_the_loan():
    # Glossary: $10,000 that buys $16,000 of positions owes $6,000. Selling $5,000 of another
    # asset short at the same time does not change that (here plus about $8 of costs).
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    broker.on_bar("ASSET_02", bar(1, 100.0))
    broker.enter("ASSET_01", Direction.LONG, amount=16_000.0, stop_price=97.0, step=1)
    broker.enter("ASSET_02", Direction.SHORT, amount=5_000.0, stop_price=103.0, step=1)
    broker.on_bar("ASSET_01", bar(2, 100.0))
    broker.on_bar("ASSET_02", bar(2, 100.0))

    assert broker.loan() == pytest.approx(6_000.0, abs=10.0)


# The account


def test_account_value_counts_each_position_at_its_last_price():
    long_ = long_2000_at_100()
    long_.on_bar("ASSET_01", bar(3, 100.0, close=101.0))
    assert long_.account_value() == pytest.approx(7_999.0 + 19.990005 * 101.0)
    assert long_.exposure() == pytest.approx(19.990005 * 101.0)

    short = short_2000_at_100()
    short.on_bar("ASSET_01", bar(3, 100.0, close=101.0))
    assert short.account_value() == pytest.approx(11_999.0 - 20.010005 * 101.0)
    assert short.exposure() == pytest.approx(20.010005 * 101.0)  # counted like a long


# A sim's last step (ADR 0009)


def test_at_the_last_step_every_position_closes_at_its_last_price_and_counts_as_a_trade():
    # Spec: $3,000 of a stock that is up $40 is sold for $3,040, less the $1 commission and
    # about $1.50 of slippage.
    broker = make_broker()
    broker.on_bar("ASSET_01", bar(1, 100.0))
    broker.enter("ASSET_01", Direction.LONG, amount=3_000.0, stop_price=97.0, step=1)
    broker.on_bar("ASSET_01", bar(2, 100.0, close=101.3833))
    broker.on_bar("ASSET_02", bar(2, 100.0))
    broker.enter("ASSET_02", Direction.SHORT, amount=2_000.0, stop_price=103.0, step=2)
    cash_before = broker.cash

    [sale] = broker.close_everything(step=5)  # the crypto entry never got its next bar

    assert sale.price_before_slippage == 101.3833  # the last close, not a next open
    assert sale.reason is ClosingReason.SIM_ENDED
    assert sale.step_carried_out == 5
    assert sale.commission_or_trading_fee == 1.0
    assert sale.slippage_cost == pytest.approx(1.52, abs=0.01)
    # The last close values the 29.985 units at about $3,040 (within 5 cents).
    assert broker.cash - cash_before == pytest.approx(3_040.0 - 1.0 - 1.52, abs=0.05)
    [trade] = broker.closed_trades
    assert trade.closing_reason is ClosingReason.SIM_ENDED
    assert broker.positions == {}
    assert len(broker.cancelled_order_ids) == 1
    assert broker.account_value() == broker.cash  # the sim ends in cash


# The buy_hold comparison (spec appendix 1, section 6)


def test_buy_hold_buys_at_the_first_bar_and_holds_through_any_fall_until_the_last_step():
    broker = make_broker()
    broker.buy_and_hold("ASSET_01", amount=2_000.0, step=1)  # no bar seen yet
    [buy] = broker.on_bar("ASSET_01", bar(2, 100.0))
    assert buy.price == pytest.approx(100.05)
    assert broker.positions["ASSET_01"].stop_price is None

    assert broker.on_bar("ASSET_01", bar(3, 90.0, low=80.0, close=90.0)) == []
    [sale] = broker.close_everything(step=4)

    assert sale.price_before_slippage == 90.0
    [trade] = broker.closed_trades
    assert trade.closing_reason is ClosingReason.SIM_ENDED


def test_an_entry_before_the_asset_has_a_bar_is_refused():
    broker = make_broker()
    with pytest.raises(ValueError, match="no bar"):
        broker.enter(
            "ASSET_01", Direction.LONG, amount=2_000.0, stop_price=97.0, step=1
        )
