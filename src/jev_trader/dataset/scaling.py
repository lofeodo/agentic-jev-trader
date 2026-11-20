"""Scaling the 58 measurements into standard scores by the warm-up period (ADR 0004).

A standard score is a reading minus the average, divided by the typical spread. The averages and
spreads come only from the warm-up period, the first three months of a dataset, in which no sim
trades. They are worked out once when the dataset is built, shared by all its assets, and frozen
with it, so nothing from after a step reaches it and a snapshot always gets the same scores.

Build choices the spec leaves open:

- The spread is the population standard deviation of the warm-up readings.
- A "not available" reading is left out of the averages and spreads, and scores 0 (average).
- A measurement with no warm-up readings, or whose readings never varied, scores 0 throughout:
  with no spread there is nothing to divide by.
"""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from statistics import fmean, pstdev

from jev_trader.dataset.measurements import MEASUREMENT_NAMES, Measurements

WARM_UP_MONTHS = 3


def warm_up_end(first_day: date) -> date:
    """The first tradable day: three calendar months after the dataset's first day.

    A day missing from the later month (the 31st, say) becomes that month's last day.
    """
    months = first_day.month - 1 + WARM_UP_MONTHS
    year, month = first_day.year + months // 12, months % 12 + 1
    return date(year, month, min(first_day.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Scale:
    average: float
    spread: float


@dataclass(frozen=True)
class WarmUpScales:
    """One average and spread per measurement, in `MEASUREMENT_NAMES` order (`None`: no spread)."""

    scales: tuple[Scale | None, ...]

    @classmethod
    def from_warm_up(
        cls, first_day: date, measurements: Iterable[Measurements]
    ) -> "WarmUpScales":
        """Averages and spreads from the snapshots in the warm-up period; all others are ignored."""
        ends = warm_up_end(first_day)
        readings: list[list[float]] = [[] for _ in MEASUREMENT_NAMES]
        for snapshot in measurements:
            if first_day <= snapshot.day < ends:
                for column, value in zip(readings, snapshot.values):
                    if value is not None:
                        column.append(value)
        scales = []
        for column in readings:
            spread = pstdev(column) if column else 0.0
            scales.append(Scale(fmean(column), spread) if spread > 0 else None)
        return cls(tuple(scales))

    def standard_scores(self, measurements: Measurements) -> tuple[float, ...]:
        """The 58 standard scores; a "not available" reading scores 0, the average."""
        return tuple(
            0.0
            if value is None or scale is None
            else (value - scale.average) / scale.spread
            for value, scale in zip(measurements.values, self.scales)
        )
