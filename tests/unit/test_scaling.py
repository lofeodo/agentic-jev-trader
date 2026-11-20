"""Scaling the 58 measurements by the warm-up period (spec appendix 3, section 2.4; ADR 0004)."""

from datetime import date

import pytest

from jev_trader.dataset.measurements import MEASUREMENT_NAMES, AssetClass, Measurements
from jev_trader.dataset.scaling import WarmUpScales, warm_up_end

FIRST_DAY = date(2023, 4, 3)
VOLUME = MEASUREMENT_NAMES.index("volume_against_normal")


def snapshot(day, **readings):
    """Made-up measurements on `day`: the given readings, every other number not available."""
    values = [readings.get(name) for name in MEASUREMENT_NAMES]
    return Measurements(AssetClass.CRYPTO, day, 1, 96, tuple(values))


def test_the_first_datasets_warm_up_ends_on_2_july_so_3_july_2023_is_tradable():
    assert warm_up_end(FIRST_DAY) == date(2023, 7, 3)


def test_three_months_from_the_31st_lands_on_the_last_day_of_a_shorter_month():
    assert warm_up_end(date(2023, 11, 30)) == date(2024, 2, 29)


def test_a_reading_becomes_a_standard_score_from_the_warm_up_average_and_spread():
    # Volume against normal reads 0.4 and 1.6 in the warm-up: average 1.0, spread 0.6.
    scales = WarmUpScales.from_warm_up(
        FIRST_DAY,
        [
            snapshot(date(2023, 4, 10), volume_against_normal=0.4),
            snapshot(date(2023, 7, 2), volume_against_normal=1.6),
        ],
    )

    scores = scales.standard_scores(
        snapshot(date(2023, 8, 1), volume_against_normal=1.8)
    )

    assert scores[VOLUME] == pytest.approx(0.8 / 0.6)  # about 1.3
    assert len(scores) == 58


def test_snapshots_after_the_warm_up_never_move_the_averages():
    warm_up = [
        snapshot(date(2023, 4, 10), volume_against_normal=0.4),
        snapshot(date(2023, 5, 10), volume_against_normal=1.6),
    ]
    later = [snapshot(date(2023, 7, 3), volume_against_normal=25.0)]

    with_later = WarmUpScales.from_warm_up(FIRST_DAY, warm_up + later)

    assert with_later == WarmUpScales.from_warm_up(FIRST_DAY, warm_up)


def test_not_available_counts_as_average_and_stays_out_of_the_averages():
    scales = WarmUpScales.from_warm_up(
        FIRST_DAY,
        [
            snapshot(date(2023, 4, 10), volume_against_normal=0.4),
            snapshot(date(2023, 4, 11)),  # not available: left out, not counted as zero
            snapshot(date(2023, 4, 12), volume_against_normal=1.6),
        ],
    )

    assert scales.standard_scores(snapshot(date(2023, 8, 1)))[VOLUME] == 0.0
    assert scales.standard_scores(
        snapshot(date(2023, 8, 1), volume_against_normal=1.0)
    )[VOLUME] == pytest.approx(0.0)


def test_a_measurement_that_never_varied_in_the_warm_up_scores_zero():
    # Every warm-up reading is 1.0: there is no spread to divide by, and no readings at all for
    # the other 57 measurements.
    scales = WarmUpScales.from_warm_up(
        FIRST_DAY, [snapshot(date(2023, 4, 10), volume_against_normal=1.0)] * 3
    )

    scores = scales.standard_scores(
        snapshot(date(2023, 8, 1), volume_against_normal=3.0)
    )

    assert scores == (0.0,) * 58
