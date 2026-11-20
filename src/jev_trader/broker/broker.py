"""The pretend broker: carries out orders with pretend money (spec appendix 1, sections 3 and 4).

How a sim drives it, for each asset that has a bar at a step:

1. `on_bar(asset, bar)`: orders waiting for this asset are carried out at the bar's open, then
   the position's stop price is checked against the bar's low (a long) or high (a short).
2. The agent decides, and places orders with `enter`, `add`, `reduce` and `close`. Each waits for
   the asset's next bar.

At the end of each day (midnight UTC) the sim calls `charge_overnight`; at a sim's last step it
calls `close_everything`. The broker keeps no clock of its own: the sim passes the step.

Two choices the spec leaves to the build (appendix 1, "Not decided by any ticket"):

- The stop price can be hit by the very bar an entry is carried out in: the position is open from
  that bar's open on.
- A short sale's proceeds go into cash, and the loan is how far cash is below zero. A $10,000
  account that sells $2,000 short holds $12,000 of cash and owes nothing.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from jev_trader.broker.config import StopPriceSettings, TradingCosts
from jev_trader.broker.stops import Direction, check_stop_price


class AssetClass(StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


class OrderKind(StrEnum):
    ENTRY = "entry"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"


class ClosingReason(StrEnum):
    """Why an order was placed, and so why a position closed."""

    JEV = "jev"
    STOP_PRICE = "stop_price"
    FORCED_CLOSE = "forced_close"
    SIM_ENDED = "sim_ended"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ChargeKind(StrEnum):
    BORROW_FEE = "borrow_fee"
    LOAN_INTEREST = "loan_interest"


@dataclass(frozen=True)
class Bar:
    step: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Fill:
    """An order carried out: what was bought or sold, at what price, and what it cost."""

    order_id: int
    position_id: int
    asset: str
    kind: OrderKind
    reason: ClosingReason
    side: Side
    step_decided: int
    step_carried_out: int
    units: float
    price_before_slippage: float
    price: float  # after slippage
    value: float  # units times price
    slippage_cost: float
    fee: float  # commission or trading fee, on top of the value


@dataclass(frozen=True)
class Charge:
    """A nightly charge: a short's borrow fee, or the day's loan interest."""

    step: int
    kind: ChargeKind
    position_id: int | None  # the short charged; none for loan interest
    charged_on: float  # the short's value, or the loan, in dollars
    yearly_rate: float
    amount: float


@dataclass
class Position:
    """A holding in one asset, from its entry until it is fully closed."""

    position_id: int
    asset: str
    direction: Direction
    stop_price: float  # fixed at entry, never moved; an add shares it
    step_opened: int
    entry_price: float = 0.0  # the entry fill's price
    average_price: float = 0.0
    units: float = 0.0  # always positive; the direction says which way
    cash_flow: float = 0.0  # every dollar in and out for this position, costs included
    trading_costs: float = 0.0  # slippage, commission or trading fee, and borrow fees


@dataclass(frozen=True)
class ClosedTrade:
    """The finished record of a position, from its entry to its full close."""

    position_id: int
    asset: str
    direction: Direction
    stop_price: float
    step_opened: int
    step_closed: int
    entry_price: float
    exit_price: float
    closing_reason: ClosingReason
    profit: float  # dollars, after every trading cost the position paid
    trading_costs: float


@dataclass
class _Order:
    order_id: int
    asset: str
    kind: OrderKind
    reason: ClosingReason
    step_decided: int
    amount: float | None = None  # dollars, for an entry or an add
    units: float | None = None  # for a reduce
    direction: Direction | None = None  # for an entry
    stop_price: float | None = None  # for an entry


# Units left below this count as none: a position whose last units were sold is closed.
_NO_UNITS = 1e-9
_DAYS_A_YEAR = 365


@dataclass
class Broker:
    """One sim's pretend account: cash, open positions, and every fill and charge so far."""

    cash: float
    asset_classes: dict[str, AssetClass]
    costs: TradingCosts
    stop_settings: StopPriceSettings
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    cancelled_order_ids: list[int] = field(default_factory=list)
    last_prices: dict[str, float] = field(default_factory=dict)
    _waiting: list[_Order] = field(default_factory=list)
    _next_id: int = 1

    # Placing orders. Each waits for the asset's next bar and returns the order's ID.

    def enter(
        self,
        asset: str,
        direction: Direction,
        amount: float,
        stop_price: float,
        step: int,
    ) -> int:
        """Open a position of `amount` dollars; its stop price is checked against the last price."""
        if asset in self.positions or any(
            o.asset == asset and o.kind is OrderKind.ENTRY for o in self._waiting
        ):
            raise ValueError(f"{asset} already has a position or an entry waiting")
        check_stop_price(
            direction, self.last_prices[asset], stop_price, self.stop_settings
        )
        return self._place(
            asset,
            OrderKind.ENTRY,
            ClosingReason.JEV,
            step,
            amount=amount,
            direction=direction,
            stop_price=stop_price,
        )

    def add(self, asset: str, amount: float, step: int) -> int:
        """Put `amount` more dollars into the open position, which keeps its stop price."""
        self._require_position(asset)
        return self._place(asset, OrderKind.ADD, ClosingReason.JEV, step, amount=amount)

    def reduce(self, asset: str, units: float, step: int) -> int:
        """Close `units` of the open position, which stays open at a smaller size."""
        self._require_position(asset)
        return self._place(
            asset, OrderKind.REDUCE, ClosingReason.JEV, step, units=units
        )

    def close(
        self, asset: str, step: int, reason: ClosingReason = ClosingReason.JEV
    ) -> int:
        """Close the whole position: by Jev's decision, or with `reason` a forced close."""
        self._require_position(asset)
        return self._place(asset, OrderKind.CLOSE, reason, step)

    # What the sim tells the broker

    def on_bar(self, asset: str, bar: Bar) -> list[Fill]:
        """The asset's next bar: carry out its waiting orders at the open, then check its stop.

        An order whose position is already gone (closed at its stop price, say) is cancelled.
        """
        fills = []
        for order in [o for o in self._waiting if o.asset == asset]:
            self._waiting.remove(order)
            fill = self._carry_out(order, bar.open, bar.step)
            if fill is None:
                self.cancelled_order_ids.append(order.order_id)
            else:
                fills.append(fill)
        position = self.positions.get(asset)
        if position is not None:
            stop_fill = self._check_stop_price(position, bar)
            if stop_fill is not None:
                fills.append(stop_fill)
        self.last_prices[asset] = bar.close
        return fills

    def charge_overnight(self, step: int) -> list[Charge]:
        """Midnight UTC: each open short pays its borrow fee, then what is owed pays loan interest.

        One day's share (1/365) of each yearly rate, on the value at the last price. A short or a
        loan gone before midnight pays nothing.
        """
        charges = []
        for position in self.positions.values():
            if position.direction is not Direction.SHORT:
                continue
            value = position.units * self.last_prices[position.asset]
            rate = (
                self.costs.stock_borrow_fee_yearly
                if self.asset_classes[position.asset] is AssetClass.STOCK
                else self.costs.crypto_borrow_fee_yearly
            )
            amount = value * rate / _DAYS_A_YEAR
            self.cash -= amount
            position.cash_flow -= amount
            position.trading_costs += amount
            charges.append(
                Charge(
                    step,
                    ChargeKind.BORROW_FEE,
                    position.position_id,
                    value,
                    rate,
                    amount,
                )
            )
        loan = self.loan()
        if loan > 0:
            rate = self.costs.loan_interest_yearly
            amount = loan * rate / _DAYS_A_YEAR
            self.cash -= amount
            charges.append(
                Charge(step, ChargeKind.LOAN_INTEREST, None, loan, rate, amount)
            )
        self.charges.extend(charges)
        return charges

    def close_everything(self, step: int) -> list[Fill]:
        """A sim's last step (ADR 0009): close every position at its asset's last closing price.

        Slippage and the usual costs apply, and orders still waiting are cancelled, so the sim
        ends in cash.
        """
        self.cancelled_order_ids.extend(o.order_id for o in self._waiting)
        self._waiting.clear()
        fills = []
        for position in list(self.positions.values()):
            order = _Order(
                self._new_id(),
                position.asset,
                OrderKind.CLOSE,
                ClosingReason.SIM_ENDED,
                step,
            )
            fills.append(self._carry_out(order, self.last_prices[position.asset], step))
        return fills

    # The account, with each position at its asset's last price

    def account_value(self) -> float:
        """What the account would be worth in cash if every position were closed now."""
        value = self.cash
        for position in self.positions.values():
            sign = 1 if position.direction is Direction.LONG else -1
            value += sign * position.units * self.last_prices[position.asset]
        return value

    def exposure(self) -> float:
        """All open positions added together, a short counted the same as a long."""
        return sum(p.units * self.last_prices[p.asset] for p in self.positions.values())

    def loan(self) -> float:
        """What the account owes: how far cash is below zero."""
        return max(0.0, -self.cash)

    # Inside

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def _place(self, asset, kind, reason, step, **details) -> int:
        order = _Order(self._new_id(), asset, kind, reason, step, **details)
        self._waiting.append(order)
        return order.order_id

    def _require_position(self, asset: str) -> None:
        if asset not in self.positions:
            raise ValueError(f"{asset} has no open position")

    def _check_stop_price(self, position: Position, bar: Bar) -> Fill | None:
        """Close at the stop price, or at the bar's open if the bar opened beyond it."""
        if position.direction is Direction.LONG:
            if bar.low > position.stop_price:
                return None
            price = min(bar.open, position.stop_price)
        else:
            if bar.high < position.stop_price:
                return None
            price = max(bar.open, position.stop_price)
        order = _Order(
            self._new_id(),
            position.asset,
            OrderKind.CLOSE,
            ClosingReason.STOP_PRICE,
            bar.step,
        )
        return self._carry_out(order, price, bar.step)

    def _carry_out(self, order: _Order, base_price: float, step: int) -> Fill | None:
        """Carry out one order at `base_price` made worse by slippage. None if its position is gone."""
        if order.kind is OrderKind.ENTRY:
            position = Position(
                position_id=self._new_id(),
                asset=order.asset,
                direction=order.direction,
                stop_price=order.stop_price,
                step_opened=step,
            )
            self.positions[order.asset] = position
        else:
            position = self.positions.get(order.asset)
            if position is None:
                return None

        buying_more = order.kind in (OrderKind.ENTRY, OrderKind.ADD)
        is_long = position.direction is Direction.LONG
        side = Side.BUY if buying_more == is_long else Side.SELL
        slippage = self.costs.slippage if side is Side.BUY else -self.costs.slippage
        price = base_price * (1 + slippage)
        if buying_more:
            units = order.amount / price
        elif order.kind is OrderKind.REDUCE:
            units = min(order.units, position.units)
        else:
            units = position.units
        value = units * price
        if self.asset_classes[order.asset] is AssetClass.STOCK:
            fee = self.costs.stock_commission
        else:
            fee = value * self.costs.crypto_trading_fee
        slippage_cost = units * abs(price - base_price)

        cash_change = (-value if side is Side.BUY else value) - fee
        self.cash += cash_change
        position.cash_flow += cash_change
        position.trading_costs += fee + slippage_cost
        if buying_more:
            held = position.units * position.average_price
            position.units += units
            position.average_price = (held + value) / position.units
            if order.kind is OrderKind.ENTRY:
                position.entry_price = price
        else:
            position.units -= units

        fill = Fill(
            order_id=order.order_id,
            position_id=position.position_id,
            asset=order.asset,
            kind=order.kind,
            reason=order.reason,
            side=side,
            step_decided=order.step_decided,
            step_carried_out=step,
            units=units,
            price_before_slippage=base_price,
            price=price,
            value=value,
            slippage_cost=slippage_cost,
            fee=fee,
        )
        self.fills.append(fill)
        if position.units <= _NO_UNITS:
            self._record_closed_trade(position, fill)
        return fill

    def _record_closed_trade(self, position: Position, last_fill: Fill) -> None:
        del self.positions[position.asset]
        self.closed_trades.append(
            ClosedTrade(
                position_id=position.position_id,
                asset=position.asset,
                direction=position.direction,
                stop_price=position.stop_price,
                step_opened=position.step_opened,
                step_closed=last_fill.step_carried_out,
                entry_price=position.entry_price,
                exit_price=last_fill.price,
                closing_reason=last_fill.reason,
                profit=position.cash_flow,
                trading_costs=position.trading_costs,
            )
        )
