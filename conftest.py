"""Repo-wide pytest hooks.

Tests that call a paid API carry the ``paid`` marker and are skipped unless pytest is
run with ``--run-paid``. Unit and replay tests never call paid APIs.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-paid",
        action="store_true",
        default=False,
        help="run tests marked 'paid', which call paid APIs and cost money",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-paid"):
        return
    skip_paid = pytest.mark.skip(reason="calls a paid API; run with --run-paid")
    for item in items:
        if "paid" in item.keywords:
            item.add_marker(skip_paid)
