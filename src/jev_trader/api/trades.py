"""The trades table of the Trading sim page (spec appendix 7 section 5.5; `GET /sims/{id}/trades`).

One table for trades and decisions: each line is a trade (a position, from the order that opened
it to the one that closed it). A filter adds the full evaluations that ended in no trade. Other
filters keep the trades that lost money, were trimmed by a risk limit, closed at their stop price,
or were held overnight. Above the lines come the day marks: days the daily loss limit was
reached, loan interest paid, and forced closes. Everything is worked out from stored records when
asked for.

`trades_of` builds the trades the measurements and the scorecard also count.

Choices the spec leaves to the build:

- A trade's profit is what it brought in minus what it paid out: the orders' values (slippage is
  inside their prices), their commissions or trading fees, and its borrow fees. Loan interest is
  the account's, not a trade's.
- A trade's closing reason is that of the order that brought it to nothing.
- Held overnight: open across a midnight UTC (still open counts up to the step reached).
- Lost money and closed at the stop price apply to closed trades only.
- Lines run oldest first, by the step the trade (or the no-trade look) was decided.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from jev_trader.api.sim_page import (
    Price,
    Sim,
    asset_of,
    carried_out,
    direction_of,
    price_of,
    real_units,
)
from jev_trader.api.sims_list import AssetName
from jev_trader.api.store import ApiStore
from jev_trader.sim.clock import day_of
from jev_trader.sim.store import ACTION_ENTRY, KIND_FULL_EVALUATION

NO_TRADE = "no_trade"
FORCED_CLOSE = "forced_close"
STOP_PRICE = "stop_price"


@dataclass
class Trade:
    """One position from open to close, in rescaled units and prices (dollars are real)."""

    position: int
    asset: str
    direction: str  # "long" or "short"
    decision: str | None  # the decision behind the entry; None for code's own (holding)
    decided_step: int
    opened_step: int
    closed_step: int | None = None
    closing_reason: str | None = None
    units_in: float = 0.0
    put_in: float = 0.0  # the value of the entry and every add
    units_out: float = 0.0
    taken_out: float = 0.0  # the value of every reduce and close
    costs: float = 0.0  # slippage, commissions or trading fees, and borrow fees
    paid_on_top: float = 0.0  # what of `costs` is not already inside the orders' values
    amount_chosen: float | None = None
    limited_by: str | None = None
    orders: list[dict] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return self.closed_step is not None

    @property
    def profit(self) -> float | None:
        if not self.closed:
            return None
        sign = 1 if self.direction == "long" else -1
        return sign * (self.taken_out - self.put_in) - self.paid_on_top

    @property
    def entry_price(self) -> float:
        return self.put_in / self.units_in

    @property
    def exit_price(self) -> float | None:
        return self.taken_out / self.units_out if self.units_out else None

    def held_overnight(self, step_reached: int | None) -> bool:
        last = self.closed_step if self.closed else step_reached
        return last is not None and day_of(last) != day_of(self.opened_step)


def trades_of(orders: list[dict], charges: list[dict]) -> list[Trade]:
    """The sim's trades, in the order they opened."""
    trades: dict[int, Trade] = {}
    for order in carried_out(orders):
        number = order["POSITION"]
        if order["KIND"] == "entry":
            trades[number] = Trade(
                position=number,
                asset=asset_of(order),
                direction=direction_of(order),
                decision=order.get("DECISION"),
                decided_step=order["STEP_DECIDED"],
                opened_step=order["STEP_CARRIED_OUT"],
                amount_chosen=order.get("AMOUNT_CHOSEN"),
            )
        trade = trades.get(number)
        if trade is None:
            continue
        trade.orders.append(order)
        fee = order.get("COMMISSION_OR_TRADING_FEE") or 0.0
        trade.costs += fee + (order.get("SLIPPAGE_COST") or 0.0)
        trade.paid_on_top += fee
        if order["KIND"] in ("entry", "add"):
            trade.units_in += order["UNITS"]
            trade.put_in += order["VALUE"]
            trade.limited_by = trade.limited_by or order.get("LIMITED_BY")
        else:
            trade.units_out += order["UNITS"]
            trade.taken_out += order["VALUE"]
            if trade.units_out >= trade.units_in - 1e-9:
                trade.closed_step = order["STEP_CARRIED_OUT"]
                trade.closing_reason = order["REASON"]
    for row in charges:
        trade = trades.get(row.get("POSITION"))
        if trade is not None:
            trade.costs += row["AMOUNT"]
            trade.paid_on_top += row["AMOUNT"]
    return sorted(trades.values(), key=lambda t: (t.opened_step, t.position))


def no_trade_looks(decisions: list[dict]) -> list[dict]:
    """The full evaluations that ended in no trade: Jev picked no trade, or the limits left
    nothing of the size."""
    return [
        d
        for d in decisions
        if d["KIND"] == KIND_FULL_EVALUATION and d["ACTION"] != ACTION_ENTRY
    ]


class TradeLine(BaseModel):
    """A trade, or a full evaluation that ended in no trade (`kind` "no trade")."""

    kind: str  # "trade" or "no trade"
    decision: (
        str | None
    )  # opens the decision trail; None for code's own trades (holding)
    position: int | None
    asset: AssetName
    direction: str | None  # "long" bets on a rise, "short" on a fall
    decided_step: int
    decided_at: datetime | None
    opened_step: int | None
    opened_at: datetime | None
    closed_step: int | None  # None while it is open
    closed_at: datetime | None
    units: float | None  # real shares or coins
    entry_price: Price | None  # the average price it was opened (and added to) at
    exit_price: Price | None  # the average price it was closed at
    put_in_usd: float | None
    profit_usd: float | None  # after every trading cost; None while it is open
    trading_costs_usd: float | None
    closing_reason: str | None  # jev, stop_price, forced_close or sim_ended
    amount_chosen: float | None  # the size Jev chose, before the risk limits
    limited_by: str | None  # the risk limit that trimmed it
    trimmed: bool
    held_overnight: bool
    screen_answer: float | None  # for a no-trade look: Jev's screen, 0 to 1
    pick: (
        str | None
    )  # for a no-trade look: Jev's pick ("no_trade", or the trade it chose)
    rating: float | None


class DayMark(BaseModel):
    """Something the page marks beside the table, at the step it happened."""

    step: int
    at: datetime | None
    kind: str  # "daily loss limit reached", "loan interest paid" or "forced close"
    amount_usd: float | None  # the interest paid


class FilterCounts(BaseModel):
    """How many lines each filter would keep, so each filter can say so."""

    trades: int
    lost_money: int
    trimmed: int
    stop_price: int
    overnight: int
    no_trade: int


class TradesTable(BaseModel):
    total: int  # lines across every page, with the filters asked for
    page: int
    page_size: int
    lines: list[TradeLine]
    counts: FilterCounts
    marks: list[DayMark]


@dataclass(frozen=True)
class Filters:
    """Each true filter keeps only the trades it names; `no_trade` adds the no-trade looks."""

    lost_money: bool = False
    trimmed: bool = False
    stop_price: bool = False
    overnight: bool = False
    no_trade: bool = False

    def keeps(self, trade: Trade, step_reached: int | None) -> bool:
        profit = trade.profit
        return (
            (not self.lost_money or (profit is not None and profit < 0))
            and (not self.trimmed or trade.limited_by is not None)
            and (not self.stop_price or trade.closing_reason == STOP_PRICE)
            and (not self.overnight or trade.held_overnight(step_reached))
        )


def trade_line(sim: Sim, trade: Trade, step_reached: int | None) -> TradeLine:
    asset = trade.asset
    exit_price = trade.exit_price
    return TradeLine(
        kind="trade",
        decision=trade.decision,
        position=trade.position,
        asset=sim.asset(asset),
        direction=trade.direction,
        decided_step=trade.decided_step,
        decided_at=sim.at(trade.decided_step),
        opened_step=trade.opened_step,
        opened_at=sim.at(trade.opened_step),
        closed_step=trade.closed_step,
        closed_at=sim.at(trade.closed_step),
        units=real_units(sim, asset, trade.units_in),
        entry_price=price_of(sim, asset, trade.entry_price),
        exit_price=None if exit_price is None else price_of(sim, asset, exit_price),
        put_in_usd=trade.put_in,
        profit_usd=trade.profit,
        trading_costs_usd=trade.costs,
        closing_reason=trade.closing_reason,
        amount_chosen=trade.amount_chosen,
        limited_by=trade.limited_by,
        trimmed=trade.limited_by is not None,
        held_overnight=trade.held_overnight(step_reached),
        screen_answer=None,
        pick=None,
        rating=None,
    )


def _no_trade_line(sim: Sim, look: dict) -> TradeLine:
    pick = look.get("PICK")
    direction = pick.split("_")[0] if pick and pick != NO_TRADE else None
    return TradeLine(
        kind="no trade",
        decision=look["ID"],
        position=None,
        asset=sim.asset(look["ASSET"]),
        direction=direction,
        decided_step=look["STEP"],
        decided_at=sim.at(look["STEP"]),
        opened_step=None,
        opened_at=None,
        closed_step=None,
        closed_at=None,
        units=None,
        entry_price=None,
        exit_price=None,
        put_in_usd=None,
        profit_usd=None,
        trading_costs_usd=None,
        closing_reason=None,
        amount_chosen=look.get("SIZE_CHOSEN"),
        limited_by=look.get("LIMITED_BY"),
        trimmed=look.get("LIMITED_BY") is not None,
        held_overnight=False,
        screen_answer=look.get("SCREEN_ANSWER"),
        pick=pick,
        rating=look.get("RATING"),
    )


def _marks(sim: Sim, store: ApiStore, trades: list[Trade], charges: list[dict]):
    marks: list[DayMark] = []
    days_marked: set[int] = set()
    for row in store.account_steps([sim.id])[sim.id]:
        if row["DAILY_LOSS_REACHED"] and day_of(row["STEP"]) not in days_marked:
            days_marked.add(day_of(row["STEP"]))
            marks.append(
                DayMark(
                    step=row["STEP"],
                    at=sim.at(row["STEP"]),
                    kind="daily loss limit reached",
                    amount_usd=None,
                )
            )
    for row in charges:
        if row["KIND"] == "loan_interest":
            marks.append(
                DayMark(
                    step=row["STEP"],
                    at=sim.at(row["STEP"]),
                    kind="loan interest paid",
                    amount_usd=row["AMOUNT"],
                )
            )
    forced = sorted({t.closed_step for t in trades if t.closing_reason == FORCED_CLOSE})
    marks += [
        DayMark(step=s, at=sim.at(s), kind="forced close", amount_usd=None)
        for s in forced
    ]
    return sorted(marks, key=lambda m: m.step)


def trades_table(
    store: ApiStore, sim_id: int, filters: Filters, page: int, page_size: int
) -> TradesTable:
    sim = Sim(store, sim_id)
    reached = sim.row.get("LAST_COMPLETED_STEP")
    charges = store.charges(sim_id)
    trades = trades_of(store.orders(sim_id), charges)
    looks = no_trade_looks(store.decisions(sim_id))

    kept = [t for t in trades if filters.keeps(t, reached)]
    lines = [(t.decided_step, t.asset, trade_line(sim, t, reached)) for t in kept]
    if filters.no_trade:
        lines += [(d["STEP"], d["ASSET"], _no_trade_line(sim, d)) for d in looks]
    lines.sort(key=lambda line: (line[0], line[1]))
    first = (page - 1) * page_size
    return TradesTable(
        total=len(lines),
        page=page,
        page_size=page_size,
        lines=[line for _, _, line in lines[first : first + page_size]],
        counts=FilterCounts(
            trades=len(trades),
            lost_money=sum(Filters(lost_money=True).keeps(t, reached) for t in trades),
            trimmed=sum(Filters(trimmed=True).keeps(t, reached) for t in trades),
            stop_price=sum(Filters(stop_price=True).keeps(t, reached) for t in trades),
            overnight=sum(Filters(overnight=True).keeps(t, reached) for t in trades),
            no_trade=len(looks),
        ),
        marks=_marks(sim, store, trades, charges),
    )
