"""The recorded-answer scenarios (spec appendix 10, section 7): each runs one asset at one step
through the agent's whole decision path and compares the memory lookups, the orders placed and
the records stored with its saved expected result, in `__snapshots__/test_scenarios.ambr`.

Rewrite the expected results after a deliberate change, then read the difference:

    conda run -n agentic-jev-trader python -m pytest tests/recorded --block-network --snapshot-update

The frame is in `scenarios.py`, the made-up data in `made_up.py`, and the paths each scenario
may name in `paths.py`. The scenarios for an asset with no position are in `no_position.py`,
those with an open position and at the sim's last step in `open_position.py`.

Every scenario that asks a model has saved answers (its cassette, under `cassettes/`), and
every scenario has a saved expected result. A new scenario fails until its answers are recorded
and its expected result written: nothing is skipped. One that asks no model anything, such as a
trade blocked by the daily loss limit, needs no saved answers: its expected result alone lets it
run.
"""

import pytest

from jev_trader.broker import ClosingReason
from jev_trader.memory.outcomes import OutcomeKind, searchable
from jev_trader.sim.clock import STEPS_PER_DAY
from jev_trader.sim.records import decision_id
from jev_trader.sim.store import KIND_POSITION_REVIEW
from tests.recorded import no_position, open_position
from tests.recorded.made_up import ASSET, SIM, made_up_series
from tests.recorded.scenarios import (
    HOLDING_ASSETS,
    Scenario,
    run_scenario,
    starting_account,
)

SCENARIOS: list[Scenario] = [*no_position.SCENARIOS, *open_position.SCENARIOS]


@pytest.mark.vcr
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario(scenario, snapshot):
    assert run_scenario(scenario).compared() == snapshot


# The hold scenario's step is two bars before midnight. Six bars after it: the price after 1
# bar, the day's end after 2, the price after 4, and the sim's end after 6 closes the trade.
HOLD = open_position.HOLD
HOLD_CASSETTE = f"test_scenario[{HOLD.name}].yaml"
BARS_AFTER = 6


@pytest.mark.vcr
@pytest.mark.default_cassette(HOLD_CASSETTE)
def test_a_position_reviews_outcomes():
    """Where the price went after 1 bar, 4 bars and by the end of the day, and how the trade
    ended; the review is searchable only once all of them are known. It replays the hold
    scenario's saved answers, then lets the bars pass with no model asked."""
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
    prices = HOLD.inputs.prices
    series = made_up_series(ASSET, HOLD.inputs.asset_class, step, prices, BARS_AFTER)
    closes = {s: series.bar(s).close for s in series.steps if s >= step}
    for kind, after in (
        (OutcomeKind.PRICE_AFTER_1_BAR, step + 1),
        (OutcomeKind.PRICE_AT_END_OF_DAY, end_of_day),
        (OutcomeKind.PRICE_AFTER_4_BARS, step + 4),
    ):
        assert learned[kind]["KNOWN_FROM"] == after
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
    # Searchable from the step its last outcome, how the trade ended, became known; never before.
    assert result.outcomes_known[review_id] == last_step
    known = {**review, "OUTCOMES_KNOWN_FROM": last_step}
    assert not searchable(known, last_step - 1)
    assert searchable(known, last_step)


# What each scenario's account holds as its step begins needs no model, so it is checked here
# while the answers are not saved yet.


@pytest.mark.parametrize(
    "scenario",
    [s for s in open_position.SCENARIOS if s.inputs.position is not None],
    ids=lambda s: s.name,
)
def test_the_position_is_open_as_the_step_begins(scenario):
    account = starting_account(scenario)

    assert account.positions[ASSET].direction is scenario.inputs.position.direction
    assert account.risk is not None


def test_the_holding_sim_holds_its_five_assets():
    account = starting_account(_named("holding_sim_sells_five"))

    assert sorted(account.positions) == list(HOLDING_ASSETS)


def test_the_stop_price_is_reached_at_the_step():
    scenario = _named("closed_at_stop_price")
    account = starting_account(scenario)

    account.on_bar(ASSET, _bar_at_step(scenario))

    assert ASSET not in account.positions
    assert account.closed_trades[-1].closing_reason == ClosingReason.STOP_PRICE


def test_the_forced_close_comes_due_at_the_step():
    scenario = _named("forced_close")
    account = starting_account(scenario)

    account.on_bar(ASSET, _bar_at_step(scenario))

    assert ASSET in account.positions  # its stop price is not reached
    assert account.check_account(scenario.inputs.step) != []


def _named(name: str) -> Scenario:
    (scenario,) = [s for s in SCENARIOS if s.name == name]
    return scenario


def _bar_at_step(scenario: Scenario):
    inputs = scenario.inputs
    series = made_up_series(ASSET, inputs.asset_class, inputs.step, inputs.prices)
    return series.bar(inputs.step)
