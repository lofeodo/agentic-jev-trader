"""The masking scan (spec appendix 1, section 2), run over everything the recorded-answer tests
send to the LLM, to Jev and to LangSmith. The scan itself is in `masking.py`.

- The saved requests under `cassettes/` are what the recorded-answer tests send: a saved answer
  is handed back only when the whole request matches.
- The tests answered by hand (`test_harness.py`, `test_service_failures.py`) send what a
  scenario with memory sends to Jev and the LLM. Here that scenario runs once more, traced to a
  stand-in for LangSmith that accepts every run, so what LangSmith would be sent is scanned too.
- A real ticker, a calendar date and an unscaled price are planted in the asset's situation text,
  which Jev, the LLM and LangSmith all read, to show the scan fails on each.
"""

import httpx2
import pytest

from jev_trader.sim.tracing import Tracing
from tests.recorded import made_up
from tests.recorded.masking import findings, findings_in, langsmith_runs, saved_requests
from tests.recorded.scenarios import run_scenario
from tests.recorded.test_harness import (
    JEV_HOST,
    LLM_HOST,
    SCENARIO,
    HandWrittenAnswers,
)
from tests.unit.sim.test_tracing import StandInLangSmith, client_over

PLANTED = {
    "a real ticker": "AAPL",
    "a real name": "Exxon Mobil",
    "a calendar date": "2024-03-15",
    "a date in words": "March 15",
    "a date with slashes": "15/03/2024",
    "an unscaled price": "$43,250.17",
}


@pytest.fixture
def answers(monkeypatch):
    """The harness's hand-written answers from Jev and the LLM, keeping every request sent."""
    by_hand = HandWrittenAnswers()
    monkeypatch.setattr(
        httpx2.HTTPTransport,
        "handle_request",
        lambda transport, request: by_hand.answer(request),
    )
    return by_hand


def sent_everywhere(answers) -> dict[str, list]:
    """Run the scenario traced to a stand-in LangSmith and return what each service was sent."""
    langsmith = StandInLangSmith(200)
    # Sent one run at a time, as it happens, so each can be read back.
    client = client_over(langsmith, auto_batch_tracing=False)
    run_scenario(SCENARIO, tracing=Tracing(client))
    client.flush()
    return {
        "Jev": [body for host, body in answers.sent if host == JEV_HOST],
        "the LLM": [body for host, body in answers.sent if host == LLM_HOST],
        "LangSmith": langsmith_runs(r.body for r in langsmith.sent),
    }


def test_the_saved_requests_hold_nothing_masking_keeps_out():
    saved = saved_requests()

    assert saved  # the cassettes were found
    assert {
        where: findings_in(body) for where, body in saved if findings_in(body)
    } == {}


def test_what_a_scenario_sends_holds_nothing_masking_keeps_out(answers):
    sent = sent_everywhere(answers)

    assert all(sent.values())  # each service was sent something
    assert {name: findings_in(bodies) for name, bodies in sent.items()} == {
        "Jev": [],
        "the LLM": [],
        "LangSmith": [],
    }


@pytest.mark.parametrize("planted", PLANTED.values(), ids=PLANTED.keys())
def test_the_scan_fails_on_what_is_planted_in_a_request(answers, monkeypatch, planted):
    situation_text = made_up.situation_text
    monkeypatch.setattr(
        made_up,
        "situation_text",
        lambda *args: f"{situation_text(*args)} Planted: {planted}.",
    )

    sent = sent_everywhere(answers)

    for name, bodies in sent.items():
        found = findings_in(bodies)
        assert found, f"nothing found in what {name} was sent"
        # Each reason ends in what it found ("calendar date: March 15"): the plant, or a word of it.
        assert all(reason.split(": ", 1)[1] in planted for reason in found), found


def test_rescaled_prices_and_whole_dollar_amounts_pass():
    text = (
        "Last price: $95.82. Typical move in one bar: $0.32. Code sells if the price falls "
        "to $398.50. Account value: $10,000. It may hold up to $20,000 in positions."
    )

    assert findings(text) == []
