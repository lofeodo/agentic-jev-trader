"""The scorecard of the Trading sim page (spec appendix 3 section 5, appendix 7 section 5.7;
`GET /sims/{id}/scorecard`).

The scorecard is the sim's own tally of how its closed trades did, group by group. The text sent
to Jev and the LLM calls it the track record. A group names a candle pattern, a direction and an
asset class: a trade counts in one group for each 15-minute pattern in the pattern window when it
was decided ("none" if there was none), and stock and crypto trades are never counted together.
A line can be split further by trend, volume level and part of the day, each taken at entry.
Worked out when asked for, never stored, with the same filing rules and ladder the agent reads
(`jev_trader.memory.scorecard`).

Each line says whether the agent is shown it: a group under the minimum sample (10 closed trades)
is hidden from it, and so is a split the agent's ladder of groups never forms (it narrows by
trend, then volume level, then part of the day). A hidden line of a split on the ladder also says
what the agent reads instead, the fallback: the narrowest broader group holding the minimum
sample, or, when none does, the count alone.

Choices the spec leaves to the build:

- A trade's entry is the step its opening was decided: the snapshot the agent read.
- A measurement not available at entry files the trade under "not available" for that detail.
- The minimum sample and the volume level's two edges are read from the sim's settings
  (`track_record`) when stored there, else the version 1 defaults (10, 0.9 and 1.1).
"""

from pydantic import BaseModel

from jev_trader.api.sim_page import Sim
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import trades_of
from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.situation_text import (
    VOLUME_HIGH_ABOVE,
    VOLUME_LOW_BELOW,
    part_of_day,
)
from jev_trader.memory.scorecard import (
    LADDER,
    MINIMUM_SAMPLE,
    FiledTrade,
    Moment,
    Split,
    Tally,
    ladder,
    trend,
    volume_level,
)


class Fallback(BaseModel):
    """The broader group the agent reads in place of a line under the minimum sample."""

    # The splits it keeps: [] is pattern, direction and asset class alone.
    split: list[Split]
    trades: int


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
    # A group under the minimum sample is hidden from the agent, and so is one the agent's
    # ladder of groups never forms (a split by volume level alone, say).
    shown_to_agent: bool
    # A hidden line of a split on the ladder: the broader group the agent reads instead. None
    # otherwise, and when no broader group holds the minimum sample (it reads the count alone).
    falls_back_to: Fallback | None


class Scorecard(BaseModel):
    minimum_sample: int
    split: list[Split]
    on_ladder: bool  # whether the agent's ladder of groups forms this split
    closed_trades: int
    lines: list[ScorecardLine]  # largest groups first


def _filed(store: ApiStore, sim: Sim, low_below: float, high_above: float):
    """The sim's closed trades with what each was filed under at entry, and how many closed."""
    closed = [
        t for t in trades_of(store.orders(sim.id), store.charges(sim.id)) if t.closed
    ]
    measured = store.entry_details(
        sim.row["DATASET"], sorted({(t.asset, t.decided_step) for t in closed})
    )
    filed = []
    for t in closed:
        found = measured.get((t.asset, t.decided_step))
        if found is None:
            continue  # the dataset has no snapshot of it: nothing to file it under
        bars_left = found["BARS_LEFT"]
        filed.append(
            FiledTrade(
                patterns=tuple(found["PATTERNS"] or ()),
                direction=t.direction,
                asset_class=found["ASSET_CLASS"],
                trend=trend(t.direction, found["LONG_TERM_TREND"]),
                volume_level=volume_level(
                    found["VOLUME_AGAINST_NORMAL"], low_below, high_above
                ),
                part_of_day=part_of_day(
                    AssetClass(found["ASSET_CLASS"]),
                    found["BAR_NUMBER"],
                    STEPS_PER_DAY
                    if bars_left is None
                    else found["BAR_NUMBER"] + bars_left,
                ),
                profit=t.profit,
                closed_step=t.closed_step,
            )
        )
    return filed, len(closed)


def scorecard(store: ApiStore, sim_id: int, split: list[Split]) -> Scorecard:
    sim = Sim(store, sim_id)
    settings = (sim.row.get("SETTINGS") or {}).get("track_record") or {}
    minimum = settings.get("minimum_sample", MINIMUM_SAMPLE)
    splits = tuple(s for s in Split if s in split)
    filed, closed = _filed(
        store,
        sim,
        settings.get("volume_low_below", VOLUME_LOW_BELOW),
        settings.get("volume_high_above", VOLUME_HIGH_ABOVE),
    )

    # Each line is a group: its pattern, direction and asset class, and the splits asked for.
    groups: dict[Moment, list[float]] = {}
    for t in filed:
        for m in t.moments():
            groups.setdefault(m.group(splits), []).append(t.profit)

    # The agent reads only the ladder's groups: the splits dropped part of day first, then
    # volume level, then trend.
    on_ladder = splits == LADDER[: len(splits)]
    lines = []
    for group, profits in groups.items():
        rung = Tally(profits)
        shown = on_ladder and rung.trades >= minimum
        fallback = None
        if on_ladder and not shown:
            used = ladder(filed, group, minimum).above(splits).used
            if used is not None:
                fallback = Fallback(split=list(used.splits), trades=used.trades)
        lines.append(
            ScorecardLine(
                pattern=group.pattern,
                direction=group.direction,
                asset_class=group.asset_class,
                trend=group.trend,
                volume_level=group.volume_level,
                part_of_day=group.part_of_day,
                trades=rung.trades,
                made_money=rung.made_money,
                share_made_money=rung.share_made_money,
                average_gain=rung.average_gain,
                average_loss=rung.average_loss,
                total_profit=rung.total_profit,
                shown_to_agent=shown,
                falls_back_to=fallback,
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
        minimum_sample=minimum,
        split=list(splits),
        on_ladder=on_ladder,
        closed_trades=closed,
        lines=lines,
    )
