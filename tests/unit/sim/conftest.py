"""A made-up three-day dataset for the sim tests: one stock and one crypto asset.

Day 1 (steps 1 to 96) is the warm-up; sims run on days 2 and 3 (steps 97 to 288). ASSET_01 is a
stock with a session of 26 bars a day (steps 151 to 176 on day 2, 247 to 272 on day 3). ASSET_02
is crypto, with a bar at every step. Prices sit at 100 until each asset's last bar, which closes
higher: the stock at 120, the crypto at 110.
"""

import pytest

from jev_trader.broker import AssetClass, Bar
from jev_trader.sim.market import DatasetInfo, InMemoryMarket, Period

DATASET = 7
STOCK, CRYPTO = "ASSET_01", "ASSET_02"
FIRST_STEP, LAST_STEP = 97, 288


def flat_bars(steps, last_close):
    bars = [Bar(step=s, open=100.0, high=100.0, low=100.0, close=100.0) for s in steps]
    last = bars[-1]
    bars[-1] = Bar(last.step, 100.0, last_close, 100.0, last_close)
    return bars


def stock_steps():
    return [s for day in range(3) for s in range(day * 96 + 55, day * 96 + 81)]


def make_market(assets=(STOCK, CRYPTO), status="published"):
    classes = {STOCK: AssetClass.STOCK, CRYPTO: AssetClass.CRYPTO}
    bars = {
        STOCK: flat_bars(stock_steps(), 120.0),
        CRYPTO: flat_bars(range(1, LAST_STEP + 1), 110.0),
    }
    return InMemoryMarket(
        datasets=[
            DatasetInfo(
                dataset_id=DATASET,
                status=status,
                first_step=1,
                last_step=LAST_STEP,
                periods=(
                    Period("warm-up", "warm-up", 1, 96),
                    Period("test", "rising market", 193, 288),
                ),
                assets={a: classes[a] for a in assets},
            )
        ],
        bars={DATASET: {a: bars[a] for a in assets}},
    )


@pytest.fixture
def market():
    return make_market()


@pytest.fixture(name="make_market")
def make_market_fixture():
    return make_market
