"""Every package in the repo layout imports from the repo root."""

import importlib

import pytest

PACKAGES = [
    "agent",
    "agent.nodes",
    "mcp_servers",
    "mcp_servers.market_data",
    "mcp_servers.broker_sim",
    "mcp_servers.memory",
    "mcp_servers.jev_decision",
    "dataset_builder",
    "dataset_builder.providers",
    "eval",
    "eval.baselines",
    "api",
    "shared",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name) is not None
