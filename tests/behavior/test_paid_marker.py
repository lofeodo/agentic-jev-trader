"""The ``paid`` marker: skipped by default, runs with ``--run-paid``.

This test calls nothing. It only proves the switch works, so real paid tests can rely
on it.
"""

import pytest


@pytest.mark.paid
def test_paid_tests_run_only_with_flag(request: pytest.FixtureRequest) -> None:
    assert request.config.getoption("--run-paid") is True
