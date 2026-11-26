"""The timing log (spec appendix 11, sections 0 and 6): one line per step, splitting its time into
database, Jev, LLM, memory lookups and the rest."""

import re

import pytest

from jev_trader.llm.selection import StandInSelector
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import InMemorySimStore
from jev_trader.sim.timing import Part, StepTimer, average_line
from tests.unit.sim.conftest import make_market
from tests.unit.sim.test_agent_with_memory_wiring import (
    PAST,
    fake_memory,
    sim_with_memory,
)
from tests.unit.sim.test_agent_without_memory import fake_jev, practice, with_snapshots


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
    database = timer.timed(Slow(clock, 3.0), Part.DATABASE)
    jev = timer.timed(Slow(clock, 0.2), Part.JEV)

    timer.start()
    assert database.call(1) == 1
    jev.call(None)
    clock.wait(0.1)  # the step's own work
    timing = timer.finish(412)

    assert timing.total == pytest.approx(3.3)
    assert timing.parts == pytest.approx(
        {
            Part.DATABASE: 3.0,
            Part.JEV: 0.2,
            Part.LLM: 0.0,
            Part.MEMORY: 0.0,
            Part.REST: 0.1,
        }
    )


def test_a_call_made_inside_another_counts_only_toward_the_inner_part():
    # The LLM's selection calls memory's lookups itself: that time is memory's, not the LLM's.
    clock = FakeClock()
    timer = StepTimer(clock)
    memory = timer.timed(Slow(clock, 0.5), Part.MEMORY)
    llm = timer.timed(Slow(clock, 1.0, inside=memory), Part.LLM)

    timer.start()
    llm.call(None)
    timing = timer.finish(1)

    assert timing.parts[Part.LLM] == pytest.approx(1.0)
    assert timing.parts[Part.MEMORY] == pytest.approx(0.5)
    assert sum(timing.parts.values()) == pytest.approx(timing.total)


def test_calls_between_steps_count_toward_no_step():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 2.0), Part.DATABASE)

    database.call(None)  # before the first step, such as reading the sim's bars
    timer.start()
    timing = timer.finish(1)

    assert timing.total == 0.0
    assert timing.parts[Part.DATABASE] == 0.0


def test_a_timed_service_still_hands_back_its_other_attributes():
    clock = FakeClock()
    service = StepTimer(clock).timed(Slow(clock, 1.0), Part.JEV)
    assert service.name == "kept as it is"


def test_a_failing_call_still_counts():
    clock = FakeClock()
    timer = StepTimer(clock)

    class Failing:
        def call(self):
            clock.wait(0.4)
            raise RuntimeError("no answer")

    jev = timer.timed(Failing(), Part.JEV)
    timer.start()
    with pytest.raises(RuntimeError):
        jev.call()
    assert timer.finish(1).parts[Part.JEV] == pytest.approx(0.4)


def test_the_line_names_the_step_its_total_and_the_five_parts():
    clock = FakeClock()
    timer = StepTimer(clock)
    database = timer.timed(Slow(clock, 3.0), Part.DATABASE)
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
    database = timer.timed(Slow(clock, 1.0), Part.DATABASE)
    times = []
    for step, extra in ((1, 0.0), (2, 2.0)):
        timer.start()
        database.call(None)
        clock.wait(extra)
        times.append(timer.finish(step))

    line = average_line(times)

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


class Slowed:
    """`service` with each call to `method` taking `seconds` on `clock` first."""

    def __init__(self, service, method: str, clock: FakeClock, seconds: float):
        self._service, self._method = service, method
        self._clock, self._seconds = clock, seconds

    def __getattr__(self, name):
        value = getattr(self._service, name)
        if name != self._method:
            return value

        def slowed(*args, **kwargs):
            self._clock.wait(self._seconds)
            return value(*args, **kwargs)

        return slowed


def summed(lines: list[str], part: str) -> float:
    return sum(
        float(re.search(rf"{part} (\d+\.\d\d)", line)[1])
        for line in lines
        if line.startswith("Timing, step ")
    )


def test_the_agents_steps_count_each_call_to_jev_toward_jev():

    market = with_snapshots(make_market())
    store = InMemorySimStore()
    clock = FakeClock()
    jev, sent = fake_jev(lambda n: 0.9)  # every screen says yes
    sim_id = practice(store, market)
    lines = []

    run_sim(
        store,
        market,
        sim_id,
        report=lines.append,
        jev=Slowed(jev, "ask", clock, 0.2),
        timer=StepTimer(clock),
    )

    steps = store.rows("SIM.ACCOUNT_STEPS", sim_id)
    assert len([line for line in lines if line.startswith("Timing, step ")]) == len(
        steps
    )
    assert summed(lines, "Jev") == pytest.approx(0.2 * len(sent))
    assert summed(lines, "database") == summed(lines, "rest") == 0.0


def test_memorys_lookups_inside_the_llms_selection_count_toward_memory():

    market = with_snapshots(make_market())
    store = InMemorySimStore()
    clock = FakeClock()
    jev, _ = fake_jev(lambda n: 0.9)
    lookups_at, asked = fake_memory([PAST])
    selections = []

    class LooksOnceMore(StandInSelector):
        """Takes a second, during which it searches memory once more itself."""

        def select(self, situation, lookups, first_search):
            selections.append(situation)
            clock.wait(1.0)
            lookups.search()
            return super().select(situation, lookups, first_search)

    def slow_lookups_at(context):
        return Slowed(
            Slowed(lookups_at(context), "search", clock, 0.05), "read", clock, 0.05
        )

    sim_id = sim_with_memory(store, market)
    lines = []

    run_sim(
        store,
        market,
        sim_id,
        report=lines.append,
        jev=jev,
        lookups_at=slow_lookups_at,
        selector=LooksOnceMore(),
        timer=StepTimer(clock),
    )

    searches = [a for a in asked if a[0] in ("search", "read")]
    assert selections
    assert summed(lines, "LLM") == pytest.approx(1.0 * len(selections))
    assert summed(lines, "memory") == pytest.approx(0.05 * len(searches))
