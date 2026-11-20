import pytest

from jev_trader.broker import (
    Direction,
    StopPriceSettings,
    check_stop_price,
    load_stop_price_settings,
    stop_prices,
)

SETTINGS = StopPriceSettings(multiples=(1.0, 2.0, 3.0), distance_cap=0.05)


def test_long_stop_prices_sit_1_2_and_3_typical_moves_below_the_price():
    # Spec appendix 1 section 3: at $100 with a typical move of $0.60.
    assert stop_prices(Direction.LONG, 100.0, 0.60, SETTINGS) == pytest.approx(
        [99.40, 98.80, 98.20]
    )


def test_short_stop_prices_sit_above_the_price():
    assert stop_prices(Direction.SHORT, 100.0, 0.60, SETTINGS) == pytest.approx(
        [100.60, 101.20, 101.80]
    )


def test_a_stop_price_more_than_5_percent_away_is_brought_in_to_5_percent():
    # Typical move $2: 1, 2, 3 moves are $2, $4, $6; the third is cut to $5.
    assert stop_prices(Direction.LONG, 100.0, 2.0, SETTINGS) == pytest.approx(
        [98.0, 96.0, 95.0]
    )


def test_a_stop_price_on_the_wrong_side_is_rejected():
    with pytest.raises(ValueError, match="wrong side"):
        check_stop_price(Direction.LONG, 100.0, 101.0, SETTINGS)
    with pytest.raises(ValueError, match="wrong side"):
        check_stop_price(Direction.SHORT, 100.0, 99.0, SETTINGS)


def test_a_stop_price_more_than_5_percent_away_is_rejected():
    with pytest.raises(ValueError, match="5"):
        check_stop_price(Direction.LONG, 100.0, 94.9, SETTINGS)
    check_stop_price(Direction.LONG, 100.0, 95.0, SETTINGS)


def test_stop_price_settings_come_from_config():
    settings = load_stop_price_settings()
    assert settings.multiples == (1.0, 2.0, 3.0)
    assert settings.distance_cap == 0.05
