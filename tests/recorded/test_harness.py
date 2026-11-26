"""The scenario harness itself (spec appendix 10, section 7): the made-up data, memory through the
real memory server, and requests that are the same on every run.

These tests need no saved answers: Jev and the LLM are answered by hand at the HTTP layer both
clients send through (`httpx2`), so the requests are seen exactly as they would leave this
computer. Jev's screen says yes, its pick is a trade and the LLM selects the first episode it
was shown, so one scenario sends every kind of request a full evaluation with memory sends.
"""

import json

import httpx2
import pytest

from jev_trader.memory.search import RESULTS
from jev_trader.sim.records import decision_id
from tests.recorded.made_up import (
    ASSET,
    DAY,
    SIM,
    STEP,
    MadeUpPrices,
    made_up_series,
)
from tests.recorded.no_position import RISING, RISING_PATTERNS, SMALL_MEMORY
from tests.recorded.scenarios import MadeUpInputs, Scenario, run_scenario
from tests.unit.sim.test_agent_without_memory import RATING, choice_answer

JEV_HOST, LLM_HOST = "api.typesafe.ai", "api.anthropic.com"
PAST = SMALL_MEMORY
SCENARIO = Scenario(
    name="harness",
    path="the LLM answers at once",
    inputs=MadeUpInputs(
        step=STEP, prices=RISING, patterns=RISING_PATTERNS, memory=PAST
    ),
)


class HandWrittenAnswers:
    """Answers Jev and the LLM by hand and keeps every request sent: (host, body)."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.read())
        self.sent.append((request.url.host, body))
        if request.url.host == LLM_HOST:
            return httpx2.Response(200, json=self._llm())
        return httpx2.Response(200, json=self._jev(body))

    @staticmethod
    def _jev(body: dict) -> dict:
        answers = {}
        for name, question in body["questions"].items():
            # A noul is a yes/no question answered as the probability of yes: 0.9 is a yes.
            if question["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.9}
            elif question["type"] == "score":
                answers[name] = RATING
            else:
                first = min(question["criteria"])
                answers[name] = choice_answer(question["criteria"], {first: 1.0})
        return {
            "model": "jev-1.14.0",
            "answers": answers,
            "usage": {"input_tokens": 1000, "output_tokens": 20},
        }

    @staticmethod
    def _llm() -> dict:
        return {
            "id": "msg_hand_written",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_hand_written",
                    "name": "select_episodes",
                    "input": {"episode_ids": ["E1"], "note": "Made-up note."},
                }
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 20},
        }


@pytest.fixture
def answers(monkeypatch):
    by_hand = HandWrittenAnswers()
    monkeypatch.setattr(
        httpx2.HTTPTransport,
        "handle_request",
        lambda transport, request: by_hand.answer(request),
    )
    return by_hand


def test_the_same_scenario_sends_the_same_requests_twice(answers):
    run_scenario(SCENARIO)
    first, answers.sent[:] = list(answers.sent), []
    run_scenario(SCENARIO)

    assert answers.sent == first
    assert {host for host, _ in first} == {JEV_HOST, LLM_HOST}


def test_memory_is_looked_up_through_the_memory_server(answers):
    result = run_scenario(SCENARIO)

    searched = [found for found in result.memory_lookups if found[0] == "search"]
    assert searched == [("search", {})]
    # The LLM selected E1: the episode the server's search ranked first, read in full.
    (read,) = [found for found in result.memory_lookups if found[0] == "read"]
    full_evaluations = {decision_id(SIM, e.step, e.asset) for e in PAST}
    assert len(read[1]) == 1 and read[1][0] in full_evaluations
    (decision,) = result.records["MEMORY.DECISIONS"]
    assert decision["SELECTED"] == read[1]
    assert len(decision["EPISODES_SHOWN"]) == min(len(PAST), RESULTS)


def test_the_last_bars_move_as_the_scenario_says():
    prices = MadeUpPrices(seed=1, last_moves=(-0.002, 0.01), last_volume=3.0)
    series = made_up_series(ASSET, SCENARIO.inputs.asset_class, STEP, prices)

    before, last = series.bar(STEP - 1), series.bar(STEP)
    assert before.close == pytest.approx(before.open * 0.998, abs=1e-3)
    assert last.close == pytest.approx(last.open * 1.01, abs=1e-3)
    assert series.measurements(STEP)["volume_against_normal"] > 2


def test_the_same_seed_draws_the_same_bars_and_another_seed_others():
    asset_class = SCENARIO.inputs.asset_class
    once = made_up_series(ASSET, asset_class, DAY, MadeUpPrices(seed=1))
    again = made_up_series(ASSET, asset_class, DAY, MadeUpPrices(seed=1))
    other = made_up_series(ASSET, asset_class, DAY, MadeUpPrices(seed=2))

    assert once.bars == again.bars
    assert once.bars != other.bars
