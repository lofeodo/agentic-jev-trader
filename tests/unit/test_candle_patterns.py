"""Candle patterns recognised on made-up bars (spec appendix 3, section 1; ADR 0005)."""

import numpy as np
import pandas as pd
import pytest
import talib

from jev_trader.dataset.bar_sizes import BAR_LENGTH
from jev_trader.dataset.candle_patterns import DETECTORS, recognise_patterns

NO_MISSING_BARS = pd.DatetimeIndex([], tz="UTC")


def recognise(bars, size, missing=()):
    """recognise_patterns, with the missing bars given as start-time strings."""
    return recognise_patterns(
        bars,
        size,
        pd.DatetimeIndex(pd.to_datetime(list(missing), utc=True))
        if missing
        else NO_MISSING_BARS,
    )


def _bars(starts, ohlc):
    """Bars starting at `starts`, from (open, high, low, close) rows, with volume 100."""
    frame = pd.DataFrame(ohlc, columns=["open", "high", "low", "close"], dtype=float)
    frame["volume"] = 100.0
    return frame.set_index(pd.DatetimeIndex(pd.to_datetime(starts, utc=True)))


def _every(first, count, step=BAR_LENGTH["15m"]):
    return pd.date_range(pd.Timestamp(first, tz="UTC"), periods=count, freq=step)


def _random_bars(count, seed=7):
    """A random walk of 15-minute bars with no missing bar; every fifth bar opens with a jump."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, count)))
    open_ = np.roll(close, 1) * np.where(
        np.arange(count) % 5 == 0, np.exp(rng.normal(0, 0.006, count)), 1
    )
    open_[0] = 100
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.002, count)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.002, count)))
    return _bars(
        _every("2026-03-02 00:00", count), np.column_stack([open_, high, low, close])
    )


FILLER = (100.0, 100.6, 99.4, 100.2)
DOWN = (101.0, 101.2, 99.8, 100.0)  # a down bar: opens at 101, closes at 100
UP_ENGULFING = (
    99.5,
    101.7,
    99.4,
    101.5,
)  # an up bar whose body (99.5 to 101.5) covers 100 to 101


def _named(found, name):
    return found[found["name"] == name]


def test_every_detector_runs_and_reports_exactly_what_ta_lib_gives():
    bars = _random_bars(3000)
    found = recognise(bars, "15m")
    arrays = [bars[c].to_numpy() for c in ("open", "high", "low", "close")]
    for detector in DETECTORS:
        raw = getattr(talib, detector)(*arrays)
        expected = [(bars.index[i], int(raw[i])) for i in np.flatnonzero(raw)]
        mine = found[found["detector"] == detector]
        assert list(zip(mine["start"], mine["value"])) == expected, detector
    # Something is recognised on most bars, often several names at once.
    assert found["start"].nunique() > 0.5 * len(bars)


def test_a_recognised_pattern_carries_its_value_lean_and_name():
    starts = _every("2026-03-02 14:00", 3)
    found = recognise(_bars(starts, [FILLER, DOWN, UP_ENGULFING]), "15m")
    engulfing = _named(found, "bullish engulfing")
    assert engulfing[["start", "detector", "value", "lean"]].values.tolist() == [
        [starts[2], "CDLENGULFING", 100, "bullish"]
    ]


def test_leans_follow_the_sign_with_the_seven_exceptions():
    found = recognise(_random_bars(3000), "15m")
    spinning = found[found["detector"] == "CDLSPINNINGTOP"]
    assert set(np.sign(spinning["value"])) == {-1, 1}
    assert set(spinning["lean"]) == {"neutral"}
    assert set(found.loc[found["detector"] == "CDLGRAVESTONEDOJI", "lean"]) <= {
        "bearish"
    }
    signed = found[
        ~found["detector"].isin(
            [
                "CDLSPINNINGTOP",
                "CDLHIGHWAVE",
                "CDLSHORTLINE",
                "CDLDOJI",
                "CDLLONGLEGGEDDOJI",
                "CDLRICKSHAWMAN",
                "CDLGRAVESTONEDOJI",
            ]
        )
    ]
    assert (signed["lean"] == np.where(signed["value"] > 0, "bullish", "bearish")).all()


def test_a_15_minute_pattern_never_spans_a_missing_bar():
    # The 14:30 bar is missing: the engulfing shape would join the bars either side of it.
    starts = pd.to_datetime(
        ["2026-03-02 14:00", "2026-03-02 14:15", "2026-03-02 14:45"], utc=True
    )
    found = recognise(_bars(starts, [FILLER, DOWN, UP_ENGULFING]), "15m")
    assert _named(found, "bullish engulfing").empty
    # With no bar missing, the same bars give the pattern.
    found = recognise(
        _bars(_every("2026-03-02 14:00", 3), [FILLER, DOWN, UP_ENGULFING]), "15m"
    )
    assert len(_named(found, "bullish engulfing")) == 1


def test_a_15_minute_pattern_never_spans_a_stocks_overnight_close():
    starts = pd.to_datetime(
        ["2026-03-02 20:30", "2026-03-02 20:45", "2026-03-03 14:30"], utc=True
    )
    found = recognise(_bars(starts, [FILLER, DOWN, UP_ENGULFING]), "15m")
    assert _named(found, "bullish engulfing").empty


def _hours(missing=()):
    """Three hours of 15-minute bars: a flat hour, a down hour, then an up hour that engulfs it."""
    filler = [(100.0, 100.3, 99.9, 100.1)] * 4
    down = [
        (101.0, 101.2, 100.6, 100.75),
        (100.75, 100.8, 100.4, 100.5),
        (100.5, 100.6, 100.2, 100.25),
        (100.25, 100.3, 99.8, 100.0),
    ]
    up = [
        (99.5, 100.1, 99.4, 100.0),
        (100.0, 100.6, 99.9, 100.5),
        (100.5, 101.1, 100.4, 101.0),
        (101.0, 101.7, 100.9, 101.5),
    ]
    bars = _bars(_every("2026-03-02 09:00", 12), filler + down + up)
    return bars.drop(pd.to_datetime(list(missing), utc=True))


def test_an_hourly_pattern_is_recognised_on_hourly_bars():
    engulfing = _named(recognise(_hours(), "1h"), "bullish engulfing")
    assert list(engulfing["start"]) == [pd.Timestamp("2026-03-02 11:00", tz="UTC")]


def test_an_hourly_pattern_never_spans_a_missing_bar():
    found = recognise(_hours(missing=["2026-03-02 11:15"]), "1h")
    assert _named(found, "bullish engulfing").empty


def test_an_hourly_pattern_never_stands_on_an_hour_that_lost_its_last_bar():
    # 11:45 is missing, so the 11:00 hourly bar closes early, at 101.0. Nothing in the bars
    # themselves shows it: only the dataset's list of missing bars does.
    bars = _hours(missing=["2026-03-02 11:45"])
    assert not _named(recognise(bars, "1h"), "bullish engulfing").empty
    found = recognise(bars, "1h", missing=["2026-03-02 11:45"])
    assert _named(found, "bullish engulfing").empty
    assert found[found["start"] == pd.Timestamp("2026-03-02 11:00", tz="UTC")].empty


def test_a_daily_pattern_runs_across_the_weekend():
    # Thursday, a falling Friday, then a rising Monday.
    starts = pd.to_datetime(
        ["2026-03-05 14:30", "2026-03-06 14:30", "2026-03-09 14:30"], utc=True
    )
    engulfing = _named(
        recognise(_bars(starts, [FILLER, DOWN, UP_ENGULFING]), "1d"),
        "bullish engulfing",
    )
    assert list(engulfing["start"]) == [pd.Timestamp("2026-03-09", tz="UTC")]


def _hikkake(starts):
    # Five quiet bars; a bar; a bar inside it; a bar with a lower high and a lower low (the shape);
    # then a bar that closes above the second bar's high (the confirmation).
    quiet = [(7.5, 8.0, 7.0, 7.6)] * 5
    shape = [(7.0, 10.0, 5.0, 8.0), (8.0, 9.0, 6.0, 7.0), (7.0, 8.5, 5.5, 6.0)]
    return _bars(starts, quiet + shape + [(6.0, 9.8, 5.9, 9.5)])


def test_hikkake_reports_its_shape_and_its_confirmation():
    starts = _every("2026-03-02 14:00", 9)
    found = recognise(_hikkake(starts), "15m")
    hikkake = found[found["detector"] == "CDLHIKKAKE"]
    assert hikkake[["start", "value"]].values.tolist() == [
        [starts[7], 100],
        [starts[8], 200],
    ]


def test_a_hikkake_confirmation_never_spans_a_missing_bar():
    starts = list(_every("2026-03-02 14:00", 8)) + [
        pd.Timestamp("2026-03-02 16:15", tz="UTC")
    ]
    found = recognise(_hikkake(starts), "15m")
    hikkake = found[found["detector"] == "CDLHIKKAKE"]
    assert hikkake[["start", "value"]].values.tolist() == [[starts[7], 100]]


def test_bars_must_be_in_utc_and_in_order():
    bars = _random_bars(20)
    with pytest.raises(ValueError):
        recognise(bars.tz_convert(None), "15m")
    with pytest.raises(ValueError):
        recognise(bars.iloc[::-1], "15m")
    with pytest.raises(ValueError):
        recognise_patterns(bars, "15m", pd.DatetimeIndex(["2026-03-02 14:00"]))
