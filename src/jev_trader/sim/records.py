"""The rows a step stores, each with an ID built from what it describes (spec appendix 6, section 6).

An ID never depends on when or how often a step is written: a redone step builds the same IDs,
so a record stored twice by mistake shows up in the duplicate count at the end of the sim.

- An order: sim, the step it was decided at, its asset, and the broker's number for it.
- The account at a step: sim and step.
- A nightly charge: sim, the midnight's step, its kind, and the position (or "loan").
- A notable moment: sim, step, kind, and its number among that step's moments of that kind.
- A decision: sim, step and asset. A Jev request and its paid call: the same, and their purpose
  (screen, pick or size; for an open position, position_screen, action, reduce or add).

An order Jev decided carries its decision's ID; code's own orders (a stop price, a forced close,
the sim's end, the holding sim's purchases) carry none.
"""

from jev_trader.broker import Broker, Charge, ClosingReason, Fill, Order, OrderKind
from jev_trader.jev.client import JevReply
from jev_trader.jev.full_evaluation import Evaluation
from jev_trader.jev.position_review import Review
from jev_trader.jev.reading import JevRequest, Reading
from jev_trader.sim.market import instrument
from jev_trader.sim.store import (
    ACTION_NOTHING,
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
    KIND_POSITION_SCREEN,
    KIND_SCREEN,
    now,
)


def order_id(sim_id: int, step_decided: int, asset: str, number: int) -> str:
    return f"{sim_id}-{step_decided}-{asset}-{number}"


def _order_row(
    sim_id: int, step_decided: int, asset: str, number: int, reason: ClosingReason
) -> dict:
    decided_by_jev = reason is ClosingReason.JEV
    return {
        "ID": order_id(sim_id, step_decided, asset, number),
        "SIM": sim_id,
        "INSTRUMENT": instrument(asset),
        "DECISION": decision_id(sim_id, step_decided, asset)
        if decided_by_jev
        else None,
        "STEP_DECIDED": step_decided,
    }


def waiting_order_row(sim_id: int, order: Order, position_id: int | None) -> dict:
    """An order placed and waiting for its asset's next bar. An entry has no position yet."""
    return {
        **_order_row(
            sim_id, order.step_decided, order.asset, order.order_id, order.reason
        ),
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
        **_order_row(sim_id, fill.step_decided, fill.asset, fill.order_id, fill.reason),
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


def decision_id(sim_id: int, step: int, asset: str) -> str:
    return f"{sim_id}-{step}-{asset}"


def decision_row(
    sim_id: int,
    dataset: int,
    step: int,
    asset: str,
    skipped_because: str | None,
    reply: JevReply | None = None,
    evaluation: Evaluation | None = None,
    action: str = ACTION_NOTHING,
) -> dict:
    """One asset with no position looked at, at one step. Tier 0: code alone. Tier 1: Jev
    answered the screen.

    Tier 2: the screen said yes and a full evaluation ran. Its record is the episode: the
    candidate trades, Jev's answers copy by copy, the pick, the size chosen, what the limits left
    of it and which limit trimmed it, and what was done ("entry" or "nothing"). Every row has
    every column, so rows of all tiers and kinds are written together.
    """
    tier = 0 if reply is None else 1 if evaluation is None else 2
    e = evaluation
    return {
        **_decision_columns(sim_id, dataset, step, asset, skipped_because, reply),
        "KIND": KIND_FULL_EVALUATION if tier == 2 else KIND_SCREEN,
        "TIER": tier,
        "SCREEN_ANSWER": None if reply is None else reply.noul("screen"),
        "CANDIDATE_TRADES": e and [t.as_record() for t in e.candidates],
        "ANSWERS": e and e.answers,
        "PICK": e and e.pick,
        "RATING": e and e.rating,
        "SIZE_CHOSEN": e and e.size_chosen,
        "SIZE_AFTER_TRIMMING": e and e.size_after_trimming,
        "LIMITED_BY": e and e.limited_by,
        "ACTION": action,
    }


def position_decision_row(
    sim_id: int,
    dataset: int,
    step: int,
    asset: str,
    position_id: int,
    skipped_because: str | None,
    reply: JevReply | None = None,
    review: Review | None = None,
    action: str = ACTION_NOTHING,
) -> dict:
    """One open position looked at, at one step. Tier 0: code alone (a stock's last bar of the
    session). Tier 1: Jev answered the position screen.

    Tier 2: a position review ran, after a yes or as an end-of-session review (with no position
    screen, so no screen answer). Its record is the episode: the position's standing, Jev's
    answers copy by copy, the action decided (in PICK), the share closed or the size added, and
    what was done ("close", "reduce", "add" or "nothing").
    """
    r = review
    return {
        **_decision_columns(sim_id, dataset, step, asset, skipped_because, reply),
        "KIND": KIND_POSITION_SCREEN if r is None else KIND_POSITION_REVIEW,
        "TIER": 2 if r is not None else 0 if reply is None else 1,
        "SCREEN_ANSWER": None if reply is None else reply.noul("position_screen"),
        "CANDIDATE_TRADES": None,
        "ANSWERS": r and r.answers,
        "PICK": r and r.action,
        "RATING": None,
        "SIZE_CHOSEN": r and r.size_chosen,
        "SIZE_AFTER_TRIMMING": r and r.size_after_trimming,
        "LIMITED_BY": r and r.limited_by,
        "ACTION": action,
        "POSITION": position_id,
        "STANDING": r and r.standing,
        "END_OF_SESSION": r and r.end_of_session,
        "THESIS_INTACT": r and r.thesis_intact,
        "REDUCE_SHARE": r and r.reduce_share,
    }


def _decision_columns(sim_id, dataset, step, asset, skipped_because, reply) -> dict:
    return {
        "ID": decision_id(sim_id, step, asset),
        "SIM": sim_id,
        "FIRST_WRITTEN_BY": sim_id,
        "DATASET": dataset,
        "ASSET": asset,
        "STEP": step,
        "SKIPPED_BECAUSE": skipped_because,
        "JEV_VERSION": None if reply is None else reply.model,
        # An open position's columns, empty for an asset with no position.
        "POSITION": None,
        "STANDING": None,
        "END_OF_SESSION": None,
        "THESIS_INTACT": None,
        "REDUCE_SHARE": None,
    }


def jev_request_row(
    sim_id: int,
    step: int,
    asset: str,
    reading: Reading,
    request: JevRequest,
    reply: JevReply,
    purpose: str = "screen",
) -> dict:
    """A request and its answer, word for word. The opening is stored once per reading version."""
    return {
        "ID": f"{sim_id}-{step}-{asset}-{purpose}",
        "SIM": sim_id,
        "STEP": step,
        "ASSET": asset,
        "DECISION": decision_id(sim_id, step, asset),
        "PURPOSE": purpose,
        "READING_VERSION": reading.version,
        "BACKGROUND_AFTER_OPENING": reading.after_opening(request.background),
        "QUESTIONS": request.questions,
        "ANSWER": reply.body,
        "JEV_VERSION": reply.model,
    }


def jev_call_row(
    sim_id: int, step: int, asset: str, reply: JevReply, purpose: str = "screen"
) -> dict:
    return {
        "ID": f"{sim_id}-{step}-{asset}-{purpose}",
        "SIM": sim_id,
        "PURPOSE": purpose,
        "STEP": step,
        "ASSET": asset,
        "DECISION": decision_id(sim_id, step, asset),
        "SERVICE": "jev",
        "MODEL": reply.model,
        "TOKENS_IN": reply.tokens_in,
        "CACHED_TOKENS": None,
        "TOKENS_OUT": reply.tokens_out,
        "THINKING_TOKENS": None,
        "COST_USD": reply.cost_usd,
        "LATENCY_SECONDS": reply.latency_seconds,
        "RETRIES": reply.retries,
        "ERROR": None,
        "CALLED_AT": now(),
    }


def event_row(sim_id: int, step: int, kind: str, number: int, details: dict) -> dict:
    return {
        "ID": f"{sim_id}-{step}-{kind}-{number}",
        "SIM": sim_id,
        "STEP": step,
        "KIND": kind,
        "DETAILS": details,
    }
