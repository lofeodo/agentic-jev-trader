"""The shared clock a sim runs on (spec appendix 1, section 1; ADR 0002).

One clock for every asset and the account, in UTC, ticking every 15 minutes, day and night.
Step 1 ends the dataset's first 15 minutes; every day has exactly 96 steps, so steps 1 to 96 are
day 1 and step 97 opens day 2. A step's day follows from its number by arithmetic. The sim
never learns a real date: those live only in the asset key.

A step is the moment a bar ends. An asset is looked at only at steps where it has a bar.
"""

from jev_trader.dataset.bars import STEPS_PER_DAY

__all__ = ["STEPS_PER_DAY", "day_of", "midnights_between"]


def day_of(step: int) -> int:
    """The day a step belongs to: 1 for steps 1 to 96."""
    return (step - 1) // STEPS_PER_DAY + 1


def midnights_between(earlier: int, later: int) -> list[int]:
    """The midnights UTC passed after step `earlier` up to step `later`, each as the step it ends.

    Step 96 ends at the first midnight. From step 96 to step 97 one midnight is passed, [96];
    from a Friday's last stock bar to Monday's first, three: one charge for each night.
    """
    return [day * STEPS_PER_DAY for day in range(day_of(earlier), day_of(later))]
