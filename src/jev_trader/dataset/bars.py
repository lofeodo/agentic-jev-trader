"""The 15-minute bar: one asset's trading over one 15-minute slice, on the one UTC clock (ADR 0002)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

BAR_LENGTH = timedelta(minutes=15)
# Every UTC day has 96 steps, one per 15-minute bar.
STEPS_PER_DAY = 96


@dataclass(frozen=True)
class Bar:
    """First, highest, lowest and last price over 15 minutes, plus the amount traded.

    `start` is timezone-aware UTC. The bar ends, and its step comes, 15 minutes later.
    """

    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def end(self) -> datetime:
        return self.start + BAR_LENGTH
