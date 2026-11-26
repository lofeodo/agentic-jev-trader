"""The decision trail (spec appendix 7 section 6; `GET /sims/{id}/decisions/{decision}/trail`).

Everything asked and answered on the way to one decision, stage by stage, every message word for
word from storage (nothing rebuilt). The standing instructions and tool descriptions, stored once
per prompt version, are joined to the messages. The text keeps the masked IDs and rescaled prices
the models saw; the key beside it turns them back into real ones.

- A full evaluation (a trade opening) has six stops: screen, memory, pick, size, limits, order.
  A full evaluation that ended in no trade stops at the pick.
- A position review has its own: position screen, memory, answer (Jev's answer and how much),
  limits, order. An end-of-session review has no position screen, so it starts at memory.

Choices the spec leaves to the build:

- A screen or a position screen that went no further (the sim page lists them among its latest
  decisions) has a trail of its one stop.
- A position review that held stops at its answer, as a full evaluation that picked no trade
  stops at its pick.
- Each Jev request is three messages: code's background (the reading's opening joined back on),
  code's questions as sent (JSON), and Jev's answer as received.
- An LLM reply is its text, then each tool call it made as JSON (name and inputs). A reply that
  was a tool call's answer is the `answer`, any other tool call a `tool call`, and a reply with
  no tool call a `reply`.
- The marks: a lookup refused at either limit (6 lookups, or the time) on the tool result that
  refused it; "asked again" on a stored failed reply; "episode never shown" on an answer naming
  a label that is not among the episodes shown.
- The key lists every asset of the sim's dataset, since a background can name other positions.
"""

import json
from datetime import datetime
from typing import Literal

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    messages_from_dict,
)
from pydantic import BaseModel

from jev_trader.api.sim_page import Sim
from jev_trader.api.sims_list import AssetName
from jev_trader.api.store import ApiStore
from jev_trader.api.trade_page import TradeOrder, order_placed
from jev_trader.jev.full_evaluation import NO_TRADE
from jev_trader.jev.position_review import HOLD
from jev_trader.llm.selection import READ, LimitHit, word_for_word
from jev_trader.llm.wording import ANSWER_TOOL
from jev_trader.sim.store import (
    ACTION_ENTRY,
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
    KIND_POSITION_SCREEN,
)

# The kinds of decision, as `MEMORY.DECISIONS` names them.
TrailKind = Literal["screen", "full_evaluation", "position_screen", "position_review"]

REFUSED_AT_THE_LIMIT = "refused at the limit"
ASKED_AGAIN = "asked again"
EPISODE_NEVER_SHOWN = "episode never shown"
# The Jev requests behind each stop, by their stored purpose, in the order they are asked.
_REQUESTS = {
    "screen": ("screen",),
    "pick": ("pick",),
    "size": ("size",),
    "position screen": ("position_screen",),
    "answer": ("action", "reduce", "add"),
}


class DecisionNotFound(KeyError):
    """The sim has no decision of that ID."""


class TrailMessage(BaseModel):
    """One message that passed, word for word as stored."""

    sender: str  # "code", "jev" or "llm"
    # Code's "instructions", "tools", "background", "questions", "request" or "tool result";
    # Jev's "answer"; the LLM's "tool call", "answer" or "reply" (neither).
    role: str
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


# Jev's requests


def _jev_messages(
    requests: list[dict], purposes: tuple[str, ...]
) -> list[TrailMessage]:
    asked = sorted(
        (r for r in requests if r["PURPOSE"] in purposes),
        key=lambda r: purposes.index(r["PURPOSE"]),
    )
    messages = []
    for r in asked:
        opening = r.get("OPENING")
        background = r["BACKGROUND_AFTER_OPENING"]
        messages += [
            TrailMessage(
                sender="code",
                role="background",
                text=f"{opening}\n\n{background}" if opening else background,
                marks=[],
            ),
            TrailMessage(
                sender="code",
                role="questions",
                text=json.dumps(r["QUESTIONS"], indent=2, ensure_ascii=False),
                marks=[],
            ),
            TrailMessage(sender="jev", role="answer", text=r["ANSWER"], marks=[]),
        ]
    return messages


# The LLM's exchange


def _tools_text(tools: list[dict]) -> str:
    return "\n\n".join(
        f"{t['name']}: {t['description']}\n"
        f"Inputs: {json.dumps(t.get('input_schema'), ensure_ascii=False)}"
        for t in tools
    )


def _reply_text(message: AIMessage) -> str:
    """A reply as stored: its text, then each tool call it made (unreadable ones too) as
    JSON."""
    stored = json.loads(word_for_word(message))
    content = stored["content"]
    text = (
        content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    )
    calls = [json.dumps(c, ensure_ascii=False) for c in stored["tool_calls"]]
    return "\n".join(part for part in [text, *calls] if part)


def _named_unshown(message: AIMessage, shown: set[str]) -> bool:
    """Whether a reply named an episode ID never shown: in its answer, or in a read lookup
    (which the selection refuses)."""
    return any(
        label not in shown
        for c in message.tool_calls
        if c["name"] in (ANSWER_TOOL, READ)
        for label in c["args"].get("episode_ids") or []
    )


def _llm_messages(decision: dict, exchange: dict) -> list[TrailMessage]:
    job = decision["KIND"]
    found = [
        TrailMessage(
            sender="code",
            role="instructions",
            text=exchange["SYSTEM_PROMPTS"].get(job) or "",
            marks=[],
        ),
        TrailMessage(
            sender="code",
            role="tools",
            text=_tools_text(exchange["TOOLS"].get(job) or []),
            marks=[],
        ),
    ]
    failed = [json.loads(reply) for reply in exchange["FAILED_REPLIES"] or []]
    lookups = iter(decision.get("LOOKUPS") or [])
    shown = {e["label"] for e in decision.get("EPISODES_SHOWN") or []}
    at_the_limit = {str(LimitHit.LOOKUPS), str(LimitHit.TIME)}
    refused: set[str] = set()  # the tool calls refused at a limit, by ID
    for message in messages_from_dict(exchange["MESSAGES"]):
        marks = []
        if isinstance(message, AIMessage):
            as_stored = json.loads(word_for_word(message))
            if as_stored in failed:  # a failed reply runs none of its lookups
                failed.remove(as_stored)
                marks.append(ASKED_AGAIN)
            else:
                for call in message.tool_calls:
                    if call["name"] == ANSWER_TOOL:
                        continue
                    lookup = next(lookups, None)
                    if lookup and lookup.get("refused") in at_the_limit:
                        refused.add(call["id"])
            if _named_unshown(message, shown):
                marks.append(EPISODE_NEVER_SHOWN)
            answers = any(c["name"] == ANSWER_TOOL for c in message.tool_calls)
            role = (
                "answer" if answers else "tool call" if message.tool_calls else "reply"
            )
            found.append(
                TrailMessage(
                    sender="llm", role=role, text=_reply_text(message), marks=marks
                )
            )
        elif isinstance(message, ToolMessage):
            if message.tool_call_id in refused:
                marks.append(REFUSED_AT_THE_LIMIT)
            found.append(
                TrailMessage(
                    sender="code",
                    role="tool result",
                    text=str(message.content),
                    marks=marks,
                )
            )
        else:
            text = message.content if isinstance(message, HumanMessage) else ""
            found.append(
                TrailMessage(sender="code", role="request", text=str(text), marks=[])
            )
    return found


# The stops


def _percent(probability: float | None) -> str:
    return "no answer" if probability is None else f"{probability:.0%} yes"


def _screen_stop(name: str, decision: dict, requests: list[dict]) -> TrailStop:
    skipped = decision.get("SKIPPED_BECAUSE")
    return TrailStop(
        name=name,
        outcome=f"not asked: {skipped}"
        if skipped
        else _percent(decision.get("SCREEN_ANSWER")),
        messages=_jev_messages(requests, _REQUESTS[name]),
    )


def _memory_stop(decision: dict, exchange: dict | None) -> TrailStop:
    if exchange is None:
        return TrailStop(name="memory", outcome="the LLM was not asked", messages=[])
    selected = len(decision.get("SELECTED") or [])
    outcome = f"{selected} past episodes chosen" if selected else "none chosen"
    if decision.get("LIMIT_HIT"):
        outcome += f", {decision['LIMIT_HIT']} limit reached"
    return TrailStop(
        name="memory", outcome=outcome, messages=_llm_messages(decision, exchange)
    )


def _limit_words(limit: str) -> str:
    """A limit's stored name as the screens say it: `trade_risk` reads "trade risk"."""
    return limit.replace("_", " ")


def _limits_stop(decision: dict, order: TradeOrder | None) -> TrailStop:
    limit = order.limited_by if order else decision.get("LIMITED_BY")
    if limit is None:
        outcome = "not trimmed"
    elif order is None or not order.amount_placed_usd:
        outcome = f"trimmed to nothing by the {_limit_words(limit)} limit"
    else:
        outcome = f"trimmed to ${order.amount_placed_usd:,.0f} by the {_limit_words(limit)} limit"
    return TrailStop(name="limits", outcome=outcome, messages=[])


def _order_stop(order: TradeOrder | None) -> TrailStop:
    if order is None:
        return TrailStop(name="order", outcome="no order", messages=[])
    costs = order.slippage_usd + order.commission_or_fee_usd
    return TrailStop(
        name="order",
        outcome=f"${order.amount_placed_usd:,.0f} placed, ${costs:,.2f} in costs",
        messages=[],
    )


def _answer_outcome(decision: dict) -> str:
    pick = decision.get("PICK")
    if pick == "add" and decision.get("SIZE_CHOSEN") is not None:
        return f"add ${decision['SIZE_CHOSEN']:,.0f}"
    if pick == "reduce" and decision.get("REDUCE_SHARE") is not None:
        return f"reduce by {decision['REDUCE_SHARE']:.0%}"
    return pick or "no answer"


def _full_evaluation_stops(
    decision: dict,
    requests: list[dict],
    exchange: dict | None,
    order: TradeOrder | None,
) -> list[TrailStop]:
    pick = decision.get("PICK")
    stops = [
        _screen_stop("screen", decision, requests),
        _memory_stop(decision, exchange),
        TrailStop(
            name="pick",
            outcome=(pick or "no answer").replace("_", " "),
            messages=_jev_messages(requests, _REQUESTS["pick"]),
        ),
    ]
    if pick in (None, NO_TRADE):
        return stops
    chosen = decision.get("SIZE_CHOSEN")
    return stops + [
        TrailStop(
            name="size",
            outcome="no size" if chosen is None else f"${chosen:,.0f} chosen",
            messages=_jev_messages(requests, _REQUESTS["size"]),
        ),
        _limits_stop(decision, order),
        _order_stop(order),
    ]


def _position_review_stops(
    decision: dict,
    requests: list[dict],
    exchange: dict | None,
    order: TradeOrder | None,
) -> list[TrailStop]:
    stops = []
    if not decision.get("END_OF_SESSION"):
        stops.append(_screen_stop("position screen", decision, requests))
    stops += [
        _memory_stop(decision, exchange),
        TrailStop(
            name="answer",
            outcome=_answer_outcome(decision),
            messages=_jev_messages(requests, _REQUESTS["answer"]),
        ),
    ]
    if decision.get("PICK") in (None, HOLD):
        return stops
    return stops + [_limits_stop(decision, order), _order_stop(order)]


def _position(decision: dict, orders: list[dict]) -> int | None:
    if decision.get("POSITION") is not None:
        return decision["POSITION"]
    for order in orders:
        if order.get("DECISION") == decision["ID"] and order["KIND"] == ACTION_ENTRY:
            return order["POSITION"]
    return None


def decision_trail(store: ApiStore, sim_id: int, decision: str) -> DecisionTrail:
    sim = Sim(store, sim_id)
    row = store.decision(sim_id, decision)
    if row is None:
        raise DecisionNotFound(decision)
    orders = store.orders(sim_id)
    requests = store.jev_requests(sim_id, [decision])
    order = order_placed(orders, decision)
    kind = row["KIND"]
    if kind == KIND_FULL_EVALUATION:
        exchange = store.llm_exchange(sim_id, decision)
        stops = _full_evaluation_stops(row, requests, exchange, order)
    elif kind == KIND_POSITION_REVIEW:
        exchange = store.llm_exchange(sim_id, decision)
        stops = _position_review_stops(row, requests, exchange, order)
    elif kind == KIND_POSITION_SCREEN:
        stops = [_screen_stop("position screen", row, requests)]
    else:
        stops = [_screen_stop("screen", row, requests)]
    return DecisionTrail(
        decision=decision,
        kind=kind,
        end_of_session=bool(row.get("END_OF_SESSION")),
        step=row["STEP"],
        at=sim.at(row["STEP"]),
        asset=sim.asset(row["ASSET"]),
        position=_position(row, orders),
        stops=stops,
        order=order,
        key=[
            TrailKey(
                masked_id=k["MASKED_ID"],
                name=k["NAME"],
                ticker=k["TICKER"],
                price_scale=k["PRICE_SCALE"],
            )
            for k in sim.key.values()
        ],
    )
