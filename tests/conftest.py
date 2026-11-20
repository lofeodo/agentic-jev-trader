"""Rules shared by the four test folders (spec appendix 10, section 6).

- `unit` and `recorded`: free tests, with the network blocked. A test that tries to reach the
  network fails, so no test can call a paid service by mistake.
- `snowflake`: skipped unless the Snowflake login is set, in the environment or in `.env`.
- `paid`: skipped unless `--run-paid` is given, by hand, with the developer's go-ahead.
- LangSmith tracing is off in every test.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

# Set before any test imports LangChain or LangSmith, which read it once.
os.environ["LANGSMITH_TRACING"] = "false"

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
