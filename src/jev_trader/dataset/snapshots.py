"""The snapshots of a dataset: candle patterns, measurements, feature vectors and situation texts.

A snapshot is everything code measures about one asset at the step a 15-minute bar ends (spec
appendix 3). A dataset build works them out once, for every asset at every bar, and stores them
(spec appendix 2, sections 8 and 9):

- **Candle patterns** on the 15-minute, hourly and daily bars, stored at the step each bar ends
  (`FEATURES.PATTERNS`).
- **The 58 measurements** of every snapshot, and from the warm-up period's snapshots the average
  and spread of each (`REF.WARMUP_STATS`), frozen with the dataset.
- **The feature vector** (58 standard scores) and **the situation text** of every snapshot
  (`FEATURES.SNAPSHOTS`). The text's embedding is added in the store, by Snowflake's model.

Everything here works on the masked bars, the rescaled and rounded prices `RAW.BARS` stores, so
a snapshot always agrees with the bars a sim reads. Patterns and measurements are ratios of
prices, so the rescaling itself changes nothing; the rounding (4 decimals on prices near 100)
can at most tip a pattern sitting exactly on one of TA-Lib's edges.
"""

import bisect
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from jev_trader.dataset import measurements as m
from jev_trader.dataset import situation_text as text
from jev_trader.dataset.bar_sizes import BarSize, build_bars
from jev_trader.dataset.bars import Bar
from jev_trader.dataset.candle_patterns import playbook, recognise_patterns
from jev_trader.dataset.layout import Clock, where_bar_sits
from jev_trader.dataset.measurements import (
    MEASUREMENT_NAMES,
    AssetClass,
    Measurements,
    Session,
)
from jev_trader.dataset.scaling import WARM_UP_MONTHS, WarmUpScales

EMBEDDING_MODEL = "snowflake-arctic-embed-m-v1.5"
EMBEDDING_SIZE = 768
FEATURE_SIZE = len(MEASUREMENT_NAMES)

# The settings behind the measurements and the text, stored with the dataset.
MEASUREMENT_SETTINGS = {
    "typical_move_bars": m.TYPICAL_MOVE_BARS,
    "short_term_trend_bars": m.TREND_BARS,
    "long_term_trend_days": m.LONG_TREND_DAYS,
    "volume_against_normal_days": m.VOLUME_DAYS,
    "shape_bars": m.SHAPE_BARS,
    "warm_up_months": WARM_UP_MONTHS,
    "pattern_window_steps": text.PATTERN_WINDOW_STEPS,
    "volume_word_cut_offs": [text.VOLUME_LOW_BELOW, text.VOLUME_HIGH_ABOVE],
}


@dataclass(frozen=True)
class AssetBars:
    """One asset's masked 15-minute bars, the start times of its missing bars, and (a stock only;
    None for crypto) its session on each day."""

    masked_id: str
    asset_class: AssetClass
    bars: list[Bar]
    missing: list[pd.Timestamp]
    sessions: dict[date, Session] | None

    @property
    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": [b.open for b in self.bars],
                "high": [b.high for b in self.bars],
                "low": [b.low for b in self.bars],
                "close": [b.close for b in self.bars],
                "volume": [b.volume for b in self.bars],
            },
            index=pd.DatetimeIndex([b.start for b in self.bars]),
        )


@dataclass(frozen=True)
class FoundPatterns:
    """One asset's candle pattern names by bar size and the step the bar ends, and the steps at
    which each of its hourly and daily bars end (to find the latest finished one)."""

    names: dict[tuple[BarSize, int], list[str]]
    ends: dict[BarSize, list[int]]

    def pattern_lists(self, step: int) -> text.PatternLists:
        """What the snapshot at `step` lists: the pattern window (in clock steps, so nothing
        from before an overnight close), and the latest finished hourly and daily bars."""
        window = [
            (name, step - at)
            for at in range(step - text.PATTERN_WINDOW_STEPS + 1, step + 1)
            for name in self.names.get(("15m", at), [])
        ]
        return text.PatternLists(
            window, self._latest("1h", step), self._latest("1d", step)
        )

    def _latest(self, size: BarSize, step: int) -> list[str]:
        ends = self.ends[size]
        i = bisect.bisect_right(ends, step)
        return self.names.get((size, ends[i - 1]), []) if i else []


def find_patterns(asset: AssetBars, clock: Clock) -> FoundPatterns:
    """Every candle pattern on the asset's 15-minute, hourly and daily bars."""
    frame = asset.frame
    missing = pd.DatetimeIndex(asset.missing, tz="UTC")

    def ending_step(size: BarSize, start: pd.Timestamp) -> int:
        ends, _, _ = where_bar_sits(size, start.to_pydatetime(), asset.sessions)
        return clock.step_ending_at(ends)

    names: dict[tuple[BarSize, int], list[str]] = defaultdict(list)
    ends: dict[BarSize, list[int]] = {}
    for size in ("15m", "1h", "1d"):
        steps = {
            start: ending_step(size, start) for start in build_bars(frame, size).index
        }
        ends[size] = sorted(steps.values())
        for found in recognise_patterns(frame, size, missing).itertuples():
            names[size, steps[found.start]].append(found.name)
    return FoundPatterns(dict(names), ends)


def pattern_rows(dataset_id: int, masked_id: str, found: FoundPatterns) -> list[dict]:
    """One `FEATURES.PATTERNS` row per name recognised on a bar of the asset."""
    return [
        {
            "DATASET": dataset_id,
            "ASSET": masked_id,
            "BAR_SIZE": size,
            "STEP": step,
            "PATTERN": name,
        }
        for (size, step), names in sorted(found.names.items())
        for name in names
    ]


def playbook_rows() -> list[dict]:
    """The playbook: one row per candle pattern, for the installed TA-Lib version."""
    return [
        {
            "TALIB_VERSION": e.talib_version,
            "PATTERN": e.detector,
            "LEAN": e.lean,
            "NAME": e.name,
            "SHAPE": e.shape,
        }
        for e in playbook()
    ]


def warm_up_rows(dataset_id: int, scales: WarmUpScales) -> list[dict]:
    """The frozen average and spread of each measurement; both empty when it had no spread."""
    return [
        {
            "DATASET": dataset_id,
            "POSITION": i + 1,
            "MEASUREMENT": name,
            "AVERAGE": scale.average if scale else None,
            "SPREAD": scale.spread if scale else None,
        }
        for i, (name, scale) in enumerate(zip(MEASUREMENT_NAMES, scales.scales))
    ]


def snapshot_rows(
    dataset_id: int,
    asset: AssetBars,
    measured: Sequence[Measurements],
    scales: WarmUpScales,
    found: FoundPatterns,
    clock: Clock,
) -> list[dict]:
    """One row per 15-minute bar: the 58 measurements, the feature vector and the situation
    text. The embedding is added when the rows are stored."""
    rows = []
    for bar, measurements in zip(asset.bars, measured, strict=True):
        step = clock.step_ending_at(bar.end)
        rows.append(
            {
                "DATASET": dataset_id,
                "ASSET": asset.masked_id,
                "STEP": step,
                "MEASUREMENTS": list(measurements.values),
                "FEATURE_VECTOR": list(scales.standard_scores(measurements)),
                "SITUATION_TEXT": text.situation_text(
                    measurements, found.pattern_lists(step)
                ),
            }
        )
    return rows
