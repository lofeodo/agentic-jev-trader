"""Recorder settings for the recorded-answer tests (spec appendix 10, section 7).

A recorded-answer test hands our code a real LLM or Jev answer saved earlier as a file (a "cassette") under
`cassettes/`, so it costs nothing and gives the same result every time. The recorder is `vcrpy`
used as it comes, through `pytest-recording`.

Recording fresh answers costs money: only with the developer's go-ahead, on the developer's
machine, with the keys in `.env`. pytest-recording never records unless `--record-mode` is given.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

ENV_FILE = Path(__file__).parents[2] / ".env"
API_KEYS = ["ANTHROPIC_API_KEY", "TYPESAFE_API_KEY"]
# The SDKs refuse to start without a key. Handing back a saved answer never sends it, so any value works.
STAND_IN_KEY = "stand-in-key"
# The repo is public. These answer headers name the developer's Anthropic account or carry a
# session cookie; handing back a saved answer does not need them.
PRIVATE_ANSWER_HEADERS = {
    "anthropic-organization-id",
    "anthropic-workspace-id",
    "set-cookie",
}


def drop_private_answer_headers(response):
    response["headers"] = {
        name: value
        for name, value in response["headers"].items()
        if name.lower() not in PRIVATE_ANSWER_HEADERS
    }
    return response


@pytest.fixture(scope="module")
def vcr_config():
    return {
        # Keep API keys out of the saved files: Anthropic sends `x-api-key`, Jev `Authorization`.
        "filter_headers": ["authorization", "x-api-key"],
        "before_record_response": drop_private_answer_headers,
        # Save answers as readable text, not compressed bytes.
        "decode_compressed_response": True,
        # A saved answer is used only when the whole request matches, body included.
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
    }


@pytest.fixture(autouse=True)
def api_keys(request, monkeypatch):
    """Give the SDKs their keys: the real ones from `.env` when recording, a stand-in otherwise."""
    recording = request.config.getoption("--record-mode") not in (None, "none")
    from_file = dotenv_values(ENV_FILE) if recording and ENV_FILE.exists() else {}
    for name in API_KEYS:
        if not os.environ.get(name):
            monkeypatch.setenv(name, from_file.get(name) or STAND_IN_KEY)
