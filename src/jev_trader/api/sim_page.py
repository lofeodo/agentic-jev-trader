"""The Trading sim page's reads (spec appendix 7 section 5; appendix 8 sections 8.2 and 8.9).

- `header`: the sim's name, status, the days it covers, and its settings (`GET /sims/{id}`).
- `chart`: account value over time for the sim, holding the five assets, and the other sims
  that replayed the same days, with one tick per trade opened (`GET /sims/{id}/chart`).
- `live`: the quick figures the page asks for every second while the sim is in progress
  (`GET /sims/{id}/live`).
- `moment`: the account, its positions and the trades around one point in time
  (`GET /sims/{id}/moment`).

Real names, prices and dates lead (appendix 8, section 8.13). A step ends 15 minutes after the
one before; step 0 ends at midnight UTC on the dataset's first day. A real price is the stored
(rescaled) price divided by the asset's price scale.

Choices the spec leaves to the build:

- "The other sims that replayed the same days" are the sims of the same kind over the same
  stretch of days and starting amount, holding excluded; for a measurement sim also of the same
  test period and repeat.
- "Latest decisions" are the last 8 rows of the sim's decisions (an asset looked at, at a
  step); the latest 8 orders come beside them.
- A position's direction is its entry's side: a buy opens a long, a sell a short.
"""

from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel

from jev_trader.api.llm_names import variant_label
from jev_trader.api.sims_list import (
    HOLDING,
    AssetName,
    days_of,
    holding_sims,
    is_not_responding,
    sim_name,
    stretch,
)
from jev_trader.api.store import ApiStore
from jev_trader.dataset.bars import BAR_LENGTH
from jev_trader.sim.store import SimStatus


class SimNotFound(KeyError):
    pass


class SimHeader(BaseModel):
    id: int
    name: str
    kind: str
    variant: str
    dataset: int
    status: str
    stop_reason: str | None
    failure_reason: str | None
    not_responding: bool
    in_progress: bool  # the page keeps asking only while this is true
    days_done: int
    days_total: int
    first_step: int
    last_step: int
    first_day: date | None  # real UTC days; None if the dataset has no asset key
    last_day: date | None
    steps_start_at: (
        datetime | None
    )  # when step 0 ends: step N ends N x 15 minutes later
    step_reached: int | None  # the last completed step
    replayed_at: datetime | None  # when the last completed step ends, UTC
    starting_value: float
    spending_cap_usd: float | None
    estimated_cost_usd: float | None
    code_version: str | None
    settings: dict
    assets: list[AssetName]


# Shared facts about one sim


class Sim:
    """One sim's row, with its dataset's asset key, and the sims drawn beside it."""

    def __init__(self, store: ApiStore, sim_id: int):
        row = store.sim(sim_id)
        if row is None:
            raise SimNotFound(sim_id)
        self.row = row
        self.id = sim_id
        self.key = {
            k["MASKED_ID"]: k
            for k in sorted(store.asset_key(), key=lambda k: k["MASKED_ID"])
            if k["DATASET"] == row["DATASET"]
        }
        first_days = [k["FIRST_DAY"] for k in self.key.values()]
        self.steps_start_at = (
            datetime.combine(min(first_days), time()) if first_days else None
        )
        self._store = store

    def at(self, step: int | None) -> datetime | None:
        if step is None or self.steps_start_at is None:
            return None
        return self.steps_start_at + step * BAR_LENGTH

    def day(self, step: int) -> date | None:
        moment = self.at(step - 1)  # the day the step starts on
        return None if moment is None else moment.date()

    def closes_at(self, step: int) -> dict[str, float]:
        return self._store.closes_at(self.row["DATASET"], step)

    def asset(self, masked_id: str) -> AssetName:
        found = self.key.get(masked_id)
        return AssetName(
            name=found["NAME"] if found else masked_id, masked_id=masked_id
        )

    def in_progress(self, at: datetime, quiet_limit: timedelta) -> bool:
        status = self.row["STATUS"]
        return status == SimStatus.CREATED or (
            status == SimStatus.RUNNING
            and not is_not_responding(self.row, at, quiet_limit)
        )


class ChartPoint(BaseModel):
    step: int
    value: float  # account value after the step


class ChartLine(BaseModel):
    sim_id: int
    role: str  # "sim", "holding", or "same days" (another sim over the same days)
    label: str
    points: list[ChartPoint]


class TradeTick(BaseModel):
    """One trade: a tick on the chart where it opened."""

    position: int
    asset: AssetName
    direction: str  # "long" bets on a rise, "short" on a fall
    opened_step: int
    closed_step: int | None  # None while it is open


class Chart(BaseModel):
    starting_value: float
    lines: list[ChartLine]
    ticks: list[TradeTick]
    window_steps: int  # what "around then" means: this many steps either side


HOLDING_LABEL = "Holding the five assets"


def _same_days(all_sims: list[dict], row: dict) -> list[dict]:
    """The other sims replayed over the same days, drawn beside this one."""

    def alike(other: dict) -> bool:
        if other["ID"] == row["ID"] or other["VARIANT"] == HOLDING:
            return False
        if stretch(other) != stretch(row) or other["KIND"] != row["KIND"]:
            return False
        if row["KIND"] == "measurement":
            return (other.get("MARKET"), other.get("REPEAT_NUMBER")) == (
                row.get("MARKET"),
                row.get("REPEAT_NUMBER"),
            )
        return True

    return sorted((s for s in all_sims if alike(s)), key=lambda s: s["ID"])


def holding_of(all_sims: list[dict], row: dict) -> dict | None:
    """The holding sim over the same days, drawn and measured beside this one."""
    if row["VARIANT"] == HOLDING:
        return None
    return holding_sims(all_sims).get(stretch(row))


def never_changes(store: ApiStore, sim_id: int) -> bool:
    """The sim has finished, and so has the holding sim it is measured beside, if any."""
    row = store.sim(sim_id)
    if row is None or row["STATUS"] != SimStatus.FINISHED:
        return False
    holding = holding_of(store.sims(), row)
    return holding is None or holding["STATUS"] == SimStatus.FINISHED


def _lines_drawn(all_sims: list[dict], row: dict) -> list[tuple[int, str, str]]:
    """(sim, role, label) for every line on the sim's chart, the sim's own first."""
    drawn = [(row["ID"], "sim", sim_name(row))]
    holding = holding_of(all_sims, row)
    if holding is not None:
        drawn.append((holding["ID"], "holding", HOLDING_LABEL))
    others = _same_days(all_sims, row)
    labels = [variant_label(s) for s in others]
    for other, label in zip(others, labels, strict=True):
        if labels.count(label) > 1:
            label = f"{label} / sim {other['ID']}"
        drawn.append((other["ID"], "same days", label))
    return drawn


def _points(rows: list[dict]) -> list[ChartPoint]:
    return [ChartPoint(step=r["STEP"], value=r["ACCOUNT_VALUE"]) for r in rows]


def carried_out(orders: list[dict]) -> list[dict]:
    return sorted(
        (o for o in orders if o["STATUS"] == "carried out"),
        key=lambda o: (o["STEP_CARRIED_OUT"], o["ID"]),
    )


def asset_of(order: dict) -> str:
    return order["INSTRUMENT"].removesuffix("_SPOT")


def direction_of(entry: dict) -> str:
    """An entry's side gives its position's direction: a buy opens a long, a sell a short."""
    return "long" if entry["SIDE"] == "buy" else "short"


def _ticks(sim: Sim, orders: list[dict]) -> list[TradeTick]:
    ticks: dict[int, TradeTick] = {}
    for order in carried_out(orders):
        if order["KIND"] == "entry":
            ticks[order["POSITION"]] = TradeTick(
                position=order["POSITION"],
                asset=sim.asset(asset_of(order)),
                direction=direction_of(order),
                opened_step=order["STEP_CARRIED_OUT"],
                closed_step=None,
            )
        elif order["KIND"] == "close" and order["POSITION"] in ticks:
            ticks[order["POSITION"]].closed_step = order["STEP_CARRIED_OUT"]
    return sorted(ticks.values(), key=lambda t: (t.opened_step, t.position))


def chart(store: ApiStore, sim_id: int, window_steps: int) -> Chart:
    sim = Sim(store, sim_id)
    drawn = _lines_drawn(store.sims(), sim.row)
    rows = store.account_steps([line_sim for line_sim, _, _ in drawn])
    return Chart(
        starting_value=sim.row["STARTING_VALUE"],
        lines=[
            ChartLine(sim_id=s, role=role, label=label, points=_points(rows[s]))
            for s, role, label in drawn
        ],
        ticks=_ticks(sim, store.orders(sim_id)),
        window_steps=window_steps,
    )


class Price(BaseModel):
    """A price as it really was, and as the agent saw it (rescaled)."""

    real: float | None  # None if the dataset has no asset key
    rescaled: float


class OpenPosition(BaseModel):
    position: int
    asset: AssetName
    direction: str  # "long" bets on a rise, "short" on a fall
    units: float  # real shares or coins
    entry_price: Price
    price_now: Price | None  # the asset's last price; None before its first bar
    stop_price: Price | None  # where code closes it at a loss; None for holding
    value_usd: float | None  # what it is worth at the last price
    profit_so_far: float | None  # after every trading cost it has paid
    opened_step: int
    opened_at: datetime | None
    amount_chosen: float | None  # what Jev chose to put in, before the risk limits
    limited_by: str | None  # the risk limit that made it smaller


class OrderLine(BaseModel):
    """One order: what the agent (or code) decided, and whether it was carried out."""

    step_decided: int
    decided_at: datetime | None
    asset: AssetName
    kind: str  # entry, add, reduce or close
    side: str | None  # buy or sell, once carried out
    reason: str  # jev, stop_price, forced_close, sim_ended or buy_hold
    status: str  # waiting, carried out or cancelled
    step_carried_out: int | None
    value_usd: float | None
    amount_chosen: float | None
    limited_by: str | None


class NotableMoment(BaseModel):
    step: int
    at: datetime | None
    kind: str
    details: dict | None


class Meters(BaseModel):
    """The three thin meters, the spending one aside (its figures are the key figures)."""

    day_change: float  # account value against its value at midnight UTC
    daily_loss_limit_usd: (
        float | None
    )  # the most the day may lose; None: no risk profile
    daily_loss_reached: bool
    held_usd: float  # all positions added together, a short counted like a long
    exposure_limit_usd: float | None  # the most that may be held; None: no risk profile


class DecisionLine(BaseModel):
    """One asset looked at, at one step, and what came of it."""

    step: int
    at: datetime | None
    asset: AssetName
    kind: str  # "screen" for now
    tier: int  # 0: code alone, nothing asked; 1: Jev answered the screen
    screen_answer: (
        float | None
    )  # Jev's probability that a closer look is worth it, 0 to 1
    skipped_because: str | None  # the limit that meant no trade could open
    action: str  # what was done: "nothing" for now


class NewPoint(BaseModel):
    sim_id: int
    step: int
    value: float


class LiveFigures(BaseModel):
    status: str
    stop_reason: str | None
    not_responding: bool
    in_progress: bool
    days_done: int
    days_total: int
    step_reached: int | None
    replayed_at: datetime | None
    account_value: float
    holding_value: float | None  # None until holding has reached this sim's step
    trades: int
    spent_usd: float
    spending_cap_usd: float | None
    meters: Meters
    open_positions: list[OpenPosition]
    latest_decisions: list[DecisionLine]  # newest first
    latest_orders: list[OrderLine]  # newest first
    notable_moments: list[NotableMoment]
    new_points: list[NewPoint]  # every chart line's points after `after_step`
    ticks: list[TradeTick]  # every trade so far, as on the chart


LATEST_ORDERS = 8  # and as many decisions


def price_of(sim: Sim, masked_id: str, rescaled: float) -> Price:
    key = sim.key.get(masked_id)
    return Price(real=rescaled / key["PRICE_SCALE"] if key else None, rescaled=rescaled)


def real_units(sim: Sim, masked_id: str, units: float) -> float:
    key = sim.key.get(masked_id)
    return units * key["PRICE_SCALE"] if key else units


def _open_position(sim: Sim, held: dict, last_prices: dict) -> OpenPosition:
    asset = held["asset"]
    last = last_prices.get(asset)
    sign = 1 if held["direction"] == "long" else -1
    return OpenPosition(
        position=held["position_id"],
        asset=sim.asset(asset),
        direction=held["direction"],
        units=real_units(sim, asset, held["units"]),
        entry_price=price_of(sim, asset, held["entry_price"]),
        price_now=None if last is None else price_of(sim, asset, last),
        stop_price=held["stop_price"] and price_of(sim, asset, held["stop_price"]),
        value_usd=None if last is None else held["units"] * last,
        profit_so_far=None
        if last is None
        else held["cash_flow"] + sign * held["units"] * last,
        opened_step=held["step_opened"],
        opened_at=sim.at(held["step_opened"]),
        amount_chosen=held.get("amount_chosen"),
        limited_by=held.get("limited_by"),
    )


def _order_line(sim: Sim, order: dict) -> OrderLine:
    return OrderLine(
        step_decided=order["STEP_DECIDED"],
        decided_at=sim.at(order["STEP_DECIDED"]),
        asset=sim.asset(asset_of(order)),
        kind=order["KIND"],
        side=order.get("SIDE"),
        reason=order["REASON"],
        status=order["STATUS"],
        step_carried_out=order.get("STEP_CARRIED_OUT"),
        value_usd=order.get("VALUE"),
        amount_chosen=order.get("AMOUNT_CHOSEN"),
        limited_by=order.get("LIMITED_BY"),
    )


def _trades(orders: list[dict]) -> int:
    return len(
        {
            o["POSITION"]
            for o in orders
            if o["KIND"] == "entry" and o["STATUS"] == "carried out"
        }
    )


def _limit(settings: dict, name: str) -> float | None:
    profile = settings.get("risk_profile") or {}
    return profile.get(name)


def _holding_value_at(store: ApiStore, holding: dict | None, step: int) -> float | None:
    """Holding's account value at `step`, once holding has stored that far; else None.

    Holding stores many steps per write, so it can be behind the sim it is compared with.
    """
    if holding is None:
        return None
    holding_reached = holding.get("LAST_COMPLETED_STEP")
    if holding_reached is None or holding_reached < step:
        return None
    return store.account_values_at([(holding["ID"], step)]).get((holding["ID"], step))


def live(
    store: ApiStore,
    sim_id: int,
    at: datetime,
    quiet_limit: timedelta,
    after_step: int | None = None,
) -> LiveFigures:
    sim = Sim(store, sim_id)
    row = sim.row
    all_sims = store.sims()
    reached = row.get("LAST_COMPLETED_STEP")
    now_row = None if reached is None else store.account_at(sim_id, reached)
    value = now_row["ACCOUNT_VALUE"] if now_row else row["STARTING_VALUE"]
    start_of_day = now_row["START_OF_DAY_VALUE"] if now_row else row["STARTING_VALUE"]

    holding = holding_of(all_sims, row)
    holding_value = (
        None if reached is None else _holding_value_at(store, holding, reached)
    )

    settings = row.get("SETTINGS") or {}
    daily_share = _limit(settings, "daily_loss_limit")
    exposure_multiple = _limit(settings, "exposure_limit")
    state = row.get("ACCOUNT_STATE") or {}
    orders = store.orders(sim_id)
    newest = sorted(orders, key=lambda o: (o["STEP_DECIDED"], o["ID"]), reverse=True)[
        :LATEST_ORDERS
    ]
    lines = [line_sim for line_sim, _, _ in _lines_drawn(all_sims, row)]
    days_done, days_total = days_of(row)
    return LiveFigures(
        status=row["STATUS"],
        stop_reason=row.get("STOP_REASON"),
        not_responding=is_not_responding(row, at, quiet_limit),
        in_progress=sim.in_progress(at, quiet_limit),
        days_done=days_done,
        days_total=days_total,
        step_reached=reached,
        replayed_at=sim.at(reached),
        account_value=value,
        holding_value=holding_value,
        trades=_trades(orders),
        spent_usd=store.spent_on(sim_id),
        spending_cap_usd=row.get("SPENDING_CAP"),
        meters=Meters(
            day_change=value - start_of_day,
            daily_loss_limit_usd=None
            if daily_share is None
            else start_of_day * daily_share,
            daily_loss_reached=bool(now_row and now_row["DAILY_LOSS_REACHED"]),
            held_usd=now_row["EXPOSURE"] if now_row else 0.0,
            exposure_limit_usd=None
            if exposure_multiple is None
            else value * exposure_multiple,
        ),
        open_positions=[
            _open_position(sim, held, state.get("last_prices", {}))
            for held in state.get("positions", [])
        ],
        latest_orders=[_order_line(sim, o) for o in newest],
        ticks=_ticks(sim, orders),
        latest_decisions=[
            DecisionLine(
                step=d["STEP"],
                at=sim.at(d["STEP"]),
                asset=sim.asset(d["ASSET"]),
                kind=d["KIND"],
                tier=d["TIER"],
                screen_answer=d["SCREEN_ANSWER"],
                skipped_because=d["SKIPPED_BECAUSE"],
                action=d["ACTION"],
            )
            for d in store.latest_decisions(sim_id, LATEST_ORDERS)
        ],
        notable_moments=[
            NotableMoment(
                step=e["STEP"],
                at=sim.at(e["STEP"]),
                kind=e["KIND"],
                details=e["DETAILS"],
            )
            for e in store.events(sim_id)
        ],
        new_points=[
            NewPoint(sim_id=line_sim, step=r["STEP"], value=r["ACCOUNT_VALUE"])
            for line_sim, rows in store.account_steps(lines, after_step).items()
            for r in rows
        ],
    )


class AccountThen(BaseModel):
    account_value: float
    cash: float
    loan: float  # owed for positions bought beyond the account's own cash
    exposure: float  # all positions added together, a short counted like a long
    start_of_day_value: float  # account value at the midnight UTC before


class PositionThen(BaseModel):
    position: int
    asset: AssetName
    direction: str
    units: float  # real shares or coins
    average_price: Price  # what it was bought (or sold short) at, on average
    price_then: Price | None  # the asset's last close at the moment
    value_usd: float | None


class Moment(BaseModel):
    step: int  # the step that ended at or just before the time asked for
    at: datetime
    account: AccountThen | None  # None before the sim stored its first step
    since_midnight: float | None
    since_start: float | None
    holding_value: float | None
    positions: list[PositionThen]
    window_steps: int
    nearby: list[OrderLine]  # orders carried out within `window_steps` either side


class NoAssetKey(ValueError):
    """The dataset has no asset key, so a real time cannot be turned into a step."""


def _positions_then(sim: Sim, orders: list[dict], step: int) -> list[PositionThen]:
    held: dict[int, dict] = {}
    for order in carried_out(orders):
        if order["STEP_CARRIED_OUT"] > step:
            break
        position = held.setdefault(
            order["POSITION"],
            {"asset": asset_of(order), "units": 0.0, "bought": 0.0, "paid": 0.0},
        )
        if order["KIND"] == "entry":
            position["direction"] = direction_of(order)
        if order["KIND"] in ("entry", "add"):
            position["units"] += order["UNITS"]
            position["bought"] += order["UNITS"]
            position["paid"] += order["UNITS"] * order["PRICE"]
        else:
            position["units"] -= order["UNITS"]
    closes = sim.closes_at(step)
    found = []
    for number, p in sorted(held.items()):
        if p["units"] <= 1e-9 or "direction" not in p:
            continue
        close = closes.get(p["asset"])
        found.append(
            PositionThen(
                position=number,
                asset=sim.asset(p["asset"]),
                direction=p["direction"],
                units=real_units(sim, p["asset"], p["units"]),
                average_price=price_of(sim, p["asset"], p["paid"] / p["bought"]),
                price_then=None if close is None else price_of(sim, p["asset"], close),
                value_usd=None if close is None else p["units"] * close,
            )
        )
    return found


def moment(store: ApiStore, sim_id: int, at: datetime, window_steps: int) -> Moment:
    sim = Sim(store, sim_id)
    row = sim.row
    if sim.steps_start_at is None:
        raise NoAssetKey(f"dataset {row['DATASET']} has no asset key")
    if at.tzinfo is not None:
        at = at.astimezone(UTC).replace(tzinfo=None)
    # A moment the replay has not reached yet is the step it has reached: no later prices.
    reached = row.get("LAST_COMPLETED_STEP")
    last = row["LAST_STEP"] if reached is None else min(reached, row["LAST_STEP"])
    step = (at - sim.steps_start_at) // BAR_LENGTH
    step = max(min(step, last), row["FIRST_STEP"])
    then = store.account_at(sim_id, step)
    holding_value = _holding_value_at(store, holding_of(store.sims(), row), step)
    orders = store.orders(sim_id)
    nearby = [
        o
        for o in carried_out(orders)
        if abs(o["STEP_CARRIED_OUT"] - step) <= window_steps
    ]
    return Moment(
        step=step,
        at=sim.at(step),
        account=None
        if then is None
        else AccountThen(
            account_value=then["ACCOUNT_VALUE"],
            cash=then["CASH"],
            loan=then["LOAN"],
            exposure=then["EXPOSURE"],
            start_of_day_value=then["START_OF_DAY_VALUE"],
        ),
        since_midnight=None
        if then is None
        else then["ACCOUNT_VALUE"] - then["START_OF_DAY_VALUE"],
        since_start=None
        if then is None
        else then["ACCOUNT_VALUE"] - row["STARTING_VALUE"],
        holding_value=holding_value,
        positions=_positions_then(sim, orders, step),
        window_steps=window_steps,
        nearby=[_order_line(sim, o) for o in nearby],
    )


def header(
    store: ApiStore, sim_id: int, at: datetime, quiet_limit: timedelta
) -> SimHeader:
    sim = Sim(store, sim_id)
    row = sim.row
    days_done, days_total = days_of(row)
    reached = row.get("LAST_COMPLETED_STEP")
    return SimHeader(
        id=sim_id,
        name=sim_name(row),
        kind=row["KIND"],
        variant=row["VARIANT"],
        dataset=row["DATASET"],
        status=row["STATUS"],
        stop_reason=row.get("STOP_REASON"),
        failure_reason=row.get("FAILURE_REASON"),
        not_responding=is_not_responding(row, at, quiet_limit),
        in_progress=sim.in_progress(at, quiet_limit),
        days_done=days_done,
        days_total=days_total,
        first_step=row["FIRST_STEP"],
        last_step=row["LAST_STEP"],
        first_day=sim.day(row["FIRST_STEP"]),
        last_day=sim.day(row["LAST_STEP"]),
        steps_start_at=sim.steps_start_at,
        step_reached=reached,
        replayed_at=sim.at(reached),
        starting_value=row["STARTING_VALUE"],
        spending_cap_usd=row.get("SPENDING_CAP"),
        estimated_cost_usd=row.get("ESTIMATED_COST"),
        code_version=row.get("CODE_VERSION"),
        settings=row.get("SETTINGS") or {},
        assets=[sim.asset(m) for m in sim.key],
    )
