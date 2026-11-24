"""The full evaluation: code lists the trades, Jev picks one and sizes it (spec appendix 4, 5 and 6).

A **candidate trade** is a long or a short with a tight, medium or wide stop price: 1, 2 or 3
typical moves from the last price (the multiples are settings), never more than the distance cap
(5%). With "no trade" that makes seven options. At $100 with a typical move of $0.60 a long's
stop prices are $99.40, $98.80 and $98.20.

Jev's pick is read by direction first, then by stop price. Its size is the average of the
five sizes weighted by its probabilities: `RiskProfile.chosen_size`.

Choices the spec leaves to the build (appendix 4, "Not decided by any ticket"):

- Every copy of the pick is shuffled, the first included. The shuffles come from the sim's
  random seed, the step and the asset, joined as text into one seed.
- Probabilities that differ only past the ninth decimal count as a tie, since floating-point
  sums of Jev's two-decimal answers wobble there.
- Two stop prices the 5% cap makes equal stay two options, each named by its width.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass

from jev_trader.broker import Direction, StopPriceSettings, stop_prices

NO_TRADE = "no_trade"
# Jev leans toward the option listed first: the pick is asked this many times, each copy in its
# own shuffled order, and the copies are averaged (spec appendix 4, section 6).
SHUFFLED_COPIES = 5
WIDTHS = ("tight", "medium", "wide")


@dataclass(frozen=True)
class CandidateTrade:
    name: str  # "long_tight_stop"
    direction: Direction
    width: str  # tight, medium or wide
    stop_price: float
    stop_share: float  # the stop price's distance from the price, as a share of it

    def as_record(self) -> dict:
        return {
            "name": self.name,
            "direction": str(self.direction),
            "stop_price": self.stop_price,
            "stop_share": self.stop_share,
        }


def candidate_trades(
    price: float, typical_move: float, settings: StopPriceSettings
) -> tuple[CandidateTrade, ...]:
    """The six trades code lists for an asset at `price`: longs first, tightest first."""
    if len(settings.multiples) != len(WIDTHS):
        raise ValueError(
            f"three stop price multiples are needed, not {settings.multiples}"
        )
    trades = []
    for direction in (Direction.LONG, Direction.SHORT):
        stops = stop_prices(direction, price, typical_move, settings)
        for width, stop in zip(WIDTHS, stops, strict=True):
            trades.append(
                CandidateTrade(
                    name=f"{direction}_{width}_stop",
                    direction=direction,
                    width=width,
                    stop_price=stop,
                    stop_share=abs(price - stop) / price,
                )
            )
    return tuple(trades)


# Probabilities a few floating-point steps apart count as equal: Jev's are rounded to two
# decimals, so 0.1 + 0.2 + 0.1 and 0.4 are a tie.
TIE_DECIMALS = 9


def shuffled_orders(
    names: list[str], seed: int, step: int, asset: str, copies: int = SHUFFLED_COPIES
) -> list[list[str]]:
    """The order each copy of the pick lists its options in, every copy shuffled.

    Drawn from the sim's random seed, the step and the asset only, so a redone step and a
    recorded-answer test send the same request.
    """
    rng = random.Random(f"{seed}/{step}/{asset}")
    return [rng.sample(names, len(names)) for _ in range(copies)]


def average_copies(answers: list[Mapping[str, float]]) -> dict[str, float]:
    """Each option's probability averaged over the copies of one question, by name."""
    names = answers[0].keys()
    return {name: sum(a[name] for a in answers) / len(answers) for name in names}


def read_pick(
    probabilities: Mapping[str, float], trades: tuple[CandidateTrade, ...]
) -> str:
    """The option picked: the direction with the most probability, then its likeliest stop price.

    A tie between directions goes to no trade; a tie between stop prices to the tighter one.
    Long 0.64 (0.34 tight, 0.21 medium, 0.09 wide), no trade 0.29, short 0.07 picks the long
    with the tight stop price.
    """
    totals = {NO_TRADE: round(probabilities[NO_TRADE], TIE_DECIMALS)}
    for direction in Direction:
        totals[direction] = round(
            sum(probabilities[t.name] for t in trades if t.direction is direction),
            TIE_DECIMALS,
        )
    best = max(totals.values())
    winners = [d for d, total in totals.items() if total == best]
    if len(winners) > 1 or winners[0] == NO_TRADE:
        return NO_TRADE
    # Tightest first, and max keeps the first of equals.
    return max(
        (t for t in trades if t.direction is winners[0]),
        key=lambda t: round(probabilities[t.name], TIE_DECIMALS),
    ).name


@dataclass
class Evaluation:
    """What one full evaluation leaves on its decision record (spec appendix 4, section 13).

    `answers` holds, by question, each copy's probabilities, and the rating's score and levels.
    """

    candidates: tuple[CandidateTrade, ...]
    answers: dict
    pick: str  # an option's name, or no trade
    rating: float | None = None
    size_chosen: float | None = None  # Jev's weighted average, in dollars
    size_after_trimming: float | None = None  # what the limits left of it when placed
    limited_by: str | None = None  # the limit that trimmed it, if one did
