"""Early check 2 (spec appendix 10, section 11; ticket #86): the recorder saves one LLM call and
one Jev call and hands them back.

Both services send their requests through the HTTP package `httpx2`. These tests show that
`vcrpy`, used as it comes, hands back both saved answers with the network blocked, and refuses a
request that differs from the saved one.

The Jev call asks one `Noul` question: a yes/no question whose answer, `noul`, is the probability
of yes, from 0 to 1 (0.98 means "almost surely yes").
"""

import json

import pytest
from langchain.chat_models import init_chat_model
from typesafe_sdk import Noul, RetryPolicy, TypeSafeClient
from vcr.errors import CannotOverwriteExistingCassetteException

LLM_CASSETTE = "test_llm_call_hands_back_the_saved_answer.yaml"
LLM_MODEL = "anthropic:claude-haiku-5-5"
LLM_PROMPT = "Reply with exactly one word: ready"
JEV_MODEL = "jev-1.14.0"
JEV_STATE = "Made-up stock XYZ traded at $100.00 at 10:00 and at $102.00 at 10:15."


def ask_llm(prompt):
    model = init_chat_model(LLM_MODEL, max_tokens=20, max_retries=0)
    return model.invoke(prompt)


def saved_body(cassette):
    return json.loads(cassette.responses[0]["body"]["string"])


def error_chain(error):
    """The error's type and the types of every error that led to it."""
    types = []
    while error is not None:
        types.append(type(error))
        error = error.__cause__ or error.__context__
    return types


@pytest.mark.vcr
def test_llm_call_hands_back_the_saved_answer(vcr):
    answer = ask_llm(LLM_PROMPT)

    assert answer.text == saved_body(vcr)["content"][0]["text"]
    assert vcr.play_count == 1


@pytest.mark.vcr
def test_jev_call_hands_back_the_saved_answer(vcr):
    with TypeSafeClient(model=JEV_MODEL, retry=RetryPolicy(max_retries=0)) as client:
        response = client.system_one(
            state=JEV_STATE,
            questions={"rose": Noul(instructions="Did the price go up?")},
        )

    assert response.nouls["rose"].noul == saved_body(vcr)["answers"]["rose"]["noul"]
    assert vcr.play_count == 1


@pytest.mark.vcr
@pytest.mark.default_cassette(LLM_CASSETTE)
def test_a_changed_request_is_refused_not_answered_from_the_saved_file(vcr):
    with pytest.raises(Exception) as raised:
        ask_llm(LLM_PROMPT.replace("ready", "steady"))

    assert CannotOverwriteExistingCassetteException in error_chain(raised.value)
    assert vcr.play_count == 0
