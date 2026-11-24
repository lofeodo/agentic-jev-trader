"""The position review: Jev decides what to do with an open position (spec appendix 4, section 7).

Four actions: hold, close, reduce (close part of it) and add (put more money in, with the same
stop price). Add is left out when nothing can be added. The action is asked as five shuffled
copies, like the pick, and the action with the highest averaged probability wins. Reduce then asks
how much: a quarter, half or three quarters, asked smallest first and largest first, and code
closes the average share weighted by Jev's probabilities (50% on a quarter and 50% on half closes
three eighths). Add asks how much more in the five sizes of a new trade.

Choices the spec leaves to the build (appendix 4, "Not decided by any ticket"):

- A tie between actions goes to hold if hold is in it, otherwise to the first of close, reduce,
  add: the action that changes least wins, as a tie between directions goes to no trade.
- The reduce share is not rounded: three eighths of 12.5 units closes 4.6875 units.
"""

from collections.abc import Mapping
from dataclasses import dataclass

HOLD, CLOSE, REDUCE, ADD = "hold", "close", "reduce", "add"
ACTIONS = (HOLD, CLOSE, REDUCE, ADD)
# A quarter, half, or three quarters of the position.
REDUCE_SHARES = (0.25, 0.5, 0.75)
_TIE = 9  # probabilities this many decimals apart are equal (see `full_evaluation`)


def reduce_option_name(share: float) -> str:
    """0.25 gives "reduce_25_percent"."""
    return f"reduce_{round(100 * share)}_percent"


def read_action(probabilities: Mapping[str, float]) -> str:
    """The action with the highest averaged probability; a tie goes to the one listed first."""
    rounded = {a: round(probabilities[a], _TIE) for a in ACTIONS if a in probabilities}
    best = max(rounded.values())
    return next(a for a in ACTIONS if rounded.get(a) == best)


@dataclass
class Review:
    """What one position review leaves on its decision record (spec appendix 4, section 13).

    `answers` holds, by question, each copy's probabilities and the recorded-only answers.
    `standing` is how the position stood when reviewed: how long open, its profit or loss so far,
    how far its stop price was.
    """

    standing: dict
    end_of_session: bool
    answers: dict
    action: str  # hold, close, reduce or add
    thesis_intact: float  # recorded only: does the reason for opening it still hold?
    reduce_share: float | None = None  # the share closed, after a reduce
    size_chosen: float | None = None  # after an add: Jev's weighted average, in dollars
    size_after_trimming: float | None = None  # what the limits left of it when placed
    limited_by: str | None = None  # the limit that trimmed it, if one did


def reduce_share(probabilities: Mapping[str, float]) -> float:
    """The share to close: the three shares averaged, each weighted by Jev's probability."""
    weights = [probabilities[reduce_option_name(s)] for s in REDUCE_SHARES]
    total = sum(weights)
    if total <= 0:
        raise ValueError("no probability was given to any share")
    return sum(w * s for w, s in zip(weights, REDUCE_SHARES, strict=True)) / total
