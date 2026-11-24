"""The Playbook screen's one read: every candle pattern with its lean and shape (spec appendix 7,
section 10).

The playbook table holds one playbook per TA-Lib version (the library whose detectors find the
patterns). The screen shows the newest one: the one the latest dataset builds use.
"""

from pydantic import BaseModel

from jev_trader.api.store import ApiStore


class Pattern(BaseModel):
    name: str  # what every reader sees: "bullish engulfing"
    detector: str  # TA-Lib's detector: "CDLENGULFING"
    lean: str  # "bullish", "bearish" or "neutral"
    shape: str  # TA-Lib's own description of the shape, in words


class Playbook(BaseModel):
    talib_version: str | None  # None while no dataset has been built
    patterns: list[Pattern]


def _version_order(version: str) -> tuple:
    """ "0.6.10" comes after "0.6.9": numbers compare as numbers."""
    return tuple(int(part) if part.isdigit() else -1 for part in version.split("."))


def playbook(store: ApiStore) -> Playbook:
    rows = store.playbook()
    if not rows:
        return Playbook(talib_version=None, patterns=[])
    newest = max({r["TALIB_VERSION"] for r in rows}, key=_version_order)
    return Playbook(
        talib_version=newest,
        patterns=sorted(
            (
                Pattern(
                    name=r["NAME"],
                    detector=r["PATTERN"],
                    lean=r["LEAN"],
                    shape=r["SHAPE"],
                )
                for r in rows
                if r["TALIB_VERSION"] == newest
            ),
            key=lambda p: p.name,
        ),
    )
