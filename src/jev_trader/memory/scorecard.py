"""The scorecard: the agent's own totals over its closed trades, by group (spec appendix 3,
section 5; ADR 0001). The text sent to Jev and the LLM calls it the track record.

Worked out from stored records whenever it is asked for, never stored. Example: "hammer, long,
stocks, with the trend, high volume: 18 trades, 5 made money, average loss $12".

**What a trade is filed under.** A candle pattern (each name in the pattern window when the trade
was decided, so one trade counts in several groups, or "none"), a direction (a long bets on a
rise, a short on a fall) and an asset class (stocks and crypto never mix). Three splits, taken at
entry, can narrow a group: the trend, the volume level and the part of the day.

**The ladder and its fallback.** The ladder is the groups that fit one moment, broadest first:
pattern, direction and asset class alone; then split by trend; by volume level too; by part of
the day too. The narrowest group holding at least the minimum sample (10 closed trades) is the
one used; a smaller group falls back to the next broader one that holds it. Below that at every
level, only the count is shown ("6 closed trades, too few to show totals"). A trade counts only
from the step it closed.

Choices the spec leaves to the build:

- A measurement not available at entry files the trade under "not available" for that split.
"""

from dataclasses import dataclass
from enum import StrEnum

MINIMUM_SAMPLE = 10
NOT_AVAILABLE = "not available"
NO_PATTERN = "none"  # what a trade opened beside no candle pattern is filed under


class Split(StrEnum):
    """A detail that narrows a group, in the order the ladder adds them."""

    TREND = "trend"
    VOLUME = "volume"
    PART_OF_DAY = "part_of_day"


LADDER = tuple(Split)


def trend(direction: str, long_term_trend: float | None) -> str:
    """A long while the price is above its 20-day average is with the trend; so is a short while
    it is below. There is no "flat"."""
    if long_term_trend is None:
        return NOT_AVAILABLE
    above = long_term_trend >= 0
    return "with the trend" if above == (direction == "long") else "against the trend"


def volume_level(
    volume_against_normal: float | None, low_below: float, high_above: float
) -> str:
    """Low below `low_below` times the usual volume at that time of day, high above
    `high_above`, average between (0.9 and 1.1 in version 1)."""
    if volume_against_normal is None:
        return NOT_AVAILABLE
    if volume_against_normal < low_below:
        return "low"
    return "high" if volume_against_normal > high_above else "average"


@dataclass(frozen=True)
class Moment:
    """What a moment, or a scorecard group, is filed under, for one pattern and direction.

    A group not split by a detail leaves it None."""

    pattern: str
    direction: str
    asset_class: str
    trend: str | None
    volume_level: str | None
    part_of_day: str | None

    def split(self, split: Split) -> str | None:
        return {
            Split.TREND: self.trend,
            Split.VOLUME: self.volume_level,
            Split.PART_OF_DAY: self.part_of_day,
        }[split]

    def group(self, splits: tuple[Split, ...]) -> "Moment":
        """The scorecard group this falls in, split only by `splits`."""
        return Moment(
            self.pattern,
            self.direction,
            self.asset_class,
            *(self.split(s) if s in splits else None for s in LADDER),
        )


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
class Tally:
    """How some closed trades' profits add up. A trade at exactly $0 neither made nor lost."""

    profits: tuple[float, ...] | list[float]

    @property
    def trades(self) -> int:
        return len(self.profits)

    @property
    def gains(self) -> list[float]:
        return [p for p in self.profits if p > 0]

    @property
    def losses(self) -> list[float]:
        return [p for p in self.profits if p < 0]

    @property
    def made_money(self) -> int:
        return len(self.gains)

    @property
    def share_made_money(self) -> float | None:
        return len(self.gains) / len(self.profits) if self.profits else None

    @property
    def average_gain(self) -> float | None:
        return sum(self.gains) / len(self.gains) if self.gains else None

    @property
    def average_loss(self) -> float | None:
        return sum(self.losses) / len(self.losses) if self.losses else None

    @property
    def total_profit(self) -> float:
        return sum(self.profits)

    @property
    def gains_over_losses(self) -> float | None:
        """Total gains over total losses (the profit factor); None with no loss."""
        return sum(self.gains) / -sum(self.losses) if self.losses else None


@dataclass(frozen=True)
class Rung(Tally):
    """One group of the ladder: the splits it keeps, and its closed trades' profits."""

    splits: tuple[Split, ...] = ()


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

    def above(self, splits: tuple[Split, ...]) -> "Ladder":
        """The broader groups only: those split by fewer than `splits`."""
        return Ladder(self.rungs[: len(splits)], self.minimum)


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
        splits = LADDER[:depth]
        group = moment.group(splits)
        profits = tuple(
            t.profit
            for t in trades
            if step is None or t.closed_step <= step
            for m in t.moments()
            if m.group(splits) == group
        )
        rungs.append(Rung(profits=profits, splits=splits))
    return Ladder(tuple(rungs), minimum)
