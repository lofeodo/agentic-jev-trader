"""The track record as memory's `read_track_record` tool hands it out (spec appendix 5, section
4; appendix 3, section 5).

The track record is the agent's own totals over its closed trades for one candle pattern and
direction, in the current asset's class: one group per rung of the ladder (`scorecard.ladder`),
broadest first, down to the narrowest holding the minimum sample (10 closed trades), which is
the group that fits the current situation. Groups under the minimum are not shown; when none
holds it, only the count is.
"""

from pydantic import BaseModel

from jev_trader.memory.scorecard import FiledTrade, Moment, ladder


class Group(BaseModel):
    # With the trend or against the trend; None: not split by it. So for the other two.
    trend: str | None = None
    volume_level: str | None = None
    part_of_day: str | None = None
    trades: int
    made_money: int
    average_gain: float | None
    average_loss: float | None  # a negative number
    total_profit: float
    # The narrowest group shown: the one that fits the current situation.
    fits: bool = False


class TrackRecord(BaseModel):
    pattern: str
    direction: str
    asset_class: str
    minimum_sample: int
    closed_trades: int  # in the broadest group
    groups: list[Group]  # broadest first; empty when none holds the minimum sample


def track_record(
    trades: list[FiledTrade], moment: Moment, minimum: int, step: int
) -> TrackRecord:
    """The groups that fit `moment`, over the trades closed by `step`."""
    found = ladder(trades, moment, minimum, step)
    used = found.used
    groups = []
    for rung in found.shown:
        group = moment.group(rung.splits)
        groups.append(
            Group(
                trend=group.trend,
                volume_level=group.volume_level,
                part_of_day=group.part_of_day,
                trades=rung.trades,
                made_money=rung.made_money,
                average_gain=rung.average_gain,
                average_loss=rung.average_loss,
                total_profit=rung.total_profit,
                fits=rung is used,
            )
        )
    return TrackRecord(
        pattern=moment.pattern,
        direction=moment.direction,
        asset_class=moment.asset_class,
        minimum_sample=minimum,
        closed_trades=found.count,
        groups=groups,
    )
