"""The recorded-answer scenarios (spec appendix 10, section 7): each runs one asset at one step
through the agent's whole decision path and compares the memory lookups, the orders placed and
the records stored with its saved expected result, in `__snapshots__/test_scenarios.ambr`.

Rewrite the expected results after a deliberate change, then read the difference:

    conda run -n agentic-jev-trader python -m pytest tests/recorded --block-network --snapshot-update

The frame is in `scenarios.py`, the made-up data in `made_up.py`, and the paths each scenario
may name in `paths.py`. The scenarios come with the slice's units.
"""

import pytest

from tests.recorded.scenarios import Scenario, run_scenario

SCENARIOS: list[Scenario] = []


@pytest.mark.vcr
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario(scenario, snapshot):
    assert run_scenario(scenario).compared() == snapshot
