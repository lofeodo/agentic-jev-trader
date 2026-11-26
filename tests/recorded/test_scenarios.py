"""The recorded-answer scenarios (spec appendix 10, section 7): each runs one asset at one step
through the agent's whole decision path and compares the memory lookups, the orders placed and
the records stored with its saved expected result, in `__snapshots__/test_scenarios.ambr`.

Rewrite the expected results after a deliberate change, then read the difference:

    conda run -n agentic-jev-trader python -m pytest tests/recorded --block-network --snapshot-update

The frame is in `scenarios.py`, the made-up data in `made_up.py`, and the paths each scenario
may name in `paths.py`. The scenarios for an asset with no position are in `no_position.py`.

A scenario with neither saved answers (its cassette) nor a saved expected result is skipped,
saying so, until its answers are recorded (the slice's closing ticket). One that asks no model
anything, such as a trade blocked by the daily loss limit, needs no saved answers: its expected
result alone lets it run.
"""

from pathlib import Path

import pytest

from tests.recorded import no_position
from tests.recorded.scenarios import Scenario, run_scenario

SCENARIOS: list[Scenario] = [*no_position.SCENARIOS]
EXPECTED_RESULTS = Path(__file__).parent / "__snapshots__" / "test_scenarios.ambr"


def _has_expected_result(test_name: str) -> bool:
    return (
        EXPECTED_RESULTS.exists()
        and f"# name: {test_name}\n" in EXPECTED_RESULTS.read_text(encoding="utf-8")
    )


@pytest.fixture
def waiting_for_answers(request, record_mode, vcr_cassette_dir, default_cassette_name):
    """Skip the scenario while it has neither saved answers nor a saved expected result, unless
    answers are being recorded or expected results rewritten."""
    answers = Path(vcr_cassette_dir, f"{default_cassette_name}.yaml")
    if (
        record_mode == "none"
        and not request.config.getoption("--snapshot-update")
        and not answers.exists()
        and not _has_expected_result(request.node.name)
    ):
        pytest.skip(
            "no saved answers yet: they are recorded in the slice's closing ticket"
        )


@pytest.mark.vcr
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario(scenario, snapshot, waiting_for_answers):
    assert run_scenario(scenario).compared() == snapshot
