"""The situation text, written by code from the measurements (spec appendix 3, section 3).

The expected texts are the spec's approved template and the walkthrough pages' made-up examples.
"""

from datetime import date

import pytest

from jev_trader.dataset.measurements import MEASUREMENT_NAMES, AssetClass, Measurements
from jev_trader.dataset.situation_text import PatternLists, part_of_day, situation_text

DAY = date(2023, 8, 1)


def snapshot(asset_class, bar_number, bars_in_day, directions, **readings):
    """Made-up measurements: the last 8 bars' directions (this bar first), plus `readings`."""
    readings.update({f"bar_{k}_direction": d for k, d in enumerate(directions)})
    values = tuple(readings.get(name) for name in MEASUREMENT_NAMES)
    return Measurements(asset_class, DAY, bar_number, bars_in_day, values)


def approved_template_snapshot(**changes):
    readings = {
        # This bar: up, 2.0 typical moves from low to high, closing 80% of the way up.
        "bar_0_body": 0.6,
        "bar_0_upper_wick": 0.2,
        "bar_0_lower_wick": 0.2,
        "bar_0_range": 2.0,
        "short_term_trend": 1.5,
        "long_term_trend": 2.1,
        "volume_against_normal": 1.8,
        "from_days_average_price": 1.0,
        "below_days_high": 1.0,
        "above_days_low": 2.0,
        "from_previous_days_high": 1.0,
        "from_previous_days_low": 4.0,
        "through_the_day": 3 / 26,
        "typical_move_share_of_price": 0.006,
    }
    readings.update(changes)
    return snapshot(AssetClass.STOCK, 3, 26, [1, 1, 1, -1, 1, -1, 1, -1], **readings)


APPROVED_PATTERNS = PatternLists(
    window=[("hammer", 2), ("bullish engulfing", 0)], hourly=[], daily=["doji"]
)


def test_the_approved_template_word_for_word():
    assert situation_text(approved_template_snapshot(), APPROVED_PATTERNS) == (
        "Stock, first hour (bar 3 of 26). "
        "Patterns in the last 4 bars: bullish engulfing (this bar), hammer (2 bars ago). "
        "Latest hourly bar: none. Latest daily bar: doji. "
        "Last 8 bars: five up, three down; this bar is a large up bar closing near its high. "
        "Short-term trend up (1.5 typical moves above the 20-bar average). "
        "Long-term trend up (2.1 above the 20-day average). "
        "Volume high (1.8 times normal). "
        "Price is 1.0 above the day's average price, 1.0 below the day's high, "
        "2.0 above the day's low, and 1.0 above the previous day's high. "
        "Typical move: 0.6% of price."
    )


def test_the_walkthroughs_last_hour_example_word_for_word():
    measured = snapshot(
        AssetClass.STOCK,
        24,
        26,
        [1, -1, -1, 1, -1, -1, -1, -1],
        # A small up bar: 0.5 typical moves, closing half-way up its range.
        bar_0_body=0.2,
        bar_0_upper_wick=0.5,
        bar_0_lower_wick=0.3,
        bar_0_range=0.5,
        short_term_trend=-1.7,
        long_term_trend=-0.9,
        volume_against_normal=0.7,
        from_days_average_price=-1.2,
        below_days_high=2.6,
        above_days_low=0.3,
        from_previous_days_high=-3.1,
        from_previous_days_low=0.4,
        typical_move_share_of_price=0.006,
    )
    patterns = PatternLists(window=[("bullish engulfing", 0)], hourly=[], daily=[])

    assert situation_text(measured, patterns) == (
        "Stock, last hour (bar 24 of 26). "
        "Patterns in the last 4 bars: bullish engulfing (this bar). "
        "Latest hourly bar: none. Latest daily bar: none. "
        "Last 8 bars: two up, six down; this bar is a small up bar closing mid-range. "
        "Short-term trend down (1.7 typical moves below the 20-bar average). "
        "Long-term trend down (0.9 below the 20-day average). "
        "Volume low (0.7 times normal). "
        "Price is 1.2 below the day's average price, 2.6 below the day's high, "
        "0.3 above the day's low, and 3.1 below the previous day's high. "
        "Typical move: 0.6% of price."
    )


def test_a_number_that_is_not_available_is_left_out():
    measured = approved_template_snapshot(
        volume_against_normal=None, from_previous_days_high=None, long_term_trend=None
    )

    text = situation_text(measured, APPROVED_PATTERNS)

    assert "Volume" not in text
    assert "Long-term" not in text
    assert "previous day" not in text
    assert "2.0 above the day's low. Typical move" in text


def test_without_a_typical_move_the_bar_has_no_size_word_and_no_typical_move_sentence():
    measured = approved_template_snapshot(
        bar_0_range=None, typical_move_share_of_price=None
    )

    text = situation_text(measured, APPROVED_PATTERNS)

    assert "this bar is an up bar closing near its high." in text
    assert "Typical move:" not in text


def test_an_assets_first_bars_count_only_the_bars_it_has_and_name_every_list():
    measured = snapshot(
        AssetClass.CRYPTO, 41, 96, [-1, 0, 1, None, None, None, None, None],
        bar_0_body=0.5, bar_0_upper_wick=0.5, bar_0_lower_wick=0.0,
    )  # fmt: skip
    empty = PatternLists(window=[], hourly=["belt-hold"], daily=[])

    assert situation_text(measured, empty) == (
        "Crypto, European hours (bar 41 of 96). "
        "Patterns in the last 4 bars: none. "
        "Latest hourly bar: belt-hold. Latest daily bar: none. "
        "Last 3 bars: one up, one down, one flat; this bar is a down bar closing at its low."
    )


def test_the_same_numbers_always_give_the_same_text():
    first = situation_text(approved_template_snapshot(), APPROVED_PATTERNS)
    again = situation_text(approved_template_snapshot(), APPROVED_PATTERNS)

    assert first == again


@pytest.mark.parametrize(
    ("reading", "word"),
    [(0.89, "low"), (0.9, "average"), (1.1, "average"), (1.11, "high")],
)
def test_the_volume_word_cuts_at_0_9_and_1_1(reading, word):
    text = situation_text(
        approved_template_snapshot(volume_against_normal=reading), APPROVED_PATTERNS
    )

    assert f"Volume {word} (" in text


def test_a_price_exactly_at_the_long_term_average_counts_as_up():
    text = situation_text(
        approved_template_snapshot(long_term_trend=0.0), APPROVED_PATTERNS
    )

    assert "Long-term trend up (0.0 above the 20-day average)." in text


@pytest.mark.parametrize(
    ("asset_class", "bar_number", "bars_in_day", "part"),
    [
        (AssetClass.STOCK, 4, 26, "first hour"),
        (AssetClass.STOCK, 5, 26, "middle"),
        (AssetClass.STOCK, 23, 26, "last hour"),
        (AssetClass.STOCK, 11, 14, "last hour"),  # a half day's last 4 bars
        (AssetClass.STOCK, 10, 14, "middle"),
        (AssetClass.CRYPTO, 32, 96, "Asian hours"),
        (AssetClass.CRYPTO, 33, 96, "European hours"),
        (AssetClass.CRYPTO, 65, 96, "American hours"),
    ],
)
def test_part_of_the_day(asset_class, bar_number, bars_in_day, part):
    assert part_of_day(asset_class, bar_number, bars_in_day) == part
