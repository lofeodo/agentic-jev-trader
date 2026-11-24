"""The scorecard of the Trading sim page (spec appendix 3 section 5, appendix 7 section 5.7;
`GET /sims/{id}/scorecard`).

The scorecard is the sim's own tally of how its closed trades did, group by group. The text sent
to Jev and the LLM calls it the track record. A group names a candle pattern, a direction and an
asset class: a trade counts in one group for each 15-minute pattern in the pattern window when it
was decided ("none" if there was none), and stock and crypto trades are never counted together.
A line can be split further by trend, volume level and part of the day, each taken at entry.
Each line says whether the agent is shown it: a group under the minimum sample (10 closed trades)
is hidden from it. Worked out when asked for, never stored.

Which group fits the agent's situation, and the fallback to broader groups, belong to the track
record itself (ticket #101), not to this page.

Choices the spec leaves to the build:

- A trade's entry is the step its opening was decided: the snapshot the agent read.
- A measurement not available at entry files the trade under "not available" for that detail.
- The minimum sample and the volume level's two edges are read from the sim's settings
  (`track_record`) when stored there, else the version 1 defaults (10, 0.9 and 1.1).
"""

from enum import StrEnum

from pydantic import BaseModel

from jev_trader.api.sim_page import Sim
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import Trade, trades_of
from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.situation_text import (
    VOLUME_HIGH_ABOVE,
    VOLUME_LOW_BELOW,
    part_of_day,
)

MINIMUM_SAMPLE = 10
NO_PATTERN = "none"
NOT_AVAILABLE = "not available"


class Split(StrEnum):
    TREND = "trend"
    VOLUME = "volume"
    PART_OF_DAY = "part_of_day"


class ScorecardLine(BaseModel):
    pattern: str  # a candle pattern's name, or "none"
    direction: str  # "long" bets on a rise, "short" on a fall
    asset_class: str  # "stock" or "crypto"
    trend: str | None  # with or against the trend; None unless split by it
    volume_level: str | None  # low, average or high; None unless split by it
    part_of_day: str | None  # None unless split by it
    trades: int  # closed trades in the group
    made_money: int
    share_made_money: float
    average_gain: float | None  # over the trades that made money
    average_loss: float | None  # over the trades that lost money (a negative number)
    total_profit: float
    shown_to_agent: bool  # a group under the minimum sample is hidden from the agent


class Scorecard(BaseModel):
    minimum_sample: int
    split: list[Split]
    closed_trades: int
    lines: list[ScorecardLine]  # largest groups first


def _trend(trade: Trade, reading: float | None) -> str:
    """A long while the price is above its 20-day average is with the trend; so is a short
    while it is below. There is no "flat"."""
    if reading is None:
        return NOT_AVAILABLE
    above = reading >= 0
    return (
        "with the trend"
        if above == (trade.direction == "long")
        else "against the trend"
    )


def _volume_level(reading: float | None, low_below: float, high_above: float) -> str:
    if reading is None:
        return NOT_AVAILABLE
    if reading < low_below:
        return "low"
    return "high" if reading > high_above else "average"


def _part_of_day(found: dict) -> str:
    asset_class = AssetClass(found["ASSET_CLASS"])
    bars_left = found["BARS_LEFT"]
    bars_in_day = (
        STEPS_PER_DAY if bars_left is None else found["BAR_NUMBER"] + bars_left
    )
    return part_of_day(asset_class, found["BAR_NUMBER"], bars_in_day)


def scorecard(store: ApiStore, sim_id: int, split: list[Split]) -> Scorecard:
    sim = Sim(store, sim_id)
    settings = (sim.row.get("SETTINGS") or {}).get("track_record") or {}
    minimum = settings.get("minimum_sample", MINIMUM_SAMPLE)
    low_below = settings.get("volume_low_below", VOLUME_LOW_BELOW)
    high_above = settings.get("volume_high_above", VOLUME_HIGH_ABOVE)
    split = [s for s in Split if s in split]

    closed = [
        t for t in trades_of(store.orders(sim_id), store.charges(sim_id)) if t.closed
    ]
    measured = store.entry_details(
        sim.row["DATASET"], sorted({(t.asset, t.decided_step) for t in closed})
    )
    groups: dict[tuple, list[float]] = {}
    for trade in closed:
        found = measured.get((trade.asset, trade.decided_step))
        if found is None:
            continue  # the dataset has no snapshot of it: nothing to file it under
        details = (
            _trend(trade, found["LONG_TERM_TREND"]) if Split.TREND in split else None,
            _volume_level(found["VOLUME_AGAINST_NORMAL"], low_below, high_above)
            if Split.VOLUME in split
            else None,
            _part_of_day(found) if Split.PART_OF_DAY in split else None,
        )
        for pattern in found["PATTERNS"] or [NO_PATTERN]:
            key = (pattern, trade.direction, found["ASSET_CLASS"], *details)
            groups.setdefault(key, []).append(trade.profit)

    lines = []
    for (
        pattern,
        direction,
        asset_class,
        trend,
        volume,
        part,
    ), profits in groups.items():
        gains = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        lines.append(
            ScorecardLine(
                pattern=pattern,
                direction=direction,
                asset_class=asset_class,
                trend=trend,
                volume_level=volume,
                part_of_day=part,
                trades=len(profits),
                made_money=len(gains),
                share_made_money=len(gains) / len(profits),
                average_gain=sum(gains) / len(gains) if gains else None,
                average_loss=sum(losses) / len(losses) if losses else None,
                total_profit=sum(profits),
                shown_to_agent=len(profits) >= minimum,
            )
        )
    lines.sort(
        key=lambda x: (
            -x.trades,
            x.pattern,
            x.direction,
            x.asset_class,
            x.trend or "",
            x.volume_level or "",
            x.part_of_day or "",
        )
    )
    return Scorecard(
        minimum_sample=minimum, split=split, closed_trades=len(closed), lines=lines
    )
