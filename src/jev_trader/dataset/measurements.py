"""The 58 measurements of a snapshot (spec appendix 3, section 2).

For every bar of one asset, code works out 48 numbers on the shapes of the asset's last 8 bars
and 10 on its surroundings. A number that cannot be worked out is `None`, "not available"; the
asset is still looked at.

Build choices where the spec leaves the detail open (appendix 3, last section):

- Order: the 48 shape numbers first, newest bar first (`bar_0` is this bar, `bar_7` the oldest),
  six per bar; then the ten surroundings in the spec's table order.
- Shape numbers per bar: direction is +1 for an up bar, -1 for a down bar, 0 when it closes
  where it opened. Body, upper wick and lower wick are shares of the bar's own range (they add up
  to 1); "not available" on a bar with no range. Range and gap (open minus the previous bar's
  close) are in multiples of the current typical move, so all 8 bars share one yardstick.
- Typical move (ATR): the plain average of the last 14 true ranges, as the glossary defines it
  (not Wilder's smoothing). A bar's true range needs the previous bar's close, so the first
  typical move comes at an asset's 15th bar. The long-term trend's daily typical move is the
  same over the last 14 finished daily bars.
- A day is the UTC day; a stock's day is its session. A day is finished at the step its session
  (or, for crypto, the UTC day) ends, so at that step its daily bar joins the long-term average.
- "The previous day" is the asset's previous day with bars, so a weekend or holiday is skipped.
  An asset's first day has none: numbers 7 and 8 are not available.
- History too short: the long-term trend needs 20 finished days and volume against normal 20
  earlier days with bars; until then each is not available, and so stays out of the warm-up
  averages and spreads. Volume against normal averages the same slot (bar number in the session
  or day, so a clock change does not shift it) over those of the 20 days that have a bar there.
- How far through the day on a half-day session: bar number over that session's own bars (14).
- The day's average price (VWAP) weights each bar's typical price, (high + low + close) / 3.
"""

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from jev_trader.dataset.bars import BAR_LENGTH, Bar

TYPICAL_MOVE_BARS = 14
TREND_BARS = 20
LONG_TREND_DAYS = 20
VOLUME_DAYS = 20
SHAPE_BARS = 8
SHAPE_FIELDS = ("direction", "body", "upper_wick", "lower_wick", "range", "gap")
CONTEXT_NAMES = (
    "short_term_trend",
    "long_term_trend",
    "volume_against_normal",
    "from_days_average_price",
    "below_days_high",
    "above_days_low",
    "from_previous_days_high",
    "from_previous_days_low",
    "through_the_day",
    "typical_move_share_of_price",
)
MEASUREMENT_NAMES = (
    tuple(f"bar_{k}_{name}" for k in range(SHAPE_BARS) for name in SHAPE_FIELDS)
    + CONTEXT_NAMES
)
_INDEX = {name: i for i, name in enumerate(MEASUREMENT_NAMES)}


class AssetClass(StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class Session:
    """A stock's trading hours on one day, in UTC: 9:30 to 16:00 New York time on a full day."""

    open: datetime
    close: datetime


@dataclass(frozen=True)
class Measurements:
    """The 58 numbers of one asset at one step, in `MEASUREMENT_NAMES` order.

    `day` is the UTC day of the bar; `bar_number` counts from 1 within the stock's session or
    crypto's UTC day, which has `bars_in_day` bars (26 in a full session, 96 for crypto).
    """

    asset_class: AssetClass
    day: date
    bar_number: int
    bars_in_day: int
    values: tuple[float | None, ...]

    def __getitem__(self, name: str) -> float | None:
        return self.values[_INDEX[name]]


@dataclass
class _Day:
    """One day of an asset's bars: when it begins and ends, its daily bar, and volume per slot."""

    day: date
    begins: datetime
    ends: datetime
    open: float
    high: float
    low: float
    close: float
    volume_by_slot: dict[int, float] = field(default_factory=dict)

    @property
    def bars_in_day(self) -> int:
        return (self.ends - self.begins) // BAR_LENGTH

    def slot(self, bar: Bar) -> int:
        return (bar.start - self.begins) // BAR_LENGTH + 1


def _true_range(bar_high: float, bar_low: float, previous_close: float) -> float:
    return max(
        bar_high - bar_low,
        abs(bar_high - previous_close),
        abs(bar_low - previous_close),
    )


def _typical_move(bars: Sequence[Bar], i: int) -> float | None:
    """The average true range over the 14 bars up to bar `i`; not available when it is zero."""
    if i < TYPICAL_MOVE_BARS:
        return None
    window = bars[i - TYPICAL_MOVE_BARS : i + 1]
    ranges = [
        _true_range(b.high, b.low, before.close)
        for before, b in itertools.pairwise(window)
    ]
    return sum(ranges) / TYPICAL_MOVE_BARS or None


def _per(distance: float, unit: float | None) -> float | None:
    return None if unit is None else distance / unit


def _from(price: float, level: float | None, unit: float | None) -> float | None:
    """How far `price` is above `level` (below when negative), in `unit`s."""
    return None if level is None else _per(price - level, unit)


def _shape(
    bars: Sequence[Bar], j: int, typical_move: float | None
) -> list[float | None]:
    if j < 0:
        return [None] * len(SHAPE_FIELDS)
    bar = bars[j]
    span = bar.high - bar.low
    direction = (bar.close > bar.open) - (bar.close < bar.open)
    if span > 0:
        body = abs(bar.close - bar.open) / span
        upper = (bar.high - max(bar.open, bar.close)) / span
        lower = (min(bar.open, bar.close) - bar.low) / span
    else:
        body = upper = lower = None
    gap = None if j == 0 else _per(bar.open - bars[j - 1].close, typical_move)
    return [direction, body, upper, lower, _per(span, typical_move), gap]


def _day_frame(
    bar: Bar, asset_class: AssetClass, sessions: Mapping[date, Session]
) -> tuple[datetime, datetime]:
    """When the bar's day begins and ends: a stock's session, or crypto's UTC day."""
    day = bar.start.date()
    if asset_class is AssetClass.CRYPTO:
        midnight = datetime.combine(day, time(), tzinfo=UTC)
        return midnight, midnight + timedelta(days=1)
    if day not in sessions:
        raise ValueError(f"No session given for the stock bar starting {bar.start}")
    return sessions[day].open, sessions[day].close


def _days(
    bars: Sequence[Bar], asset_class: AssetClass, sessions: Mapping[date, Session]
) -> tuple[list[_Day], list[int]]:
    """The asset's days with bars, in order, and the index of each bar's day."""
    days: list[_Day] = []
    day_of_bar = []
    for bar in bars:
        if not days or days[-1].day != bar.start.date():
            begins, ends = _day_frame(bar, asset_class, sessions)
            days.append(
                _Day(
                    bar.start.date(),
                    begins,
                    ends,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                )
            )
        today = days[-1]
        today.high = max(today.high, bar.high)
        today.low = min(today.low, bar.low)
        today.close = bar.close
        today.volume_by_slot[today.slot(bar)] = bar.volume
        day_of_bar.append(len(days) - 1)
    return days, day_of_bar


def _long_term_trend(price: float, finished: list[_Day]) -> float | None:
    """Price against the average close of the last 20 finished days, in daily typical moves."""
    if len(finished) < LONG_TREND_DAYS:
        return None
    average = sum(d.close for d in finished[-LONG_TREND_DAYS:]) / LONG_TREND_DAYS
    recent = finished[-TYPICAL_MOVE_BARS - 1 :]
    daily_ranges = [
        _true_range(d.high, d.low, before.close)
        for before, d in itertools.pairwise(recent)
    ]
    return _from(price, average, sum(daily_ranges) / TYPICAL_MOVE_BARS or None)


def _volume_against_normal(
    volume: float, slot: int, earlier: list[_Day]
) -> float | None:
    """The bar's volume against the same slot's average over the previous 20 days with bars."""
    if len(earlier) < VOLUME_DAYS:
        return None
    same_slot = [
        d.volume_by_slot[slot]
        for d in earlier[-VOLUME_DAYS:]
        if slot in d.volume_by_slot
    ]
    if not sum(same_slot):
        return None
    return volume / (sum(same_slot) / len(same_slot))


def measure_asset(
    bars: Sequence[Bar],
    asset_class: AssetClass,
    sessions: Mapping[date, Session] | None = None,
) -> list[Measurements]:
    """The 58 measurements at every bar of one asset, in the order of `bars` (oldest first).

    A stock needs `sessions`: its session on each UTC day it has bars (the exchange calendar).
    """
    if any(b.start >= later.start for b, later in itertools.pairwise(bars)):
        raise ValueError("Bars must be in time order, at most one per step")
    days, day_of_bar = _days(bars, asset_class, sessions or {})
    result = []
    for i, bar in enumerate(bars):
        d = day_of_bar[i]
        today = days[d]
        if i == 0 or day_of_bar[i - 1] != d:
            day_high, day_low, day_volume, day_price_volume = (
                bar.high,
                bar.low,
                0.0,
                0.0,
            )
        day_high, day_low = max(day_high, bar.high), min(day_low, bar.low)
        day_volume += bar.volume
        day_price_volume += (bar.high + bar.low + bar.close) / 3 * bar.volume
        days_average = day_price_volume / day_volume if day_volume else None
        typical_move = _typical_move(bars, i)
        slot = today.slot(bar)
        finished = days[: d + 1] if bar.end >= today.ends else days[:d]
        previous = days[d - 1] if d else None
        short_average = (
            sum(b.close for b in bars[i - TREND_BARS + 1 : i + 1]) / TREND_BARS
            if i >= TREND_BARS - 1
            else None
        )

        values: list[float | None] = []
        for k in range(SHAPE_BARS):
            values += _shape(bars, i - k, typical_move)
        values += [
            _from(bar.close, short_average, typical_move),
            _long_term_trend(bar.close, finished),
            _volume_against_normal(bar.volume, slot, days[:d]),
            _from(bar.close, days_average, typical_move),
            _per(day_high - bar.close, typical_move),
            _per(bar.close - day_low, typical_move),
            _from(bar.close, previous and previous.high, typical_move),
            _from(bar.close, previous and previous.low, typical_move),
            slot / today.bars_in_day,
            _per(typical_move, bar.close) if typical_move else None,
        ]
        result.append(
            Measurements(asset_class, today.day, slot, today.bars_in_day, tuple(values))
        )
    return result
