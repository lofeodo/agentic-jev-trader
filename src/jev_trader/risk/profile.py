"""The risk profile and its arithmetic (spec appendix 1, section 5).

A risk limit is a cap on the account that code enforces whatever Jev chose. Jev chooses how much
money to put in; code then makes the trade smaller if it would break the trade risk limit, the
position limit or the exposure limit. The amount is cut only when it is above a limit.

Choices the spec leaves to the build (appendix 1, "Not decided by any ticket"):

- No rounding and no minimum size: an amount made smaller keeps its cents, and an amount the
  limits cut to nothing is not traded.
- A position's trade risk is measured from the price the size is worked out at (the last price
  when the order is placed, the open when it is carried out) to the stop price, on either side.
"""

import math
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

RISK_PROFILE_PATH = Path(__file__).resolve().parents[3] / "config" / "risk_profile.toml"


class RiskLimit(StrEnum):
    """The limit that made an order smaller, or blocked it."""

    TRADE_RISK = "trade_risk"
    POSITION = "position"
    EXPOSURE = "exposure"
    DAILY_LOSS = "daily_loss"
    SESSION_END = "session_end"  # a stock's last bars of the session


@dataclass(frozen=True)
class RiskProfile:
    """A named set of risk limits. Shares are of account value: 0.01 is 1%, 2.0 is twice it."""

    name: str
    trade_risk_limit: float
    size_buckets: tuple[float, ...]
    position_limit: float
    exposure_limit: float
    daily_loss_limit: float
    forced_close_share: float
    no_new_stock_trade_bars: int

    def chosen_size(
        self, probabilities: Sequence[float], account_value: float
    ) -> float:
        """Jev's size: the size buckets averaged, each weighted by the probability Jev gave it.

        50% on $4,000 and 50% on $8,000 gives $6,000.
        """
        if len(probabilities) != len(self.size_buckets):
            raise ValueError(
                f"{len(probabilities)} probabilities for {len(self.size_buckets)} size buckets"
            )
        return sum(
            p * bucket * account_value
            for p, bucket in zip(probabilities, self.size_buckets, strict=True)
        )

    def largest_size(
        self,
        *,
        account_value: float,
        price: float,
        stop_price: float,
        position_value: float = 0.0,
        exposure: float = 0.0,
    ) -> tuple[float, RiskLimit]:
        """The most an entry (or an add, given the position's value) may put in, and the limit
        that sets it.

        Trade risk: the whole position, losing the stop price's distance, loses at most 1% of
        account value. A stop price 0.95% away allows about $10,500 of a $10,000 account. For an
        add, the position already held uses part of that room. The position and exposure limits
        leave room up to twice account value. Never below zero.
        """
        if account_value <= 0:
            return 0.0, RiskLimit.TRADE_RISK
        distance = abs(price - stop_price) / price
        trade_risk_room = (
            self.trade_risk_limit * account_value / distance - position_value
            if distance > 0
            else math.inf
        )
        rooms = [
            (trade_risk_room, RiskLimit.TRADE_RISK),
            (self.position_limit * account_value - position_value, RiskLimit.POSITION),
            (self.exposure_limit * account_value - exposure, RiskLimit.EXPOSURE),
        ]
        room, limit = min(rooms, key=lambda pair: pair[0])
        return max(0.0, room), limit

    def fit(
        self,
        amount: float,
        *,
        account_value: float,
        price: float,
        stop_price: float,
        position_value: float = 0.0,
        exposure: float = 0.0,
    ) -> tuple[float, RiskLimit | None]:
        """`amount` made smaller to fit the limits, and the limit that made it smaller (if any)."""
        largest, limit = self.largest_size(
            account_value=account_value,
            price=price,
            stop_price=stop_price,
            position_value=position_value,
            exposure=exposure,
        )
        if amount <= largest:
            return amount, None
        return largest, limit

    def forced_close_due(self, account_value: float, exposure: float) -> bool:
        """Whether account value has fallen below the forced close share of exposure.

        $3,000 holding $13,000: a quarter is $3,250, so yes.
        """
        return exposure > 0 and account_value < self.forced_close_share * exposure

    def daily_loss_reached(self, account_value: float, start_of_day: float) -> bool:
        """Whether account value is down the daily loss limit since midnight: $500 of $10,000."""
        return account_value <= start_of_day * (1 - self.daily_loss_limit)

    def stock_entry_allowed(self, bars_left: int) -> bool:
        """No new stock trade in a session's last two bars (`bars_left` is 1 or 0)."""
        return bars_left >= self.no_new_stock_trade_bars

    @staticmethod
    def stock_add_allowed(bars_left: int) -> bool:
        """No add on a stock's last bar: its order would be carried out the next morning."""
        return bars_left > 0


def load_risk_profile(path: Path = RISK_PROFILE_PATH) -> RiskProfile:
    with open(path, "rb") as file:
        values = tomllib.load(file)
    values["size_buckets"] = tuple(values["size_buckets"])
    return RiskProfile(**values)
