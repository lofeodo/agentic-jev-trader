"""A whole dataset build, with made-up providers and an in-memory stand-in for Snowflake.

The range is 3 to 7 July 2023: 3 July closes early (13:00 New York time, 17:00 UTC) and
4 July is a holiday, so the stock has four sessions: 14 + 26 + 26 + 26 = 92 bars.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from jev_trader.dataset.bars import BAR_LENGTH, Bar
from jev_trader.dataset.build import BuildStopped, build_dataset
from jev_trader.dataset.exchange_calendar import stock_sessions
from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.providers import UnknownTicker
from jev_trader.dataset.quality import Limits
from jev_trader.dataset.settings import AssetSettings, DatasetSettings, Period
from jev_trader.dataset.store import InMemoryStore

FIRST, LAST = date(2023, 7, 3), date(2023, 7, 7)
BUILD_DAY = date(2023, 7, 10)


def settings(**changes) -> DatasetSettings:
    base = {
        "name": "tiny",
        "first_day": FIRST,
        "last_day": LAST,
        "assets": [
            AssetSettings(
                ticker="XYZ", name="Made-up Corp", asset_class=AssetClass.STOCK
            ),
            AssetSettings(
                ticker="COIN",
                name="Made-up Coin",
                asset_class=AssetClass.CRYPTO,
                provider_symbol="COINUSDT",
            ),
        ],
        "test_periods": [Period("falling market", date(2023, 7, 6), LAST)],
    }
    return DatasetSettings(**(base | changes))


class FakeStocks:
    """Bars on every session from the calendar, up to the usual 16:00 New York close.

    Bars after an early close carry zero volume, as Twelve Data's do. `zero_volume_on` days get
    one zero-volume bar inside the session.
    """

    def __init__(self, zero_volume_on=(), history_from=date(2023, 1, 1)):
        self.zero_volume_on = set(zero_volume_on)
        self.history_from = history_from
        self.asked = []

    def stock_bars(self, ticker, first_day, last_day):
        self.asked.append((ticker, first_day, last_day))
        bars = []
        for day, sess in stock_sessions(max(first_day, self.history_from), last_day):
            usual_close = sess.open + 26 * BAR_LENGTH
            for i in range(26):
                start = sess.open + i * BAR_LENGTH
                price = 50.0 + i
                volume = 1000.0
                if start >= sess.close or (day in self.zero_volume_on and i == 3):
                    volume = 0.0
                bars.append(
                    Bar(start, price, price + 1, price - 1, price + 0.5, volume)
                )
            assert bars[-1].start < usual_close
        return bars


class FakeCrypto:
    def crypto_bars(self, symbol, first_day, last_day):
        start = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
        n = ((last_day - first_day).days + 1) * 96
        return [
            Bar(start + i * BAR_LENGTH, 20.0, 21.0, 19.0, 20.5, 4.0) for i in range(n)
        ]


def build(store=None, stocks=None, **kwargs):
    store = store or InMemoryStore()
    result = build_dataset(
        kwargs.pop("settings", settings()),
        stocks=stocks or FakeStocks(),
        crypto=FakeCrypto(),
        store=store,
        today=BUILD_DAY,
        report=lambda line: None,
        **kwargs,
    )
    return result, store


def rows(store, table, dataset_id, **match):
    return [
        r
        for r in store.tables[table]
        if r["DATASET"] == dataset_id and all(r[k] == v for k, v in match.items())
    ]


def test_a_clean_build_publishes_masked_15_minute_bars_on_the_step_clock():
    result, store = build()

    dataset = store.datasets[result.dataset_id]
    assert dataset["STATUS"] == "published"
    assert dataset["PUBLISHED_WITHOUT_CHECK"] is False
    assert dataset["FIRST_STEP"] == 1 and dataset["LAST_STEP"] == 5 * 96

    stock = rows(store, "RAW.BARS", result.dataset_id, ASSET="ASSET_01", BAR_SIZE="15m")
    assert len(stock) == 92  # early-close bars dropped, lead-in sessions not stored
    first = stock[0]
    # 3 July 13:30 UTC is the 55th quarter hour of day 1: that bar ends at step 55.
    assert first["STEP"] == 55 and first["DAY"] == 1
    assert (first["BAR_NUMBER"], first["BARS_LEFT"]) == (1, 13)
    assert first["OPEN"] == 100.0  # every series starts at 100
    assert first["CLOSE"] == 101.0  # $50.50 against a $50.00 first open
    last_of_half_day = [r for r in stock if r["DAY"] == 1][-1]
    assert (last_of_half_day["BAR_NUMBER"], last_of_half_day["BARS_LEFT"]) == (14, 0)
    assert not [r for r in stock if r["DAY"] == 2]  # the holiday

    coin = rows(store, "RAW.BARS", result.dataset_id, ASSET="ASSET_02", BAR_SIZE="15m")
    assert len(coin) == 5 * 96
    assert coin[0]["VOLUME"] == 100.0  # its average bar over its first 5 days is 100
    assert coin[0]["BARS_LEFT"] is None  # crypto has no session


def test_hourly_and_daily_bars_are_built_from_the_15_minute_bars():
    result, store = build()

    hourly = rows(
        store, "RAW.BARS", result.dataset_id, ASSET="ASSET_01", BAR_SIZE="1h", DAY=1
    )
    # 13:30-17:00 UTC: a short first hour (13:30-14:00), then 14, 15 and 16 o'clock.
    assert [r["STEP"] for r in hourly] == [56, 60, 64, 68]
    assert [r["BARS_LEFT"] for r in hourly] == [3, 2, 1, 0]
    assert (
        hourly[0]["OPEN"] == 100.0 and hourly[0]["HIGH"] == 104.0
    )  # $52.00 against $50.00

    daily = rows(store, "RAW.BARS", result.dataset_id, ASSET="ASSET_01", BAR_SIZE="1d")
    assert [(r["DAY"], r["STEP"]) for r in daily] == [
        (1, 68),
        (3, 2 * 96 + 80),
        (4, 3 * 96 + 80),
        (5, 4 * 96 + 80),
    ]
    coin_daily = rows(
        store, "RAW.BARS", result.dataset_id, ASSET="ASSET_02", BAR_SIZE="1d"
    )
    assert [r["STEP"] for r in coin_daily] == [96, 192, 288, 384, 480]


def test_real_names_dates_and_prices_live_only_in_the_asset_key():
    result, store = build()

    [key] = rows(store, "KEYS.ASSET_KEY", result.dataset_id, MASKED_ID="ASSET_01")
    assert key["TICKER"] == "XYZ" and key["NAME"] == "Made-up Corp"
    assert key["FIRST_DAY"] == FIRST
    assert key["PRICE_SCALE"] == pytest.approx(2.0)  # $50.00 becomes 100

    outside_key = repr(
        {t: r for t, r in store.tables.items() if not t.startswith("KEYS.")}
    ) + repr(store.datasets)
    for secret in ("XYZ", "Made-up", "COIN", "2023"):
        assert secret not in outside_key


def test_the_dataset_stores_its_periods_settings_and_the_check_numbers():
    result, store = build()

    periods = rows(store, "REF.DATASET_PERIODS", result.dataset_id)
    assert [
        (p["KIND"], p["NAME"], p["FIRST_STEP"], p["LAST_STEP"]) for p in periods
    ] == [
        ("warm-up", "warm-up", 1, 5 * 96),  # three months: longer than this tiny range
        ("test", "falling market", 3 * 96 + 1, 5 * 96),
    ]
    dataset = store.datasets[result.dataset_id]
    assert dataset["LIMIT_OTHER_MISSING"] == 0.005
    assert dataset["LIMIT_PARTIAL_VOLUME_DAYS"] == 0.03
    assert dataset["PARTIAL_VOLUME_SHARE_OF_USUAL"] == 0.25
    assert dataset["PARTIAL_VOLUME_SESSIONS"] == 20
    assert dataset["CHECK_RESULT"]["passed"] is True
    assert [a["asset"] for a in dataset["CHECK_RESULT"]["assets"]] == [
        "ASSET_01",
        "ASSET_02",
    ]
    assert [
        (r["MASKED_ID"], r["ASSET_CLASS"])
        for r in rows(store, "REF.ASSETS", result.dataset_id)
    ] == [
        ("ASSET_01", "stock"),
        ("ASSET_02", "crypto"),
    ]
    assert dataset["BUILD_STAGE"] == "Publish" and dataset["BUILD_PROGRESS"] == 1.0


def test_the_quality_report_lists_partial_volume_days_and_their_missing_bars():
    # One zero-volume bar on 5 July: with the check off the build still publishes.
    result, store = build(
        stocks=FakeStocks(zero_volume_on={date(2023, 7, 5)}), check=False
    )

    [day] = rows(store, "REF.PARTIAL_VOLUME_DAYS", result.dataset_id)
    assert (day["ASSET"], day["DAY"], day["TEST"]) == (
        "ASSET_01",
        3,
        "a zero-volume bar",
    )
    missing = rows(store, "REF.MISSING_BARS", result.dataset_id, ASSET="ASSET_01")
    assert len(missing) == 26
    assert {m["REASON"] for m in missing} == {"partial-volume day"}
    assert not rows(
        store, "RAW.BARS", result.dataset_id, ASSET="ASSET_01", BAR_SIZE="15m", DAY=3
    )


def test_a_dataset_over_a_limit_fails_before_the_slow_part_and_says_why():
    # 1 partial-volume day in 4 sessions is 25%, over the 3% limit.
    result, store = build(stocks=FakeStocks(zero_volume_on={date(2023, 7, 5)}))

    dataset = store.datasets[result.dataset_id]
    assert dataset["STATUS"] == "failed"
    assert (
        "XYZ: 25.0% of its sessions are partial-volume days (limit 3.0%)"
        in result.message
    )
    assert "--no-check" in result.message
    assert dataset["CHECK_RESULT"]["passed"] is False  # the app still gets the numbers
    assert not any(store.tables.values())  # nothing written past the check


def test_with_the_check_off_a_dataset_over_a_limit_is_published_and_marked():
    result, store = build(
        stocks=FakeStocks(zero_volume_on={date(2023, 7, 5)}),
        settings=settings(limits=Limits(partial_volume_days=0.03)),
        check=False,
    )
    dataset = store.datasets[result.dataset_id]
    assert dataset["STATUS"] == "published"
    assert dataset["PUBLISHED_WITHOUT_CHECK"] is True
    assert dataset["CHECK_RESULT"]["passed"] is False


def test_lead_in_sessions_are_downloaded_to_judge_usual_volume():
    stocks = FakeStocks()
    build(stocks=stocks)
    # The 20 sessions before 3 July 2023 start on 2 June.
    assert stocks.asked == [("XYZ", date(2023, 6, 2), LAST)]


def test_a_stock_whose_history_does_not_reach_20_sessions_back_stops_the_build():
    store = InMemoryStore()
    with pytest.raises(BuildStopped, match="XYZ.*later first day"):
        build(store=store, stocks=FakeStocks(history_from=date(2023, 6, 20)))
    [dataset] = store.datasets.values()
    assert dataset["STATUS"] == "failed"
    assert "later first day" in dataset["FAILURE_REASON"]
    assert_no_real_name_or_date(dataset["FAILURE_REASON"])


def assert_no_real_name_or_date(stored: str):
    for secret in ("XYZ", "Made-up", "COIN", "2023"):
        assert secret not in stored


class BrokenStocks:
    def __init__(self, error):
        self.error = error

    def stock_bars(self, ticker, first_day, last_day):
        raise self.error


def test_a_ticker_the_provider_does_not_know_stops_the_build_and_is_named():
    store = InMemoryStore()
    unknown = UnknownTicker("Twelve Data does not know this ticker: XYZ not found")
    with pytest.raises(BuildStopped, match="XYZ"):
        build(store=store, stocks=BrokenStocks(unknown))
    [dataset] = store.datasets.values()
    assert (
        dataset["FAILURE_REASON"] == "ASSET_01: the provider does not know this ticker"
    )


def test_an_unexpected_error_stores_no_real_name_or_date():
    store = InMemoryStore()
    crash = RuntimeError("GET https://example.test/XYZ-15m-2023-04.zip failed")
    with pytest.raises(RuntimeError):
        build(store=store, stocks=BrokenStocks(crash))
    [dataset] = store.datasets.values()
    assert dataset["STATUS"] == "failed"
    assert_no_real_name_or_date(dataset["FAILURE_REASON"])


def test_a_dataset_must_end_at_least_a_day_before_the_build_day():
    with pytest.raises(BuildStopped, match="last day"):
        build(settings=settings(last_day=BUILD_DAY))


def test_each_build_of_the_same_settings_gets_the_next_version():
    store = InMemoryStore()
    first, _ = build(store=store)
    second, _ = build(store=store)
    assert (first.version, second.version) == (1, 2)
    assert first.dataset_id != second.dataset_id


def test_settings_are_read_from_a_file(tmp_path):
    from jev_trader.dataset.settings import load_settings

    path = tmp_path / "tiny.toml"
    path.write_text(
        """
name = "tiny"
first_day = 2023-07-03
last_day = 2023-07-07

[limits]
other_missing = 0.01

[[test_period]]
name = "falling market"
first_day = 2023-07-06
last_day = 2023-07-07

[[assets]]
ticker = "XYZ"
name = "Made-up Corp"
class = "stock"

[[assets]]
ticker = "COIN"
name = "Made-up Coin"
class = "crypto"
provider_symbol = "COINUSDT"
"""
    )
    loaded = load_settings(path)
    assert loaded.limits == Limits(other_missing=0.01, partial_volume_days=0.03)
    assert loaded.assets[1].downloaded_as == "COINUSDT"
    assert loaded.test_periods[0].first_day == date(2023, 7, 6)
    assert loaded.usual_volume_share == 0.25 and loaded.usual_volume_sessions == 20
    assert loaded.first_day + timedelta(days=4) == loaded.last_day


def test_the_first_datasets_settings_match_the_spec():
    from pathlib import Path

    from jev_trader.dataset.settings import load_settings

    first = load_settings(Path(__file__).parents[3] / "datasets" / "first.toml")
    assert [a.ticker for a in first.assets] == ["SPY", "AAPL", "JPM", "XOM", "BTC"]
    assert len(stock_sessions(first.first_day, first.last_day)) == 899
    assert [p.name for p in first.test_periods] == ["falling market", "rising market"]
