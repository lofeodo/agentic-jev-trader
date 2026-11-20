"""A broker saved as plain data and brought back carries on exactly as if it had never stopped.

This is how a stopped sim resumes (ADR 0013): its account is saved with each completed step.
"""

import json

from jev_trader.broker import (
    AssetClass,
    Bar,
    Broker,
    Direction,
    OrderKind,
    load_stop_price_settings,
    load_trading_costs,
)
from jev_trader.risk import load_risk_profile

STOCK, CRYPTO = "ASSET_01", "ASSET_02"
CLASSES = {STOCK: AssetClass.STOCK, CRYPTO: AssetClass.CRYPTO}


def make_broker():
    return Broker(
        cash=10_000.0,
        asset_classes=CLASSES,
        costs=load_trading_costs(),
        stop_settings=load_stop_price_settings(),
        risk=load_risk_profile(),
    )


def bar(step, open_, high, low, close):
    return Bar(step=step, open=open_, high=high, low=low, close=close)


def brought_back(broker):
    saved = json.loads(json.dumps(broker.state()))  # as it travels through the database
    return Broker.from_state(
        saved,
        asset_classes=CLASSES,
        costs=load_trading_costs(),
        stop_settings=load_stop_price_settings(),
        risk=load_risk_profile(),
    )


def a_broker_mid_sim():
    """A long crypto position, a short stock position, and a stock add still waiting."""
    broker = make_broker()
    broker.on_bar(STOCK, bar(55, 100.0, 100.5, 99.5, 100.0))
    broker.on_bar(CRYPTO, bar(55, 100.0, 100.5, 99.5, 100.0))
    broker.enter(CRYPTO, Direction.LONG, 4_000.0, 97.0, 55)
    broker.enter(STOCK, Direction.SHORT, 3_000.0, 101.5, 55, bars_left=20)
    broker.on_bar(STOCK, bar(56, 100.0, 100.4, 99.0, 99.2))
    broker.on_bar(CRYPTO, bar(56, 100.2, 101.0, 100.0, 100.8))
    broker.add(STOCK, 2_000.0, 56, bars_left=19)
    broker.charge_overnight(96)
    return broker


def carry_on(broker):
    """The same next bars and decisions, and what came of them."""
    fills = broker.on_bar(STOCK, bar(57, 99.0, 99.3, 98.0, 98.4))
    fills += broker.on_bar(CRYPTO, bar(57, 100.8, 102.0, 100.5, 101.7))
    broker.reduce(CRYPTO, 10.0, 57)
    fills += broker.on_bar(CRYPTO, bar(58, 101.7, 101.9, 101.0, 101.2))
    fills += broker.close_everything(58)
    return fills, broker.cash, broker.closed_trades


def test_a_broker_brought_back_from_its_saved_state_carries_on_identically():
    never_stopped = a_broker_mid_sim()
    resumed = brought_back(a_broker_mid_sim())

    assert carry_on(resumed) == carry_on(never_stopped)


def test_the_saved_state_keeps_orders_still_waiting():
    resumed = brought_back(a_broker_mid_sim())

    [waiting] = resumed.waiting_orders
    assert (waiting.asset, waiting.kind, waiting.amount_chosen) == (
        STOCK,
        OrderKind.ADD,
        2_000.0,
    )
