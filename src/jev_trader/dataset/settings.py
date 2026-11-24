"""A dataset's settings file, kept in the repo under `datasets/` (spec appendix 2, section 10).

It holds the assets (ticker, real name, stock or crypto), the first and last day, the test
period, the two quality limits, the partial-volume test's two settings, and the number of
decimals kept in prices. Whether the limits are enforced is chosen when the build is started
(`--no-check`), as the web app's tick box does.

The web app's form gives typed tickers only (`settings_from_tickers`): a ticker in `CRYPTO` is
downloaded from Binance, any other is a stock at Twelve Data, and a stock's real name is left
blank for the build to look up. The API writes such settings out as a file (`settings_toml`)
and starts the same build command on it.
"""

import json
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.quality import QualityLimits, UsualVolume

# Masked prices start at 100; four decimals keep a move of a hundredth of a cent on a $100 stock.
PRICE_DECIMALS = 4
# The crypto assets a typed ticker can name: ticker, then real name and Binance's symbol (priced
# in USDT, a token worth $1). Any other ticker is taken for a stock.
CRYPTO = {"BTC": ("Bitcoin", "BTCUSDT"), "ETH": ("Ether", "ETHUSDT")}


@dataclass(frozen=True)
class AssetSettings:
    """One asset as typed. `provider_symbol` is the data provider's name for it when it
    differs from the ticker: Binance calls Bitcoin priced in USDT `BTCUSDT`."""

    ticker: str
    name: str
    asset_class: AssetClass
    provider_symbol: str = ""

    @property
    def downloaded_as(self) -> str:
        """The name the asset is downloaded under."""
        return self.provider_symbol or self.ticker


@dataclass(frozen=True)
class Period:
    """A named stretch of days, such as the test period's "falling market"."""

    name: str
    first_day: date
    last_day: date


@dataclass(frozen=True)
class DatasetSettings:
    name: str
    first_day: date
    last_day: date
    assets: list[AssetSettings]
    test_periods: list[Period] = field(default_factory=list)
    limits: QualityLimits = field(default_factory=QualityLimits)
    usual_volume: UsualVolume = field(default_factory=UsualVolume)
    price_decimals: int = PRICE_DECIMALS


def load_settings(path: Path) -> DatasetSettings:
    """Read a dataset's settings file (TOML)."""
    return load_settings_text(Path(path).read_text(encoding="utf-8"))


def load_settings_text(text: str) -> DatasetSettings:
    """Read a dataset's settings from the text of its file."""
    raw = tomllib.loads(text)
    limits = raw.get("limits", {})
    partial = raw.get("partial_volume", {})
    return DatasetSettings(
        name=raw["name"],
        first_day=raw["first_day"],
        last_day=raw["last_day"],
        assets=[
            AssetSettings(
                ticker=a["ticker"],
                name=a.get("name", ""),
                asset_class=AssetClass(a["class"]),
                provider_symbol=a.get("provider_symbol", ""),
            )
            for a in raw["assets"]
        ],
        test_periods=[
            Period(p["name"], p["first_day"], p["last_day"])
            for p in raw.get("test_period", [])
        ],
        limits=QualityLimits(
            other_missing=limits.get("other_missing", QualityLimits.other_missing),
            partial_volume_days=limits.get(
                "partial_volume_days", QualityLimits.partial_volume_days
            ),
        ),
        usual_volume=UsualVolume(
            share=partial.get("share_of_usual", UsualVolume.share),
            sessions=partial.get("sessions", UsualVolume.sessions),
        ),
        price_decimals=raw.get("price_decimals", PRICE_DECIMALS),
    )


def asset_for(ticker: str) -> AssetSettings:
    """A typed ticker as an asset: crypto if `CRYPTO` knows it, else a stock to be named."""
    ticker = ticker.strip().upper()
    if ticker in CRYPTO:
        name, symbol = CRYPTO[ticker]
        return AssetSettings(ticker, name, AssetClass.CRYPTO, symbol)
    return AssetSettings(ticker, "", AssetClass.STOCK)


def settings_from_tickers(
    tickers: list[str],
    first_day: date,
    last_day: date,
    test_periods: list[Period] | None = None,
    limits: QualityLimits | None = None,
) -> DatasetSettings:
    """The settings the web app's form asks for. The name says the tickers and the days, so a
    build of the same settings is a new version of the same dataset."""
    assets = [asset_for(t) for t in tickers if t.strip()]
    return DatasetSettings(
        name=f"{' '.join(a.ticker for a in assets)} {first_day} to {last_day}",
        first_day=first_day,
        last_day=last_day,
        assets=assets,
        test_periods=list(test_periods or []),
        limits=limits or QualityLimits(),
    )


def _text(value: str) -> str:
    """A TOML string: JSON's quoting is TOML's for plain text."""
    return json.dumps(value, ensure_ascii=False)


def settings_toml(settings: DatasetSettings) -> str:
    """The settings as a file `load_settings` reads back the same."""
    lines = [
        f"name = {_text(settings.name)}",
        f"first_day = {settings.first_day}",
        f"last_day = {settings.last_day}",
        f"price_decimals = {settings.price_decimals}",
        "",
        "[limits]",
        f"other_missing = {settings.limits.other_missing!r}",
        f"partial_volume_days = {settings.limits.partial_volume_days!r}",
        "",
        "[partial_volume]",
        f"share_of_usual = {settings.usual_volume.share!r}",
        f"sessions = {settings.usual_volume.sessions}",
    ]
    for period in settings.test_periods:
        lines += [
            "",
            "[[test_period]]",
            f"name = {_text(period.name)}",
            f"first_day = {period.first_day}",
            f"last_day = {period.last_day}",
        ]
    for asset in settings.assets:
        lines += [
            "",
            "[[assets]]",
            f"ticker = {_text(asset.ticker)}",
            f"name = {_text(asset.name)}",
            f"class = {_text(str(asset.asset_class))}",
        ]
        if asset.provider_symbol:
            lines.append(f"provider_symbol = {_text(asset.provider_symbol)}")
    return "\n".join(lines) + "\n"
