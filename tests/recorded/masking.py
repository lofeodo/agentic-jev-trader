"""The masking scan (spec appendix 1, section 2): a free code check over everything the
recorded-answer tests send to the LLM, to Jev and to LangSmith.

Masking is how the models are kept from recognising real history: they know each asset only by
a masked ID (`ASSET_01`) and each moment by a step or day number, and prices are rescaled so each
series starts at $100. `findings` reads one text and names everything in it that masking should
have kept out:

- **a real ticker or name**: each asset a dataset in `datasets/` lists, by its ticker and the
  data provider's symbol (whole words, as written: `AAPL`) and by its name and each distinctive
  word of it (any case: `Apple Inc.`, `apple`);
- **a calendar date**: `2024-03-15`, `15/03/2024`, `15.03.2024`, `March 15`, `15 March`,
  `Mar 2024`. Weekdays and the time of day are accepted leaks, and a bare year is not looked
  for: step numbers such as 2024 are allowed;
- **an unscaled price**: a price is written with its cents (`$95.82`) and money amounts in whole
  dollars (`$10,000`), so a figure with cents above $400 is a price that was not rescaled. Every
  made-up series starts at $100 and stays far below four times that, while a real price level,
  such as Bitcoin's tens of thousands of dollars, does not. A real price near $100 cannot be told
  apart from a rescaled one: the made-up data holds no real prices.

`findings_in` reads anything sent, a request body or its parsed JSON, every key and text in it.
What LangSmith is sent is read run by run (`langsmith_runs`): each run's name, inputs, outputs and
metadata. LangSmith's own bookkeeping (run IDs, when a run started, the SDK's version) is not
market history and is left out.
"""

import json
import re
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import yaml

from tests.recorded.made_up import FIRST_PRICE

DATASETS = Path(__file__).parents[2] / "datasets"
CASSETTES = Path(__file__).parent / "cassettes"
HIGHEST_RESCALED_PRICE = 4 * FIRST_PRICE
# Words of a company's name that name no one in particular.
COMMON_NAME_WORDS = {
    "&",
    "co",
    "co.",
    "company",
    "corp",
    "corp.",
    "corporation",
    "etf",
    "group",
    "holdings",
    "inc",
    "inc.",
    "ltd",
    "ltd.",
    "plc",
    "the",
    "trust",
}

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
DATES = [
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),  # 2024-03-15, and a timestamp's date
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),  # 15/03/2024, 3/15/24
    # 15.03.2024: the year in full, since a version number (1.7.12) is written the same way
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
    re.compile(rf"\b{_MONTH}\s+\d{{1,4}}\b"),  # March 15, Mar 2024
    re.compile(
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?![a-z])"
    ),  # 15 March
]
PRICE_WITH_CENTS = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)\.\d+")


def _assets() -> list[dict]:
    assets = []
    for path in sorted(DATASETS.glob("*.toml")):
        with open(path, "rb") as file:
            assets += tomllib.load(file).get("assets", [])
    return assets


def _whole_word(word: str, flags: int = 0) -> re.Pattern:
    return re.compile(rf"(?<![\w&]){re.escape(word)}(?![\w&])", flags)


def _real_names() -> dict[str, re.Pattern]:
    names: dict[str, re.Pattern] = {}
    for asset in _assets():
        for symbol in (asset["ticker"], asset.get("provider_symbol")):
            if symbol:
                names[symbol] = _whole_word(symbol)
        name = asset["name"]
        names[name] = _whole_word(name, re.IGNORECASE)
        for word in name.split():
            if word.lower() not in COMMON_NAME_WORDS and re.search("[A-Za-z]", word):
                names[word] = _whole_word(word, re.IGNORECASE)
    return names


REAL_NAMES = _real_names()


def findings(text: str) -> list[str]:
    """Everything in `text` that masking should have kept out, each as a short reason."""
    found = [
        f"real ticker or name: {name}"
        for name, pattern in REAL_NAMES.items()
        if pattern.search(text)
    ]
    for pattern in DATES:
        found += [f"calendar date: {m.group()}" for m in pattern.finditer(text)]
    for m in PRICE_WITH_CENTS.finditer(text):
        if float(m.group(1).replace(",", "")) > HIGHEST_RESCALED_PRICE:
            found.append(f"unscaled price: {m.group()}")
    return found


def _texts(sent: Any) -> Iterator[str]:
    if isinstance(sent, bytes):
        sent = sent.decode("utf-8", errors="replace")
    if isinstance(sent, str):
        try:
            parsed = json.loads(sent)
        except ValueError:
            yield sent
            return
        if isinstance(parsed, dict | list):
            yield from _texts(parsed)
        else:
            yield sent
    elif isinstance(sent, dict):
        for key, value in sent.items():
            yield str(key)
            yield from _texts(value)
    elif isinstance(sent, list | tuple):
        for item in sent:
            yield from _texts(item)


def findings_in(sent: Any) -> list[str]:
    """Everything masked in what was sent: a body as text or bytes, or its parsed JSON."""
    return [reason for text in _texts(sent) for reason in findings(text)]


def langsmith_runs(bodies: Iterable[Any]) -> list[dict]:
    """What LangSmith was sent of each run, from the bodies of the requests it received, sent
    one run at a time (`auto_batch_tracing=False`)."""
    runs = []
    for body in bodies:
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        run = json.loads(body)
        runs.append(
            {
                "name": run.get("name"),
                "inputs": run.get("inputs"),
                "outputs": run.get("outputs"),
                "metadata": (run.get("extra") or {}).get("metadata"),
            }
        )
    return runs


def saved_requests() -> list[tuple[str, Any]]:
    """Every request saved under `cassettes/`, as (where it is saved, its body): by `match_on`
    the body is exactly what the recorded-answer tests send."""
    saved = []
    for path in sorted(CASSETTES.rglob("*.yaml")):
        cassette = yaml.safe_load(path.read_text(encoding="utf-8"))
        for n, interaction in enumerate(cassette["interactions"]):
            where = f"{path.relative_to(CASSETTES).as_posix()} #{n}"
            saved.append((where, interaction["request"]["body"]))
    return saved
