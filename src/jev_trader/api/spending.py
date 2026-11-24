"""The Spending screen's one read: real dollars paid to Jev and the LLM against the ceiling, by
item (spec appendix 7, section 10; appendix 8, sections 8.2 and 8.5).

The spec leaves the items open. They follow the lines of the project's cost estimate (spec
appendix 9, section 13): one per sim that has made a paid call, grouped by the sim's kind in the
sims list's order, then one per purpose of the paid calls made outside any sim (the benchmark,
saving answers for tests).

What is left under the ceiling is counted as the checker counts it (8.5): the ceiling, less the
money already spent, less the unspent part of the cap of every sim in progress. A sim in progress
is one created or running; the spec leaves the exact rule open (8.15).
"""

from pydantic import BaseModel

from jev_trader.api.sims_list import KIND_ORDER, sim_name
from jev_trader.api.store import ApiStore
from jev_trader.sim.store import SimStatus

OUTSIDE_SIMS = "outside sims"
# The two paid services: a call is Jev's when its SERVICE says so, the LLM's otherwise.
JEV = "jev"
IN_PROGRESS = (SimStatus.CREATED, SimStatus.RUNNING)


class SpendingItem(BaseModel):
    kind: str  # the sim's kind, or "outside sims"
    sim_id: int | None  # None for calls outside any sim
    name: str  # the sim's name, or the calls' purpose
    jev_usd: float
    llm_usd: float
    total_usd: float
    calls: int  # paid calls made, failed ones included


class Spending(BaseModel):
    spent_usd: float
    ceiling_usd: float
    reserved_usd: float  # what sims in progress may still spend, up to their caps
    left_usd: float  # ceiling - spent - reserved; below zero only if spending passed it
    jev_usd: float
    llm_usd: float
    items: list[SpendingItem]


def _without_float_noise(value: float) -> float:
    """Sums of floats pick up noise (0.1 + 0.2); six decimals keep every fraction of a cent."""
    return round(value, 6)


def spending(store: ApiStore, ceiling: float) -> Spending:
    sims = {s["ID"]: s for s in store.sims()}
    items: dict[tuple, dict] = {}
    for row in store.spending_by_item():
        key = (row["SIM"], row["PURPOSE"])
        item = items.setdefault(key, {"jev_usd": 0.0, "llm_usd": 0.0, "calls": 0})
        paid = "jev_usd" if row["SERVICE"] == JEV else "llm_usd"
        item[paid] += row["COST_USD"]
        item["calls"] += row["CALLS"]

    def line(key: tuple, item: dict) -> SpendingItem:
        sim_id, purpose = key
        sim = sims.get(sim_id) if sim_id is not None else None
        if sim_id is None:
            kind, name = OUTSIDE_SIMS, purpose
        elif sim is None:
            kind, name = "unknown", f"Sim {sim_id}"
        else:
            kind, name = sim["KIND"], sim_name(sim)
        return SpendingItem(
            kind=kind,
            sim_id=sim_id,
            name=name,
            jev_usd=_without_float_noise(item["jev_usd"]),
            llm_usd=_without_float_noise(item["llm_usd"]),
            total_usd=_without_float_noise(item["jev_usd"] + item["llm_usd"]),
            calls=item["calls"],
        )

    def order(line: SpendingItem) -> tuple:
        if line.sim_id is None:
            return (len(KIND_ORDER) + 1, 0, line.name)
        if line.kind in KIND_ORDER:
            return (KIND_ORDER.index(line.kind), line.sim_id, "")
        return (len(KIND_ORDER), line.sim_id, "")

    lines = sorted((line(k, v) for k, v in items.items()), key=order)
    spent_by_sim = {i.sim_id: i.total_usd for i in lines if i.sim_id is not None}
    reserved = sum(
        max(sim["SPENDING_CAP"] - spent_by_sim.get(sim_id, 0.0), 0.0)
        for sim_id, sim in sims.items()
        if sim["STATUS"] in IN_PROGRESS and sim.get("SPENDING_CAP") is not None
    )
    jev = _without_float_noise(sum(i["jev_usd"] for i in items.values()))
    llm = _without_float_noise(sum(i["llm_usd"] for i in items.values()))
    spent = _without_float_noise(jev + llm)
    return Spending(
        spent_usd=spent,
        ceiling_usd=ceiling,
        reserved_usd=_without_float_noise(reserved),
        left_usd=_without_float_noise(ceiling - spent - reserved),
        jev_usd=jev,
        llm_usd=llm,
        items=lines,
    )
