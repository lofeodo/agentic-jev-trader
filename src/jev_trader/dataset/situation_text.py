"""The situation text: one fixed paragraph written by code from a snapshot (appendix 3, section 3).

It is written from the 58 measurements and the three candle pattern lists alone, so the same
numbers always give the same text. Every number comes with a word; a "not available" number is
left out.

Build choices where the spec leaves the detail open (appendix 3, last section):

- This bar's size, by its range in typical moves: small below 0.75, medium up to 1.5, large above.
- Where it closed, as a share of the way from its low to its high: "at its high" from 0.95,
  "near its high" from 2/3, "at its low" up to 0.05, "near its low" up to 1/3, else "mid-range".
- Trend words: "up"/"above" when the reading is zero or more, else "down"/"below". Distances
  from the day's average price and the previous day's high: "above" when zero or more.
- The previous day's low (measurement 8) is not written, as in the approved template and every
  walkthrough example; it stays in the feature vector.
- A bar that closes where it opened is "flat"; the last bars' summary counts only bars the asset
  has (fewer than 8 near its first bar).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from jev_trader.dataset.measurements import SHAPE_BARS, AssetClass, Measurements

PATTERN_WINDOW_STEPS = 4
VOLUME_LOW_BELOW = 0.9
VOLUME_HIGH_ABOVE = 1.1
SMALL_BAR_BELOW = 0.75
LARGE_BAR_ABOVE = 1.5
CLOSE_AT_END = 0.05
CLOSE_NEAR_END = 1 / 3
STOCK_FIRST_AND_LAST_HOUR_BARS = 4
CRYPTO_PART_BARS = 32
CRYPTO_PARTS = ("Asian hours", "European hours", "American hours")
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight")


@dataclass(frozen=True)
class PatternLists:
    """The candle patterns a snapshot lists, names exactly as TA-Lib's give them (ADR 0005).

    `window` holds each 15-minute pattern of the pattern window with how many steps ago it was
    recognised (0 is this bar); `hourly` and `daily` the patterns on the latest finished hourly
    and daily bars.
    """

    window: Sequence[tuple[str, int]]
    hourly: Sequence[str]
    daily: Sequence[str]


def part_of_day(asset_class: AssetClass, bar_number: int, bars_in_day: int) -> str:
    """A stock's first hour, middle or last hour; crypto's Asian, European or American hours."""
    if asset_class is AssetClass.CRYPTO:
        return CRYPTO_PARTS[(bar_number - 1) // CRYPTO_PART_BARS]
    if bar_number <= STOCK_FIRST_AND_LAST_HOUR_BARS:
        return "first hour"
    if bar_number > bars_in_day - STOCK_FIRST_AND_LAST_HOUR_BARS:
        return "last hour"
    return "middle"


def _names(names: Sequence[str]) -> str:
    return ", ".join(names) or "none"


def _age(steps: int) -> str:
    if steps == 0:
        return "this bar"
    return f"{steps} bar{'s' if steps > 1 else ''} ago"


def _number(value: float) -> str:
    return f"{abs(value):.1f}"


def _above(value: float) -> str:
    return "above" if value >= 0 else "below"


def _last_bars(m: Measurements) -> str:
    directions = [m[f"bar_{k}_direction"] for k in range(SHAPE_BARS)]
    known = [d for d in directions if d is not None]
    counts = [
        f"{NUMBER_WORDS[known.count(1)]} up",
        f"{NUMBER_WORDS[known.count(-1)]} down",
    ]
    if flat := known.count(0):
        counts.append(f"{NUMBER_WORDS[flat]} flat")

    kind = {1: "up", -1: "down", 0: "flat"}[m["bar_0_direction"]]
    span = m["bar_0_range"]
    if span is not None:
        size = (
            "small"
            if span < SMALL_BAR_BELOW
            else "large"
            if span > LARGE_BAR_ABOVE
            else "medium"
        )
        kind = f"{size} {kind}"
    this_bar = f"{'an' if kind.startswith('up') else 'a'} {kind} bar"

    lower_wick, body = m["bar_0_lower_wick"], m["bar_0_body"]
    if lower_wick is not None:
        closed_at = lower_wick + (body if m["bar_0_direction"] == 1 else 0.0)
        if closed_at >= 1 - CLOSE_AT_END:
            this_bar += " closing at its high"
        elif closed_at >= 1 - CLOSE_NEAR_END:
            this_bar += " closing near its high"
        elif closed_at <= CLOSE_AT_END:
            this_bar += " closing at its low"
        elif closed_at <= CLOSE_NEAR_END:
            this_bar += " closing near its low"
        else:
            this_bar += " closing mid-range"
    return f"Last {len(known)} bars: {', '.join(counts)}; this bar is {this_bar}."


def _price_sentence(m: Measurements) -> str | None:
    parts = []
    if (value := m["from_days_average_price"]) is not None:
        parts.append(f"{_number(value)} {_above(value)} the day's average price")
    if (value := m["below_days_high"]) is not None:
        parts.append(f"{_number(value)} below the day's high")
    if (value := m["above_days_low"]) is not None:
        parts.append(f"{_number(value)} above the day's low")
    if (value := m["from_previous_days_high"]) is not None:
        parts.append(f"{_number(value)} {_above(value)} the previous day's high")
    if not parts:
        return None
    if len(parts) > 1:
        parts[-1] = f"and {parts[-1]}"
    return f"Price is {(', ' if len(parts) > 2 else ' ').join(parts)}."


def situation_text(m: Measurements, patterns: PatternLists) -> str:
    """The paragraph about one snapshot, the same every time for the same numbers."""
    window = sorted(patterns.window, key=lambda pattern: pattern[1])
    sentences = [
        (
            f"{m.asset_class.value.capitalize()}, "
            f"{part_of_day(m.asset_class, m.bar_number, m.bars_in_day)} "
            f"(bar {m.bar_number} of {m.bars_in_day})."
        ),
        (
            f"Patterns in the last {PATTERN_WINDOW_STEPS} bars: "
            f"{_names([f'{name} ({_age(age)})' for name, age in window])}."
        ),
        f"Latest hourly bar: {_names(patterns.hourly)}.",
        f"Latest daily bar: {_names(patterns.daily)}.",
        _last_bars(m),
    ]
    if (value := m["short_term_trend"]) is not None:
        sentences.append(
            f"Short-term trend {'up' if value >= 0 else 'down'} "
            f"({_number(value)} typical moves {_above(value)} the 20-bar average)."
        )
    if (value := m["long_term_trend"]) is not None:
        sentences.append(
            f"Long-term trend {'up' if value >= 0 else 'down'} "
            f"({_number(value)} {_above(value)} the 20-day average)."
        )
    if (value := m["volume_against_normal"]) is not None:
        level = (
            "low"
            if value < VOLUME_LOW_BELOW
            else "high"
            if value > VOLUME_HIGH_ABOVE
            else "average"
        )
        sentences.append(f"Volume {level} ({value:.1f} times normal).")
    if price := _price_sentence(m):
        sentences.append(price)
    if (value := m["typical_move_share_of_price"]) is not None:
        sentences.append(f"Typical move: {value * 100:.1f}% of price.")
    return " ".join(sentences)
