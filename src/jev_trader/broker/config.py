"""The broker's settings, read from the files in `config/` (spec appendix 1, sections 3 and 4).

Every number here is a setting: a tuning sim may change it with no code change, and each sim
stores the numbers it ran with (`dataclasses.asdict` gives them as a plain dictionary).
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@dataclass(frozen=True)
class TradingCosts:
    """What buying, selling and holding cost a sim, in simulated money.

    Rates are shares: 0.0005 is 0.05%, 0.05 a year is 5% a year.
    """

    slippage: float
    stock_commission: float
    crypto_trading_fee: float
    stock_borrow_fee_yearly: float
    crypto_borrow_fee_yearly: float
    loan_interest_yearly: float


@dataclass(frozen=True)
class StopPriceSettings:
    """How far from the price a candidate trade's stop prices sit."""

    multiples: tuple[float, ...]
    distance_cap: float


def load_trading_costs(path: Path = CONFIG_DIR / "trading_costs.toml") -> TradingCosts:
    with open(path, "rb") as file:
        return TradingCosts(**tomllib.load(file))


def load_stop_price_settings(
    path: Path = CONFIG_DIR / "stop_prices.toml",
) -> StopPriceSettings:
    with open(path, "rb") as file:
        values = tomllib.load(file)
    return StopPriceSettings(
        multiples=tuple(values["multiples"]), distance_cap=values["distance_cap"]
    )
