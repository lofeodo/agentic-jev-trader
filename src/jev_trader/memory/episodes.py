"""A past episode as memory hands it out, built by code from stored facts (spec appendix 5,
sections 1 and 4; ADR 0001).

An episode is a stored full evaluation or position review with how it turned out: "bullish
engulfing after four falling bars; a $800 long; closed 6 bars later, up $9". It is built from
its decision row (`MEMORY.DECISIONS`), its outcomes (`MEMORY.OUTCOMES`), its snapshot's
situation text and measurements, and for a trade the decision rows of the position's bars (its
journal). Nothing here reads the orders: the memory server's login cannot.

The models cross the MCP connection as JSON; `jev_trader.memory.render` writes them as text.

Choices the spec leaves to the build:

- A full evaluation whose entry was never carried out (cancelled) shows as no trade, with where
  the price went, as its outcomes judge it.
- A trade's stop price distance is the one listed when it was decided, from that step's close.
- A trade's percent is its profit over the money its entry put in.
- A position's bars are counted as the agent counts them: bar 0 is the bar it was opened in.
  A stop price, forced close or the sim's end is written at the bar after the last one looked
  at, where it happened.
"""

from pydantic import BaseModel

from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import (
    VOLUME_HIGH_ABOVE,
    VOLUME_LOW_BELOW,
    read_situation,
)
from jev_trader.memory.outcomes import OutcomeKind
from jev_trader.memory.scorecard import volume_level
from jev_trader.sim.store import (
    ACTION_ADD,
    ACTION_CLOSE,
    ACTION_ENTRY,
    ACTION_REDUCE,
    KIND_POSITION_REVIEW,
)

HOLD = "hold"
NO_TRADE = "no_trade"
_LONG_TERM_TREND = MEASUREMENT_NAMES.index("long_term_trend")
_VOLUME = MEASUREMENT_NAMES.index("volume_against_normal")


class Trade(BaseModel):
    direction: str  # "long" or "short"
    stop: str  # "tight", "medium" or "wide"
    stop_distance: float  # as a share of the price: 0.006 is 0.6%
    dollars: float  # what the entry put in


class Standing(BaseModel):
    """How a position stood at a review (as `PositionView.standing` stores it)."""

    direction: str
    put_in: float
    bars_open: int
    profit: float  # what closing then would have left, after trading costs
    percent: float  # the same in percent: 0.4 is 0.4%
    stop_distance: float  # as a share of the price
    best: float
    worst: float


class Step(BaseModel):
    """One bar of a position's journal, or a review's decision."""

    bar: int
    action: str  # hold, close, reduce, add, or how the trade ended: stop_price, forced_close,
    # sim_ended
    share: float | None = None  # a reduce: the share closed
    profit: float | None = None  # a reduce: what that part would have made
    amount: float | None = None  # an add: the dollars placed
    this_review: bool = False


class Prices(BaseModel):
    """Where the price went after the decision, as changes: 0.002 is up 0.2%."""

    after_1_bar: float
    after_4_bars: float
    end_of_day: float


class Ended(BaseModel):
    reason: str  # jev, stop_price, forced_close or sim_ended
    bars_after: int  # the asset's bars after the decision
    profit: float  # the whole trade, after trading costs
    percent: float | None  # of the money the entry put in: 0.4 is 0.4%
    best: float | None = None
    worst: float | None = None
    closed_at_this_review: bool = False


class Episode(BaseModel):
    id: str  # the stored decision's ID
    kind: str  # full_evaluation or position_review
    asset: str
    asset_class: str
    step: int
    situation: str
    patterns: list[str]  # the 15-minute patterns of the pattern window
    longer_patterns: list[str]  # those on the latest hourly and daily bars
    part_of_day: str
    trend: str | None  # the long-term trend, "up" or "down"
    volume: str | None  # low, average or high
    decided: str  # long, short, no_trade; or hold, close, reduce, add
    trade: Trade | None = None  # a full evaluation whose entry was carried out
    review: Step | None = None  # a position review's decision
    standing: Standing | None = None
    end_of_session: bool = False
    prices: Prices | None = None
    ended: Ended | None = None
    journal: list[Step] = []  # the trade bar by bar; only when read in full

    @property
    def is_review(self) -> bool:
        return self.kind == KIND_POSITION_REVIEW


def _value(outcomes: dict[str, dict], kind: OutcomeKind) -> dict | None:
    found = outcomes.get(str(kind))
    return None if found is None else found["VALUE"]


def _prices(outcomes: dict[str, dict]) -> Prices | None:
    changes = [
        _value(outcomes, k)
        for k in (
            OutcomeKind.PRICE_AFTER_1_BAR,
            OutcomeKind.PRICE_AFTER_4_BARS,
            OutcomeKind.PRICE_AT_END_OF_DAY,
        )
    ]
    if any(c is None for c in changes):
        return None
    return Prices(
        after_1_bar=changes[0]["change"],
        after_4_bars=changes[1]["change"],
        end_of_day=changes[2]["change"],
    )


def _ended(outcomes: dict[str, dict], put_in: float | None) -> Ended | None:
    closed = _value(outcomes, OutcomeKind.POSITION_CLOSED)
    if closed is None:
        return None
    entered = closed.get("amount_entered") or put_in
    return Ended(
        reason=closed["closing_reason"],
        bars_after=closed["bars_after"],
        profit=closed["profit"],
        percent=100 * closed["profit"] / entered if entered else None,
        best=closed.get("best"),
        worst=closed.get("worst"),
        closed_at_this_review=bool(closed.get("closed_at_this_review")),
    )


def position_step(row: dict, bar: int) -> Step:
    """One decision row of an open position as a step of its journal."""
    action = row["ACTION"]
    if action == ACTION_REDUCE:
        share = row["REDUCE_SHARE"]
        return Step(
            bar=bar,
            action=action,
            share=share,
            profit=share * (row.get("STANDING") or {}).get("profit", 0.0),
        )
    if action == ACTION_ADD:
        return Step(bar=bar, action=action, amount=row["SIZE_AFTER_TRIMMING"])
    if action == ACTION_CLOSE:
        return Step(bar=bar, action=action)
    return Step(bar=bar, action=HOLD)


def journal(
    position_rows: list[dict], ended: Ended | None, review_step: int | None = None
) -> list[Step]:
    """The trade bar by bar: one step per decision row of its position (oldest first), then how
    it ended if code closed it, with the review at `review_step` marked."""
    rows = sorted(position_rows, key=lambda r: r["STEP"])
    steps = [
        position_step(r, bar).model_copy(
            update={"this_review": r["STEP"] == review_step}
        )
        for bar, r in enumerate(rows)
    ]
    if ended is not None and ended.reason != "jev":
        steps.append(Step(bar=len(rows), action=ended.reason))
    return steps


def build(
    decision: dict,
    outcomes: list[dict],
    position_rows: list[dict] | None = None,
    volume_cut_offs: tuple[float, float] = (VOLUME_LOW_BELOW, VOLUME_HIGH_ABOVE),
) -> Episode:
    """An episode from its decision row (with its snapshot's SITUATION_TEXT, MEASUREMENTS and
    ASSET_CLASS), its outcome rows, and, to read it in full, its position's decision rows.
    `volume_cut_offs` are the sim's: below the first is low volume, above the second high."""
    by_kind = {o["KIND"]: o for o in outcomes}
    read = read_situation(decision["SITUATION_TEXT"])
    measured = decision["MEASUREMENTS"]
    trend = measured[_LONG_TERM_TREND]
    volume = volume_level(measured[_VOLUME], *volume_cut_offs)
    episode = {
        "id": decision["ID"],
        "kind": decision["KIND"],
        "asset": decision["ASSET"],
        "asset_class": decision["ASSET_CLASS"],
        "step": decision["STEP"],
        "situation": decision["SITUATION_TEXT"],
        "patterns": list(read.window),
        "longer_patterns": list(read.longer_bars),
        "part_of_day": read.part_of_day,
        "trend": None if trend is None else "up" if trend >= 0 else "down",
        "volume": None if volume == "not available" else volume,
        "prices": _prices(by_kind),
    }
    if decision["KIND"] == KIND_POSITION_REVIEW:
        standing = Standing(**decision["STANDING"])
        review = position_step(decision, standing.bars_open)
        ended = _ended(by_kind, standing.put_in)
        return Episode(
            **episode,
            decided=review.action,
            review=review,
            standing=standing,
            end_of_session=bool(decision.get("END_OF_SESSION")),
            ended=ended,
            journal=journal(position_rows or [], ended, decision["STEP"])
            if position_rows
            else [],
        )
    entry = _value(by_kind, OutcomeKind.ORDER_CARRIED_OUT) or {}
    if decision["ACTION"] != ACTION_ENTRY or not entry.get("carried_out"):
        return Episode(**episode, decided=NO_TRADE)
    pick = decision["PICK"]
    listed = next(t for t in decision["CANDIDATE_TRADES"] if t["name"] == pick)
    trade = Trade(
        direction=listed["direction"],
        stop=pick.split("_")[1],
        stop_distance=listed["stop_share"],
        dollars=entry["value"],
    )
    ended = _ended(by_kind, trade.dollars)
    return Episode(
        **episode,
        decided=trade.direction,
        trade=trade,
        ended=ended,
        journal=journal(position_rows, ended) if position_rows else [],
    )


def position_of(outcomes: list[dict]) -> int | None:
    """The position a traded full evaluation opened, from its entry's outcome."""
    for o in outcomes:
        if o["KIND"] == OutcomeKind.ORDER_CARRIED_OUT:
            return o["VALUE"].get("position")
    return None
