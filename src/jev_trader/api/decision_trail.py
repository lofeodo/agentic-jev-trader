"""The decision trail (spec appendix 7 section 6; `GET /sims/{id}/decisions/{decision}/trail`).

Everything asked and answered on the way to one decision, stage by stage, every message word for
word from storage (nothing rebuilt). The standing instructions and tool descriptions, stored once
per prompt version, are joined to the messages. The text keeps the masked IDs and rescaled prices
the models saw; the key beside it turns them back into real ones.

- A full evaluation (a trade opening) has six stops: screen, memory, pick, size, limits, order.
  A full evaluation that ended in no trade stops at the pick.
- A position review has its own: position screen, memory, answer (Jev's answer and how much),
  limits, order. An end-of-session review has no position screen, so it starts at memory.

Skeleton: the answer is fixed and made up, of the right shape. Only an unknown sim is refused.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from jev_trader.api.sim_page import Sim
from jev_trader.api.sims_list import AssetName
from jev_trader.api.store import ApiStore
from jev_trader.api.trade_page import TradeOrder
from jev_trader.sim.store import KIND_FULL_EVALUATION

# The two kinds of decision with a trail, as `MEMORY.DECISIONS` names them.
TrailKind = Literal["full_evaluation", "position_review"]


class DecisionNotFound(KeyError):
    """The sim has no decision of that ID."""


class TrailMessage(BaseModel):
    """One message that passed, word for word as stored."""

    sender: str  # "code", "jev" or "llm"
    role: str  # "instructions", "tools", "request", "answer", "tool call" or "tool result"
    text: str
    # Memory's marks: "refused at the limit", "asked again", "episode never shown".
    marks: list[str]


class TrailStop(BaseModel):
    """One box of the strip, and the messages behind it."""

    name: str  # screen, memory, pick, size, limits, order; position screen, answer
    outcome: str  # what the stop came to, in a few words
    messages: list[TrailMessage]


class TrailKey(BaseModel):
    """Turns a masked ID and its rescaled prices back into real ones."""

    masked_id: str
    name: str
    ticker: str
    price_scale: float  # a real price is the shown price divided by this


class DecisionTrail(BaseModel):
    decision: str
    kind: TrailKind
    end_of_session: bool  # a position review at the end of a stock's session
    step: int
    at: datetime | None
    asset: AssetName
    position: int | None  # the trade it opened or reviewed; None for no trade
    stops: list[TrailStop]  # in order
    # The limits and order stops' figures: the size Jev chose, the size after trimming, which
    # limit trimmed it, and the costs. None when no order was placed.
    order: TradeOrder | None
    key: list[TrailKey]


def decision_trail(store: ApiStore, sim_id: int, decision: str) -> DecisionTrail:
    sim = Sim(store, sim_id)
    return DecisionTrail(
        decision=decision,
        kind=KIND_FULL_EVALUATION,
        end_of_session=False,
        step=0,
        at=sim.at(0),
        asset=AssetName(name="Apple", masked_id="ASSET_01"),
        position=None,
        stops=[
            TrailStop(name=name, outcome="placeholder", messages=[])
            for name in ("screen", "memory", "pick", "size", "limits", "order")
        ],
        order=None,
        key=[
            TrailKey(masked_id="ASSET_01", name="Apple", ticker="AAPL", price_scale=0.5)
        ],
    )
