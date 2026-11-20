"""The shared clock: 96 steps a day in UTC, a step's day by arithmetic (ADR 0002)."""

from jev_trader.sim.clock import day_of, midnights_between


def test_steps_1_to_96_are_day_1_and_step_97_opens_day_2():
    assert day_of(1) == 1
    assert day_of(96) == 1
    assert day_of(97) == 2


def test_no_midnight_inside_one_day():
    assert midnights_between(1, 96) == []


def test_the_midnight_ending_day_1_is_step_96():
    # From the day's last crypto bar (step 96) to the first bar after midnight (step 97).
    assert midnights_between(96, 97) == [96]


def test_a_weekend_skipped_by_a_stocks_only_sim_counts_every_midnight():
    # Friday's last stock bar ends at step 80 of day 5; Monday's first at step 55 of day 8.
    friday, monday = 4 * 96 + 80, 7 * 96 + 55
    assert midnights_between(friday, monday) == [5 * 96, 6 * 96, 7 * 96]
