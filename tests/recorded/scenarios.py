"""The frame of the recorded-answer scenarios (spec appendix 10, section 7).

A **scenario** is one made-up situation: one asset at one step, run through the agent's whole
decision path, with Jev's and the LLM's answers handed back from saved files (the cassettes,
by the recorder in `conftest.py`). `run_scenario` runs one and returns the three things each
test compares with what was saved:

- `memory_lookups`: every lookup asked of memory, in order (code's first search and track
  records, then the LLM's own);
- `orders`: the orders the step placed (the one Jev decided, or code's own: a stop price, a
  forced close, the sim's end);
- `records`: every other row the step stores, by table.

The expected results are kept with `syrupy`, in `__snapshots__/` beside the test file that runs
the scenarios; `--snapshot-update` rewrites them.

The step runs through the sim runner's own `run_step`, on the real agent, broker, Jev client and
LLM selection. Not built yet, each with the ticket that builds it:

- memory's lookups through the real memory server over the in-memory stand-in (#168);
- an account holding a position on the asset (#170).
"""

from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass, field
from typing import Any

from jev_trader.broker import (
    AssetClass,
    Bar,
    Broker,
    Direction,
    load_stop_price_settings,
    load_trading_costs,
)
from jev_trader.jev.client import JevClient, load_jev_settings
from jev_trader.jev.reading import Reading
from jev_trader.llm.selection import LlmSelector, MemoryLookups
from jev_trader.llm.settings import load_llm_settings
from jev_trader.memory.bridge import LookupContext
from jev_trader.memory.episodes import Episode
from jev_trader.memory.lookups import Episodes, SearchResult
from jev_trader.memory.track_record import TrackRecord
from jev_trader.risk import load_risk_profile
from jev_trader.sim.agent import AgentWithMemory, AgentWithoutMemory
from jev_trader.sim.market import DatasetInfo, InMemoryMarket, Period, Snapshot
from jev_trader.sim.runner import StepBatch, run_step
from jev_trader.sim.tracing import Tracing

SIM, DATASET, ASSET = 1, 1, "ASSET_01"
RANDOM_SEED = 0
# Columns that differ from run to run however the answers are handed back: when a call was
# made and how long it took. They are left out of what is compared.
VARIES_RUN_TO_RUN = frozenset({"CALLED_AT", "LATENCY_SECONDS"})


@dataclass(frozen=True)
class MadeUpPosition:
    """A position the account holds on the asset when the step begins."""

    direction: Direction
    amount: float  # dollars put in
    steps_ago: int  # the step it was opened at, counted back from the scenario's step
    stop_price: float


@dataclass(frozen=True)
class MadeUpInputs:
    """What one scenario hands the agent, all made up.

    `bars` are the asset's bars up to the scenario's step, the last one at it; `snapshot` is
    what the dataset measured there. `memory` holds the made-up past episodes (none: memory holds
    none yet); `with_memory` False runs the agent without memory. `sim_ends_here` makes the step
    the sim's last, where everything is sold (ADR 0009).
    """

    bars: tuple[Bar, ...]
    snapshot: Snapshot
    asset_class: AssetClass = AssetClass.CRYPTO
    memory: tuple[Episode, ...] = ()
    with_memory: bool = True
    cash: float = 10_000.0
    position: MadeUpPosition | None = None
    sim_ends_here: bool = False
    playbook: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def step(self) -> int:
        return self.bars[-1].step


@dataclass(frozen=True)
class Scenario:
    """One asset at one step: its name (the test's ID and its saved files' name), the path
    through the agent it covers, and its made-up inputs."""

    name: str
    path: str
    inputs: MadeUpInputs


@dataclass(frozen=True)
class ScenarioResult:
    """The three things a scenario's test compares with what was saved."""

    memory_lookups: list[tuple]
    orders: list[dict]
    records: dict[str, list[dict]]

    def compared(self) -> dict[str, Any]:
        return asdict(self)


class _NoMemoryServerYet:
    """Memory's lookups, until the real memory server over the in-memory stand-in is wired
    in (#168)."""

    def search(self, **filters: str) -> SearchResult:
        raise NotImplementedError("memory's lookups come with ticket #168")

    def read(self, episode_ids: list[str]) -> Episodes:
        raise NotImplementedError("memory's lookups come with ticket #168")

    def track_record(self, pattern: str, direction: str) -> TrackRecord:
        raise NotImplementedError("memory's lookups come with ticket #168")


class _NotedLookups:
    """Memory's lookups for one moment, each noted in `asked` before it is passed on."""

    def __init__(self, lookups: MemoryLookups, asked: list[tuple]):
        self.lookups, self.asked = lookups, asked

    def search(self, **filters: str) -> SearchResult:
        self.asked.append(("search", dict(sorted(filters.items()))))
        return self.lookups.search(**filters)

    def read(self, episode_ids: list[str]) -> Episodes:
        self.asked.append(("read", list(episode_ids)))
        return self.lookups.read(episode_ids)

    def track_record(self, pattern: str, direction: str) -> TrackRecord:
        self.asked.append(("track_record", pattern, direction))
        return self.lookups.track_record(pattern, direction)


def _noted(asked: list[tuple]) -> Callable[[LookupContext], MemoryLookups]:
    source = _NoMemoryServerYet()
    return lambda context: _NotedLookups(source, asked)


def _market(inputs: MadeUpInputs) -> InMemoryMarket:
    step = inputs.step
    info = DatasetInfo(
        dataset_id=DATASET,
        status="published",
        first_step=inputs.bars[0].step,
        last_step=step,
        periods=(Period("test", "made-up market", inputs.bars[0].step, step),),
        assets={ASSET: inputs.asset_class},
    )
    return InMemoryMarket(
        datasets=[info],
        bars={DATASET: {ASSET: list(inputs.bars)}},
        snapshots={DATASET: {step: {ASSET: inputs.snapshot}}},
        playbook=inputs.playbook,
    )


def _without_run_to_run_columns(rows: list[dict]) -> list[dict]:
    return [
        {k: v for k, v in row.items() if k not in VARIES_RUN_TO_RUN} for row in rows
    ]


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Run the scenario's one step through the agent's whole decision path.

    Jev and the LLM are the real clients: their requests are answered from the test's saved
    files, and a request with no saved answer fails the test.
    """
    inputs = scenario.inputs
    if inputs.position is not None:
        raise NotImplementedError(
            "an account holding a position comes with ticket #170"
        )
    step = inputs.step
    market = _market(inputs)
    costs, risk = load_trading_costs(), load_risk_profile()
    stops = load_stop_price_settings()
    broker = Broker(
        cash=inputs.cash,
        asset_classes={ASSET: inputs.asset_class},
        costs=costs,
        stop_settings=stops,
        risk=risk,
    )
    last_step = step if inputs.sim_ends_here else step + 1
    asked: list[tuple] = []
    with closing(JevClient(load_jev_settings())) as jev:
        arguments = (
            SIM,
            DATASET,
            last_step,
            market,
            jev,
            Reading(costs, risk),
            stops,
            RANDOM_SEED,
        )
        if inputs.with_memory:
            agent = AgentWithMemory(
                *arguments,
                lookups_at=_noted(asked),
                selector=LlmSelector(load_llm_settings()),
                tracing=Tracing(),
            )
        else:
            agent = AgentWithoutMemory(*arguments, tracing=Tracing())
        batch = StepBatch()
        # The step before is the step itself: no midnight passes, so no night is charged.
        previous = step
        run_step(
            SIM,
            step,
            previous,
            last_step,
            broker,
            agent,
            {ASSET: inputs.bars[-1]},
            batch,
        )
    tables = batch.tables()
    orders = tables.pop("SIM.ORDERS")
    return ScenarioResult(
        memory_lookups=asked,
        orders=_without_run_to_run_columns(orders),
        records={
            table: _without_run_to_run_columns(rows) for table, rows in tables.items()
        },
    )
