"""The cleaning rules a dataset build applies to one asset's bars (spec appendix 2, sections 5 and 6).

All bars here are made up: no provider data lands in the repo.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from jev_trader.dataset.bars import BAR_LENGTH, Bar
from jev_trader.dataset.measurements import Session
from jev_trader.dataset.quality import (
    MissingBar,
    MissingReason,
    NotEnoughHistory,
    PartialVolumeTest,
    clean_crypto,
    clean_stock,
)

FULL_DAY_BARS = 26


def session(day: date, close_hour: int = 20) -> tuple[date, Session]:
    """A New York session in summer: opens 13:30 UTC, closes 20:00 (or 17:00 on a half day)."""
    opens = datetime(day.year, day.month, day.day, 13, 30, tzinfo=UTC)
    closes = datetime(day.year, day.month, day.day, close_hour, tzinfo=UTC)
    return day, Session(open=opens, close=closes)


def bars_for(
    sess: Session, volume: float = 1000.0, count: int | None = None
) -> list[Bar]:
    """Bars from the session's open, every 15 minutes, up to its close (or `count` bars)."""
    n = count if count is not None else (sess.close - sess.open) // BAR_LENGTH
    return [
        Bar(sess.open + i * BAR_LENGTH, 100.0, 101.0, 99.0, 100.5, volume)
        for i in range(n)
    ]


def weekdays(first: date, n: int) -> list[date]:
    days, d = [], first
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


# 20 lead-in sessions in June 2023, then the dataset's sessions in July.
LEAD_IN = [session(d) for d in weekdays(date(2023, 6, 1), 20)]
LEAD_IN_BARS = [b for _, s in LEAD_IN for b in bars_for(s)]


def test_early_close_day_drops_bars_after_the_close_and_is_not_a_partial_volume_day():
    # 3 July 2023: the market closes at 13:00 New York time (17:00 UTC). The provider still
    # returns zero-volume bars up to the usual close, 20:00 UTC.
    half_day = session(date(2023, 7, 3), close_hour=17)
    usual_close = Session(
        open=half_day[1].open, close=half_day[1].close.replace(hour=20)
    )
    supplied = bars_for(usual_close)
    supplied = [
        b if b.start < half_day[1].close else Bar(b.start, 100, 100, 100, 100, 0.0)
        for b in supplied
    ]

    result = clean_stock(LEAD_IN_BARS + supplied, sessions=[half_day], lead_in=LEAD_IN)

    assert len(result.bars) == 14
    assert result.bars[-1].start == datetime(2023, 7, 3, 16, 45, tzinfo=UTC)
    assert result.partial_volume_days == []
    assert result.missing == []


JULY = [session(d) for d in weekdays(date(2023, 7, 5), 3)]


def test_a_zero_volume_bar_makes_the_whole_day_missing():
    first, second, third = JULY
    bad = bars_for(second[1])
    bad[5] = Bar(bad[5].start, 100, 100, 100, 100, 0.0)
    supplied = LEAD_IN_BARS + bars_for(first[1]) + bad + bars_for(third[1])

    result = clean_stock(supplied, sessions=JULY, lead_in=LEAD_IN)

    [day] = result.partial_volume_days
    assert day.day == second[0]
    assert day.test is PartialVolumeTest.ZERO_VOLUME_BAR
    assert len(result.missing) == FULL_DAY_BARS
    assert {m.reason for m in result.missing} == {MissingReason.PARTIAL_VOLUME_DAY}
    assert all(b.start.date() != second[0] for b in result.bars)
    assert len(result.bars) == 2 * FULL_DAY_BARS
    assert result.partial_volume_share == pytest.approx(1 / 3)
    assert result.other_missing_share == 0


def test_a_day_under_a_quarter_of_usual_volume_per_bar_is_partial_volume():
    # Usual is 1,000 a bar. A fifth of it (200) is caught; three tenths (300) is not.
    first, second, third = JULY
    supplied = (
        LEAD_IN_BARS
        + bars_for(first[1], volume=200)
        + bars_for(second[1], volume=300)
        + bars_for(third[1])
    )

    result = clean_stock(supplied, sessions=JULY, lead_in=LEAD_IN)

    [day] = result.partial_volume_days
    assert day.day == first[0]
    assert day.test is PartialVolumeTest.UNDER_USUAL
    assert day.share_of_usual == pytest.approx(0.2)


def test_volume_is_compared_per_bar_so_a_short_session_with_normal_bars_passes():
    half_day = session(date(2023, 7, 3), close_hour=17)
    result = clean_stock(
        LEAD_IN_BARS + bars_for(half_day[1]), sessions=[half_day], lead_in=LEAD_IN
    )
    assert result.partial_volume_days == []


def test_usual_is_the_median_of_the_previous_20_sessions_so_one_bad_session_does_not_move_it():
    lead_in_bars = [
        Bar(b.start, b.open, b.high, b.low, b.close, 1.0 if b.start.day == 9 else 1000)
        for b in LEAD_IN_BARS
    ]
    first = JULY[0]
    result = clean_stock(
        lead_in_bars + bars_for(first[1], volume=240), sessions=[first], lead_in=LEAD_IN
    )
    assert result.partial_volume_days[0].share_of_usual == pytest.approx(0.24)


def test_a_bar_the_provider_did_not_supply_stays_missing_and_is_never_filled():
    first = JULY[0]
    day_bars = bars_for(first[1])
    gap = day_bars.pop(10)

    result = clean_stock(LEAD_IN_BARS + day_bars, sessions=[first], lead_in=LEAD_IN)

    assert result.missing == [MissingBar(gap.start, MissingReason.NOT_SUPPLIED)]
    assert len(result.bars) == FULL_DAY_BARS - 1
    assert gap.start not in {b.start for b in result.bars}
    assert result.other_missing_share == pytest.approx(1 / FULL_DAY_BARS)


def test_lead_in_bars_and_stray_bars_outside_the_session_are_not_kept():
    first = JULY[0]
    overnight = Bar(datetime(2023, 7, 5, 2, 0, tzinfo=UTC), 100, 100, 100, 100, 50)
    result = clean_stock(
        LEAD_IN_BARS + [overnight] + bars_for(first[1]),
        sessions=[first],
        lead_in=LEAD_IN,
    )
    assert [b.start for b in result.bars] == [b.start for b in bars_for(first[1])]


def test_a_stock_whose_history_does_not_reach_20_sessions_back_stops_the_build():
    first = JULY[0]
    late_start = [b for b in LEAD_IN_BARS if b.start.date() >= date(2023, 6, 10)]
    with pytest.raises(NotEnoughHistory):
        clean_stock(late_start + bars_for(first[1]), sessions=[first], lead_in=LEAD_IN)
    with pytest.raises(NotEnoughHistory):
        clean_stock(LEAD_IN_BARS, sessions=[first], lead_in=LEAD_IN[1:])


def test_bitcoin_zero_volume_bars_stay_missing_one_at_a_time():
    day = date(2023, 7, 1)
    start = datetime(2023, 7, 1, tzinfo=UTC)
    supplied = [
        Bar(start + i * BAR_LENGTH, 100, 101, 99, 100, 0.0 if i == 40 else 5.0)
        for i in range(96)
        if i != 7
    ]

    result = clean_crypto(supplied, first_day=day, last_day=day)

    assert [(m.start, m.reason) for m in result.missing] == [
        (start + 7 * BAR_LENGTH, MissingReason.NOT_SUPPLIED),
        (start + 40 * BAR_LENGTH, MissingReason.ZERO_VOLUME),
    ]
    assert len(result.bars) == 94
    assert result.partial_volume_days == []
    assert result.other_missing_share == pytest.approx(2 / 96)
