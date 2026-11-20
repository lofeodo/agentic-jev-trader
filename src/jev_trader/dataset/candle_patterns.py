"""Candle patterns from TA-Lib's 61 detectors, used unmodified (ADR 0005, spec appendix 3).

A candle pattern is a named shape of one to five bars, such as a "hammer", read as a hint of where
the price goes next. Each recognised pattern carries a lean: bullish (a hint of a rise), bearish (a
hint of a fall) or neutral (indecision). The detectors are never adjusted; the lean is our label on
the plus or minus sign TA-Lib reports.

This module recognises patterns on 15-minute, hourly and daily bars (`recognise_patterns`) and
lists the playbook: one entry per candle pattern, with its name, lean and shape (`playbook`).
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
import talib
from talib import abstract

from jev_trader.dataset.bar_sizes import BAR_LENGTH, BarSize, bar_starts, build_bars

TALIB_VERSION: str = talib.__version__

Lean = Literal["bullish", "bearish", "neutral"]

#: The 61 detectors, as TA-Lib lists them.
DETECTORS: tuple[str, ...] = tuple(talib.get_function_groups()["Pattern Recognition"])

# Six detectors describe an undecided bar, whatever sign TA-Lib gives it; gravestone doji means a
# fall although TA-Lib reports it as plus (spec appendix 3, section 1.5).
_LEAN_EXCEPTIONS: dict[str, Lean] = {
    "CDLDOJI": "neutral",
    "CDLLONGLEGGEDDOJI": "neutral",
    "CDLRICKSHAWMAN": "neutral",
    "CDLHIGHWAVE": "neutral",
    "CDLSHORTLINE": "neutral",
    "CDLSPINNINGTOP": "neutral",
    "CDLGRAVESTONEDOJI": "bearish",
}

# How many bars each detector's shape covers, read from TA-Lib's source (v0.8.3,
# src/ta_func/ta_CDL*.c). 13 read one bar, 19 two, 21 three, 4 four and 4 five.
_BARS_READ: dict[str, int] = {
    **dict.fromkeys(
        [
            "CDLBELTHOLD",
            "CDLCLOSINGMARUBOZU",
            "CDLDOJI",
            "CDLDRAGONFLYDOJI",
            "CDLGRAVESTONEDOJI",
            "CDLHIGHWAVE",
            "CDLLONGLEGGEDDOJI",
            "CDLLONGLINE",
            "CDLMARUBOZU",
            "CDLRICKSHAWMAN",
            "CDLSHORTLINE",
            "CDLSPINNINGTOP",
            "CDLTAKURI",
        ],
        1,
    ),
    **dict.fromkeys(
        [
            "CDLCOUNTERATTACK",
            "CDLDARKCLOUDCOVER",
            "CDLDOJISTAR",
            "CDLENGULFING",
            "CDLHAMMER",
            "CDLHANGINGMAN",
            "CDLHARAMI",
            "CDLHARAMICROSS",
            "CDLHOMINGPIGEON",
            "CDLINNECK",
            "CDLINVERTEDHAMMER",
            "CDLKICKING",
            "CDLKICKINGBYLENGTH",
            "CDLMATCHINGLOW",
            "CDLONNECK",
            "CDLPIERCING",
            "CDLSEPARATINGLINES",
            "CDLSHOOTINGSTAR",
            "CDLTHRUSTING",
        ],
        2,
    ),
    **dict.fromkeys(
        [
            "CDL2CROWS",
            "CDL3INSIDE",
            "CDL3OUTSIDE",
            "CDL3STARSINSOUTH",
            "CDL3WHITESOLDIERS",
            "CDLABANDONEDBABY",
            "CDLADVANCEBLOCK",
            "CDLEVENINGDOJISTAR",
            "CDLEVENINGSTAR",
            "CDLGAPSIDESIDEWHITE",
            "CDLHIKKAKE",
            "CDLIDENTICAL3CROWS",
            "CDLMORNINGDOJISTAR",
            "CDLMORNINGSTAR",
            "CDLSTALLEDPATTERN",
            "CDLSTICKSANDWICH",
            "CDLTASUKIGAP",
            "CDLTRISTAR",
            "CDLUNIQUE3RIVER",
            "CDLUPSIDEGAP2CROWS",
            "CDLXSIDEGAP3METHODS",
        ],
        3,
    ),
    **dict.fromkeys(
        ["CDL3BLACKCROWS", "CDL3LINESTRIKE", "CDLCONCEALBABYSWALL", "CDLHIKKAKEMOD"], 4
    ),
    **dict.fromkeys(
        ["CDLBREAKAWAY", "CDLLADDERBOTTOM", "CDLMATHOLD", "CDLRISEFALL3METHODS"], 5
    ),
}

# Hikkake and modified hikkake report +-200 on a later bar that confirms their shape, up to this
# many bars after it.
_CONFIRMING_DETECTORS = ("CDLHIKKAKE", "CDLHIKKAKEMOD")
_CONFIRMATION_REACH = 3

# Each candle pattern's shape in plain words, restated from the comments in TA-Lib's source
# (v0.8.3, src/ta_func/ta_CDL*.c). An up bar closes above where it opened, a down bar below; the
# body is the part between the open and the close; a wick is the part above or below the body; a
# jump is a gap between one bar and the next, where the price skips a range.
_SHAPES: dict[tuple[str, Lean], str] = {
    ("CDL2CROWS", "bearish"): (
        "A long up bar; a down bar whose body jumps above the first bar's body; then a down bar "
        "that opens inside the second bar's body and closes inside the first bar's body."
    ),
    ("CDL3BLACKCROWS", "bearish"): (
        "An up bar, then three down bars in a row, each closing lower, each with little or no "
        "lower wick, each opening inside the last bar's body; the first down bar closes below "
        "the up bar's high."
    ),
    ("CDL3INSIDE", "bullish"): (
        "A long down bar; a small bar whose body sits inside the first bar's body; then an up "
        "bar that closes above the first bar's open."
    ),
    ("CDL3INSIDE", "bearish"): (
        "A long up bar; a small bar whose body sits inside the first bar's body; then a down "
        "bar that closes below the first bar's open."
    ),
    ("CDL3LINESTRIKE", "bullish"): (
        "Three up bars, each closing higher and opening inside or near the last bar's body; "
        "then a down bar that opens above the third bar's close and closes below the first "
        "bar's open."
    ),
    ("CDL3LINESTRIKE", "bearish"): (
        "Three down bars, each closing lower and opening inside or near the last bar's body; "
        "then an up bar that opens below the third bar's close and closes above the first "
        "bar's open."
    ),
    ("CDL3OUTSIDE", "bullish"): (
        "A down bar; an up bar whose body covers the first bar's body; then a bar that closes "
        "higher than the second."
    ),
    ("CDL3OUTSIDE", "bearish"): (
        "An up bar; a down bar whose body covers the first bar's body; then a bar that closes "
        "lower than the second."
    ),
    ("CDL3STARSINSOUTH", "bullish"): (
        "A long down bar with a long lower wick; a smaller down bar that opens above the first "
        "bar's close, stays above its low and closes off its own low; then a small down bar "
        "with very short wicks that stays within the second bar's range."
    ),
    ("CDL3WHITESOLDIERS", "bullish"): (
        "Three up bars in a row, none of them short, each closing higher, each opening inside "
        "or near the last bar's body, each with little or no upper wick, and none far shorter "
        "than the one before."
    ),
    ("CDLABANDONEDBABY", "bullish"): (
        "A long down bar; a doji (a bar that closes almost where it opened) that jumps below it "
        "with no overlap at all; then an up bar that jumps above the doji with no overlap and "
        "closes well inside the first bar's body."
    ),
    ("CDLABANDONEDBABY", "bearish"): (
        "A long up bar; a doji (a bar that closes almost where it opened) that jumps above it "
        "with no overlap at all; then a down bar that jumps below the doji with no overlap and "
        "closes well inside the first bar's body."
    ),
    ("CDLADVANCEBLOCK", "bearish"): (
        "Three up bars in a row, each closing higher and opening inside or near the last "
        "bar's body; the first is long with little upper wick, and the later ones weaken, with "
        "smaller bodies or longer upper wicks."
    ),
    ("CDLBELTHOLD", "bullish"): "A long up bar with little or no lower wick.",
    ("CDLBELTHOLD", "bearish"): "A long down bar with little or no upper wick.",
    ("CDLBREAKAWAY", "bullish"): (
        "Five bars: a long down bar; a down bar that jumps lower; two more bars, each with a "
        "lower high and a lower low, the last of them down; then an up bar that closes inside "
        "the jump between the first two bars."
    ),
    ("CDLBREAKAWAY", "bearish"): (
        "Five bars: a long up bar; an up bar that jumps higher; two more bars, each with a "
        "higher high and a higher low, the last of them up; then a down bar that closes inside "
        "the jump between the first two bars."
    ),
    ("CDLCLOSINGMARUBOZU", "bullish"): "A long up bar with little or no upper wick.",
    ("CDLCLOSINGMARUBOZU", "bearish"): "A long down bar with little or no lower wick.",
    ("CDLCONCEALBABYSWALL", "bullish"): (
        "Two down bars with almost no wicks; a down bar that opens with a jump lower but whose "
        "upper wick reaches into the second bar's body; then a down bar that covers the whole "
        "third bar, wicks included."
    ),
    ("CDLCOUNTERATTACK", "bullish"): (
        "A long down bar, then a long up bar that closes at the same price."
    ),
    ("CDLCOUNTERATTACK", "bearish"): (
        "A long up bar, then a long down bar that closes at the same price."
    ),
    ("CDLDARKCLOUDCOVER", "bearish"): (
        "A long up bar, then a down bar that opens above the first bar's high and closes well "
        "into the first bar's body."
    ),
    ("CDLDOJI", "neutral"): "A bar that closes almost exactly where it opened.",
    ("CDLDOJISTAR", "bullish"): (
        "A long down bar, then a doji (a bar that closes almost where it opened) that jumps "
        "below it."
    ),
    ("CDLDOJISTAR", "bearish"): (
        "A long up bar, then a doji (a bar that closes almost where it opened) that jumps "
        "above it."
    ),
    ("CDLDRAGONFLYDOJI", "bullish"): (
        "A bar that opens and closes almost at the same price, at or near its high, with a "
        "lower wick that is not short."
    ),
    ("CDLENGULFING", "bullish"): (
        "A down bar, then an up bar whose body covers the first bar's body."
    ),
    ("CDLENGULFING", "bearish"): (
        "An up bar, then a down bar whose body covers the first bar's body."
    ),
    ("CDLEVENINGDOJISTAR", "bearish"): (
        "A long up bar; a doji (a bar that closes almost where it opened) that jumps above it; "
        "then a down bar that closes well inside the first bar's body."
    ),
    ("CDLEVENINGSTAR", "bearish"): (
        "A long up bar; a bar with a short body that jumps above it; then a down bar that "
        "closes well inside the first bar's body."
    ),
    ("CDLGAPSIDESIDEWHITE", "bullish"): (
        "A jump up between two bars' bodies; then two up bars side by side above it, of about "
        "the same size and opening at about the same price, the second not closing the jump."
    ),
    ("CDLGAPSIDESIDEWHITE", "bearish"): (
        "A jump down between two bars' bodies; then two up bars side by side below it, of "
        "about the same size and opening at about the same price, the second not closing the "
        "jump."
    ),
    ("CDLGRAVESTONEDOJI", "bearish"): (
        "A bar that opens and closes almost at the same price, at or near its low, with an "
        "upper wick that is not short."
    ),
    ("CDLHAMMER", "bullish"): (
        "A small body with a long lower wick and little or no upper wick, sitting at or below "
        "the previous bar's low."
    ),
    ("CDLHANGINGMAN", "bearish"): (
        "A small body with a long lower wick and little or no upper wick, sitting at or above "
        "the previous bar's high."
    ),
    ("CDLHARAMI", "bullish"): (
        "A long down bar, then a bar with a short body that sits inside the first bar's body."
    ),
    ("CDLHARAMI", "bearish"): (
        "A long up bar, then a bar with a short body that sits inside the first bar's body."
    ),
    ("CDLHARAMICROSS", "bullish"): (
        "A long down bar, then a doji (a bar that closes almost where it opened) inside the "
        "first bar's body."
    ),
    ("CDLHARAMICROSS", "bearish"): (
        "A long up bar, then a doji (a bar that closes almost where it opened) inside the "
        "first bar's body."
    ),
    ("CDLHIGHWAVE", "neutral"): "A short body with very long wicks above and below.",
    ("CDLHIKKAKE", "bullish"): (
        "A bar; a second bar inside its range (a lower high and a higher low); then a bar with "
        "a lower high and a lower low than the second. It is confirmed when, within the next "
        "three bars, a bar closes above the second bar's high."
    ),
    ("CDLHIKKAKE", "bearish"): (
        "A bar; a second bar inside its range (a lower high and a higher low); then a bar with "
        "a higher high and a higher low than the second. It is confirmed when, within the next "
        "three bars, a bar closes below the second bar's low."
    ),
    ("CDLHIKKAKEMOD", "bullish"): (
        "A bar; a second bar with a smaller range that closes near its low; a third bar inside "
        "the second's range; then a bar with a lower high and a lower low than the third. It "
        "is confirmed when, within the next three bars, a bar closes above the third bar's "
        "high."
    ),
    ("CDLHIKKAKEMOD", "bearish"): (
        "A bar; a second bar with a smaller range that closes near its high; a third bar "
        "inside the second's range; then a bar with a higher high and a higher low than the "
        "third. It is confirmed when, within the next three bars, a bar closes below the third "
        "bar's low."
    ),
    ("CDLHOMINGPIGEON", "bullish"): (
        "A long down bar, then a down bar with a short body inside the first bar's body."
    ),
    ("CDLIDENTICAL3CROWS", "bearish"): (
        "Three down bars in a row, each closing lower, each with little or no lower wick, each "
        "opening at or very near the last bar's close."
    ),
    ("CDLINNECK", "bearish"): (
        "A long down bar, then an up bar that opens below the first bar's low and closes just "
        "inside the first bar's body."
    ),
    ("CDLINVERTEDHAMMER", "bullish"): (
        "A small body with a long upper wick and little or no lower wick, jumping below the "
        "previous bar's body."
    ),
    ("CDLKICKING", "bullish"): (
        "A down bar with almost no wicks, then an up bar with almost no wicks that jumps above "
        "it."
    ),
    ("CDLKICKING", "bearish"): (
        "An up bar with almost no wicks, then a down bar with almost no wicks that jumps below "
        "it."
    ),
    ("CDLKICKINGBYLENGTH", "bullish"): (
        "Two bars with almost no wicks, one up and one down, with a jump between them; the "
        "longer of the two is the up bar."
    ),
    ("CDLKICKINGBYLENGTH", "bearish"): (
        "Two bars with almost no wicks, one up and one down, with a jump between them; the "
        "longer of the two is the down bar."
    ),
    ("CDLLADDERBOTTOM", "bullish"): (
        "Three down bars, each opening and closing lower; a fourth down bar with a clear upper "
        "wick; then an up bar that opens above the fourth bar's body and closes above its "
        "high."
    ),
    ("CDLLONGLEGGEDDOJI", "neutral"): (
        "A bar that closes almost where it opened, with one or two long wicks."
    ),
    ("CDLLONGLINE", "bullish"): "A long up bar with short wicks.",
    ("CDLLONGLINE", "bearish"): "A long down bar with short wicks.",
    ("CDLMARUBOZU", "bullish"): "A long up bar with little or no wick on either side.",
    (
        "CDLMARUBOZU",
        "bearish",
    ): "A long down bar with little or no wick on either side.",
    (
        "CDLMATCHINGLOW",
        "bullish",
    ): "A down bar, then a down bar that closes at the same price.",
    ("CDLMATHOLD", "bullish"): (
        "Five bars: a long up bar; a small down bar that jumps above its body; two more small "
        "bars drifting lower that stay mostly within the first bar's body; then an up bar that "
        "opens above the last small bar's close and closes above the highest of the small bars."
    ),
    ("CDLMORNINGDOJISTAR", "bullish"): (
        "A long down bar; a doji (a bar that closes almost where it opened) that jumps below "
        "it; then an up bar that closes well inside the first bar's body."
    ),
    ("CDLMORNINGSTAR", "bullish"): (
        "A long down bar; a bar with a short body that jumps below it; then an up bar that "
        "closes well inside the first bar's body."
    ),
    ("CDLONNECK", "bearish"): (
        "A long down bar, then an up bar that opens below the first bar's low and closes at "
        "that low."
    ),
    ("CDLPIERCING", "bullish"): (
        "A long down bar, then a long up bar that opens below the first bar's low and closes "
        "above the middle of the first bar's body."
    ),
    ("CDLRICKSHAWMAN", "neutral"): (
        "A bar that closes almost where it opened, near the middle of its range, with two long "
        "wicks."
    ),
    ("CDLRISEFALL3METHODS", "bullish"): (
        "Five bars: a long up bar; three small bars drifting lower within its range; then a "
        "long up bar that opens above the last small bar's close and closes above the first "
        "bar's close."
    ),
    ("CDLRISEFALL3METHODS", "bearish"): (
        "Five bars: a long down bar; three small bars drifting higher within its range; then a "
        "long down bar that opens below the last small bar's close and closes below the first "
        "bar's close."
    ),
    ("CDLSEPARATINGLINES", "bullish"): (
        "A down bar, then a long up bar that opens at the first bar's open with little or no "
        "lower wick."
    ),
    ("CDLSEPARATINGLINES", "bearish"): (
        "An up bar, then a long down bar that opens at the first bar's open with little or no "
        "upper wick."
    ),
    ("CDLSHOOTINGSTAR", "bearish"): (
        "A small body with a long upper wick and little or no lower wick, jumping above the "
        "previous bar's body."
    ),
    ("CDLSHORTLINE", "neutral"): "A bar with a short body and short wicks.",
    ("CDLSPINNINGTOP", "neutral"): "A small body with wicks longer than the body.",
    ("CDLSTALLEDPATTERN", "bearish"): (
        "Three up bars in a row, each closing higher: two long ones, the second with little "
        "upper wick, then a small one that sits at the top of the second bar's body or jumps "
        "above it."
    ),
    ("CDLSTICKSANDWICH", "bullish"): (
        "A down bar; an up bar that trades only above the first bar's close; then a down bar "
        "that closes at the same price as the first."
    ),
    ("CDLTAKURI", "bullish"): (
        "A bar that opens and closes almost at the same price, at or near its high, with a "
        "very long lower wick."
    ),
    ("CDLTASUKIGAP", "bullish"): (
        "A jump up; an up bar above the jump; then a down bar of about the same size that "
        "opens inside the up bar's body and closes below it, but still inside the jump."
    ),
    ("CDLTASUKIGAP", "bearish"): (
        "A jump down; a down bar below the jump; then an up bar of about the same size that "
        "opens inside the down bar's body and closes above it, but still inside the jump."
    ),
    ("CDLTHRUSTING", "bearish"): (
        "A long down bar, then an up bar that opens below the first bar's low and closes inside "
        "the first bar's body, below its middle."
    ),
    ("CDLTRISTAR", "bullish"): (
        "Three doji in a row (bars that close almost where they opened); the second jumps "
        "below the first, and the third sits higher than the second."
    ),
    ("CDLTRISTAR", "bearish"): (
        "Three doji in a row (bars that close almost where they opened); the second jumps "
        "above the first, and the third sits lower than the second."
    ),
    ("CDLUNIQUE3RIVER", "bullish"): (
        "A long down bar; a down bar with its body inside the first bar's body but a lower "
        "low; then a small up bar that opens no lower than the second bar's low."
    ),
    ("CDLUPSIDEGAP2CROWS", "bearish"): (
        "An up bar; a small down bar whose body jumps above it; then a down bar whose body "
        "covers the second bar's body and closes above the first bar's close."
    ),
    ("CDLXSIDEGAP3METHODS", "bullish"): (
        "Two up bars with a jump up between their bodies, then a down bar that opens inside "
        "the second bar's body and closes inside the first bar's body."
    ),
    ("CDLXSIDEGAP3METHODS", "bearish"): (
        "Two down bars with a jump down between their bodies, then an up bar that opens inside "
        "the second bar's body and closes inside the first bar's body."
    ),
}


@dataclass(frozen=True)
class PlaybookEntry:
    """One candle pattern: a detector and a lean."""

    detector: str
    lean: Lean
    name: str
    shape: str


def lean_of(detector: str, value: int) -> Lean:
    """The lean of a result TA-Lib reports: its sign, or the written exception for the detector."""
    if detector in _LEAN_EXCEPTIONS:
        return _LEAN_EXCEPTIONS[detector]
    return "bullish" if value > 0 else "bearish"


def _leans(detector: str) -> list[Lean]:
    """The leans a detector can give, from the signs TA-Lib's function listing says it returns."""
    flags = abstract.Function(detector).output_flags["integer"]
    signs = [
        s
        for s, flag in [(1, "positive"), (-1, "negative")]
        if f"Output can be {flag}" in flags
    ]
    return list(dict.fromkeys(lean_of(detector, s) for s in signs))


def pattern_name(detector: str, lean: Lean) -> str:
    """A candle pattern's name: TA-Lib's own, in lower case, without a trailing "pattern", with
    the lean in front when the detector gives both a bullish and a bearish candle pattern."""
    name = (
        abstract.Function(detector)
        .info["display_name"]
        .lower()
        .removesuffix(" pattern")
    )
    return f"{lean} {name}" if len(_leans(detector)) > 1 else name


def playbook() -> tuple[PlaybookEntry, ...]:
    """Every candle pattern of the 61 detectors, a rising and a falling version counted as two."""
    return tuple(
        PlaybookEntry(
            detector, lean, pattern_name(detector, lean), _SHAPES[detector, lean]
        )
        for detector in DETECTORS
        for lean in _leans(detector)
    )


def _bars_reached(detector: str, raw: np.ndarray, i: int) -> int:
    """How many bars, ending at bar i, the result TA-Lib reports at bar i stands on.

    A hikkake confirmation (+-200) stands on its shape and on the bars since the shape ended."""
    shape = _BARS_READ[detector]
    if detector in _CONFIRMING_DETECTORS and abs(raw[i]) == 200:
        for back in range(1, _CONFIRMATION_REACH + 1):
            if i - back >= 0 and abs(raw[i - back]) == 100:
                return shape + back
        return shape + _CONFIRMATION_REACH
    return shape


def _stretches(bars_15m: pd.DataFrame, size: BarSize) -> tuple[np.ndarray, np.ndarray]:
    """For each bar of `size`, the unbroken stretch of 15-minute bars its first and its last
    15-minute bar belong to. A stretch breaks at every missing bar and every overnight close:
    wherever two 15-minute bars in a row are not 15 minutes apart."""
    breaks = bars_15m.index.to_series().diff() != BAR_LENGTH["15m"]
    stretch = pd.Series(breaks.cumsum().to_numpy())
    grouped = stretch.groupby(bar_starts(bars_15m, size).to_numpy())
    return grouped.first().to_numpy(), grouped.last().to_numpy()


def recognise_patterns(bars_15m: pd.DataFrame, size: BarSize) -> pd.DataFrame:
    """Every candle pattern TA-Lib's 61 detectors recognise on one asset's bars of `size`.

    `bars_15m` are the asset's 15-minute bars, indexed by start time in UTC and in order; hourly
    and daily bars are built from them. Each detector runs once over the whole series, unmodified,
    so its averages carry across days. A 15-minute or hourly pattern whose bars span a missing bar
    or an overnight close is then dropped; a daily pattern runs across consecutive days with bars.

    Returns one row per recognised pattern, at the bar its shape ends on: `start` (that bar's start
    time), `detector`, `value` (TA-Lib's result: +-100, +-80 for a weaker form, +-200 for a
    confirmation), `lean` and `name`. Several names on one bar are all listed.
    """
    index = bars_15m.index
    if not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC":
        raise ValueError("bars must be indexed by start time in UTC")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError("bars must be in time order, one per start time")

    bars = build_bars(bars_15m, size)
    prices = [
        bars[column].to_numpy(dtype=float)
        for column in ("open", "high", "low", "close")
    ]
    if size != "1d":
        first_stretch, last_stretch = _stretches(bars_15m, size)
    names = {(e.detector, e.lean): e.name for e in playbook()}

    rows = []
    for detector in DETECTORS:
        raw = getattr(talib, detector)(*prices)
        for i in np.flatnonzero(raw):
            first = i - _bars_reached(detector, raw, i) + 1
            if size != "1d" and (first < 0 or first_stretch[first] != last_stretch[i]):
                continue
            value = int(raw[i])
            lean = lean_of(detector, value)
            rows.append((bars.index[i], detector, value, lean, names[detector, lean]))

    found = pd.DataFrame(rows, columns=["start", "detector", "value", "lean", "name"])
    return found.sort_values(["start", "detector"], kind="stable", ignore_index=True)
