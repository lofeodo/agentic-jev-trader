"""Stop prices: where code closes a losing position by itself (spec appendix 1, section 3).

A stop price is fixed when the position opens and never moved. A long's sits below the price,
a short's above it.
"""

from enum import StrEnum

from jev_trader.broker.config import StopPriceSettings


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


def stop_prices(
    direction: Direction,
    price: float,
    typical_move: float,
    settings: StopPriceSettings,
) -> list[float]:
    """The tight, medium and wide stop prices for a trade at `price`.

    Each sits its multiple of the typical move away, cut to the distance cap when it would be
    further: at $100 with a typical move of $2 and a 5% cap, 3 moves ($6) is cut to $5.
    """
    cap = price * settings.distance_cap
    distances = [min(multiple * typical_move, cap) for multiple in settings.multiples]
    sign = -1 if direction is Direction.LONG else 1
    return [price + sign * distance for distance in distances]


def check_stop_price(
    direction: Direction,
    price: float,
    stop_price: float,
    settings: StopPriceSettings,
) -> None:
    """Reject a stop price on the wrong side of `price` or further away than the cap."""
    if direction is Direction.LONG and not stop_price < price:
        raise ValueError(f"a long's stop price must be below {price}: wrong side")
    if direction is Direction.SHORT and not stop_price > price:
        raise ValueError(f"a short's stop price must be above {price}: wrong side")
    # A tiny allowance so a stop price exactly at the cap is not lost to rounding.
    if abs(stop_price - price) > price * settings.distance_cap * (1 + 1e-9):
        raise ValueError(
            f"stop price {stop_price} is more than {settings.distance_cap:.0%} from {price}"
        )
