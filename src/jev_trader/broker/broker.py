"""The pretend broker: carries out orders with pretend money (spec appendix 1, sections 3 and 4).

How a sim drives it, for each asset that has a bar at a step:

1. `on_bar(asset, bar)`: orders waiting for this asset are carried out at the bar's open, then
   the position's stop price is checked against the bar's low (a long) or high (a short).
2. The agent decides, and places orders with `enter`, `add`, `reduce` and `close`. Each waits for
   the asset's next bar.

At the end of each day (midnight UTC) the sim calls `charge_overnight`; at a sim's last step it
calls `close_everything`. The broker keeps no clock of its own: the sim passes the step.

Three choices the spec leaves to the build (appendix 1, "Not decided by any ticket"):

- The stop price can be hit by the very bar an entry is carried out in: the position is open from
  that bar's open on. A bar that opens beyond the stop price enters and closes at that open.
- The 5% cap on a stop price is checked once, against the last price it was worked out from,
  when the order is placed. It is not checked again against the price the order is carried out at.
- A short sale's money goes into cash but is not the account's own: the loan is what the
  positions bought cost beyond the account's own cash, as the glossary has it. $10,000 that buys
  $16,000 and sells $5,000 short owes $6,000; selling $2,000 short alone owes nothing.

Every position has a stop price, except the long `buy_and_hold` opens for the `buy_hold`
comparison, which never trades until the sim's last step.

**Risk limits** (spec appendix 1, section 5). A broker given a risk profile (every sim the agent
trades in; not `buy_hold`) enforces it whatever Jev chose:

- An entry or an add is made smaller to fit the trade risk, position and exposure limits when it
  is placed (at the last price) and again when it is carried out (at the open, with account value
  and exposure as they stand just before it). The fill and the closed trade record the amount
  chosen and the limit that made it smaller. An order the limits leave nothing of is cancelled,
  and `blocked_orders` records which limit did it.
- Once the daily loss limit is reached, entries and adds are refused until midnight UTC, and those
  already waiting are cancelled when their bar comes. Closes and reduces are never blocked.
- No stock entry in a session's last bars (two in medium), no stock add on its last bar.
- `check_account`, called by the sim once a step after every bar, latches the daily loss limit
  and places a forced close of every position when account value is below the forced close share
  of exposure (a quarter in medium). A forced close cancels every other waiting order, and while
  one waits no entry or add is placed or carried out.
- The second check starts again from the amount Jev chose, so an order cut when placed may be
  carried out larger, never above Jev's amount, if room has opened since.
"""

from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum

from jev_trader.broker.config import StopPriceSettings, TradingCosts
from jev_trader.broker.stops import Direction, check_stop_price
from jev_trader.risk import RiskLimit, RiskProfile


class AssetClass(StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


class OrderKind(StrEnum):
    ENTRY = "entry"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"

    @property
    def grows(self) -> bool:
        """An entry or an add: puts money into a position, so the risk limits apply."""
        return self in (OrderKind.ENTRY, OrderKind.ADD)


class ClosingReason(StrEnum):
    """Why an order was placed, and so why a position closed."""

    JEV = "jev"
    STOP_PRICE = "stop_price"
    FORCED_CLOSE = "forced_close"
    SIM_ENDED = "sim_ended"
    BUY_HOLD = "buy_hold"  # a purchase of the holding sim, which nobody decides


class BlockedByRiskLimit(ValueError):
    """An entry or an add a risk limit forbids outright: the deciding code should not ask for it.

    `Broker.entry_blocked_by` and `Broker.add_blocked_by` say so beforehand.
    """

    def __init__(self, limit: RiskLimit, asset: str):
        super().__init__(f"{asset}: blocked by the {limit} limit")
        self.limit = limit


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
    commission_or_trading_fee: float  # on top of the value
    # An entry or an add under a risk profile: the amount Jev chose, and the limit that made it
    # smaller (None if none did; the value is then the amount chosen).
    amount_chosen: float | None = None
    limited_by: RiskLimit | None = None


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
    stop_price: (
        float | None
    )  # fixed at entry, never moved; an add shares it; None: `buy_hold`
    step_opened: int
    entry_price: float = 0.0  # the entry fill's price
    average_price: float = 0.0
    units: float = 0.0  # always positive; the direction says which way
    cash_flow: float = 0.0  # every dollar in and out for this position, costs included
    # Slippage, commission or trading fee, and borrow fees. Loan interest is the account's,
    # not one position's, so it is not here.
    trading_costs: float = 0.0
    # The entry: the amount Jev chose, the amount put in, and the limit that made it smaller.
    amount_chosen: float | None = None
    amount_entered: float = 0.0
    limited_by: RiskLimit | None = None
    # Its best and worst point so far: what closing would have left, after trading costs, at
    # each of its bars' closes. None until its first bar has closed.
    best: float | None = None
    worst: float | None = None


@dataclass(frozen=True)
class ClosedTrade:
    """The finished record of a position, from its entry to its full close."""

    position_id: int
    asset: str
    direction: Direction
    stop_price: float | None
    step_opened: int
    step_closed: int
    entry_price: float
    exit_price: float
    closing_reason: ClosingReason
    profit: float  # dollars, after every trading cost the position paid
    trading_costs: float
    # The entry: the amount Jev chose, the amount put in, and the limit that made it smaller.
    amount_chosen: float | None = None
    amount_entered: float = 0.0
    limited_by: RiskLimit | None = None


@dataclass
class Order:
    """An order placed and not yet carried out (or cancelled before it was)."""

    order_id: int
    asset: str
    kind: OrderKind
    reason: ClosingReason
    step_decided: int
    amount: float | None = (
        None  # dollars, for an entry or an add, after the risk limits
    )
    amount_chosen: float | None = None  # dollars, as Jev chose them
    limited_by: RiskLimit | None = None
    units: float | None = None  # for a reduce
    direction: Direction | None = None  # for an entry
    stop_price: float | None = None  # for an entry


def _limit(value: str | None) -> RiskLimit | None:
    return None if value is None else RiskLimit(value)


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
    risk: RiskProfile | None = None  # None only for the `buy_hold` comparison
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    cancelled_orders: list[Order] = field(default_factory=list)
    blocked_orders: dict[int, RiskLimit] = field(
        default_factory=dict
    )  # cancelled by a limit
    last_prices: dict[str, float] = field(default_factory=dict)
    start_of_day_value: float | None = None  # account value at the last midnight UTC
    daily_loss_reached: bool = False
    _waiting: list[Order] = field(default_factory=list)
    _next_id: int = 1

    def __post_init__(self) -> None:
        if self.start_of_day_value is None:
            self.start_of_day_value = self.cash

    @property
    def cancelled_order_ids(self) -> list[int]:
        return [o.order_id for o in self.cancelled_orders]

    @property
    def waiting_orders(self) -> tuple[Order, ...]:
        """Copies of the orders waiting for their asset's next bar, oldest first."""
        return tuple(replace(o) for o in self._waiting)

    # Saving the account and bringing it back (ADR 0013)

    def state(self) -> dict:
        """Everything needed to carry on from here, as plain data JSON can hold.

        Cash, open positions, waiting orders, last prices, the day's starting value and the next
        order number. The history (fills, charges, closed trades, cancelled orders) is left out:
        the sim has stored it already. So are the settings, which the sim stores once.
        """
        return {
            "cash": self.cash,
            "positions": [asdict(p) for p in self.positions.values()],
            "waiting": [asdict(o) for o in self._waiting],
            "last_prices": dict(self.last_prices),
            "start_of_day_value": self.start_of_day_value,
            "daily_loss_reached": self.daily_loss_reached,
            "next_id": self._next_id,
        }

    @classmethod
    def from_state(
        cls,
        state: dict,
        asset_classes: dict[str, AssetClass],
        costs: TradingCosts,
        stop_settings: StopPriceSettings,
        risk: RiskProfile | None = None,
    ) -> "Broker":
        """The broker that `state()` saved, given the settings it ran with."""
        positions = [
            Position(
                **{
                    **p,
                    "direction": Direction(p["direction"]),
                    "limited_by": _limit(p["limited_by"]),
                }
            )
            for p in state["positions"]
        ]
        waiting = [
            Order(
                **{
                    **o,
                    "kind": OrderKind(o["kind"]),
                    "reason": ClosingReason(o["reason"]),
                    "limited_by": _limit(o["limited_by"]),
                    "direction": o["direction"] and Direction(o["direction"]),
                }
            )
            for o in state["waiting"]
        ]
        return cls(
            cash=state["cash"],
            asset_classes=asset_classes,
            costs=costs,
            stop_settings=stop_settings,
            risk=risk,
            positions={p.asset: p for p in positions},
            last_prices=dict(state["last_prices"]),
            start_of_day_value=state["start_of_day_value"],
            daily_loss_reached=state["daily_loss_reached"],
            _waiting=waiting,
            _next_id=state["next_id"],
        )

    # Placing orders. Each waits for the asset's next bar and returns the order's ID.

    def enter(
        self,
        asset: str,
        direction: Direction,
        amount: float,
        stop_price: float,
        step: int,
        bars_left: int | None = None,
    ) -> int:
        """Open a position of `amount` dollars; its stop price is checked against the last price.

        Under a risk profile, a stock order gives `bars_left`, the bars left in its session (0 on
        the last bar), and the amount is made smaller to fit the limits.
        """
        if asset not in self.last_prices:
            raise ValueError(f"{asset} has no bar yet to check a stop price against")
        check_stop_price(
            direction, self.last_prices[asset], stop_price, self.stop_settings
        )
        blocked_by = self.entry_blocked_by(asset, bars_left)
        if blocked_by is not None:
            raise BlockedByRiskLimit(blocked_by, asset)
        return self._place_entry(asset, direction, amount, stop_price, step)

    def buy_and_hold(self, asset: str, amount: float, step: int) -> int:
        """Open a long of `amount` dollars with no stop price: only for `buy_hold`.

        The comparison that holds the five assets (spec appendix 1, section 6) never trades
        between its first purchases and the sim's last step, so it has no stop price to hit.
        """
        if self.risk is not None:
            raise ValueError("under a risk profile every position has a stop price")
        return self._place_entry(
            asset, Direction.LONG, amount, None, step, ClosingReason.BUY_HOLD
        )

    def add(
        self, asset: str, amount: float, step: int, bars_left: int | None = None
    ) -> int:
        """Put `amount` more dollars into the open position, which keeps its stop price.

        Under a risk profile, made smaller so the whole position fits the limits.
        """
        self._require_position(asset)
        blocked_by = self.add_blocked_by(asset, bars_left)
        if blocked_by is not None:
            raise BlockedByRiskLimit(blocked_by, asset)
        return self._place(asset, OrderKind.ADD, ClosingReason.JEV, step, amount=amount)

    # What the risk limits allow at this step

    def entry_blocked_by(
        self, asset: str, bars_left: int | None = None
    ) -> RiskLimit | None:
        """The limit that forbids a new entry in `asset` now, or None."""
        return self._blocked_by(asset, bars_left, entry=True)

    def add_blocked_by(
        self, asset: str, bars_left: int | None = None
    ) -> RiskLimit | None:
        """The limit that forbids an add to `asset` now, or None."""
        return self._blocked_by(asset, bars_left, entry=False)

    def check_account(self, step: int) -> list[int]:
        """Once a step, after every bar: latch the daily loss limit, and place a forced close.

        A forced close happens when account value is below a quarter of exposure: every other
        waiting order is cancelled and every position gets a close order, carried out at its
        next bar. Returns the forced close order IDs placed at this step.
        """
        if self.risk is None:
            return []
        self._update_daily_loss()
        if not self.risk.forced_close_due(self.account_value(), self.exposure()):
            return []
        for order in list(self._waiting):
            if order.reason is not ClosingReason.FORCED_CLOSE:
                self._waiting.remove(order)
                self.cancelled_orders.append(order)
        already_closing = {o.asset for o in self._waiting}
        return [
            self._place(asset, OrderKind.CLOSE, ClosingReason.FORCED_CLOSE, step)
            for asset in self.positions
            if asset not in already_closing
        ]

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
                self.cancelled_orders.append(order)
            else:
                fills.append(fill)
        position = self.positions.get(asset)
        if position is not None:
            stop_fill = self._check_stop_price(position, bar)
            if stop_fill is not None:
                fills.append(stop_fill)
        self.last_prices[asset] = bar.close
        position = self.positions.get(asset)
        if position is not None:
            profit = self.profit_if_closed(asset)
            position.best = (
                profit if position.best is None else max(position.best, profit)
            )
            position.worst = (
                profit if position.worst is None else min(position.worst, profit)
            )
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
            value = self._value(position)
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
        # A new day: the daily loss limit is measured from here, after the night's charges.
        self.start_of_day_value = self.account_value()
        self.daily_loss_reached = False
        return charges

    def close_everything(self, step: int) -> list[Fill]:
        """A sim's last step (ADR 0009): close every position at its asset's last closing price.

        Slippage and the usual costs apply, and orders still waiting are cancelled, so the sim
        ends in cash.
        """
        self.cancelled_orders.extend(self._waiting)
        self._waiting.clear()
        return [
            self._close_now(
                position,
                self.last_prices[position.asset],
                step,
                ClosingReason.SIM_ENDED,
            )
            for position in list(self.positions.values())
        ]

    # The account, with each position at its asset's last price

    def account_value(self) -> float:
        """What the account would be worth in cash if every position were closed now."""
        value = self.cash
        for position in self.positions.values():
            sign = 1 if position.direction is Direction.LONG else -1
            value += sign * self._value(position)
        return value

    def exposure(self) -> float:
        """All open positions added together, a short counted the same as a long."""
        return sum(self._value(p) for p in self.positions.values())

    def _account_at_price(self, asset: str, price: float) -> tuple[float, float, float]:
        """Account value, exposure and `asset`'s position value, with `asset` at `price`."""
        position = self.positions.get(asset)
        if position is None:
            return self.account_value(), self.exposure(), 0.0
        old = self._value(position)
        new = position.units * price
        sign = 1 if position.direction is Direction.LONG else -1
        return (
            self.account_value() + sign * (new - old),
            self.exposure() + new - old,
            new,
        )

    def profit_if_closed(self, asset: str) -> float:
        """What the position would have made, after every trading cost, if closed at the last price.

        $4,000 of crypto bought at $100.05 for $4,004 with its fee, sold at $100 less slippage
        ($99.95) and a 0.1% fee, leaves about -$12.
        """
        position = self.positions[asset]
        is_long = position.direction is Direction.LONG
        closing_side = Side.SELL if is_long else Side.BUY
        value = position.units * self._price_paid(self.last_prices[asset], closing_side)
        fee = self._commission_or_fee(asset, value)
        return position.cash_flow + (value if is_long else -value) - fee

    def _price_paid(self, base_price: float, side: Side) -> float:
        """The price an order is carried out at: slippage makes it worse for either side."""
        slippage = self.costs.slippage if side is Side.BUY else -self.costs.slippage
        return base_price * (1 + slippage)

    def _commission_or_fee(self, asset: str, value: float) -> float:
        """A stock order's flat commission, or a crypto order's trading fee on its value."""
        if self.asset_classes[asset] is AssetClass.STOCK:
            return self.costs.stock_commission
        return value * self.costs.crypto_trading_fee

    def loan(self) -> float:
        """What the account owes for the positions it bought beyond its own cash.

        Cash holds the money from short sales, but that money stands behind the borrowed units
        and is not the account's own, so the shorts' value is set aside first. $10,000 that buys
        $16,000 and sells $5,000 short holds -$1,000 of cash and owes $6,000.
        """
        shorts = sum(
            self._value(p)
            for p in self.positions.values()
            if p.direction is Direction.SHORT
        )
        return max(0.0, shorts - self.cash)

    def _value(self, position: Position) -> float:
        """A position's size at its asset's last price, a short counted like a long."""
        return position.units * self.last_prices[position.asset]

    # Inside

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def _place(self, asset, kind, reason, step, **details) -> int:
        order = Order(self._new_id(), asset, kind, reason, step, **details)
        if kind.grows:
            if not order.amount > 0:
                raise ValueError(f"an amount must be above zero, not {order.amount}")
            order.amount_chosen = order.amount
            if self.risk is not None and not self._fit_to_limits(
                order, self.last_prices[asset]
            ):
                self.cancelled_orders.append(order)
                return order.order_id
        self._waiting.append(order)
        return order.order_id

    def _fit_to_limits(self, order: Order, price: float) -> bool:
        """Size an entry or an add to fit the risk limits, from Jev's amount, at `price`.

        False, with the limit recorded in `blocked_orders`, if the limits leave nothing of it.
        """
        self._update_daily_loss()
        if self._forced_close_waiting():
            amount, limited_by = 0.0, RiskLimit.FORCED_CLOSE
        elif self.daily_loss_reached:
            amount, limited_by = 0.0, RiskLimit.DAILY_LOSS
        else:
            stop_price = (
                order.stop_price
                if order.kind is OrderKind.ENTRY
                else self.positions[order.asset].stop_price
            )
            account_value, exposure, position_value = self._account_at_price(
                order.asset, price
            )
            amount, limited_by = self.risk.fit(
                order.amount_chosen,
                account_value=account_value,
                price=price,
                stop_price=stop_price,
                position_value=position_value,
                exposure=exposure,
            )
        order.amount, order.limited_by = amount, limited_by
        if order.amount <= 0:
            self.blocked_orders[order.order_id] = limited_by
            return False
        return True

    def _blocked_by(
        self, asset: str, bars_left: int | None, entry: bool
    ) -> RiskLimit | None:
        if self.risk is None:
            return None
        if self._forced_close_waiting():
            return RiskLimit.FORCED_CLOSE
        if self.asset_classes[asset] is AssetClass.STOCK:
            if bars_left is None:
                raise ValueError(
                    f"{asset} is a stock: give the bars left in its session"
                )
            allowed = (
                self.risk.stock_entry_allowed(bars_left)
                if entry
                else self.risk.stock_add_allowed(bars_left)
            )
            if not allowed:
                return RiskLimit.SESSION_END
        self._update_daily_loss()
        return RiskLimit.DAILY_LOSS if self.daily_loss_reached else None

    def _forced_close_waiting(self) -> bool:
        return any(o.reason is ClosingReason.FORCED_CLOSE for o in self._waiting)

    def _update_daily_loss(self) -> None:
        """Once reached, the daily loss limit stays reached until midnight UTC."""
        if self.risk is not None and self.risk.daily_loss_reached(
            self.account_value(), self.start_of_day_value
        ):
            self.daily_loss_reached = True

    def _place_entry(
        self, asset, direction, amount, stop_price, step, reason=ClosingReason.JEV
    ) -> int:
        if asset in self.positions or any(
            o.asset == asset and o.kind is OrderKind.ENTRY for o in self._waiting
        ):
            raise ValueError(f"{asset} already has a position or an entry waiting")
        return self._place(
            asset,
            OrderKind.ENTRY,
            reason,
            step,
            amount=amount,
            direction=direction,
            stop_price=stop_price,
        )

    def _require_position(self, asset: str) -> None:
        if asset not in self.positions:
            raise ValueError(f"{asset} has no open position")

    def _check_stop_price(self, position: Position, bar: Bar) -> Fill | None:
        """Close at the stop price, or at the bar's open if the bar opened beyond it."""
        if position.stop_price is None:  # `buy_hold` only
            return None
        if position.direction is Direction.LONG:
            if bar.low > position.stop_price:
                return None
            price = min(bar.open, position.stop_price)
        else:
            if bar.high < position.stop_price:
                return None
            price = max(bar.open, position.stop_price)
        return self._close_now(position, price, bar.step, ClosingReason.STOP_PRICE)

    def _close_now(
        self, position: Position, price: float, step: int, reason: ClosingReason
    ) -> Fill:
        """Close a whole position at `price` straight away, decided and carried out at `step`."""
        order = Order(self._new_id(), position.asset, OrderKind.CLOSE, reason, step)
        return self._carry_out(order, price, step)

    def _carry_out(self, order: Order, base_price: float, step: int) -> Fill | None:
        """Carry out one order at `base_price` made worse by slippage. None if its position is gone."""
        if order.kind is not OrderKind.ENTRY and order.asset not in self.positions:
            return None
        # The limits again, at the open and with the account as it stands just before the fill.
        if (
            order.kind.grows
            and self.risk is not None
            and not self._fit_to_limits(order, base_price)
        ):
            return None
        if order.kind is OrderKind.ENTRY:
            position = Position(
                position_id=self._new_id(),
                asset=order.asset,
                direction=order.direction,
                stop_price=order.stop_price,
                step_opened=step,
                amount_chosen=order.amount_chosen,
                limited_by=order.limited_by,
            )
            self.positions[order.asset] = position
        else:
            position = self.positions[order.asset]

        # An entry or an add grows the position: a long buys more units, a short sells more.
        grows = order.kind.grows
        is_long = position.direction is Direction.LONG
        side = Side.BUY if grows == is_long else Side.SELL
        price = self._price_paid(base_price, side)
        if grows:
            units = order.amount / price
        elif order.kind is OrderKind.REDUCE:
            units = min(order.units, position.units)
        else:
            units = position.units
        value = units * price
        commission_or_trading_fee = self._commission_or_fee(order.asset, value)
        slippage_cost = units * abs(price - base_price)

        cash_change = (
            -value if side is Side.BUY else value
        ) - commission_or_trading_fee
        self.cash += cash_change
        position.cash_flow += cash_change
        position.trading_costs += commission_or_trading_fee + slippage_cost
        if grows:
            held = position.units * position.average_price
            position.units += units
            position.average_price = (held + value) / position.units
            if order.kind is OrderKind.ENTRY:
                position.entry_price = price
                position.amount_entered = value
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
            commission_or_trading_fee=commission_or_trading_fee,
            amount_chosen=order.amount_chosen,
            limited_by=order.limited_by,
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
                amount_chosen=position.amount_chosen,
                amount_entered=position.amount_entered,
                limited_by=position.limited_by,
            )
        )
