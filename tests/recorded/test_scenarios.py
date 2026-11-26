"""The recorded-answer scenarios (spec appendix 10, section 7): each runs one asset at one step
through the agent's whole decision path and compares the memory lookups, the orders placed and
the records stored with its saved expected result, in `__snapshots__/test_scenarios.ambr`.

Rewrite the expected results after a deliberate change, then read the difference:

    conda run -n agentic-jev-trader python -m pytest tests/recorded --block-network --snapshot-update

The frame is in `scenarios.py`, the made-up data in `made_up.py`, and the paths each scenario
may name in `paths.py`. A scenario that asks a model is skipped, with its reason, until its
answers are saved (`cassettes/test_scenarios/`): the slice's closing ticket records them.
"""

from pathlib import Path

import pytest

from jev_trader.memory.outcomes import OutcomeKind, searchable
from jev_trader.sim.clock import STEPS_PER_DAY
from jev_trader.sim.records import decision_id
from jev_trader.sim.store import KIND_POSITION_REVIEW
from tests.recorded.made_up import ASSET, SIM, made_up_series
from tests.recorded.open_position_scenarios import HOLD, OPEN_POSITION_SCENARIOS
from tests.recorded.scenarios import Scenario, run_scenario

SCENARIOS: list[Scenario] = [*OPEN_POSITION_SCENARIOS]


def skip_without_saved_answers(request, cassette: Path) -> None:
    """Skip, saying why, a test whose answers are not saved yet, unless it is recording them."""
    recording = request.config.getoption("--record-mode") not in (None, "none")
    if not recording and not cassette.exists():
        pytest.skip(
            f"no saved answers yet ({cassette.name}): "
            "the slice's closing ticket records them"
        )


@pytest.mark.vcr
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario(scenario, snapshot, request, vcr_cassette_dir, default_cassette_name):
    if scenario.asks_a_model:
        cassette = Path(vcr_cassette_dir) / f"{default_cassette_name}.yaml"
        skip_without_saved_answers(request, cassette)

    assert run_scenario(scenario).compared() == snapshot


# The hold scenario's step is two bars before midnight. Six bars after it: the price after 1
# bar, the day's end after 2, the price after 4, and the sim's end after 6 closes the trade.
HOLD_CASSETTE = f"test_scenario[{HOLD.name}].yaml"
BARS_AFTER = 6


@pytest.mark.vcr
@pytest.mark.default_cassette(HOLD_CASSETTE)
def test_a_position_reviews_outcomes(request, vcr_cassette_dir):
    """Where the price went after 1 bar, 4 bars and by the end of the day, and how the trade
    ended; the review is searchable only once all of them are known. It replays the hold
    scenario's saved answers, then lets the bars pass with no model asked."""
    skip_without_saved_answers(request, Path(vcr_cassette_dir) / HOLD_CASSETTE)
    step = HOLD.inputs.step

    result = run_scenario(HOLD, bars_after=BARS_AFTER)

    review_id = decision_id(SIM, step, ASSET)
    (review,) = [d for d in result.records["MEMORY.DECISIONS"] if d["ID"] == review_id]
    assert review["KIND"] == KIND_POSITION_REVIEW
    learned = {
        row["KIND"]: row
        for row in result.records["MEMORY.OUTCOMES"]
        if row["DECISION"] == review_id
    }
    end_of_day = (step // STEPS_PER_DAY + 1) * STEPS_PER_DAY
    assert learned[OutcomeKind.PRICE_AFTER_1_BAR]["KNOWN_FROM"] == step + 1
    assert learned[OutcomeKind.PRICE_AT_END_OF_DAY]["KNOWN_FROM"] == end_of_day
    assert learned[OutcomeKind.PRICE_AFTER_4_BARS]["KNOWN_FROM"] == step + 4
    prices = HOLD.inputs.prices
    series = made_up_series(ASSET, HOLD.inputs.asset_class, step, prices, BARS_AFTER)
    closes = {s: series.bar(s).close for s in series.steps if s >= step}
    for kind, after in (
        (OutcomeKind.PRICE_AFTER_1_BAR, step + 1),
        (OutcomeKind.PRICE_AT_END_OF_DAY, end_of_day),
        (OutcomeKind.PRICE_AFTER_4_BARS, step + 4),
    ):
        assert learned[kind]["VALUE"]["price"] == closes[after]
        assert learned[kind]["VALUE"]["change"] == pytest.approx(
            closes[after] / closes[step] - 1
        )
    closed = learned[OutcomeKind.POSITION_CLOSED]
    last_step = step + BARS_AFTER
    assert closed["KNOWN_FROM"] == last_step
    assert closed["VALUE"]["closing_reason"] == "sim_ended"
    assert closed["VALUE"]["step_closed"] == last_step
    assert closed["VALUE"]["closed_at_this_review"] is False
    # Searchable from the step its last outcome became known, never before.
    known = {**review, "OUTCOMES_KNOWN_FROM": result.outcomes_known[review_id]}
    assert known["OUTCOMES_KNOWN_FROM"] == last_step
    assert not searchable(known, last_step - 1)
    assert searchable(known, last_step)
