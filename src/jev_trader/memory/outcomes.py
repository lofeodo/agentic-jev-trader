"""Episode outcomes: what happened after each full evaluation and position review (spec appendix 5
section 1; appendix 6 section 3.5; ADR 0001).

An episode is a stored full evaluation or position review with how it turned out. Its outcomes
are facts code records as bars pass and trades close, each in `MEMORY.OUTCOMES` with the step from
which memory may show it (`KNOWN_FROM`). No model writes any of them.

- **Where the price went:** the asset's close after 1 bar, after 4 bars (its own bars, so a stock
  counts across the night), and at the end of the decision's day, each with its change from the
  close the decision was made at (0.002 is 0.2%).
- **The order carried out:** for a full evaluation that placed a trade, whether its entry was
  carried out, and at what price.
- **The position closed:** why it closed, at which step, how many of the asset's bars after the
  decision, and its total profit or loss after trading costs. A review whose own close ended it
  reads "closed at this review".

Once every outcome a decision needs is in, the decision's `OUTCOMES_KNOWN_FROM` is set to the
latest of their steps: from then on episode search may return it, never before (`searchable`).

| Decision | Complete once |
|---|---|
| Full evaluation that placed a trade | its entry was carried out and the position has fully closed |
| Full evaluation with no trade (or a trade the limits left nothing of) | the three prices are in |
| Position review | the three prices are in and its trade has closed |

An entry cancelled before it was carried out then needs the three prices, like no trade. A
decision whose outcomes fall after the sim's last step stays incomplete and out of search.

Choices the spec leaves to the build:

- A day ends at a stock's last bar of the session, and at a crypto's last bar of the UTC day
  (the step that ends at midnight). If that bar is missing, the day's end is read at the asset's
  first bar of a later day, from the last close of the decision's day.
- A decision made at its day's last bar has its end-of-day price at once: its own close.
- The three prices are recorded for every episode, also those that need only how the trade
  ended; they then show in memory from their own steps.
"""

import copy
from enum import StrEnum

from jev_trader.broker import ClosedTrade, ClosingReason, Fill, Order, OrderKind
from jev_trader.sim.clock import STEPS_PER_DAY, day_of
from jev_trader.sim.records import decision_id
from jev_trader.sim.store import (
    ACTION_ENTRY,
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
)

EPISODE_KINDS = (KIND_FULL_EVALUATION, KIND_POSITION_REVIEW)


class OutcomeKind(StrEnum):
    PRICE_AFTER_1_BAR = "price_after_1_bar"
    PRICE_AFTER_4_BARS = "price_after_4_bars"
    PRICE_AT_END_OF_DAY = "price_at_end_of_day"
    ORDER_CARRIED_OUT = "order_carried_out"
    POSITION_CLOSED = "position_closed"


PRICES = (
    OutcomeKind.PRICE_AFTER_1_BAR,
    OutcomeKind.PRICE_AFTER_4_BARS,
    OutcomeKind.PRICE_AT_END_OF_DAY,
)
_AFTER_BARS = {1: OutcomeKind.PRICE_AFTER_1_BAR, 4: OutcomeKind.PRICE_AFTER_4_BARS}


def searchable(decision: dict, step: int) -> bool:
    """Whether episode search may return the decision at `step`: an episode whose outcomes are
    all known by then."""
    known_from = decision.get("OUTCOMES_KNOWN_FROM")
    return (
        decision["KIND"] in EPISODE_KINDS
        and known_from is not None
        and known_from <= step
    )


def is_last_bar_of_day(step: int, bars_left: int | None) -> bool:
    """A stock's last bar of the session (`bars_left` 0), or a crypto's bar ending at midnight."""
    if bars_left is not None:
        return bars_left == 0
    return step % STEPS_PER_DAY == 0


class Outcomes:
    """The episodes still waiting for outcomes, for one sim.

    `watch` each episode as it is decided; once a step's bars are in and its orders are carried
    out, `on_step` returns the outcome rows that step learned and the decisions it made complete.
    What is waiting is plain data (`state`), saved with the account so a resumed sim carries on.
    """

    def __init__(self, sim_id: int, state: dict | None = None):
        self.sim_id = sim_id
        self._waiting: dict[str, dict] = copy.deepcopy(state or {})

    def state(self) -> dict:
        return copy.deepcopy(self._waiting)

    def watch(self, decision: dict, price: float, last_bar_of_day: bool) -> list[dict]:
        """Start waiting for a full evaluation's or a position review's outcomes.

        `price` is the asset's close the decision was made at. Returns the outcome rows known
        at once (the end-of-day price of a decision at its day's last bar)."""
        kind = decision["KIND"]
        if kind not in EPISODE_KINDS:
            return []
        traded = kind == KIND_FULL_EVALUATION and decision["ACTION"] == ACTION_ENTRY
        if traded:
            needs = [OutcomeKind.ORDER_CARRIED_OUT, OutcomeKind.POSITION_CLOSED]
        elif kind == KIND_POSITION_REVIEW:
            needs = [*PRICES, OutcomeKind.POSITION_CLOSED]
        else:
            needs = list(PRICES)
        episode = {
            "decision": decision["ID"],
            "kind": kind,
            "asset": decision["ASSET"],
            "step": decision["STEP"],
            "price": price,
            "last_close": price,
            "bars": 0,
            "position": decision.get("POSITION"),
            "needs": [str(n) for n in needs],
            "known": {},  # outcome kind to the step it became known
        }
        self._waiting[decision["ID"]] = episode
        rows = []
        if last_bar_of_day:
            rows.append(
                self._learned(
                    episode,
                    OutcomeKind.PRICE_AT_END_OF_DAY,
                    decision["STEP"],
                    self._price(episode, price),
                )
            )
        return rows

    def on_step(
        self,
        step: int,
        closes: dict[str, float],
        last_bars_of_day: set[str],
        fills: list[Fill],
        cancelled: list[Order],
        closed: list[ClosedTrade],
    ) -> tuple[list[dict], dict[str, int]]:
        """What `step` taught: `closes` by asset with a bar now, the assets whose bar now is their
        day's last, and the orders carried out, cancelled and positions closed at this step.

        Returns the outcome rows learned, and each decision made complete with its step."""
        rows: list[dict] = []
        for episode in list(self._waiting.values()):
            if episode["step"] >= step:
                continue
            asset = episode["asset"]
            if asset in closes:
                rows += self._bar(
                    episode, step, closes[asset], asset in last_bars_of_day
                )
        for fill in fills:
            rows += self._fill(fill)
        for order in cancelled:
            rows += self._cancelled(order, step)
        for trade in closed:
            rows += self._closed(trade, fills)
        return rows, self._completed()

    # What each event teaches

    def _bar(self, episode: dict, step: int, close: float, last_of_day: bool):
        rows = []
        end_of_day = str(OutcomeKind.PRICE_AT_END_OF_DAY)
        if end_of_day not in episode["known"] and day_of(step) > day_of(
            episode["step"]
        ):
            # The day's last bar was missing: its end is the last close seen that day.
            rows.append(
                self._learned(
                    episode,
                    OutcomeKind.PRICE_AT_END_OF_DAY,
                    step,
                    self._price(episode, episode["last_close"]),
                )
            )
        episode["bars"] += 1
        if day_of(step) == day_of(episode["step"]):
            episode["last_close"] = close
        after = _AFTER_BARS.get(episode["bars"])
        if after is not None:
            rows.append(
                self._learned(episode, after, step, self._price(episode, close))
            )
        if (
            last_of_day
            and day_of(step) == day_of(episode["step"])
            and end_of_day not in episode["known"]
        ):
            rows.append(
                self._learned(
                    episode,
                    OutcomeKind.PRICE_AT_END_OF_DAY,
                    step,
                    self._price(episode, close),
                )
            )
        return rows

    def _fill(self, fill: Fill) -> list[dict]:
        if fill.kind is not OrderKind.ENTRY or fill.reason is not ClosingReason.JEV:
            return []
        episode = self._waiting.get(
            decision_id(self.sim_id, fill.step_decided, fill.asset)
        )
        if episode is None or OutcomeKind.ORDER_CARRIED_OUT not in episode["needs"]:
            return []
        episode["position"] = fill.position_id
        return [
            self._learned(
                episode,
                OutcomeKind.ORDER_CARRIED_OUT,
                fill.step_carried_out,
                {
                    "carried_out": True,
                    "price": fill.price,
                    "value": fill.value,
                },
            )
        ]

    def _cancelled(self, order: Order, step: int) -> list[dict]:
        if order.kind is not OrderKind.ENTRY or order.reason is not ClosingReason.JEV:
            return []
        episode = self._waiting.get(
            decision_id(self.sim_id, order.step_decided, order.asset)
        )
        if episode is None or OutcomeKind.ORDER_CARRIED_OUT not in episode["needs"]:
            return []
        # Never carried out: the decision is now judged by where the price went, like no trade.
        episode["needs"] = [str(OutcomeKind.ORDER_CARRIED_OUT), *map(str, PRICES)]
        return [
            self._learned(
                episode, OutcomeKind.ORDER_CARRIED_OUT, step, {"carried_out": False}
            )
        ]

    def _closed(self, trade: ClosedTrade, fills: list[Fill]) -> list[dict]:
        last = next(
            (
                f
                for f in reversed(fills)
                if f.position_id == trade.position_id
                and f.step_carried_out == trade.step_closed
            ),
            None,
        )
        rows = []
        for episode in self._waiting.values():
            if episode["position"] != trade.position_id:
                continue
            value = {
                "closing_reason": str(trade.closing_reason),
                "step_closed": trade.step_closed,
                "bars_after": episode["bars"],
                "profit": trade.profit,
                "trading_costs": trade.trading_costs,
            }
            if episode["kind"] == KIND_POSITION_REVIEW:
                value["closed_at_this_review"] = (
                    last is not None
                    and last.reason is ClosingReason.JEV
                    and last.step_decided == episode["step"]
                )
            rows.append(
                self._learned(
                    episode, OutcomeKind.POSITION_CLOSED, trade.step_closed, value
                )
            )
        return rows

    # Bookkeeping

    def _price(self, episode: dict, close: float) -> dict:
        return {"price": close, "change": close / episode["price"] - 1}

    def _learned(
        self, episode: dict, kind: OutcomeKind, step: int, value: dict
    ) -> dict:
        episode["known"][str(kind)] = step
        return {
            "ID": f"{episode['decision']}-{kind}",
            "SIM": self.sim_id,
            "FIRST_WRITTEN_BY": self.sim_id,
            "DECISION": episode["decision"],
            "KIND": str(kind),
            "VALUE": value,
            "KNOWN_FROM": step,
        }

    def _completed(self) -> dict[str, int]:
        """Each decision whose needed outcomes are all in, with the latest of their steps. A
        decision stops being watched once every outcome it can have is in."""
        completed = {}
        for key, episode in list(self._waiting.items()):
            known = episode["known"]
            if episode.get("complete") is None and all(
                n in known for n in episode["needs"]
            ):
                episode["complete"] = max(known[n] for n in episode["needs"])
                completed[key] = episode["complete"]
            possible = {*map(str, PRICES), *episode["needs"]}
            if episode.get("complete") is not None and possible <= known.keys():
                del self._waiting[key]
        return completed
