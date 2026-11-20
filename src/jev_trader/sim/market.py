"""What a sim reads about its dataset: the dataset's row, its assets, and its 15-minute bars.

`InMemoryMarket` is the stand-in the unit tests use; `snowflake_store.SnowflakeMarket` reads
`REF.DATASETS`, `REF.DATASET_PERIODS`, `REF.ASSETS` and `RAW.BARS`. Nothing here reads the
asset key: a sim knows assets by masked ID and time by step number only.
"""

from dataclasses import dataclass
from typing import Protocol

from jev_trader.broker import AssetClass, Bar


@dataclass(frozen=True)
class Period:
    """A stretch of a dataset's steps. `kind` is "warm-up" or "test"."""

    kind: str
    name: str
    first_step: int
    last_step: int


@dataclass(frozen=True)
class DatasetInfo:
    dataset_id: int
    status: str  # "being built", "published" or "failed"
    first_step: int
    last_step: int
    periods: tuple[Period, ...]
    assets: dict[str, AssetClass]  # masked ID to asset class

    @property
    def warm_up_last_step(self) -> int:
        return max(
            (p.last_step for p in self.periods if p.kind == "warm-up"), default=0
        )

    def test_periods(self) -> list[Period]:
        return [p for p in self.periods if p.kind == "test"]


# Bars by step, then by asset: only the assets with a bar at that step.
BarsByStep = dict[int, dict[str, Bar]]


class Market(Protocol):
    def dataset(self, dataset_id: int) -> DatasetInfo:
        """The dataset's row; KeyError if there is none."""

    def bars(self, dataset_id: int, first_step: int, last_step: int) -> BarsByStep:
        """The 15-minute bars that end from `first_step` to `last_step`, both included."""


def instrument(asset: str) -> str:
    """The one spot instrument of an asset in version 1, as `REF.INSTRUMENTS` names it."""
    return f"{asset}_SPOT"


class InMemoryMarket:
    """Datasets and their bars as plain lists: `bars` maps a dataset to each asset's bars."""

    def __init__(
        self, datasets: list[DatasetInfo], bars: dict[int, dict[str, list[Bar]]]
    ):
        self.datasets = list(datasets)
        self.bars_by_asset = bars

    def dataset(self, dataset_id: int) -> DatasetInfo:
        for info in self.datasets:
            if info.dataset_id == dataset_id:
                return info
        raise KeyError(f"no dataset {dataset_id}")

    def bars(self, dataset_id: int, first_step: int, last_step: int) -> BarsByStep:
        by_step: BarsByStep = {}
        for asset, bars in sorted(self.bars_by_asset[dataset_id].items()):
            for bar in bars:
                if first_step <= bar.step <= last_step:
                    by_step.setdefault(bar.step, {})[asset] = bar
        return by_step
