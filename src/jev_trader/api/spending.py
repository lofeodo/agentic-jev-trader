"""The Spending screen's one read: real dollars paid to Jev and the LLM against the ceiling, by
item (spec appendix 7, section 10; appendix 8, sections 8.2 and 8.5).

The spec leaves the items open. They follow the budget's lines (spec appendix 9, section 13):
one per sim that has made a paid call, grouped by the sim's kind in the sims list's order, then
one per purpose of the paid calls made outside any sim (the benchmark, saving answers for tests).
"""

from pydantic import BaseModel

from jev_trader.api.sims_list import KIND_ORDER, sim_name
from jev_trader.api.store import ApiStore

OUTSIDE_SIMS = "outside sims"
JEV = "jev"  # the one paid service besides the LLM


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
    left_usd: float  # can go below zero only if spending passed the ceiling
    jev_usd: float
    llm_usd: float
    items: list[SpendingItem]


def _cents_safe(value: float) -> float:
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
        return SpendingItem(
            kind=OUTSIDE_SIMS if sim_id is None else (sim or {}).get("KIND", "unknown"),
            sim_id=sim_id,
            name=purpose
            if sim_id is None
            else (sim_name(sim) if sim else f"Sim {sim_id}"),
            jev_usd=_cents_safe(item["jev_usd"]),
            llm_usd=_cents_safe(item["llm_usd"]),
            total_usd=_cents_safe(item["jev_usd"] + item["llm_usd"]),
            calls=item["calls"],
        )

    def order(line: SpendingItem) -> tuple:
        if line.sim_id is None:
            return (len(KIND_ORDER) + 1, 0, line.name)
        if line.kind in KIND_ORDER:
            return (KIND_ORDER.index(line.kind), line.sim_id, "")
        return (len(KIND_ORDER), line.sim_id, "")

    lines = sorted((line(k, v) for k, v in items.items()), key=order)
    jev = _cents_safe(sum(i["jev_usd"] for i in items.values()))
    llm = _cents_safe(sum(i["llm_usd"] for i in items.values()))
    spent = _cents_safe(jev + llm)
    return Spending(
        spent_usd=spent,
        ceiling_usd=ceiling,
        left_usd=_cents_safe(ceiling - spent),
        jev_usd=jev,
        llm_usd=llm,
        items=lines,
    )
