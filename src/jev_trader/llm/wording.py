"""The LLM's wording and its prompt version (spec appendix 5, section 8).

The words live in `prompts/llm_selection.toml` (the standing instructions, the first message's
layout, the answer tool, the limit and re-ask messages) and `prompts/llm_tools.toml` (the three
lookup tools). The **prompt version** is a short fingerprint worked out from both, so a changed
word gives a new version and nobody bumps a number by hand. It is stored with the sim's settings
and on every full evaluation.
"""

import hashlib
import json
import tomllib
from pathlib import Path

from jev_trader.memory import bridge

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "llm_selection.toml"
VERSION_LENGTH = 12


def load_wording(path: Path = WORDING_PATH) -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def prompt_version(wording: dict | None = None, tools: dict | None = None) -> str:
    """The fingerprint of the LLM's wording and its lookup tools' descriptions."""
    fingerprinted = json.dumps(
        {
            "wording": load_wording() if wording is None else wording,
            "tools": bridge.load_wording() if tools is None else tools,
        },
        sort_keys=True,
    )
    return hashlib.sha256(fingerprinted.encode("utf-8")).hexdigest()[:VERSION_LENGTH]
