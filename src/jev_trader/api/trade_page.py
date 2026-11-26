"""The Trade page (spec appendix 7 section 7; `GET /sims/{id}/trades/{trade}`).

One trade reviewed the way a trader would: the price chart around it with entry, stop price and
close marked and each position screen or review ticked; the order (the size Jev chose, the size
after trimming and which limit trimmed it, the costs); every position review with Jev's
probabilities, told apart from the steps where the position screen said no; the nightly charges;
and memory in two parts, the entry memory beside each review's fresh memory.

A trade is named by its position number, as the trades table's lines are. Real names, prices and
dates lead (appendix 8, section 8.13).

Skeleton: the answer is fixed and made up, of the right shape. Only an unknown sim is refused.
"""

from datetime import datetime

from pydantic import BaseModel

from jev_trader.api.sim_page import Price, Sim
from jev_trader.api.sims_list import AssetName
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import TradeLine


class TradeNotFound(KeyError):
    """The sim has no trade of that position number."""


class ChartBar(BaseModel):
    """One 15-minute bar's close, around the trade."""

    step: int
    at: datetime | None
    close: Price


class ChartMark(BaseModel):
    """A mark on the chart: entry, stop price, close, or a position screen or review ticked."""

    step: int
    at: datetime | None
    kind: str  # "entry", "stop price", "close", "position screen" or "position review"
    price: Price | None
    decision: str | None  # the review's decision, which opens its trail


class TradeOrder(BaseModel):
    """The order that opened the trade, and what it cost."""

    amount_chosen_usd: float | None  # the size Jev chose, before the risk limits
    amount_placed_usd: float  # the size after trimming
    limited_by: str | None  # the risk limit that trimmed it
    slippage_usd: float  # paid inside the price: filled a little worse than the bar's
    commission_or_fee_usd: float


class Probability(BaseModel):
    """One of Jev's answers and how likely it rated it, 0 to 1."""

    option: str
    probability: float


class EpisodeRead(BaseModel):
    """A past episode Jev read, as it was written for it."""

    episode: str  # the episode's ID, as the LLM named it
    text: str


class MemoryRead(BaseModel):
    """What Jev read from memory for one decision."""

    decision: str | None  # opens the trail of the decision it was read for
    scorecard_lines: list[str]
    episodes: list[EpisodeRead]


class PositionStep(BaseModel):
    """A step the open position was looked at: a review, or the position screen saying no
    (nothing more asked: the position was held, guarded by its stop price)."""

    step: int
    at: datetime | None
    kind: str  # "review" or "screen said no"
    # A stock's end-of-session review, with no position screen first.
    end_of_session: bool
    decision: str | None  # opens the review's trail
    # The position screen's answer, 0 to 1; None at end of session.
    screen_answer: float | None
    answer: str | None  # a review's: hold, close, reduce or add
    amount_usd: float | None  # how much to reduce or add
    probabilities: list[Probability]  # a review's: Jev's probability for each answer
    fresh_memory: MemoryRead | None  # a review's own memory, for its own moment


class NightlyCharge(BaseModel):
    """A charge the trade paid for being held overnight, such as a short's borrow fee."""

    step: int
    at: datetime | None
    kind: str
    amount_usd: float


class TradePage(BaseModel):
    trade: TradeLine  # the trade's line in the trades table
    stop_price: Price | None  # where code closes it at a loss; None for holding
    bars: list[ChartBar]
    marks: list[ChartMark]
    order: TradeOrder
    position_steps: list[PositionStep]  # oldest first
    nightly_charges: list[NightlyCharge]
    entry_memory: MemoryRead  # read when the trade opened; kept, not read again by Jev


def trade_page(store: ApiStore, sim_id: int, trade: int) -> TradePage:
    sim = Sim(store, sim_id)
    asset = AssetName(name="Apple", masked_id="ASSET_01")
    price = Price(real=200.0, rescaled=100.0)
    entry = MemoryRead(decision="placeholder", scorecard_lines=[], episodes=[])
    return TradePage(
        trade=TradeLine(
            kind="trade",
            decision="placeholder",
            position=trade,
            asset=asset,
            direction="long",
            decided_step=0,
            decided_at=sim.at(0),
            opened_step=1,
            opened_at=sim.at(1),
            closed_step=None,
            closed_at=None,
            units=1.0,
            entry_price=price,
            exit_price=None,
            put_in_usd=100.0,
            profit_usd=None,
            trading_costs_usd=0.0,
            closing_reason=None,
            amount_chosen=None,
            limited_by=None,
            trimmed=False,
            held_overnight=False,
            screen_answer=None,
            pick=None,
            rating=None,
        ),
        stop_price=None,
        bars=[ChartBar(step=1, at=sim.at(1), close=price)],
        marks=[
            ChartMark(
                step=1, at=sim.at(1), kind="entry", price=price, decision="placeholder"
            )
        ],
        order=TradeOrder(
            amount_chosen_usd=None,
            amount_placed_usd=100.0,
            limited_by=None,
            slippage_usd=0.0,
            commission_or_fee_usd=0.0,
        ),
        position_steps=[],
        nightly_charges=[],
        entry_memory=entry,
    )
