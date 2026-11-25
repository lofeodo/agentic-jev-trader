"""The LLM's wording and its prompt version (spec appendix 5, sections 5 and 8).

The words live in `prompts/llm_selection.toml` (the standing instructions, the layout of the
messages that hold episodes, the answer tool, the limit and re-ask messages) and
`prompts/llm_tools.toml` (the three lookup tools). The **prompt version** is a short fingerprint
worked out from both and from `prompts/episodes.toml` (how a past episode is written), so a
changed word gives a new version and nobody bumps a number by hand.
It is stored with the sim's settings and on every full evaluation.

`LlmWording` builds each text from plain data and returns it exactly, as the walkthrough page's
text-building functions do (`docs/llm-prompt-walkthrough.html`). Nothing it is given or writes
holds a clock time, a sim or step number, a real date or a random ID, so the same situation
gives the same request. A past episode's one line and its record in full are written by
`jev_trader.memory.render`, shared with Jev's background.
"""

import hashlib
import json
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from jev_trader.memory import bridge, render
from jev_trader.memory.lookups import MOST_READ
from jev_trader.memory.search import FULL_EVALUATION, Filters

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "llm_selection.toml"
VERSION_LENGTH = 12

ANSWER_TOOL = "select_episodes"
ANY = "any"  # a filter left unset


def load_wording(path: Path = WORDING_PATH) -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def prompt_version(
    wording: dict | None = None,
    tools: dict | None = None,
    episodes: dict | None = None,
) -> str:
    """The fingerprint of the LLM's wording, its lookup tools' descriptions, and the words a past
    episode is written in (`prompts/episodes.toml`, shared with Jev's background)."""
    fingerprinted = json.dumps(
        {
            "wording": load_wording() if wording is None else wording,
            "tools": bridge.load_wording() if tools is None else tools,
            "episodes": render.load_wording() if episodes is None else episodes,
        },
        sort_keys=True,
    )
    return hashlib.sha256(fingerprinted.encode("utf-8")).hexdigest()[:VERSION_LENGTH]


@dataclass(frozen=True)
class LlmWording:
    """The LLM's texts for a full evaluation, within the selection's limits (the same
    defaults as `jev_trader.llm.selection.SelectionLimits`). A position review's words are not
    in `prompts/` yet: they come with position reviews with memory.
    """

    most_lookups: int = 6
    most_selected: int = MOST_READ
    note_length: int = 200
    wording: dict = field(default_factory=load_wording, compare=False, repr=False)
    tools: dict = field(default_factory=bridge.load_wording, compare=False, repr=False)

    @property
    def version(self) -> str:
        return prompt_version(self.wording, self.tools)

    def _limits(self) -> dict:
        return {
            "most_lookups": self.most_lookups,
            "per_read": MOST_READ,
            "most_selected": self.most_selected,
            "note_length": self.note_length,
        }

    def system_prompt(self) -> str:
        """The standing instructions, sent first in every call."""
        return self.wording[FULL_EVALUATION]["system_prompt"].format(**self._limits())

    def answer_tool(self) -> bridge.ToolDefinition:
        """`select_episodes`, the answer: the same in both jobs, never counted, never taken
        away."""
        w = self.wording["select_episodes"]
        limits = self._limits()
        return bridge.ToolDefinition(
            ANSWER_TOOL,
            w["description"],
            {
                "type": "object",
                "properties": {
                    "episode_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": self.most_selected,
                        "description": w["episode_ids"].format(**limits),
                    },
                    "note": {
                        "type": "string",
                        "description": w["note"].format(**limits),
                    },
                },
                "required": ["episode_ids", "note"],
            },
        )

    def first_message(
        self,
        asset: str,
        asset_class: str,
        situation: str,
        summaries: Sequence[str],
        pattern_notes: str = "",
    ) -> str:
        """The first message of a full evaluation: the asset (its masked ID and "stock" or
        "crypto"), its situation text, and code's first search as one line per episode, closest
        first (`summaries`, from `jev_trader.memory.render.summary_line`). `pattern_notes` is
        `pattern_notes(...)` for the patterns named in the situation and in the lines."""
        return (
            self.wording[FULL_EVALUATION]["first_message"].format(
                asset=asset,
                asset_class=asset_class,
                situation=situation,
                **self._listing(summaries),
            )
            + pattern_notes
        )

    def search_result(
        self,
        filters: Filters,
        summaries: Sequence[str],
        pattern_notes: str = "",
    ) -> str:
        """A search the LLM asked for: the filters it set and one line per episode found,
        closest first."""
        m = self.wording["messages"]
        said = self.filters_text(filters)
        if not summaries:
            return m["no_match"].format(filters=said)
        return (
            m["search_result"].format(filters=said, **self._listing(summaries))
            + pattern_notes
        )

    def _listing(self, summaries: Sequence[str]) -> dict:
        """A list of one-line episodes: how many, the column headings, and the lines."""
        m = self.wording["messages"]
        return {
            "episodes": _count(m["episodes"], len(summaries)),
            "columns": m["summary_columns"],
            "summaries": "\n".join(summaries),
        }

    def filters_text(self, filters: Filters) -> str:
        """ "same asset, bullish engulfing, any decision": the asset, the pattern and what was
        decided, in that order."""
        words = self.wording["messages"]["filters"]
        return ", ".join(
            [
                words["any_asset" if filters.asset == ANY else filters.asset],
                words["any_pattern"] if filters.pattern == ANY else filters.pattern,
                words["any_decision" if filters.decided == ANY else filters.decided],
            ]
        )

    def pattern_notes(
        self, names: Iterable[str], playbook: Mapping[str, tuple[str, str]]
    ) -> str:
        """The notes added below a message for the candle patterns `names`, in the order first
        named, repeats dropped; nothing when `names` is empty. The caller passes only the
        patterns not yet explained in this evaluation. `playbook` gives each pattern's lean and
        shape ("bullish", "A down bar, then ...")."""
        m = self.wording["messages"]
        fresh = list(dict.fromkeys(names))
        if not fresh:
            return ""
        notes = [
            m["pattern_note"].format(
                name=name, lean=playbook[name][0], shape=playbook[name][1]
            )
            for name in fresh
        ]
        return "\n\n" + "\n".join([m["pattern_notes_heading"], *notes])

    def lookups_used_up(self) -> str:
        """A lookup asked for beyond the limit, refused."""
        return self.wording["limits"]["lookups_used_up"].format(**self._limits())

    def answer_now_at_limit(self) -> str:
        return self.wording["limits"]["answer_now_at_limit"].format(**self._limits())

    def answer_now_out_of_time(self) -> str:
        return self.wording["limits"]["answer_now_out_of_time"].format(**self._limits())

    def reask(self, lookups_left: bool) -> str:
        """A failed reply asked again: a lookup is offered only while one is left."""
        key = "reask" if lookups_left else "reask_at_limit"
        return self.wording["failed_replies"][key]

    def value_not_allowed(self, input_name: str, allowed: Sequence[str]) -> str:
        """A lookup whose input is not an allowed value, refused with the allowed values."""
        return self.wording["failed_replies"]["value_not_allowed"].format(
            input=input_name, allowed=", ".join(f'"{value}"' for value in allowed)
        )

    def answer_does_not_fit(self) -> str:
        return self.wording["failed_replies"]["answer_does_not_fit"]


def _count(forms: list[str], n: int) -> str:
    return forms[0 if n == 1 else 1].format(n=n)
