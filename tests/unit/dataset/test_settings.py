"""A dataset's settings from typed tickers, and its settings file (spec appendix 2, section 10)."""

from datetime import date

from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.quality import QualityLimits
from jev_trader.dataset.settings import (
    AssetSettings,
    Period,
    load_settings,
    settings_from_tickers,
    settings_toml,
)


def test_typed_tickers_become_stocks_except_known_crypto():
    settings = settings_from_tickers(
        [" aapl", "BTC ", "xom"],
        first_day=date(2023, 4, 3),
        last_day=date(2026, 10, 31),
    )
    assert settings.assets == [
        AssetSettings(ticker="AAPL", name="", asset_class=AssetClass.STOCK),
        AssetSettings(
            ticker="BTC",
            name="Bitcoin",
            asset_class=AssetClass.CRYPTO,
            provider_symbol="BTCUSDT",
        ),
        AssetSettings(ticker="XOM", name="", asset_class=AssetClass.STOCK),
    ]


def test_the_name_says_the_tickers_and_days_so_the_same_settings_count_up_versions():
    one = settings_from_tickers(["AAPL", "BTC"], date(2023, 4, 3), date(2026, 10, 31))
    assert one.name == "AAPL BTC 2023-04-03 to 2026-10-31"


def test_the_settings_file_reads_back_the_same(tmp_path):
    settings = settings_from_tickers(
        ["SPY", "BTC"],
        first_day=date(2023, 4, 3),
        last_day=date(2026, 10, 31),
        test_periods=[Period("falling market", date(2025, 3, 10), date(2025, 4, 8))],
        limits=QualityLimits(other_missing=0.01, partial_volume_days=0.05),
    )
    path = tmp_path / "dataset.toml"
    path.write_text(settings_toml(settings), encoding="utf-8")
    assert load_settings(path) == settings


def test_the_first_datasets_file_still_reads():
    settings = load_settings("datasets/first.toml")
    assert [a.ticker for a in settings.assets] == ["SPY", "AAPL", "JPM", "XOM", "BTC"]
    assert settings.assets[1].name == "Apple Inc."
