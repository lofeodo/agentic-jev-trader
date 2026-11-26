"""The two service-failure paths (spec appendix 10, section 8), and a sim carrying on when
LangSmith refuses a trace (section 7).

Failures cannot be recorded on demand, so these scenarios run on hand-written fake answers, given
at the HTTP layer both clients send through (`httpx2`), as in `test_harness.py`. Each runs the
harness's scenario: an asset with no position, Jev's screen saying yes, so a full evaluation with
memory follows.

- **A service failing 3 times stops the sim.** A call still failing after its 3 retries (4 tries
  in all) raises `JevFailed` or `LlmFailed`, which `run_sim` turns into a stopped sim ("Jev
  failed", "LLM failed") that can be resumed. Here Jev, then the LLM, answers every try with
  HTTP 529 ("overloaded"), a failure worth retrying.
- **A third failed reply stops the sim.** A failed reply is an answer code cannot use, such as a
  sentence instead of a tool call; it gets a fixed re-ask, and the third in one full evaluation
  raises `LlmFailed`.

The step stops where it failed, before anything of it is stored. That `run_sim` then marks the
sim stopped with its reason, and that a resumed sim redoes the step, are the sim's own unit tests
(`tests/unit/sim`). The masking scan (`masking.py`) runs over everything these tests send.
"""

import json

import httpx2
import pytest

from jev_trader.jev.client import JevFailed
from jev_trader.llm.clients import LlmFailed
from jev_trader.llm.selection import SystemWallClock
from jev_trader.sim.tracing import Tracing
from tests.recorded.masking import findings_in
from tests.recorded.scenarios import Scenario, run_scenario
from tests.recorded.test_harness import (
    JEV_HOST,
    LLM_HOST,
    SCENARIO,
    HandWrittenAnswers,
)
from tests.unit.sim.test_tracing import StandInLangSmith, client_over

TRIES = 4  # the first try and 3 retries

JEV_KEEPS_FAILING = Scenario(
    name="jev_fails_after_3_retries",
    path="a service failing 3 times stops the sim",
    inputs=SCENARIO.inputs,
)
LLM_KEEPS_FAILING = Scenario(
    name="the_llm_fails_after_3_retries",
    path="a service failing 3 times stops the sim",
    inputs=SCENARIO.inputs,
)
THREE_SENTENCES = Scenario(
    name="three_replies_without_a_tool_call",
    path="a third failed reply stops the sim",
    inputs=SCENARIO.inputs,
)
SCENARIOS = [JEV_KEEPS_FAILING, LLM_KEEPS_FAILING, THREE_SENTENCES]


class FailingAnswers(HandWrittenAnswers):
    """The harness's hand-written answers, except that the host `overloaded` names answers every
    request with HTTP 529, and the LLM answers with a sentence when `sentences` is set."""

    def __init__(self):
        super().__init__()
        self.overloaded: str | None = None
        self.sentences = False

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        host = request.url.host
        if host != self.overloaded and not (host == LLM_HOST and self.sentences):
            return super().answer(request)
        self.sent.append((host, json.loads(request.read())))
        if host == self.overloaded:
            # Retry at once: the SDKs read how long to wait from `retry-after`.
            return httpx2.Response(
                529,
                headers={"retry-after": "0"},
                json={
                    "type": "error",
                    "error": {"type": "overloaded_error", "message": "Overloaded"},
                },
            )
        sentence = {
            **self._llm(),
            "content": [{"type": "text", "text": "Episode E1 looks most like it."}],
            "stop_reason": "end_turn",
        }
        return httpx2.Response(200, json=sentence)

    def sent_to(self, host: str) -> list[dict]:
        return [body for to, body in self.sent if to == host]


@pytest.fixture
def answers(monkeypatch):
    fake = FailingAnswers()
    monkeypatch.setattr(
        httpx2.HTTPTransport,
        "handle_request",
        lambda transport, request: fake.answer(request),
    )
    # The LLM's retries wait on the selection's clock: no waiting here.
    monkeypatch.setattr(SystemWallClock, "sleep", lambda clock, seconds: None)
    return fake


def test_jev_failing_after_its_retries_stops_the_sim(answers):
    answers.overloaded = JEV_HOST

    with pytest.raises(JevFailed, match="after 3 retries.*529"):
        run_scenario(JEV_KEEPS_FAILING)

    # Jev's screen is the first call, tried 4 times; nothing follows it.
    screens = answers.sent_to(JEV_HOST)
    assert len(screens) == TRIES
    assert all(body == screens[0] for body in screens)
    assert answers.sent_to(LLM_HOST) == []
    assert findings_in(answers.sent) == []  # the masking scan


def test_the_llm_failing_after_its_retries_stops_the_sim(answers):
    answers.overloaded = LLM_HOST

    with pytest.raises(LlmFailed, match="after 3 retries.*529") as stopped:
        run_scenario(LLM_KEEPS_FAILING)

    assert len(answers.sent_to(LLM_HOST)) == TRIES
    assert stopped.value.call.retries == 3
    # Jev's screen said yes; its pick waits on the LLM's selection and is never asked.
    assert len(answers.sent_to(JEV_HOST)) == 1
    assert findings_in(answers.sent) == []  # the masking scan


def test_a_third_failed_reply_stops_the_sim(answers):
    answers.sentences = True

    with pytest.raises(LlmFailed, match="failed reply number 3 .*a sentence"):
        run_scenario(THREE_SENTENCES)

    calls = answers.sent_to(LLM_HOST)
    assert len(calls) == 3
    # The first two sentences were each asked again: the third call carries both re-asks.
    assert len(calls[2]["messages"]) == len(calls[0]["messages"]) + 4
    assert len(answers.sent_to(JEV_HOST)) == 1
    assert findings_in(answers.sent) == []  # the masking scan, re-asks included


def test_a_sim_carries_on_when_langsmith_refuses_a_trace(answers):
    # HTTP 429: LangSmith refusing past the free plan's allowance.
    refusing = StandInLangSmith(429)
    client = client_over(refusing)

    result = run_scenario(SCENARIO, tracing=Tracing(client))
    client.flush()

    assert any(r.method == "POST" for r in refusing.sent)  # it was refused, not unasked
    # The full evaluation went on to its pick and size: the trade was ordered and recorded.
    assert len(result.orders) == 1
    (decision,) = result.records["MEMORY.DECISIONS"]
    assert decision["ACTION"] == "entry"
