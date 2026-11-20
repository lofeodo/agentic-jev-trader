"""A dataset's settings file, kept in the repo under `datasets/` (spec appendix 2, section 10).

It holds the assets (ticker, real name, stock or crypto), the first and last day, the test
period, the two quality limits, the partial-volume test's two settings, and the number of
decimals kept in prices. Whether the limits are enforced is chosen when the build is started
(`--no-check`), as the web app's tick box does.
"""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.quality import QualityLimits, UsualVolume

# Masked prices start at 100; four decimals keep a move of a hundredth of a cent on a $100 stock.
PRICE_DECIMALS = 4


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
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    limits = raw.get("limits", {})
    partial = raw.get("partial_volume", {})
    return DatasetSettings(
        name=raw["name"],
        first_day=raw["first_day"],
        last_day=raw["last_day"],
        assets=[
            AssetSettings(
                ticker=a["ticker"],
                name=a["name"],
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
