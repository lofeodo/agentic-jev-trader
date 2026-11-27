"""Rules shared by the test folders (spec appendix 10, section 6).

- `unit` and `recorded`: free tests, with the network blocked. A test that tries to reach the
  network fails, so no test can call a paid service by mistake.
- `snowflake`: skipped unless the Snowflake login is set, in the environment or in `.env`.
- `paid`: skipped unless `--run-paid` is given, by hand, with the developer's go-ahead.
- `postgres`: the database tests, against the local Postgres in Docker (never RDS): free.
- `model`: runs the text-to-numbers model on this computer, downloading it once (free, about
  2 GB). Skipped unless `--run-model` is given.
- LangSmith tracing is off in every test.
- `dormant`: a slice's tests, written before the code they test (`/implement`'s tests ticket).
  They are skipped, in CI too, unless `--run-dormant` is given; the slice's closing ticket
  switches them on by removing the marker.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

# Set before any test imports LangChain or LangSmith. The client reads the older `_V2` names
# first, and both the LANGSMITH_ and LANGCHAIN_ prefixes, so all four are switched off.
for _switch in [
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
]:
    os.environ[_switch] = "false"

TESTS_DIR = Path(__file__).parent
ENV_FILE = TESTS_DIR.parent / ".env"
FREE_FOLDERS = [TESTS_DIR / "unit", TESTS_DIR / "recorded"]
SNOWFLAKE_FOLDER = TESTS_DIR / "snowflake"
PAID_FOLDER = TESTS_DIR / "paid"
SNOWFLAKE_LOGIN = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PRIVATE_KEY_FILE",
    "SNOWFLAKE_PRIVATE_KEY_FILE_PWD",
]


def pytest_addoption(parser):
    parser.addoption(
        "--run-paid",
        action="store_true",
        help="Run the tests in tests/paid, which call paid services. Only with the go-ahead.",
    )
    parser.addoption(
        "--run-dormant",
        action="store_true",
        help="Run the dormant tests: a slice's tests, failing until its code is built.",
    )
    parser.addoption(
        "--run-model",
        action="store_true",
        help="Run the tests marked model: they download the text-to-numbers model once.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "dormant: a slice's test, skipped until its closing ticket removes the marker",
    )
    config.addinivalue_line(
        "markers",
        "model: runs the text-to-numbers model on this computer; needs --run-model",
    )


def _missing_snowflake_login():
    from_file = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    return [
        name
        for name in SNOWFLAKE_LOGIN
        if not (os.environ.get(name) or from_file.get(name))
    ]


def pytest_collection_modifyitems(config, items):
    missing_login = _missing_snowflake_login()
    for item in items:
        path = Path(item.path)
        if item.get_closest_marker("dormant") and not config.getoption("--run-dormant"):
            item.add_marker(
                pytest.mark.skip(reason="dormant until its slice's closing ticket")
            )
        if item.get_closest_marker("model") and not config.getoption("--run-model"):
            item.add_marker(
                pytest.mark.skip(
                    reason="downloads the text-to-numbers model: add --run-model"
                )
            )
        if any(path.is_relative_to(folder) for folder in FREE_FOLDERS):
            # pytest-recording's own marker: blocks the network whatever the command line says.
            item.add_marker(pytest.mark.block_network)
        elif path.is_relative_to(SNOWFLAKE_FOLDER) and missing_login:
            reason = "Snowflake login not set: " + ", ".join(missing_login)
            item.add_marker(pytest.mark.skip(reason=reason))
        elif path.is_relative_to(PAID_FOLDER) and not config.getoption("--run-paid"):
            item.add_marker(
                pytest.mark.skip(reason="calls a paid service: add --run-paid")
            )
