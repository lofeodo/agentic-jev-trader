"""Hourly and daily bars built from 15-minute bars (glossary: hourly bar, daily bar)."""

import pandas as pd

from jev_trader.dataset.bar_sizes import build_bars


def _bars(rows):
    """15-minute bars from (start, open, high, low, close, volume) rows; times are UTC."""
    frame = pd.DataFrame(
        rows, columns=["start", "open", "high", "low", "close", "volume"]
    )
    return frame.set_index(
        pd.DatetimeIndex(pd.to_datetime(frame.pop("start"), utc=True))
    )


# A stock's session opening at 13:30 UTC (9:30 New York): two bars in the first hour, four in the next.
SESSION = _bars(
    [
        ("2026-03-02 13:30", 100.0, 101.0, 99.5, 100.5, 1000),
        ("2026-03-02 13:45", 100.5, 102.0, 100.0, 101.5, 2000),
        ("2026-03-02 14:00", 101.5, 101.8, 100.2, 100.4, 1500),
        ("2026-03-02 14:15", 100.4, 100.9, 99.0, 99.2, 500),
        ("2026-03-02 14:30", 99.2, 103.0, 99.1, 102.8, 700),
        ("2026-03-02 14:45", 102.8, 102.9, 101.0, 101.1, 300),
    ]
)


def test_hourly_bars_summarise_each_clock_hour():
    hourly = build_bars(SESSION, "1h")
    assert list(hourly.index) == list(
        pd.to_datetime(["2026-03-02 13:00", "2026-03-02 14:00"], utc=True)
    )
    # The session's first hourly bar is short: two 15-minute bars.
    assert hourly.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 102.0,
        "low": 99.5,
        "close": 101.5,
        "volume": 3000,
    }
    assert hourly.iloc[1].to_dict() == {
        "open": 101.5,
        "high": 103.0,
        "low": 99.0,
        "close": 101.1,
        "volume": 3000,
    }


def test_a_daily_bar_summarises_the_whole_day():
    daily = build_bars(SESSION, "1d")
    assert list(daily.index) == list(pd.to_datetime(["2026-03-02"], utc=True))
    assert daily.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 101.1,
        "volume": 6000,
    }


def test_an_hour_with_no_bars_gives_no_hourly_bar_and_none_is_made_up():
    skips_an_hour = _bars(
        [
            ("2026-03-02 13:45", 100.0, 101.0, 99.0, 100.5, 10),
            ("2026-03-02 15:00", 100.5, 102.0, 100.0, 101.0, 20),
        ]
    )
    hourly = build_bars(skips_an_hour, "1h")
    assert list(hourly.index) == list(
        pd.to_datetime(["2026-03-02 13:00", "2026-03-02 15:00"], utc=True)
    )


def test_15_minute_bars_come_back_unchanged():
    assert build_bars(SESSION, "15m").equals(SESSION)
