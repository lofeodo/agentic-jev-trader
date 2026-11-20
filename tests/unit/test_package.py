import importlib

import pytest

PARTS = [
    "dataset",
    "broker",
    "jev",
    "llm",
    "memory",
    "storage",
    "sim",
    "benchmark",
    "api",
]


@pytest.mark.parametrize("part", PARTS)
def test_each_part_of_the_package_can_be_imported(part):
    importlib.import_module(f"jev_trader.{part}")
