"""One call to Jev through the real SDK, with hand-written fake answers (spec appendix 10, section 7)."""

import json

import httpx2
import pytest

from jev_trader.jev.client import JevClient, JevFailed, load_jev_settings
from jev_trader.jev.reading import JevRequest

REQUEST = JevRequest(
    background="A made-up background.",
    questions={"screen": {"type": "noul", "instructions": "Worth a look?"}},
)
GOOD_BODY = {
    "model": "jev-1.14.0",
    "answers": {"screen": {"type": "noul", "noul": 0.62}},
    "usage": {"input_tokens": 1_000_000, "output_tokens": 20},
}


def good(_request=None):
    return httpx2.Response(200, json=GOOD_BODY)


def failing(status):
    return httpx2.Response(status, json={"error": "made-up failure"})


def client_answering(answers):
    """A client whose calls get `answers` in turn; `sent` lists the requests it received."""
    sent = []
    remaining = iter(answers)

    def handler(request):
        sent.append(request)
        return next(remaining)

    client = JevClient(
        load_jev_settings(),
        api_key="stand-in-key",
        transport=httpx2.MockTransport(handler),
        backoff_seconds=0,
    )
    return client, sent


def test_an_answer_comes_back_with_its_figures():
    client, sent = client_answering([good()])

    reply = client.ask(REQUEST)

    assert reply.noul("screen") == 0.62
    assert reply.model == "jev-1.14.0"
    assert (reply.tokens_in, reply.tokens_out) == (1_000_000, 20)
    # A million tokens read at $0.042 per million; what Jev writes back is free.
    assert reply.cost_usd == pytest.approx(0.042)
    assert reply.retries == 0
    assert reply.latency_seconds >= 0
    assert json.loads(reply.body) == GOOD_BODY
    body = json.loads(sent[0].content)
    assert body["state"] == "A made-up background."
    assert body["model"] == "jev-latest"


def test_a_call_that_succeeds_on_its_last_retry_counts_three_retries():
    client, sent = client_answering([failing(429), failing(503), failing(429), good()])

    assert client.ask(REQUEST).retries == 3
    assert len(sent) == 4


def test_a_call_still_failing_after_three_retries_fails_with_a_clear_reason():
    client, sent = client_answering([failing(429)] * 4)

    with pytest.raises(JevFailed, match="after 3 retries.*429"):
        client.ask(REQUEST)
    assert len(sent) == 4


def test_a_refused_request_is_not_retried():
    client, sent = client_answering([failing(400)])

    with pytest.raises(JevFailed, match="after 0 retries.*400"):
        client.ask(REQUEST)
    assert len(sent) == 1


def test_a_background_above_the_cap_is_never_sent():
    client, sent = client_answering([good()])
    too_long = JevRequest("x" * 48_001, REQUEST.questions)  # about 20,000 tokens

    with pytest.raises(JevFailed, match="20,000"):
        client.ask(too_long)
    assert sent == []


def test_the_key_never_appears_in_a_failure():
    client, _ = client_answering([failing(400)])

    with pytest.raises(JevFailed) as failed:
        client.ask(REQUEST)
    assert "stand-in-key" not in str(failed.value)
