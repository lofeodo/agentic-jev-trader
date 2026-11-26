"""The timing log (spec appendix 11, sections 0 and 6): one line per step, splitting its time into
database, Jev, LLM, memory lookups and the rest."""

import re

import pytest

from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import InMemorySimStore
from jev_trader.sim.timing import StepTimer, average


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def wait(self, seconds: float) -> None:
        self.now += seconds


class Slow:
    """A service whose `call` takes `seconds`, then runs `inside` (a call it makes itself)."""

    def __init__(self, clock: FakeClock, seconds: float, inside=None):
        self.clock, self.seconds, self.inside = clock, seconds, inside
        self.name = "kept as it is"

    def call(self, value):
        self.clock.wait(self.seconds)
        if self.inside is not None:
            self.inside.call(None)
        return value


def test_each_part_gets_the_time_of_its_calls_and_the_rest_is_what_is_left():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 3.0), "database")
    jev = timer.timed(Slow(clock, 0.2), "jev")

    timer.start()
    assert database.call(1) == 1
    jev.call(None)
    clock.wait(0.1)  # the step's own work
    timing = timer.finish(412)

    assert timing.total == pytest.approx(3.3)
    assert timing.parts == pytest.approx(
        {"database": 3.0, "jev": 0.2, "llm": 0.0, "memory": 0.0, "rest": 0.1}
    )


def test_a_call_made_inside_another_counts_only_toward_the_inner_part():
    # The LLM's selection calls memory's lookups itself: that time is memory's, not the LLM's.
    clock = FakeClock()
    timer = StepTimer(clock)
    memory = timer.timed(Slow(clock, 0.5), "memory")
    llm = timer.timed(Slow(clock, 1.0, inside=memory), "llm")

    timer.start()
    llm.call(None)
    timing = timer.finish(1)

    assert timing.parts["llm"] == pytest.approx(1.0)
    assert timing.parts["memory"] == pytest.approx(0.5)
    assert sum(timing.parts.values()) == pytest.approx(timing.total)


def test_calls_between_steps_count_toward_no_step():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 2.0), "database")

    database.call(None)  # before the first step, such as reading the sim's bars
    timer.start()
    timing = timer.finish(1)

    assert timing.total == 0.0
    assert timing.parts["database"] == 0.0


def test_a_timed_service_still_hands_back_its_other_attributes():
    clock = FakeClock()
    service = StepTimer(clock).timed(Slow(clock, 1.0), "jev")
    assert service.name == "kept as it is"


def test_a_failing_call_still_counts():
    clock = FakeClock()
    timer = StepTimer(clock)

    class Failing:
        def call(self):
            clock.wait(0.4)
            raise RuntimeError("no answer")

    jev = timer.timed(Failing(), "jev")
    timer.start()
    with pytest.raises(RuntimeError):
        jev.call()
    assert timer.finish(1).parts["jev"] == pytest.approx(0.4)


def test_the_line_names_the_step_its_total_and_the_five_parts():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 3.0), "database")
    timer.start()
    database.call(None)
    clock.wait(0.4)

    line = timer.finish(412).line()

    assert line == (
        "Timing, step 412: 3.40 s = database 3.00, Jev 0.00, LLM 0.00, memory 0.00, "
        "rest 0.40"
    )


def test_the_average_is_taken_part_by_part():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 1.0), "database")
    times = []
    for step, extra in ((1, 0.0), (2, 2.0)):
        timer.start()
        database.call(None)
        clock.wait(extra)
        times.append(timer.finish(step))

    line = average(times)

    assert line == (
        "Timing, average of 2 steps: 2.00 s = database 1.00, Jev 0.00, LLM 0.00, "
        "memory 0.00, rest 1.00"
    )


def test_every_step_a_sim_runs_writes_one_timing_line_and_the_run_ends_with_the_average(
    market,
):
    store = InMemorySimStore()
    sim_id = create_sim(
        store,
        market,
        SimRequest(
            dataset=7, variant="buy_hold", kind="practice", first_step=97, last_step=288
        ),
    )
    lines = []

    run_sim(store, market, sim_id, steps_per_write=50, report=lines.append)

    timing = [line for line in lines if line.startswith("Timing, step ")]
    steps = [s["STEP"] for s in store.rows("SIM.ACCOUNT_STEPS", sim_id)]
    assert [int(re.match(r"Timing, step (\d+):", line)[1]) for line in timing] == steps
    for line in timing:
        total, *parts = (float(n) for n in re.findall(r"\d+\.\d\d", line))
        assert sum(parts) == pytest.approx(total, abs=0.03)  # each figure is rounded
    assert lines[-1].startswith(f"Timing, average of {len(steps)} steps: ")
