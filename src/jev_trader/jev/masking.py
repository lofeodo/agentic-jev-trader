"""The masking scan: what must never reach a model (spec appendix 1, section 2).

Models know assets by masked IDs (`ASSET_03`), prices rescaled to start at 100, and time as bar
counts. The tests run this scan over everything sent to a model, and it reports:

- a real ticker or name, from the settings files in `datasets/`;
- a calendar date or a clock time;
- a random ID;
- an unscaled price: a figure equal, at the decimals it shows, to a real price the test gives it
  ($187, 187.4 and 187.44 all match a real $187.44). A bare whole number under 100 is a count.

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
# Words of a company's name that say nothing about which company it is.
_COMMON_NAME_WORDS = {"&", "co.", "corporation", "etf", "inc.", "trust"}
# Any number, with its dollar sign if it has one.
_NUMBER = re.compile(r"(?<![\d.,\w])(\$?)(\d[\d,]*)(?:\.(\d+))?")
# A bare whole number below this is a count (bar 3 of 26), not a price.
_SMALLEST_BARE_PRICE = 100


class MaskingLeak(AssertionError):
    """Something a model must not see was in its text."""


@dataclass(frozen=True)
class RealValues:
    tickers: frozenset[str]  # matched with their exact capitals: "SPY", not "spy"
    names: frozenset[str]  # matched in any capitals
    prices: frozenset[float]  # compared at as many decimals as the text shows


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
                names.add(asset["name"])
                names.update(
                    word
                    for word in asset["name"].split()
                    if word.lower() not in _COMMON_NAME_WORDS and not word.isdigit()
                )
    return RealValues(frozenset(tickers), frozenset(names), frozenset(prices))


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
    for match in _NUMBER.finditer(text):
        sign, whole, decimals = match.groups()
        figure = float(f"{whole.replace(',', '')}.{decimals or 0}")
        if not (sign or decimals or figure >= _SMALLEST_BARE_PRICE):
            continue
        places = len(decimals or "")
        if any(round(price, places) == figure for price in real.prices):
            leaks.append(f"unscaled price: {match.group()}")
    return leaks


def assert_masked(text: str, real: RealValues) -> None:
    """Raise `MaskingLeak`, naming what leaked, if `text` holds anything a model must not see."""
    leaks = find_leaks(text, real)
    if leaks:
        raise MaskingLeak("; ".join(leaks))
