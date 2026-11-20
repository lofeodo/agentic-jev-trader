"""The three kinds of bar: 15-minute bars, and the hourly and daily bars built from them.

Bars are a DataFrame indexed by each bar's start time in UTC, with columns open, high, low, close
and volume. An hourly bar summarises one clock hour and a daily bar one UTC day: the first bar's
open, the highest high, the lowest low, the last bar's close and the volume added up (glossary).
A stock's session sits inside one UTC day, so its daily bar is its session. An hour or a day with
no bars gets no bar: nothing is made up.
"""

from typing import Literal

import pandas as pd

BarSize = Literal["15m", "1h", "1d"]

BAR_LENGTH: dict[BarSize, pd.Timedelta] = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "1d": pd.Timedelta(days=1),
}

_SUMMARY = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def bar_starts(bars_15m: pd.DataFrame, size: BarSize) -> pd.DatetimeIndex:
    """For each 15-minute bar, the start of the bar of `size` that holds it."""
    return bars_15m.index.floor(BAR_LENGTH[size])


def build_bars(bars_15m: pd.DataFrame, size: BarSize) -> pd.DataFrame:
    """The bars of `size` built from one asset's 15-minute bars."""
    if size == "15m":
        return bars_15m
    return bars_15m.groupby(bar_starts(bars_15m, size)).agg(_SUMMARY)[list(_SUMMARY)]
