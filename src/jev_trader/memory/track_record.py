"""The track record: the agent's own totals over its closed trades, by group (spec appendix 3,
section 5; ADR 0001). The web app calls it the scorecard.

Worked out from stored records whenever it is asked for, never stored. Example: "hammer, long,
stocks, with the trend, high volume: 18 trades, 5 made money, average loss $12".

**What a trade is filed under.** A candle pattern (each name in the pattern window when the trade
was decided, so one trade counts in several groups, or "none"), a direction (a long bets on a
rise, a short on a fall) and an asset class (stocks and crypto never mix). Three details, taken at
entry, can narrow a group: the trend, the volume level and the part of the day.

**The ladder and its fallback.** Narrowest first: all three details; without the part of the day;
without the volume level too; then pattern, direction and asset class alone. The narrowest group
that fits the moment and holds at least the minimum sample (10 closed trades) is the one used.
Below that at every level, only the count is shown ("6 closed trades, too few to show totals").
A trade counts only from the step it closed.

Choices the spec leaves to the build:

- A measurement not available at entry files the trade under "not available" for that detail.
"""

from dataclasses import dataclass
from enum import StrEnum

from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.situation_text import (
    VOLUME_HIGH_ABOVE,
    VOLUME_LOW_BELOW,
    part_of_day,
)

MINIMUM_SAMPLE = 10
NOT_AVAILABLE = "not available"
NO_PATTERN = "none"  # what a trade opened beside no candle pattern is filed under


class Detail(StrEnum):
    """A detail that narrows a group, in the order the ladder adds them."""

    TREND = "trend"
    VOLUME = "volume"
    PART_OF_DAY = "part_of_day"


LADDER = tuple(Detail)


def trend(direction: str, long_term_trend: float | None) -> str:
    """A long while the price is above its 20-day average is with the trend; so is a short while
    it is below. There is no "flat"."""
    if long_term_trend is None:
        return NOT_AVAILABLE
    above = long_term_trend >= 0
    return "with the trend" if above == (direction == "long") else "against the trend"


def volume_level(
    volume_against_normal: float | None,
    low_below: float = VOLUME_LOW_BELOW,
    high_above: float = VOLUME_HIGH_ABOVE,
) -> str:
    if volume_against_normal is None:
        return NOT_AVAILABLE
    if volume_against_normal < low_below:
        return "low"
    return "high" if volume_against_normal > high_above else "average"


def part_of_the_day(asset_class: str, bar_number: int, bars_in_day: int | None) -> str:
    """Stocks: first hour, middle, last hour. Crypto: Asian, European, American hours."""
    return part_of_day(AssetClass(asset_class), bar_number, bars_in_day)


@dataclass(frozen=True)
class Moment:
    """What the present moment (or one group) is filed under, for one pattern and direction.

    A group not split by a detail leaves it None."""

    pattern: str
    direction: str
    asset_class: str
    trend: str | None
    volume_level: str | None
    part_of_day: str | None

    def detail(self, detail: Detail) -> str | None:
        return {
            Detail.TREND: self.trend,
            Detail.VOLUME: self.volume_level,
            Detail.PART_OF_DAY: self.part_of_day,
        }[detail]


@dataclass(frozen=True)
class FiledTrade:
    """A closed trade with what it was filed under at entry."""

    patterns: tuple[str, ...]  # empty: filed under "none"
    direction: str
    asset_class: str
    trend: str
    volume_level: str
    part_of_day: str
    profit: float  # dollars, after trading costs
    closed_step: int

    def moments(self) -> list[Moment]:
        """One per pattern it was filed under."""
        return [
            Moment(
                pattern,
                self.direction,
                self.asset_class,
                self.trend,
                self.volume_level,
                self.part_of_day,
            )
            for pattern in self.patterns or (NO_PATTERN,)
        ]


@dataclass(frozen=True)
class Rung:
    """One group of the ladder: the details it keeps, and the profits of its closed trades."""

    details: tuple[Detail, ...]
    profits: tuple[float, ...]

    @property
    def trades(self) -> int:
        return len(self.profits)

    @property
    def made_money(self) -> int:
        return sum(1 for p in self.profits if p > 0)

    @property
    def share_made_money(self) -> float | None:
        return self.made_money / self.trades if self.trades else None

    @property
    def average_gain(self) -> float | None:
        gains = [p for p in self.profits if p > 0]
        return sum(gains) / len(gains) if gains else None

    @property
    def average_loss(self) -> float | None:
        losses = [p for p in self.profits if p < 0]
        return sum(losses) / len(losses) if losses else None

    @property
    def total_profit(self) -> float:
        return sum(self.profits)


@dataclass(frozen=True)
class Ladder:
    rungs: tuple[Rung, ...]  # broadest first
    minimum: int

    @property
    def count(self) -> int:
        """The closed trades of the broadest group: what is shown when no group is used."""
        return self.rungs[0].trades

    @property
    def shown(self) -> tuple[Rung, ...]:
        """The groups holding the minimum sample, broadest first."""
        return tuple(r for r in self.rungs if r.trades >= self.minimum)

    @property
    def used(self) -> Rung | None:
        """The narrowest group holding the minimum sample; None if none does."""
        shown = self.shown
        return shown[-1] if shown else None


def ladder(
    trades: list[FiledTrade],
    moment: Moment,
    minimum: int = MINIMUM_SAMPLE,
    step: int | None = None,
) -> Ladder:
    """The groups that fit `moment`, broadest first, over the trades closed by `step` (all of
    them when None)."""
    rungs = []
    for depth in range(len(LADDER) + 1):
        details = LADDER[:depth]
        profits = tuple(
            t.profit
            for t in trades
            if step is None or t.closed_step <= step
            for m in t.moments()
            if in_group(m, moment, details)
        )
        rungs.append(Rung(details, profits))
    return Ladder(tuple(rungs), minimum)


def in_group(filed: Moment, group: Moment, details: tuple[Detail, ...]) -> bool:
    """Whether a trade filed under `filed` counts in `group` narrowed by `details`."""
    return (
        (filed.pattern, filed.direction, filed.asset_class)
        == (group.pattern, group.direction, group.asset_class)
    ) and all(filed.detail(d) == group.detail(d) for d in details)
