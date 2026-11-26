"""The timing log (spec appendix 11, sections 0 and 6): where each step's time goes.

Each step a sim runs writes one line splitting how long it took into the database, Jev, the LLM,
memory's lookups and the rest (the sim's own work: the broker, the screens, building requests):

    Timing, step 412: 3.40 s = database 3.00, Jev 0.20, LLM 0.00, memory 0.10, rest 0.10

`StepTimer.timed` wraps a service so every call to it counts toward one part. A call made inside
another counts only toward the inner one (the LLM's selection calls memory's lookups itself: that
time is memory's), so the parts always add up to the step's total. Calls between steps, such as
reading the sim's bars before the first one, count toward no step.

Choices the spec leaves to the build:

- The lines go out with the sim's other progress lines (`run_sim`'s `report`): the terminal for
  the command, `logs/sims/sim-<id>.log` for a job the API starts on this computer, the Job's
  output (`kubectl logs`) in the kind cluster. A run ends with the average of its steps.
- A step's time runs from the start of its work to the end of its write. A sim that stores many
  steps at once (the holding sim) has its write in the step it happens at.
- What a sim reads once before its first step (its bars, its settings, a copy of memory) is in
  no step. Snapshots are read a day at a time, inside the step that first needs them.
"""

import functools
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum


class Part(StrEnum):
    """Where a step's time goes. `REST` is what is left once the services' parts are counted."""

    DATABASE = "database"
    JEV = "Jev"
    LLM = "LLM"
    MEMORY = "memory"
    REST = "rest"


SERVICES = (
    Part.DATABASE,
    Part.JEV,
    Part.LLM,
    Part.MEMORY,
)  # the parts a service is timed as


@dataclass(frozen=True)
class StepTime:
    """One step's time in seconds: its total and its five parts, which add up to it."""

    step: int
    total: float
    parts: dict[Part, float]  # every part, the rest included

    def line(self) -> str:
        return f"Timing, step {self.step}: {_split(self.total, self.parts)}"


class StepTimer:
    """Times each step and its calls to the services `timed` wraps, by `clock` (in seconds)."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._parts = dict.fromkeys(SERVICES, 0.0)
        # For each call under way, the time taken by the calls made inside it.
        self._inner: list[float] = []
        self._started = clock()

    def timed[T](self, service: T, part: Part) -> T:
        """`service` with every call to one of its methods counted toward `part`."""
        return _Timed(service, part, self)  # type: ignore[return-value]

    def start(self) -> None:
        """A step begins: what was counted before it is dropped."""
        self._parts = dict.fromkeys(SERVICES, 0.0)
        self._started = self._clock()

    def finish(self, step: int) -> StepTime:
        total = self._clock() - self._started
        parts = {**self._parts, Part.REST: total - sum(self._parts.values())}
        return StepTime(step, total, parts)

    @contextmanager
    def counting(self, part: Part) -> Iterator[None]:
        """Count the time of the code inside toward `part`, less the calls counted inside it."""
        began = self._clock()
        self._inner.append(0.0)
        try:
            yield
        finally:
            took = self._clock() - began
            self._parts[part] += took - self._inner.pop()
            if self._inner:
                self._inner[-1] += took


class _Timed:
    """A service whose method calls `timer` counts toward `part`; its other attributes as
    they are."""

    def __init__(self, service: object, part: Part, timer: StepTimer):
        self._service, self._part, self._timer = service, part, timer

    def __getattr__(self, name: str):
        value = getattr(self._service, name)
        if not callable(value):
            return value

        @functools.wraps(value)
        def counted(*args, **kwargs):
            with self._timer.counting(self._part):
                return value(*args, **kwargs)

        return counted


def average_line(times: Sequence[StepTime]) -> str:
    """The line for the average step of `times`, part by part."""
    n = max(1, len(times))
    total = sum(t.total for t in times) / n
    parts = {p: sum(t.parts[p] for t in times) / n for p in Part}
    return f"Timing, average of {len(times)} steps: {_split(total, parts)}"


def _split(total: float, parts: dict[Part, float]) -> str:
    named = ", ".join(f"{p} {parts[p]:.2f}" for p in Part)
    return f"{total:.2f} s = {named}"
