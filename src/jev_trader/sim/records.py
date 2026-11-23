"""The rows a step stores, each with an ID built from what it describes (spec appendix 6, section 6).

An ID never depends on when or how often a step is written: a redone step builds the same IDs,
so a record stored twice by mistake shows up in the duplicate count at the end of the sim.

- An order: sim, the step it was decided at, its asset, and the broker's number for it.
- The account at a step: sim and step.
- A nightly charge: sim, the midnight's step, its kind, and the position (or "loan").
- A notable moment: sim, step, kind, and its number among that step's moments of that kind.
"""

from jev_trader.broker import Broker, Charge, Fill, Order, OrderKind
from jev_trader.sim.market import instrument


def order_id(sim_id: int, step_decided: int, asset: str, number: int) -> str:
    return f"{sim_id}-{step_decided}-{asset}-{number}"


def _order_row(sim_id: int, step_decided: int, asset: str, number: int) -> dict:
    return {
        "ID": order_id(sim_id, step_decided, asset, number),
        "SIM": sim_id,
        "INSTRUMENT": instrument(asset),
        "DECISION": None,  # the decision behind it: the agent's sims fill this in
        "STEP_DECIDED": step_decided,
    }


def waiting_order_row(sim_id: int, order: Order, position_id: int | None) -> dict:
    """An order placed and waiting for its asset's next bar. An entry has no position yet."""
    return {
        **_order_row(sim_id, order.step_decided, order.asset, order.order_id),
        "POSITION": position_id,
        "KIND": str(order.kind),
        "REASON": str(order.reason),
        "SIDE": None,
        "STEP_CARRIED_OUT": None,
        "STATUS": "waiting",
        "UNITS": None,
        "PRICE_BEFORE_SLIPPAGE": None,
        "PRICE": None,
        "VALUE": None,
        "SLIPPAGE_COST": None,
        "COMMISSION_OR_TRADING_FEE": None,
        "AMOUNT_CHOSEN": order.amount_chosen,
        "AMOUNT_AFTER_TRIMMING": order.amount,
        "LIMITED_BY": order.limited_by and str(order.limited_by),
    }


def cancelled_order_row(sim_id: int, order: Order, position_id: int | None) -> dict:
    return {**waiting_order_row(sim_id, order, position_id), "STATUS": "cancelled"}


def filled_order_row(sim_id: int, fill: Fill) -> dict:
    grows = fill.kind in (OrderKind.ENTRY, OrderKind.ADD)
    return {
        **_order_row(sim_id, fill.step_decided, fill.asset, fill.order_id),
        "POSITION": fill.position_id,
        "KIND": str(fill.kind),
        "REASON": str(fill.reason),
        "SIDE": str(fill.side),
        "STEP_CARRIED_OUT": fill.step_carried_out,
        "STATUS": "carried out",
        "UNITS": fill.units,
        "PRICE_BEFORE_SLIPPAGE": fill.price_before_slippage,
        "PRICE": fill.price,
        "VALUE": fill.value,
        "SLIPPAGE_COST": fill.slippage_cost,
        "COMMISSION_OR_TRADING_FEE": fill.commission_or_trading_fee,
        "AMOUNT_CHOSEN": fill.amount_chosen,
        "AMOUNT_AFTER_TRIMMING": fill.value if grows else None,
        "LIMITED_BY": fill.limited_by and str(fill.limited_by),
    }


def account_row(sim_id: int, step: int, broker: Broker) -> dict:
    return {
        "ID": f"{sim_id}-{step}",
        "SIM": sim_id,
        "STEP": step,
        "CASH": broker.cash,
        "LOAN": broker.loan(),
        "EXPOSURE": broker.exposure(),
        "ACCOUNT_VALUE": broker.account_value(),
        "START_OF_DAY_VALUE": broker.start_of_day_value,
        "DAILY_LOSS_REACHED": broker.daily_loss_reached,
    }


def charge_row(sim_id: int, charge: Charge) -> dict:
    charged = "loan" if charge.position_id is None else charge.position_id
    return {
        "ID": f"{sim_id}-{charge.step}-{charge.kind}-{charged}",
        "SIM": sim_id,
        "STEP": charge.step,
        "KIND": str(charge.kind),
        "POSITION": charge.position_id,
        "CHARGED_ON": charge.charged_on,
        "YEARLY_RATE": charge.yearly_rate,
        "AMOUNT": charge.amount,
    }


def event_row(sim_id: int, step: int, kind: str, number: int, details: dict) -> dict:
    return {
        "ID": f"{sim_id}-{step}-{kind}-{number}",
        "SIM": sim_id,
        "STEP": step,
        "KIND": kind,
        "DETAILS": details,
    }
