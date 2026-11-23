"""The Trading sims screen's one read: every sim as a line (spec appendix 8, section 8.2).

The sim that holds the five assets is never a line: it is the "holding" figure on the others.
A sim is compared with holding at the step the sim has reached, so a sim halfway through is
measured against holding halfway through, not against where holding ended.
"""

from datetime import date, datetime, timedelta

from pydantic import BaseModel

from jev_trader.api.store import ApiStore
from jev_trader.sim.clock import day_of
from jev_trader.sim.store import SimStatus

HOLDING = "buy_hold"
KIND_ORDER = ("measurement", "build-up", "free", "tuning", "practice")
VARIANT_WORDS = {"memory_on": "with memory", "memory_off": "without memory"}


class AssetName(BaseModel):
    """The real name leads; the masked ID is the disguised label the agent saw."""

    name: str
    masked_id: str


class SimLine(BaseModel):
    id: int
    name: str
    kind: str
    status: str
    stop_reason: str | None
    not_responding: bool  # worked out when read: running, but quiet for too long
    days_done: int
    days_total: int
    first_step: int
    last_step: int
    first_day: date | None  # real UTC dates; None if the dataset has no asset key
    last_day: date | None
    account_value: float
    holding_value: float | None  # None until holding has reached this sim's step
    trades: int
    spent_usd: float
    spending_cap_usd: float | None
    assets: list[AssetName]


class SimsList(BaseModel):
    sims: list[SimLine]


def _name(sim: dict) -> str:
    variant = VARIANT_WORDS.get(sim["VARIANT"], sim["VARIANT"])
    if sim.get("MARKET"):
        parts = [sim["MARKET"], variant]
        if sim.get("REPEAT_NUMBER") is not None:
            parts.append(f"repeat {sim['REPEAT_NUMBER']}")
        return " / ".join(parts)
    return f"Sim {sim['ID']} / {variant}"


def _days(sim: dict) -> tuple[int, int]:
    first, last = sim["FIRST_STEP"], sim["LAST_STEP"]
    total = day_of(last) - day_of(first) + 1
    reached = sim.get("LAST_COMPLETED_STEP")
    if reached is None:
        return 0, total
    if reached >= last:
        return total, total
    return day_of(reached + 1) - day_of(first), total  # days whose last step is stored


def _not_responding(sim: dict, at: datetime, quiet_limit: timedelta) -> bool:
    if sim["STATUS"] != SimStatus.RUNNING:
        return False
    last_sign = sim.get("LAST_WRITTEN_AT") or sim.get("STARTED_AT")
    return last_sign is not None and at - last_sign >= quiet_limit


def _reached(sim: dict) -> int:
    reached = sim.get("LAST_COMPLETED_STEP")
    return -1 if reached is None else reached


def _holding_sims(all_sims: list[dict]) -> dict[tuple, dict]:
    """The holding sim of each stretch of days: the one that got furthest, unless it failed."""
    found: dict[tuple, dict] = {}
    for sim in sorted(all_sims, key=lambda s: s["ID"]):
        if sim["VARIANT"] == HOLDING and sim["STATUS"] != SimStatus.FAILED:
            best = found.get(_stretch(sim))
            if best is None or _reached(sim) > _reached(best):
                found[_stretch(sim)] = sim
    return found


def _stretch(sim: dict) -> tuple:
    """What a sim and its holding sim share: the same days, from the same starting amount."""
    return sim["DATASET"], sim["FIRST_STEP"], sim["LAST_STEP"], sim["STARTING_VALUE"]


def _holding_at_same_moment(sim: dict, holding: dict[tuple, dict]) -> int | None:
    """The holding sim to compare with, if it has stored the step this sim has reached.

    A holding sim stores many steps per write, so it can be behind a sim on the same days.
    """
    found = holding.get(_stretch(sim))
    if found is None or _reached(sim) < 0 or _reached(found) < _reached(sim):
        return None
    return found["ID"]


def sims_list(store: ApiStore, at: datetime, quiet_limit: timedelta) -> SimsList:
    all_sims = store.sims()
    lines = [s for s in all_sims if s["VARIANT"] != HOLDING]
    if not lines:
        return SimsList(sims=[])

    holding = _holding_sims(all_sims)
    wanted = []
    for sim in lines:
        reached = sim.get("LAST_COMPLETED_STEP")
        if reached is not None:
            wanted.append((sim["ID"], reached))
            holding_id = _holding_at_same_moment(sim, holding)
            if holding_id is not None:
                wanted.append((holding_id, reached))
    values = store.account_values_at(wanted) if wanted else {}
    trades, spent = store.trades_by_sim(), store.spent_by_sim()

    assets: dict[int, list[dict]] = {}
    for row in sorted(store.asset_key(), key=lambda r: r["MASKED_ID"]):
        assets.setdefault(row["DATASET"], []).append(row)

    def line(sim: dict) -> SimLine:
        reached = sim.get("LAST_COMPLETED_STEP")
        holding_id = _holding_at_same_moment(sim, holding)
        days_done, days_total = _days(sim)
        dataset_assets = assets.get(sim["DATASET"], [])
        dataset_first_day = dataset_assets[0]["FIRST_DAY"] if dataset_assets else None
        return SimLine(
            id=sim["ID"],
            name=_name(sim),
            kind=sim["KIND"],
            status=sim["STATUS"],
            stop_reason=sim.get("STOP_REASON"),
            not_responding=_not_responding(sim, at, quiet_limit),
            days_done=days_done,
            days_total=days_total,
            first_step=sim["FIRST_STEP"],
            last_step=sim["LAST_STEP"],
            first_day=dataset_first_day
            and dataset_first_day + timedelta(day_of(sim["FIRST_STEP"]) - 1),
            last_day=dataset_first_day
            and dataset_first_day + timedelta(day_of(sim["LAST_STEP"]) - 1),
            account_value=values.get((sim["ID"], reached), sim["STARTING_VALUE"]),
            holding_value=values.get((holding_id, reached)),
            trades=trades.get(sim["ID"], 0),
            spent_usd=spent.get(sim["ID"], 0.0),
            spending_cap_usd=sim.get("SPENDING_CAP"),
            assets=[
                AssetName(name=a["NAME"], masked_id=a["MASKED_ID"])
                for a in dataset_assets
            ],
        )

    ordered = sorted(
        lines,
        key=lambda s: (
            KIND_ORDER.index(s["KIND"]) if s["KIND"] in KIND_ORDER else len(KIND_ORDER),
            s["ID"],
        ),
    )
    return SimsList(sims=[line(sim) for sim in ordered])
