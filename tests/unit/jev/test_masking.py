"""The masking scan: what must never reach a model (spec appendix 1, section 2)."""

import pytest

from jev_trader.jev.masking import MaskingLeak, assert_masked, find_leaks, real_values

# A made-up real price of $187.44 that the dataset shows, rescaled, as $104.20.
REAL = real_values(prices=[187.44])
CLEAN = (
    "# The asset: ASSET_03 (stock)\nLast price: $104.20. Typical move in one bar: $0.63.\n"
    "Stock, first hour (bar 3 of 26). Volume high (1.8 times normal). "
    "Account value: $10,000. It may hold up to $20,000 in 15-minute steps. "
    "Every order is carried out at a price 0.05% worse. A spy may hold."
)


def test_clean_text_has_no_leaks():
    assert find_leaks(CLEAN, REAL) == []


@pytest.mark.parametrize(
    "leak",
    [
        "AAPL",
        "SPY",
        "BTCUSDT",
        "Apple Inc.",
        "apple",
        "JPMorgan",
        "Chase",
        "Mobil",
        "S&P 500",
        "Exxon Mobil Corporation",
        "bitcoin",
    ],
)
def test_a_real_ticker_or_name_is_a_leak(leak):
    assert find_leaks(f"{CLEAN} {leak} rose.", REAL)


@pytest.mark.parametrize(
    "leak",
    ["2025-03-10", "03/10/2025", "March 10", "10 March", "Mar 10, 2025", "in 2024"],
)
def test_a_calendar_date_is_a_leak(leak):
    assert find_leaks(f"{CLEAN} On {leak} it rose.", REAL)


@pytest.mark.parametrize(
    "leak", ["$187.44", "187.44", "$187.4", "187.4", "$187", "187"]
)
def test_an_unscaled_price_is_a_leak(leak):
    assert find_leaks(f"{CLEAN} It traded at {leak} today.", REAL)


@pytest.mark.parametrize("leak", ["15:45", "9:30"])
def test_a_clock_time_is_a_leak(leak):
    assert find_leaks(f"{CLEAN} At {leak} it rose.", REAL)


@pytest.mark.parametrize(
    "leak", ["3f2b8c1e-9d4a-4e6f-8a7b-1c2d3e4f5a6b", "a5d9cc4ac9ea4e19"]
)
def test_a_random_id_is_a_leak(leak):
    assert find_leaks(f"{CLEAN} Request {leak}.", REAL)


def test_a_masked_price_that_looks_like_a_year_is_not_a_leak():
    assert find_leaks("Last price: $2012.33.", REAL) == []


def test_assert_masked_names_what_leaked():
    with pytest.raises(MaskingLeak, match="AAPL"):
        assert_masked("AAPL rose.", REAL)
