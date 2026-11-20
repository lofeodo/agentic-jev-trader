"""The 58 measurements on made-up bars (spec appendix 3, section 2).

Every expected value is worked out by hand from the made-up prices, never by repeating the code.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from jev_trader.dataset.bars import Bar
from jev_trader.dataset.measurements import (
    MEASUREMENT_NAMES,
    AssetClass,
    Session,
    measure_asset,
)

QUARTER = timedelta(minutes=15)
CRYPTO_DAY_1 = datetime(2023, 4, 3, tzinfo=UTC)


def flat_bars(count, start=CRYPTO_DAY_1, price=100.0, spread=0.5, volume=1000.0):
    """Bars that each open and close at `price` and reach `spread` above and below it.

    Every bar's range, and so the typical move, is 2 x spread ($1.00 by default).
    """
    return [
        Bar(
            start=start + i * QUARTER,
            open=price,
            high=price + spread,
            low=price - spread,
            close=price,
            volume=volume,
        )
        for i in range(count)
    ]


def test_there_are_58_measurements_48_on_shapes_then_10_on_surroundings():
    assert len(MEASUREMENT_NAMES) == 58
    assert MEASUREMENT_NAMES[:6] == (
        "bar_0_direction",
        "bar_0_body",
        "bar_0_upper_wick",
        "bar_0_lower_wick",
        "bar_0_range",
        "bar_0_gap",
    )
    assert MEASUREMENT_NAMES[42] == "bar_7_direction"
    assert MEASUREMENT_NAMES[48:] == (
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


def test_this_bars_shape_in_shares_of_its_range_and_in_typical_moves():
    # 14 earlier bars each cover $1.00, so the typical move is $1.00 until this bar.
    bars = flat_bars(15)
    # This bar opens at $100.00 (no gap), falls to $99.80, rises to $101.80, closes at $101.30.
    # Range $2.00; body $1.30 (65% of the range); upper wick $0.50 (25%); lower wick $0.20 (10%).
    # Its true range is $2.00, so the typical move over the last 14 bars is (13 x 1 + 2) / 14.
    bars.append(Bar(bars[-1].end, 100.0, 101.8, 99.8, 101.3, 1000.0))
    this_bar = measure_asset(bars, AssetClass.CRYPTO)[-1]
    typical_move = 15 / 14

    assert this_bar["bar_0_direction"] == 1
    assert this_bar["bar_0_body"] == pytest.approx(0.65)
    assert this_bar["bar_0_upper_wick"] == pytest.approx(0.25)
    assert this_bar["bar_0_lower_wick"] == pytest.approx(0.10)
    assert this_bar["bar_0_range"] == pytest.approx(2.0 / typical_move)
    assert this_bar["bar_0_gap"] == pytest.approx(0.0)


def test_an_older_bars_gap_is_its_open_against_the_bar_before_it():
    bars = flat_bars(15)
    # Two bars ago the price jumped: the bar opened $0.50 above the previous close.
    jumped = bars[-3]
    bars[-3] = Bar(jumped.start, 100.5, 101.0, 100.0, 100.0, 1000.0)
    # True ranges: the jumped bar's is still $1.00, and so are the others; typical move $1.00.
    this_bar = measure_asset(bars, AssetClass.CRYPTO)[-1]

    assert this_bar["bar_2_gap"] == pytest.approx(0.5)
    assert this_bar["bar_2_direction"] == -1
    assert this_bar["bar_1_gap"] == pytest.approx(0.0)


def test_a_number_that_cannot_be_worked_out_is_not_available_and_the_rest_still_are():
    # Only 3 bars: no typical move yet, and nothing for bars 3 to 7.
    third = measure_asset(flat_bars(3), AssetClass.CRYPTO)[-1]

    assert third["bar_0_range"] is None
    assert third["bar_0_gap"] is None
    assert third["bar_2_gap"] is None  # the asset's first bar has no bar before it
    assert third["bar_0_body"] == pytest.approx(0.0)
    assert third["bar_0_upper_wick"] == pytest.approx(0.5)
    assert third["bar_3_direction"] is None
    assert third["bar_7_range"] is None


def test_a_price_that_did_not_move_for_14_bars_leaves_no_typical_move():
    # Every bar opens, closes, and trades at $100.00: no range, so no shares of it either.
    still = measure_asset(flat_bars(20, spread=0.0), AssetClass.CRYPTO)[-1]

    assert still["bar_0_direction"] == 0
    assert still["bar_0_body"] is None
    assert still["bar_0_range"] is None
    assert still["typical_move_share_of_price"] is None


def test_surroundings_within_the_day_for_crypto():
    # 19 quiet bars at $100.00 from midnight UTC, 1,000 traded each, then a rise:
    # this bar opens at $100.00, dips to $99.50, and closes at its high of $101.50 on 3,000.
    bars = flat_bars(19)
    bars.append(Bar(bars[-1].end, 100.0, 101.5, 99.5, 101.5, 3000.0))
    this_bar = measure_asset(bars, AssetClass.CRYPTO)[-1]
    typical_move = 15 / 14  # 13 bars of $1.00 and this bar's $2.00
    # The day's average price weights each bar's typical price (high + low + close) / 3 by
    # its volume: 19 x 1,000 at $100.00 and 3,000 at $100.8333, so $100.11364.
    days_average = (19_000 * 100.0 + 3000 * (101.5 + 99.5 + 101.5) / 3) / 22_000

    # The 20-bar average close is (19 x $100.00 + $101.50) / 20 = $100.075.
    assert this_bar["short_term_trend"] == pytest.approx(1.425 / typical_move)
    assert this_bar["from_days_average_price"] == pytest.approx(
        (101.5 - days_average) / typical_move
    )
    assert this_bar["below_days_high"] == pytest.approx(0.0)
    assert this_bar["above_days_low"] == pytest.approx(2.0 / typical_move)
    assert this_bar["through_the_day"] == pytest.approx(20 / 96)
    assert this_bar["typical_move_share_of_price"] == pytest.approx(
        typical_move / 101.5
    )


def test_the_short_term_trend_needs_20_bars():
    nineteen = measure_asset(flat_bars(19), AssetClass.CRYPTO)[-1]

    assert nineteen["short_term_trend"] is None
    assert nineteen["below_days_high"] == pytest.approx(
        0.5
    )  # $0.50 below, typical move $1.00


def one_noon_bar_a_day(days):
    """One quiet $100.00 bar at 12:00 UTC (bar 49 of 96) on each of `days` days.

    The daily bar is that one bar, so each day's range and true range is $1.00.
    """
    return [
        flat_bars(1, start=CRYPTO_DAY_1 + timedelta(days=n, hours=12))[0]
        for n in range(days)
    ]


def test_surroundings_that_reach_back_over_earlier_days():
    # 20 quiet days, a day with no bars, then a day whose noon bar closes at $103.00 on 1,800.
    bars = one_noon_bar_a_day(20)
    holiday_then_today = bars[-1].start + timedelta(days=2)
    bars.append(Bar(holiday_then_today, 100.0, 103.5, 99.5, 103.0, 1800.0))
    this_bar = measure_asset(bars, AssetClass.CRYPTO)[-1]
    # 15-minute typical move: 13 true ranges of $1.00 and this bar's $4.00.
    typical_move = 17 / 14

    # The 20 finished daily bars close at $100.00 on average and move $1.00 a day.
    assert this_bar["long_term_trend"] == pytest.approx(3.0)
    # 1,800 against 1,000 at noon on the 20 earlier days with bars.
    assert this_bar["volume_against_normal"] == pytest.approx(1.8)
    # The previous day with bars, across the day with none: high $100.50, low $99.50.
    assert this_bar["from_previous_days_high"] == pytest.approx(2.5 / typical_move)
    assert this_bar["from_previous_days_low"] == pytest.approx(3.5 / typical_move)


def test_the_day_in_progress_is_not_in_the_long_term_average():
    bars = one_noon_bar_a_day(20)
    # On the 20th day only 19 days are finished, and only 19 earlier days have bars.
    twentieth = measure_asset(bars, AssetClass.CRYPTO)[-1]

    assert twentieth["long_term_trend"] is None
    assert twentieth["volume_against_normal"] is None
    assert twentieth["from_previous_days_high"] == pytest.approx(-0.5)


def test_volume_against_normal_compares_the_same_time_of_day_only():
    bars = one_noon_bar_a_day(20)
    # Today's bar comes at 12:15, a slot no earlier day has a bar in.
    bars.append(
        Bar(bars[-1].start + timedelta(days=1, minutes=15), 100, 100.5, 99.5, 100, 500)
    )

    assert measure_asset(bars, AssetClass.CRYPTO)[-1]["volume_against_normal"] is None


def full_session(day):
    """9:30 to 16:00 New York time in summer: 13:30 to 20:00 UTC, 26 bars."""
    opens = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=13.5
    )
    return Session(opens, opens + 26 * QUARTER)


def test_a_stock_counts_its_bars_from_the_sessions_open_and_a_half_day_has_14():
    day = CRYPTO_DAY_1.date()
    opens = datetime(2023, 4, 3, 13, 30, tzinfo=UTC)
    half_day = Session(
        opens, opens + 14 * QUARTER
    )  # an early close at 13:00 New York time
    third_bar = flat_bars(1, start=opens + 2 * QUARTER)

    measured = measure_asset(third_bar, AssetClass.STOCK, {day: half_day})[-1]

    assert (measured.bar_number, measured.bars_in_day) == (3, 14)
    assert measured["through_the_day"] == pytest.approx(3 / 14)


def test_a_stock_bar_needs_its_session():
    with pytest.raises(ValueError, match="No session"):
        measure_asset(flat_bars(1), AssetClass.STOCK, {})


def test_at_a_sessions_last_step_its_day_is_finished_and_joins_the_long_term_average():
    # 20 sessions with one bar each, the session's last bar (15:45 to 16:00 New York time).
    days = [CRYPTO_DAY_1.date() + timedelta(days=n) for n in range(20)]
    sessions = {day: full_session(day) for day in days}
    bars = [flat_bars(1, start=sessions[day].close - QUARTER)[0] for day in days[:-1]]
    # The 20th closes at $101.00 after a high of $101.50: a daily true range of $2.00.
    bars.append(
        Bar(sessions[days[-1]].close - QUARTER, 100.0, 101.5, 99.5, 101.0, 1000.0)
    )

    last = measure_asset(bars, AssetClass.STOCK, sessions)[-1]

    # Average of the 20 daily closes: $100.05. Daily typical move: (13 x $1.00 + $2.00) / 14.
    assert last.bar_number == 26
    assert last["long_term_trend"] == pytest.approx(0.95 / (15 / 14))


def test_volume_against_normal_follows_the_session_across_a_clock_change():
    # 20 summer sessions open at 13:30 UTC; after the clocks change, 9:30 New York is 14:30 UTC.
    summer = [date(2023, 10, 2) + timedelta(days=n) for n in range(20)]
    winter_day = date(2023, 11, 6)
    sessions = {day: full_session(day) for day in summer}
    winter_open = datetime(2023, 11, 6, 14, 30, tzinfo=UTC)
    sessions[winter_day] = Session(winter_open, winter_open + 26 * QUARTER)
    bars = [flat_bars(1, start=sessions[day].open)[0] for day in summer]
    bars += flat_bars(1, start=winter_open, volume=1500.0)

    first_bar = measure_asset(bars, AssetClass.STOCK, sessions)[-1]

    # The session's first bar against the 20 earlier first bars of 1,000 each.
    assert first_bar.bar_number == 1
    assert first_bar["volume_against_normal"] == pytest.approx(1.5)


def test_a_stock_bar_outside_its_session_is_refused():
    day = CRYPTO_DAY_1.date()
    before_the_open = flat_bars(1, start=full_session(day).open - QUARTER)

    with pytest.raises(ValueError, match="outside its session"):
        measure_asset(before_the_open, AssetClass.STOCK, {day: full_session(day)})
