"""The masking scan: what must never reach a model (spec appendix 1, section 2).

Models know assets by masked IDs (`ASSET_03`), prices rescaled to start at 100, and time as bar
counts. The tests run this scan over everything sent to a model, and it reports:

- a real ticker or name, from the settings files in `datasets/`;
- a calendar date or a clock time;
- a random ID;
- an unscaled price: a figure equal, to the cent, to one of the real prices the test gives it.

The sim itself cannot run the last check: its login is not allowed to read real prices.
"""

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parents[3] / "datasets"

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATES = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    rf"|\b{_MONTH}\.?\s+\d{{1,2}}\b"
    rf"|\b\d{{1,2}}\s+{_MONTH}\b"
    r"|(?<![$\d.,])(?:19|20)\d{2}(?!\d|[.,]\d)"
)
_CLOCK_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_RANDOM_ID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    r"|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{16,}\b"
)
# A dollar figure, or any number with at least two decimals.
_PRICE = re.compile(r"\$(\d[\d,]*(?:\.\d+)?)|(?<![\d.])(\d[\d,]*\.\d{2,})")


class MaskingLeak(AssertionError):
    """Something a model must not see was in its text."""


@dataclass(frozen=True)
class RealValues:
    tickers: frozenset[str]  # matched with their exact capitals: "SPY", not "spy"
    names: frozenset[str]  # matched in any capitals
    prices: frozenset[float]  # to the cent


def real_values(
    prices: Iterable[float] = (), datasets_dir: Path = DATASETS_DIR
) -> RealValues:
    """Every real ticker and name in the dataset settings files, and the given real prices."""
    tickers, names = set(), set()
    for path in sorted(datasets_dir.glob("*.toml")):
        with open(path, "rb") as file:
            for asset in tomllib.load(file)["assets"]:
                tickers.add(asset["ticker"])
                if "provider_symbol" in asset:
                    tickers.add(asset["provider_symbol"])
                names.update((asset["name"], asset["name"].split()[0]))
    return RealValues(
        frozenset(tickers), frozenset(names), frozenset(round(p, 2) for p in prices)
    )


def _whole_word(word: str) -> str:
    return rf"(?<!\w){re.escape(word)}(?!\w)"


def find_leaks(text: str, real: RealValues) -> list[str]:
    """Each thing in `text` a model must not see, described."""
    leaks = []
    for ticker in sorted(real.tickers):
        if re.search(_whole_word(ticker), text):
            leaks.append(f"real ticker: {ticker}")
    for name in sorted(real.names):
        if re.search(_whole_word(name), text, re.IGNORECASE):
            leaks.append(f"real name: {name}")
    leaks += [f"calendar date: {m.group()}" for m in _DATES.finditer(text)]
    leaks += [f"clock time: {m.group()}" for m in _CLOCK_TIME.finditer(text)]
    leaks += [f"random ID: {m.group()}" for m in _RANDOM_ID.finditer(text)]
    for match in _PRICE.finditer(text):
        figure = (match.group(1) or match.group(2)).replace(",", "")
        if round(float(figure), 2) in real.prices:
            leaks.append(f"unscaled price: {match.group()}")
    return leaks


def assert_masked(text: str, real: RealValues) -> None:
    """Raise `MaskingLeak`, naming what leaked, if `text` holds anything a model must not see."""
    leaks = find_leaks(text, real)
    if leaks:
        raise MaskingLeak("; ".join(leaks))
