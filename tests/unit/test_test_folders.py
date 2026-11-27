"""The rules each test folder follows, checked by running pytest on a small made-up tree
that uses this repo's real `tests/conftest.py`."""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

REAL_CONFTEST = Path(__file__).parents[1] / "conftest.py"
SNOWFLAKE_LOGIN = {
    "SNOWFLAKE_ACCOUNT": "made-up-account",
    "SNOWFLAKE_USER": "made-up-user",
    "SNOWFLAKE_PRIVATE_KEY_FILE": "made-up-key.p8",
    "SNOWFLAKE_PRIVATE_KEY_FILE_PWD": "made-up-passphrase",
}


@pytest.fixture
def tree(pytester, monkeypatch):
    for name in [*SNOWFLAKE_LOGIN, "LANGSMITH_TRACING"]:
        monkeypatch.delenv(name, raising=False)
    tests = pytester.path / "tests"
    for folder in ["unit", "recorded", "snowflake", "paid"]:
        (tests / folder).mkdir(parents=True)
    (tests / "conftest.py").write_text(REAL_CONFTEST.read_text())
    return pytester


def write_test(pytester, folder, body):
    path = pytester.path / "tests" / folder / f"test_in_{folder}.py"
    path.write_text(body)
    return path


def test_paid_tests_are_skipped_unless_asked_for_by_hand(tree):
    write_test(tree, "paid", "def test_calls_a_paid_service():\n    pass\n")

    tree.runpytest_subprocess("tests").assert_outcomes(skipped=1)
    tree.runpytest_subprocess("tests", "--run-paid").assert_outcomes(passed=1)


def test_snowflake_tests_are_skipped_without_database_credentials(tree):
    write_test(tree, "snowflake", "def test_runs_a_query():\n    pass\n")

    tree.runpytest_subprocess("tests").assert_outcomes(skipped=1)


def test_snowflake_tests_run_when_credentials_are_in_the_environment(tree, monkeypatch):
    for name, value in SNOWFLAKE_LOGIN.items():
        monkeypatch.setenv(name, value)
    write_test(tree, "snowflake", "def test_runs_a_query():\n    pass\n")

    tree.runpytest_subprocess("tests").assert_outcomes(passed=1)


def test_snowflake_tests_run_when_credentials_are_in_the_env_file(tree):
    lines = [f"{name}={value}" for name, value in SNOWFLAKE_LOGIN.items()]
    (tree.path / ".env").write_text("\n".join(lines) + "\n")
    write_test(tree, "snowflake", "def test_runs_a_query():\n    pass\n")

    tree.runpytest_subprocess("tests").assert_outcomes(passed=1)


@pytest.mark.parametrize("folder", ["unit", "recorded"])
def test_free_tests_that_try_to_reach_the_network_fail(tree, folder):
    # 192.0.2.1 is an address reserved for documentation: nothing real answers there.
    write_test(
        tree,
        folder,
        "import socket\n\n"
        "def test_reaches_out():\n"
        "    socket.create_connection(('192.0.2.1', 443), timeout=1)\n",
    )

    result = tree.runpytest_subprocess("tests")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Network is disabled*"])


TRACING_SWITCHES = [
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
]


def test_langsmith_tracing_is_off_in_tests(tree, monkeypatch):
    # The older switch takes priority in the LangSmith client, so a machine may have it on.
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    write_test(
        tree,
        "unit",
        "import os\n\n"
        "def test_tracing_is_off():\n"
        f"    for name in {TRACING_SWITCHES!r}:\n"
        "        assert os.environ[name] == 'false'\n",
    )

    tree.runpytest_subprocess("tests").assert_outcomes(passed=1)


def test_dormant_tests_are_skipped_unless_asked_for(tree):
    write_test(
        tree,
        "unit",
        "import pytest\n\n"
        "@pytest.mark.dormant\n"
        "def test_waits_for_its_slice():\n"
        "    pass\n",
    )

    tree.runpytest_subprocess("tests").assert_outcomes(skipped=1)
    tree.runpytest_subprocess("tests", "--run-dormant").assert_outcomes(passed=1)


def test_model_tests_are_skipped_unless_asked_for(tree):
    write_test(
        tree,
        "unit",
        "import pytest\n\n@pytest.mark.model\ndef test_runs_the_model():\n    pass\n",
    )

    tree.runpytest_subprocess("tests").assert_outcomes(skipped=1)
    tree.runpytest_subprocess("tests", "--run-model").assert_outcomes(passed=1)
