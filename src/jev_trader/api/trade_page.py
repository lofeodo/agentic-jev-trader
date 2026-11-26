"""The Trade page (spec appendix 7 section 7; `GET /sims/{id}/trades/{trade}`).

One trade reviewed the way a trader would: the price chart around it with entry, stop price and
close marked and each position screen or review ticked; the order (the size Jev chose, the size
after trimming and which limit trimmed it, the costs); every position review with Jev's
probabilities, told apart from the steps where the position screen said no; the nightly charges;
and memory in two parts, the entry memory beside each review's fresh memory.

A trade is named by its position number, as the trades table's lines are. Real names, prices and
dates lead (appendix 8, section 8.13), turned back by `sim_page.Sim` and `sim_page.price_of`.
Everything is read from stored records when asked for.

Choices the spec leaves to the build:

- The chart shows the asset's 15-minute closes from 32 steps (8 hours) before the trade was
  decided to 32 after it closed (or after the last completed step, while it is open).
- The stop price is that of the candidate trade Jev picked; the stop price mark sits at the
  entry. A position review's or position screen's tick carries no price.
- A position screen with no answer (code alone, at a stock's last bar, asked nothing) is not a
  step the position screen said no, so it is left out.
- Memory is the stored request's background word for word, so it keeps the rescaled prices Jev
  read: the entry memory from the full evaluation's pick request, a review's fresh memory from
  its action request. Scorecard lines come from the track record section, episodes from the
  past episodes section, each with its stored decision ID, newest first as Jev read them. The
  sections are found by the headings of the current reading's wording.
- A review's probabilities are Jev's averaged over the copies of its question (`action_*`); the
  amount is what it added after the limits, or the value of what it reduced.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from jev_trader.api.sim_page import Price, Sim, carried_out, price_of
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import Trade, TradeLine, trade_line, trades_of
from jev_trader.jev.reading import load_wording
from jev_trader.sim.store import (
    ACTION_ADD,
    ACTION_REDUCE,
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
)


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
    """An order a decision placed (on the Trade page, the one that opened the trade): its size
    before and after the risk limits, and what it cost."""

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
    kind: Literal["review", "screen said no"]
    # A stock's end-of-session review, with no position screen first.
    end_of_session: bool
    decision: str | None  # opens the review's trail
    # The position screen's answer, 0 to 1; None at end of session.
    screen_answer: float | None
    answer: str | None  # a review's: hold, close, reduce or add
    amount_usd: float | None  # how much was added or reduced, after the limits
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


# The Jev request a decision's memory was read in: a full evaluation's pick, a review's action.
MEMORY_REQUEST = {KIND_FULL_EVALUATION: "pick", KIND_POSITION_REVIEW: "action"}
# How many steps of price the chart shows before the trade was decided and after it closed.
AROUND_STEPS = 32
_WORDING = load_wording()


def _prefix(wording_key: str) -> str:
    """A heading's or footer's words up to its first blank to fill in."""
    return _WORDING[wording_key].split("{")[0]


def _sections(background: str) -> list[list[str]]:
    """The background's sections, each a list of its blank-line-separated parts; a section
    starts at a part opening with a "# " heading."""
    sections: list[list[str]] = []
    for part in background.split("\n\n"):
        if part.startswith("# ") or not sections:
            sections.append([part])
        else:
            sections[-1].append(part)
    return sections


def _scorecard_lines(sections: list[list[str]]) -> list[str]:
    heading = _WORDING["track_record_heading"]
    footer = _prefix("track_record_footer")
    for parts in sections:
        lines = "\n\n".join(parts).split("\n")
        if lines[0] == heading:
            return [
                line
                for line in lines[1:]
                if not line.startswith(footer)
                and line != _WORDING["track_record_no_pattern"]
            ]
    return []


def _episode_blocks(sections: list[list[str]]) -> list[str]:
    headings = (
        _prefix("past_episodes_heading"),
        _prefix("review_past_episodes_heading"),
    )
    label = _prefix("episode_label")
    for first, *rest in sections:
        if first.startswith(headings):
            blocks: list[str] = []
            for part in [first.partition("\n")[2], *rest]:
                if part.startswith(label) or not blocks:
                    blocks.append(part)
                else:  # a blank line inside an episode
                    blocks[-1] += "\n\n" + part
            return blocks
    return []


def _newest_first(episode_ids: list[str]) -> list[str]:
    """Stored decision IDs (sim, step, asset) in the order Jev reads them: newest first."""
    return sorted(episode_ids, key=lambda e: (-int(e.split("-")[1]), e))


def memory_read(decision: dict, requests: list[dict]) -> MemoryRead:
    """What Jev read from memory for a full evaluation or a position review: the track record's
    lines and the past episodes, word for word from the background of the request it was read
    in, each episode with its stored decision ID. Empty without memory."""
    purpose = MEMORY_REQUEST.get(decision["KIND"])
    background = next(
        (
            r["BACKGROUND_AFTER_OPENING"]
            for r in requests
            if r["DECISION"] == decision["ID"] and r["PURPOSE"] == purpose
        ),
        "",
    )
    sections = _sections(background)
    ids = _newest_first(list(decision.get("SELECTED") or []))
    return MemoryRead(
        decision=decision["ID"],
        scorecard_lines=_scorecard_lines(sections),
        episodes=[
            EpisodeRead(episode=ids[n] if n < len(ids) else "", text=text)
            for n, text in enumerate(_episode_blocks(sections))
        ],
    )


def trade_order(order: dict) -> TradeOrder:
    return TradeOrder(
        amount_chosen_usd=order.get("AMOUNT_CHOSEN"),
        amount_placed_usd=order.get("AMOUNT_AFTER_TRIMMING")
        or order.get("VALUE")
        or 0.0,
        limited_by=order.get("LIMITED_BY"),
        slippage_usd=order.get("SLIPPAGE_COST") or 0.0,
        commission_or_fee_usd=order.get("COMMISSION_OR_TRADING_FEE") or 0.0,
    )


def order_placed(orders: list[dict], decision_id: str) -> TradeOrder | None:
    """The order a decision placed and that was carried out; None if there is none (a
    cancelled or still waiting order charged nothing)."""
    for order in carried_out(orders):
        if order.get("DECISION") == decision_id:
            return trade_order(order)
    return None


def average_answers(answers: dict | None) -> list[Probability]:
    """A review's probability for each answer (hold, close, reduce, add), averaged over the
    copies of the question Jev was asked (`action_1`, `action_2`, ...)."""
    copies = [v for k, v in (answers or {}).items() if k.startswith("action_")]
    if not copies:
        return []
    return [
        Probability(
            option=option,
            probability=sum(c.get(option, 0.0) for c in copies) / len(copies),
        )
        for option in copies[0]
    ]


def _review_amount(review: dict, orders: list[dict]) -> float | None:
    """How much a review added (after the limits), or the value of what it reduced."""
    if review["ACTION"] == ACTION_ADD:
        return review.get("SIZE_AFTER_TRIMMING")
    if review["ACTION"] == ACTION_REDUCE:
        for order in carried_out(orders):
            if order.get("DECISION") == review["ID"]:
                return order["VALUE"]
    return None


def _position_step(
    sim: Sim, row: dict, requests: list[dict], orders: list[dict]
) -> PositionStep | None:
    if row["KIND"] == KIND_POSITION_REVIEW:
        return PositionStep(
            step=row["STEP"],
            at=sim.at(row["STEP"]),
            kind="review",
            end_of_session=bool(row.get("END_OF_SESSION")),
            decision=row["ID"],
            screen_answer=row.get("SCREEN_ANSWER"),
            answer=row.get("PICK"),
            amount_usd=_review_amount(row, orders),
            probabilities=average_answers(row.get("ANSWERS")),
            fresh_memory=memory_read(row, requests),
        )
    if row.get("SCREEN_ANSWER") is None:  # code alone at a stock's last bar
        return None
    return PositionStep(
        step=row["STEP"],
        at=sim.at(row["STEP"]),
        kind="screen said no",
        end_of_session=False,
        decision=row["ID"],
        screen_answer=row["SCREEN_ANSWER"],
        answer=None,
        amount_usd=None,
        probabilities=[],
        fresh_memory=None,
    )


def _stop_price(sim: Sim, entry: dict | None, asset: str) -> Price | None:
    """The stop price of the candidate trade Jev picked."""
    for candidate in (entry or {}).get("CANDIDATE_TRADES") or []:
        if candidate["name"] == entry["PICK"]:
            return price_of(sim, asset, candidate["stop_price"])
    return None


def _marks(
    sim: Sim, trade: Trade, stop_price: Price | None, steps: list[PositionStep]
) -> list[ChartMark]:
    opened, asset = trade.opened_step, trade.asset
    entry, last = trade.orders[0], trade.orders[-1]
    marks = [
        ChartMark(
            step=opened,
            at=sim.at(opened),
            kind="entry",
            price=price_of(sim, asset, entry["PRICE"]),
            decision=trade.decision,
        )
    ]
    if stop_price is not None:
        marks.append(
            ChartMark(
                step=opened,
                at=sim.at(opened),
                kind="stop price",
                price=stop_price,
                decision=None,
            )
        )
    marks += [
        ChartMark(
            step=s.step,
            at=s.at,
            kind="position review" if s.kind == "review" else "position screen",
            price=None,
            decision=s.decision,
        )
        for s in steps
    ]
    if trade.closed_step is not None:
        marks.append(
            ChartMark(
                step=trade.closed_step,
                at=sim.at(trade.closed_step),
                kind="close",
                price=price_of(sim, asset, last["PRICE"]),
                decision=last.get("DECISION"),
            )
        )
    return sorted(marks, key=lambda m: m.step)


def trade_page(store: ApiStore, sim_id: int, trade: int) -> TradePage:
    sim = Sim(store, sim_id)
    charges = store.charges(sim_id)
    orders = store.orders(sim_id)
    found = next((t for t in trades_of(orders, charges) if t.position == trade), None)
    if found is None:
        raise TradeNotFound(trade)
    reached = sim.row.get("LAST_COMPLETED_STEP")

    entry = None if found.decision is None else store.decision(sim_id, found.decision)
    looked_at = store.position_decisions(sim_id, trade)
    decisions = [d["ID"] for d in looked_at] + ([entry["ID"]] if entry else [])
    requests = store.jev_requests(sim_id, decisions)
    steps = [
        s
        for row in looked_at
        if (s := _position_step(sim, row, requests, orders)) is not None
    ]
    stop_price = _stop_price(sim, entry, found.asset)

    last = found.closed_step or reached or found.opened_step
    closes = store.closes(
        sim.row["DATASET"],
        found.asset,
        found.decided_step - AROUND_STEPS,
        last + AROUND_STEPS,
    )
    return TradePage(
        trade=trade_line(sim, found, reached),
        stop_price=stop_price,
        bars=[
            ChartBar(step=s, at=sim.at(s), close=price_of(sim, found.asset, c))
            for s, c in sorted(closes.items())
        ],
        marks=_marks(sim, found, stop_price, steps),
        order=trade_order(found.orders[0]),
        position_steps=steps,
        nightly_charges=[
            NightlyCharge(
                step=c["STEP"],
                at=sim.at(c["STEP"]),
                kind=c["KIND"],
                amount_usd=c["AMOUNT"],
            )
            for c in charges
            if c.get("POSITION") == trade
        ],
        entry_memory=memory_read(entry, requests)
        if entry is not None
        else MemoryRead(decision=None, scorecard_lines=[], episodes=[]),
    )
