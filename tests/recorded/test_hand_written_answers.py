"""The paths the real models would not take on demand, run on one hand-written answer each
(spec appendix 10, sections 7 and 8).

Three recording rounds tried these paths with real answers, and none came back:

- **the LLM's slips**: in about 25 real evaluations Claude Haiku never hit its 6-lookup limit,
  never replied without a tool call, never named an episode it was not shown, and always
  selected some episodes;
- **Jev's rarer reviews**: on every review of a losing position Jev closed it (sold all of it)
  or held it; it never rated reducing (selling part) or adding (buying more) more likely than
  1 in 10, and a review whose LLM selects none needs the LLM's slip above.

So each scenario here hands back a recorded scenario's real answers, in the order they were
saved, with only the answer that decides the path written by hand: the LLM's reply with no tool
call, Jev's review leaning to reduce, and so on. Everything else, the requests our code sends
included, is as in a real run. Answers the recording never saved (the re-ask's reply, Jev's
"how much" after a reduce or an add) are written by hand too. The developer chose this over
more recording rounds (ticket #172).

These are never re-recorded: `--record-mode` does not touch them, and their answers come from
the recorded scenario's saved file, so a re-record of that scenario carries them along. Each
compares its memory lookups, orders and records with its saved expected result, like a recorded
scenario, and checks that it took its path.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
import yaml

from jev_trader.llm.selection import (
    FAILED_REPLY_EVENT,
    LIMIT_HIT_EVENT,
    UNKNOWN_ID_EVENT,
)
from jev_trader.sim.store import KIND_POSITION_REVIEW
from tests.recorded import no_position, open_position
from tests.recorded.masking import findings_in
from tests.recorded.scenarios import Scenario, ScenarioResult, run_scenario
from tests.recorded.test_harness import JEV_HOST, LLM_HOST, HandWrittenAnswers
from tests.unit.sim.test_agent_without_memory import choice_answer

CASSETTES = Path(__file__).parent / "cassettes" / "test_scenarios"
SENTENCE = "Episode E1 looks most like this moment."
NEVER_SHOWN = "E99"


def _named(scenarios: list[Scenario], name: str) -> Scenario:
    (scenario,) = [s for s in scenarios if s.name == name]
    return scenario


AT_ONCE = _named(no_position.SCENARIOS, "answers_at_once_after_hammers_seen_before")
LOOKS_FURTHER = _named(no_position.SCENARIOS, "looks_further_in_a_busy_memory")
REVIEW = _named(open_position.SCENARIOS, "review_ends_in_close")


@dataclass
class SavedAnswers:
    """The answers to hand back, in order: the LLM's replies and Jev's answers, each a saved
    answer's body."""

    llm: list[dict]
    jev: list[dict]


@dataclass(frozen=True)
class HandWrittenScenario:
    """A scenario run on `recorded`'s saved answers, with `edit` writing the deciding one by
    hand."""

    scenario: Scenario
    recorded: Scenario
    edit: Callable[[SavedAnswers], None]
    took_its_path: Callable[[ScenarioResult], bool]


def _saved_answers(scenario: Scenario) -> SavedAnswers:
    saved = yaml.safe_load(
        (CASSETTES / f"test_scenario[{scenario.name}].yaml").read_text(encoding="utf-8")
    )
    answers = SavedAnswers([], [])
    for interaction in saved["interactions"]:
        body = json.loads(interaction["response"]["body"]["string"])
        host = httpx2.URL(interaction["request"]["uri"]).host
        (answers.llm if host == LLM_HOST else answers.jev).append(body)
    return answers


def _reply(like: dict, *calls: tuple[str, dict], text: str | None = None) -> dict:
    """An LLM reply shaped as `like`, holding `calls` as tool calls, or `text` alone."""
    if text is not None:
        content = [{"type": "text", "text": text}]
    else:
        content = [
            {
                "type": "tool_use",
                "id": f"toolu_hand_written_{n}",
                "name": name,
                "input": args,
            }
            for n, (name, args) in enumerate(calls, start=1)
        ]
    return {
        **like,
        "id": "msg_hand_written",
        "content": content,
        "stop_reason": "end_turn" if text is not None else "tool_use",
    }


def _selection(answers: SavedAnswers) -> dict:
    """The tool call of the last LLM reply, which selects the episodes."""
    (call,) = [c for c in answers.llm[-1]["content"] if c["type"] == "tool_use"]
    assert call["name"] == "select_episodes"
    return call["input"]


def _sentence_first(answers: SavedAnswers) -> None:
    answers.llm.insert(0, _reply(answers.llm[0], text=SENTENCE))


def _three_more_lookups(answers: SavedAnswers) -> None:
    """The recorded evaluation looked up 3 times before it selected: 3 more reach the limit."""
    more = [
        ("search_episodes", {"pattern": "hammer", "asset": "same_asset_class"}),
        ("read_track_record", {"pattern": "hammer", "direction": "long"}),
        ("search_episodes", {"pattern": "bullish engulfing"}),
    ]
    at = len(answers.llm) - 1
    answers.llm[at:at] = [_reply(answers.llm[0], call) for call in more]


def _names_one_never_shown(answers: SavedAnswers) -> None:
    _selection(answers)["episode_ids"].insert(0, NEVER_SHOWN)


def _selects_none(answers: SavedAnswers) -> None:
    _selection(answers).update(
        episode_ids=[], note="None of these past episodes is like this moment."
    )
    # With no past episode shown, Jev is not asked whether they are relevant: its saved answer
    # to that question goes too.
    for answer in answers.jev:
        answer["answers"].pop("memories_relevant", None)


def _review_leans_to(action: str) -> Callable[[SavedAnswers], None]:
    def edit(answers: SavedAnswers) -> None:
        (review,) = [a for a in answers.jev if "action_1" in a["answers"]]
        for name, answer in review["answers"].items():
            if not name.startswith("action_"):
                continue  # the review's other questions keep their real answers
            others = [option for option in answer["probabilities"] if option != action]
            review["answers"][name] = choice_answer(
                answer["probabilities"], {action: 0.7, **dict.fromkeys(others, 0.1)}
            )

    return edit


def _events(result: ScenarioResult) -> list[str]:
    return [e["KIND"] for e in result.records["SIM.SIM_EVENTS"]]


def _decision(result: ScenarioResult) -> dict:
    (decision,) = result.records["MEMORY.DECISIONS"]
    return decision


def _reviewed(action: str) -> Callable[[ScenarioResult], bool]:
    def took(result: ScenarioResult) -> bool:
        decision = _decision(result)
        return decision["KIND"] == KIND_POSITION_REVIEW and decision["PICK"] == action

    return took


def _hand_written(
    name: str,
    path: str,
    recorded: Scenario,
    edit: Callable[[SavedAnswers], None],
    took: Callable[[ScenarioResult], bool],
) -> HandWrittenScenario:
    return HandWrittenScenario(
        Scenario(name, path, recorded.inputs), recorded, edit, took
    )


HAND_WRITTEN = [
    _hand_written(
        "hand_written_lookup_limit",
        "the LLM hits its limit of 6 lookups",
        LOOKS_FURTHER,
        _three_more_lookups,
        lambda r: LIMIT_HIT_EVENT in _events(r) and _decision(r)["LIMIT_HIT"],
    ),
    _hand_written(
        "hand_written_reply_without_a_tool_call",
        "the LLM replies without a tool call and is asked again",
        AT_ONCE,
        _sentence_first,
        lambda r: (
            _events(r) == [FAILED_REPLY_EVENT] and _decision(r)["ACTION"] == "entry"
        ),
    ),
    _hand_written(
        "hand_written_episode_never_shown",
        "the LLM names an episode ID it was never shown",
        AT_ONCE,
        _names_one_never_shown,
        lambda r: (
            _events(r) == [UNKNOWN_ID_EVENT] and len(_decision(r)["SELECTED"]) == 3
        ),
    ),
    _hand_written(
        "hand_written_selects_none",
        "the LLM selects none",
        AT_ONCE,
        _selects_none,
        lambda r: _decision(r)["SELECTED"] == [],
    ),
    _hand_written(
        "hand_written_review_selects_none",
        "a review where the LLM selects none",
        REVIEW,
        _selects_none,
        lambda r: (
            _decision(r)["SELECTED"] == []
            and _decision(r)["KIND"] == KIND_POSITION_REVIEW
        ),
    ),
    _hand_written(
        "hand_written_review_ends_in_reduce",
        "a position review ending in reduce",
        REVIEW,
        _review_leans_to("reduce"),
        _reviewed("reduce"),
    ),
    _hand_written(
        "hand_written_review_ends_in_add",
        "a position review ending in add",
        REVIEW,
        _review_leans_to("add"),
        _reviewed("add"),
    ),
]
SCENARIOS = [h.scenario for h in HAND_WRITTEN]


class SavedThenByHand(HandWrittenAnswers):
    """Hands back the saved answers in order, host by host, keeping every request sent:
    (host, body). Jev's requests past the saved ones (the "how much" after a reduce or an add)
    get the harness's hand-written answer."""

    def __init__(self, saved: SavedAnswers):
        super().__init__()
        self.saved = saved

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        host = request.url.host
        waiting = self.saved.llm if host == LLM_HOST else self.saved.jev
        if not waiting and host == JEV_HOST:
            return super().answer(request)
        self.sent.append((host, json.loads(request.read())))
        return httpx2.Response(200, json=waiting.pop(0))


@pytest.mark.parametrize("hand_written", HAND_WRITTEN, ids=lambda h: h.scenario.name)
def test_hand_written_scenario(hand_written, snapshot, monkeypatch):
    saved = _saved_answers(hand_written.recorded)
    hand_written.edit(saved)
    answers = SavedThenByHand(saved)
    monkeypatch.setattr(
        httpx2.HTTPTransport,
        "handle_request",
        lambda transport, request: answers.answer(request),
    )

    result = run_scenario(hand_written.scenario)

    assert hand_written.took_its_path(result)
    assert saved.llm == []  # every LLM reply was asked for
    assert findings_in(answers.sent) == []  # the masking scan
    assert result.compared() == snapshot
