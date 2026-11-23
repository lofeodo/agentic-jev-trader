"""Starting a sim and running it to its last step (spec appendix 1, sections 1 and 6; appendix 6).

`create_sim` checks a request and stores the sim's row with every setting it will run with.
`run_sim` runs it, or resumes it from its last completed step:

1. Each step where some asset has a bar (and always the first and last step): any midnight
   passed since the step before charges the night's borrow fees and loan interest; each asset
   with a bar gets it, so orders waiting for it are carried out at its open; the strategy
   decides; the broker checks the account. Steps where no asset has a bar are skipped.
2. At the last step every position is closed at its asset's last close (ADR 0009).
3. Everything the steps produced is stored `steps_per_write` steps at a time, with the sim's last
   completed step and the saved account (`store.SimStore.write_steps`). One step per write is the safe
   default; the holding sim, which calls nothing paid, stores many at once.
4. At the end the duplicate IDs are counted. None: the sim is finished. Any: it is failed.

A sim killed mid-step stored nothing of that step. Run again, it brings back its account as it
stood after its last completed step (ADR 0013) and carries on from the next one, so it ends with
the same records as a sim that never stopped.

Choices the spec leaves to the build (appendix 1, "Not decided by any ticket"):

- The holding sim's purchases are decided at the sim's first step and carried out like any
  order, at each asset's next bar's open (a stock's next session if the first step is at
  night). Each asset's equal part is made smaller, down to the cent, to leave room for its
  commission or trading fee, so the holding sim never owes money and pays no loan interest.
- No nightly charge at the last step: by then every position is closed and nothing is owed.
"""

import math
import os
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jev_trader.broker import (
    AssetClass,
    Bar,
    Broker,
    StopPriceSettings,
    TradingCosts,
    load_stop_price_settings,
    load_trading_costs,
)
from jev_trader.dataset.store import DatasetStatus
from jev_trader.sim import records
from jev_trader.sim.clock import midnights_between
from jev_trader.sim.market import DatasetInfo, Market
from jev_trader.sim.store import (
    SimStatus,
    SimStore,
    StepAlreadyWritten,
    StopReason,
    now,
)

KINDS = ("practice", "tuning", "build-up", "measurement", "free")
VARIANTS = ("buy_hold", "memory_off", "memory_on")
BUILT_VARIANTS = ("buy_hold",)
REPO_ROOT = Path(__file__).resolve().parents[3]


class DuplicateRecords(Exception):
    """The check at the end of a sim found record IDs stored more than once."""


@dataclass(frozen=True)
class SimRequest:
    dataset: int
    variant: str
    kind: str
    first_step: int
    last_step: int
    starting_value: float = 10_000.0
    market: str | None = None  # the test period's name, for a measurement sim
    random_seed: int = 0


@dataclass(frozen=True)
class SimResult:
    sim_id: int
    ending_value: float
    steps_stored: int


@dataclass
class BuyHold:
    """Equal money into every asset at the first step, held to the last (appendix 1, section 6)."""

    first_step: int
    starting_value: float

    def on_step(self, step: int, broker: Broker, bars: dict[str, Bar]) -> None:
        if step != self.first_step:
            return
        share = self.starting_value / len(broker.asset_classes)
        for asset, asset_class in sorted(broker.asset_classes.items()):
            if asset_class is AssetClass.STOCK:
                amount = share - broker.costs.stock_commission
            else:
                amount = share / (1 + broker.costs.crypto_trading_fee)
            broker.buy_and_hold(asset, _cents_down(amount), step)


def _cents_down(amount: float) -> float:
    return math.floor(round(amount * 100, 6)) / 100


# Starting a sim


def settings_document(starting_value: float) -> dict:
    """Every setting the sim runs with, stored on its row so a resumed sim uses the same ones.

    The holding sim applies no risk profile, so it stores none. The agent's sims add theirs.
    """
    return {
        "starting_value": starting_value,
        "risk_profile": None,
        "trading_costs": asdict(load_trading_costs()),
        "stop_prices": asdict(load_stop_price_settings()),
    }


def code_version() -> str:
    """The git commit the code came from, or "unknown" where git is not at hand."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def check_request(request: SimRequest, info: DatasetInfo) -> None:
    """Refuse a sim the spec does not allow. The message says what to change."""
    if info.status != DatasetStatus.PUBLISHED:
        raise ValueError(
            f"dataset {info.dataset_id} is {info.status}, not published: "
            "no sim can start on it"
        )
    if request.variant not in VARIANTS:
        raise ValueError(f"variant must be one of {', '.join(VARIANTS)}")
    if request.variant not in BUILT_VARIANTS:
        raise ValueError(f"the {request.variant} variant is not built yet")
    if request.kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not request.first_step <= request.last_step:
        raise ValueError("the first step must come before the last")
    if not (
        info.first_step <= request.first_step and request.last_step <= info.last_step
    ):
        raise ValueError(
            f"the dataset runs from step {info.first_step} to {info.last_step}"
        )
    if request.first_step <= info.warm_up_last_step:
        raise ValueError(
            f"no sim runs in the warm-up period: start after step {info.warm_up_last_step}"
        )
    if request.kind == "free":
        for period in info.test_periods():
            if (
                request.first_step <= period.last_step
                and period.first_step <= request.last_step
            ):
                raise ValueError(
                    f'a free sim cannot use test period days ("{period.name}", steps '
                    f"{period.first_step} to {period.last_step})"
                )
    if not request.starting_value > 0:
        raise ValueError("the starting account value must be above zero")


def create_sim(store: SimStore, market: Market, request: SimRequest) -> int:
    """Check the request and store the sim's row, with status created. Returns its ID."""
    check_request(request, market.dataset(request.dataset))
    return store.create(
        {
            "DATASET": request.dataset,
            "KIND": request.kind,
            "VARIANT": request.variant,
            "MARKET": request.market,
            "FIRST_STEP": request.first_step,
            "LAST_STEP": request.last_step,
            "STARTING_VALUE": request.starting_value,
            "RANDOM_SEED": request.random_seed,
            "SETTINGS": settings_document(request.starting_value),
            "CODE_VERSION": code_version(),
        }
    )


# Running it


@dataclass
class _Batch:
    """What the steps since the last write produced, waiting to be stored together."""

    steps: int = 0
    orders: dict[str, dict] = field(default_factory=dict)  # by ID: the latest row wins
    rows: dict[str, list[dict]] = field(
        default_factory=lambda: {
            "SIM.ACCOUNT_STEPS": [],
            "SIM.CHARGES": [],
            "SIM.SIM_EVENTS": [],
        }
    )

    def tables(self) -> dict[str, list[dict]]:
        return {"SIM.ORDERS": list(self.orders.values()), **self.rows}


def run_sim(
    store: SimStore,
    market: Market,
    sim_id: int,
    steps_per_write: int = 1,
    report: Callable[[str], None] = lambda line: None,
) -> SimResult:
    """Run the sim from its first step, or resume it after its last completed step."""
    sim = store.sim(sim_id)
    if sim["STATUS"] == SimStatus.FINISHED:
        raise ValueError(f"sim {sim_id} is finished: code writes nothing more to it")
    if sim["VARIANT"] not in BUILT_VARIANTS:
        raise ValueError(f"the {sim['VARIANT']} variant is not built yet")
    info = market.dataset(sim["DATASET"])
    first_step, last_step = sim["FIRST_STEP"], sim["LAST_STEP"]
    settings = sim["SETTINGS"]
    costs = TradingCosts(**settings["trading_costs"])
    stops = StopPriceSettings(
        multiples=tuple(settings["stop_prices"]["multiples"]),
        distance_cap=settings["stop_prices"]["distance_cap"],
    )

    last_completed = sim["LAST_COMPLETED_STEP"]
    if last_completed is None:
        broker = Broker(
            cash=sim["STARTING_VALUE"],
            asset_classes=dict(info.assets),
            costs=costs,
            stop_settings=stops,
        )
        start, previous = first_step, first_step
    else:
        broker = Broker.from_state(
            sim["ACCOUNT_STATE"], dict(info.assets), costs, stops
        )
        start, previous = last_completed + 1, last_completed
        report(f"Resuming sim {sim_id} after step {last_completed}.")

    store.update(
        sim_id,
        STATUS=str(SimStatus.RUNNING),
        STOP_REASON=None,
        FAILURE_REASON=None,
        RUNNING_ON=f"pid {os.getpid()}",
        **({} if sim.get("STARTED_AT") else {"STARTED_AT": now()}),
    )
    strategy = BuyHold(first_step, sim["STARTING_VALUE"])
    batch = _Batch()
    if last_completed is not None and start <= last_step:
        batch.rows["SIM.SIM_EVENTS"].append(
            records.event_row(
                sim_id, start, "restarted", 1, {"after_step": last_completed}
            )
        )
    steps_stored = 0

    try:
        bars_by_step = (
            market.bars(info.dataset_id, start, last_step) if start <= last_step else {}
        )
        steps = sorted(
            set(bars_by_step)
            | ({first_step} if last_completed is None else set())
            | ({last_step} if start <= last_step else set())
        )
        for step in steps:
            _run_step(
                sim_id,
                step,
                previous,
                last_step,
                broker,
                strategy,
                bars_by_step.get(step, {}),
                batch,
            )
            previous = step
            if batch.steps >= steps_per_write or step == last_step:
                store.write_steps(
                    sim_id, last_completed, step, batch.tables(), broker.state()
                )
                last_completed, steps_stored = step, steps_stored + batch.steps
                batch = _Batch()
                report(f"Stored up to step {step} of {last_step}.")
    except StepAlreadyWritten:
        raise  # another copy is running it: leave its row alone
    except KeyboardInterrupt:
        store.update(
            sim_id,
            STATUS=str(SimStatus.STOPPED),
            STOP_REASON=str(StopReason.STOPPED_BY_HAND),
            ENDED_AT=now(),
        )
        raise
    except Exception as error:
        store.update(
            sim_id,
            STATUS=str(SimStatus.FAILED),
            FAILURE_REASON=f"{type(error).__name__}: {error}",
            ENDED_AT=now(),
        )
        raise

    duplicates = store.duplicate_ids(sim_id)
    if duplicates:
        found = ", ".join(f"{n} in {table}" for table, n in sorted(duplicates.items()))
        store.update(
            sim_id,
            STATUS=str(SimStatus.FAILED),
            FAILURE_REASON=f"record IDs stored more than once: {found}",
            ENDED_AT=now(),
        )
        raise DuplicateRecords(found)
    store.update(
        sim_id,
        STATUS=str(SimStatus.FINISHED),
        STOP_REASON=str(StopReason.FINISHED),
        ENDED_AT=now(),
    )
    return SimResult(sim_id, broker.account_value(), steps_stored)


def _run_step(
    sim_id: int,
    step: int,
    previous: int,
    last_step: int,
    broker: Broker,
    strategy: BuyHold,
    bars: dict[str, Bar],
    batch: _Batch,
) -> None:
    """One step, worked out in memory: its records go into `batch`."""
    waiting_before = {o.order_id for o in broker.waiting_orders}
    fills_before = len(broker.fills)
    cancelled_before = len(broker.cancelled_orders)
    charges_before = len(broker.charges)

    for midnight in midnights_between(previous, step):
        broker.charge_overnight(midnight)
    for asset in sorted(bars):
        broker.on_bar(asset, bars[asset])
    strategy.on_step(step, broker, bars)
    broker.check_account(step)
    if step == last_step:
        broker.close_everything(step)

    def position_of(asset: str) -> int | None:
        position = broker.positions.get(asset)
        return None if position is None else position.position_id

    for order in broker.waiting_orders:
        if order.order_id not in waiting_before:
            row = records.waiting_order_row(sim_id, order, position_of(order.asset))
            batch.orders[row["ID"]] = row
    for order in broker.cancelled_orders[cancelled_before:]:
        row = records.cancelled_order_row(sim_id, order, position_of(order.asset))
        batch.orders[row["ID"]] = row
    for fill in broker.fills[fills_before:]:
        row = records.filled_order_row(sim_id, fill)
        batch.orders[row["ID"]] = row
    batch.rows["SIM.CHARGES"] += [
        records.charge_row(sim_id, c) for c in broker.charges[charges_before:]
    ]
    batch.rows["SIM.ACCOUNT_STEPS"].append(records.account_row(sim_id, step, broker))
    batch.steps += 1
