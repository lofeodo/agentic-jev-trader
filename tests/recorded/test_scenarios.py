"""The recorded-answer scenarios (spec appendix 10, section 7): each runs one asset at one step
through the agent's whole decision path and compares the memory lookups, the orders placed and
the records stored with its saved expected result, in `__snapshots__/test_scenarios.ambr`.

Rewrite the expected results after a deliberate change, then read the difference:

    python -m pytest tests/recorded --snapshot-update

The frame is in `scenarios.py`. Only one trivial scenario is here so far, which asks no model:
the real scenarios come with the slice's units.
"""

import pytest

from jev_trader.broker import Bar
from jev_trader.sim.market import Snapshot
from tests.recorded.scenarios import MadeUpInputs, Scenario, run_scenario

SCENARIOS = [
    # A crypto asset whose dataset has no typical move at the step: no candidate trade can be
    # built, so code skips it (tier 0) and asks neither Jev nor the LLM.
    Scenario(
        name="no_typical_move",
        path="no position: code asks nothing",
        inputs=MadeUpInputs(
            bars=(Bar(step=200, open=100.0, high=101.0, low=99.0, close=100.5),),
            snapshot=Snapshot(
                situation_text="Made-up situation.",
                typical_move=None,
                bars_left=None,
                patterns=(),
            ),
        ),
    ),
]


@pytest.mark.vcr
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario(scenario, snapshot):
    assert run_scenario(scenario).compared() == snapshot
