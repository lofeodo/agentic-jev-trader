"""What the API reads (spec appendix 8). `InMemoryApiStore` is the stand-in the unit tests use;
`snowflake_store.SnowflakeApiStore` reads the same things from Snowflake as the API login.
"""

from typing import Protocol

from jev_trader.api.llm_names import llm_model_of
from jev_trader.sim.market import DatasetInfo, InMemoryMarket
from jev_trader.sim.store import (
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
    InMemorySimStore,
)

JEV_SERVICE = "jev"  # SIM.CALLS.SERVICE of a call to Jev; every other call is the LLM's


class ApiStore(Protocol):
    def total_spent(self) -> float:
        """Dollars paid for every Jev and LLM call, those made outside a sim included."""

    def sims(self) -> list[dict]:
        """Every sim's row, by column name, the holding sims included (no settings or account).

        Each row also has LLM_MODEL: the LLM its settings name, without the provider
        (`claude-haiku-5-5`), or None."""

    def sim(self, sim_id: int) -> dict | None:
        """One sim's whole row, its settings and saved account included; None if there is none."""

    def account_values_at(
        self, wanted: list[tuple[int, int]]
    ) -> dict[tuple[int, int], float]:
        """For each (sim, step): the account value at that step, or at the sim's last stored
        step before it. A pair with no stored step at or before it is left out."""

    def account_steps(
        self, sim_ids: list[int], after_step: int | None = None
    ) -> dict[int, list[dict]]:
        """Each sim's `SIM.ACCOUNT_STEPS` rows after `after_step` (all if None), in step order."""

    def account_at(self, sim_id: int, step: int) -> dict | None:
        """The sim's `SIM.ACCOUNT_STEPS` row at `step`, or its last one before it."""

    def orders(self, sim_id: int) -> list[dict]:
        """The sim's `SIM.ORDERS` rows, waiting and cancelled ones included."""

    def events(self, sim_id: int) -> list[dict]:
        """The sim's notable moments (`SIM.SIM_EVENTS`), in step order."""

    def latest_decisions(self, sim_id: int, limit: int) -> list[dict]:
        """The sim's last `limit` `MEMORY.DECISIONS` rows: latest step first, then by asset."""

    def closes_at(self, dataset: int, step: int) -> dict[str, float]:
        """Each asset's latest 15-minute close (rescaled) at or before `step`, by masked ID."""

    def trades_by_sim(self) -> dict[int, int]:
        """How many positions each sim has opened. A sim with none is left out."""

    def spent_by_sim(self) -> dict[int, float]:
        """Dollars paid for each sim's calls. A sim with none is left out."""

    def spent_on(self, sim_id: int) -> float:
        """Dollars paid for one sim's calls."""

    def asset_key(self) -> list[dict]:
        """The asset key's DATASET, MASKED_ID, TICKER, NAME, PRICE_SCALE and FIRST_DAY."""

    def charges(self, sim_id: int) -> list[dict]:
        """The sim's nightly charges (`SIM.CHARGES`), borrow fees and loan interest, by step."""

    def decisions(self, sim_id: int) -> list[dict]:
        """Every one of the sim's `MEMORY.DECISIONS` rows, by step then asset, without their
        candidate trades (no report needs them)."""

    def calls(self, sim_id: int) -> list[dict]:
        """The sim's paid calls (`SIM.CALLS`): at least DECISION, PURPOSE, COST_USD and
        LATENCY_SECONDS."""

    def comparison_figures(self, sim_ids: list[int]) -> dict[int, dict]:
        """What the Comparison screen needs of each sim, summed in the database:

        - FULL_EVALUATIONS and POSITION_REVIEWS: how many the sim made itself (rows copied in
          with its memory are not its own);
        - LLM_USD: dollars paid for its LLM calls (every call not to Jev);
        - FULL_EVALUATION_SECONDS: the seconds of every call made for one of its full
          evaluations, added up;
        - LLM_MODELS: the model names the LLM's provider returned, sorted;
        - JEV_VERSIONS: the Jev versions that answered its decisions, sorted.

        Every sim asked for is in the answer, with zeros and empty lists if it has nothing."""

    def entry_details(
        self, dataset: int, wanted: list[tuple[str, int]]
    ) -> dict[tuple[str, int], dict]:
        """What the dataset measured about each (asset, step) wanted, for the scorecard:

        - ASSET_CLASS: "stock" or "crypto";
        - PATTERNS: the 15-minute candle patterns of the pattern window ending at the step;
        - LONG_TERM_TREND and VOLUME_AGAINST_NORMAL: those measurements, None if not available;
        - BAR_NUMBER and BARS_LEFT: the bar's place in its session or UTC day (BARS_LEFT is
          None for crypto).

        A pair with no snapshot is left out."""

    def playbook(self) -> list[dict]:
        """Every `REF.PLAYBOOK` row, of every TA-Lib version stored."""

    def spending_by_item(self) -> list[dict]:
        """`SIM.CALLS` summed: one row per SIM, PURPOSE and SERVICE, with COST_USD (a call that
        failed before it was priced counts $0) and CALLS. PURPOSE is None for a sim's calls."""

    # What starting, stopping and resuming a sim needs (spec appendix 8, section 8.7). The API's
    # login may add a sim's row and change it, nothing else of a sim.

    def dataset(self, dataset_id: int) -> DatasetInfo:
        """A dataset's status, steps, periods and assets. KeyError if there is none."""

    def create(self, row: dict) -> int:
        """Add a sim's row (status created); returns its ID."""

    def update(self, sim_id: int, **columns) -> None:
        """Set columns of a sim's row; never on a finished sim."""

    # What the one checker reads (`jev_trader.sim.checker`), as `sim.store.SimStore` and
    # `sim.market.Market` describe them.

    def spent(self, sim_id: int) -> float: ...

    def sims_in_progress(self) -> list[dict]: ...

    def latest_tier_2_share(self) -> float | None: ...

    def bar_count(self, dataset_id: int, first_step: int, last_step: int) -> int: ...


# Left out of the list of every sim: large, and only the sim page needs them.
_LIST_LEAVES_OUT = ("SETTINGS", "ACCOUNT_STATE")


class InMemoryApiStore:
    """The API's reads over the in-memory sim store, plus a made-up asset key and closes.

    `closes` gives each dataset's rescaled 15-minute closes: dataset, then asset, then step.
    `entry_details` gives each dataset's `entry_details` answers, by (asset, step).
    `playbook` gives the `REF.PLAYBOOK` rows.
    `market` holds the datasets a sim can start on.
    """

    def __init__(
        self,
        sims: InMemorySimStore,
        asset_key: list[dict],
        closes: dict[int, dict[str, dict[int, float]]] | None = None,
        entry_details: dict[int, dict[tuple[str, int], dict]] | None = None,
        market: InMemoryMarket | None = None,
        playbook: list[dict] | None = None,
    ):
        self._sims = sims
        self._asset_key = asset_key
        self._closes = closes or {}
        self._entry_details = entry_details or {}
        self._playbook = playbook or []
        self._market = market or InMemoryMarket(datasets=[], bars={})

    def total_spent(self) -> float:
        return sum(r["COST_USD"] or 0.0 for r in self._sims.tables["SIM.CALLS"])

    def sims(self) -> list[dict]:
        return [
            {k: v for k, v in row.items() if k not in _LIST_LEAVES_OUT}
            | {"LLM_MODEL": llm_model_of(row.get("SETTINGS"))}
            for _, row in sorted(self._sims.sims.items())
        ]

    def sim(self, sim_id):
        row = self._sims.sims.get(sim_id)
        return None if row is None else dict(row)

    def account_values_at(self, wanted):
        found = {}
        for sim_id, step in wanted:
            row = self.account_at(sim_id, step)
            if row is not None:
                found[(sim_id, step)] = row["ACCOUNT_VALUE"]
        return found

    def account_steps(self, sim_ids, after_step=None):
        return {
            sim_id: sorted(
                (
                    dict(r)
                    for r in self._sims.rows("SIM.ACCOUNT_STEPS", sim_id)
                    if after_step is None or r["STEP"] > after_step
                ),
                key=lambda r: r["STEP"],
            )
            for sim_id in sim_ids
        }

    def account_at(self, sim_id, step):
        stored = [
            r for r in self._sims.rows("SIM.ACCOUNT_STEPS", sim_id) if r["STEP"] <= step
        ]
        return dict(max(stored, key=lambda r: r["STEP"])) if stored else None

    def orders(self, sim_id):
        return [dict(r) for r in self._sims.rows("SIM.ORDERS", sim_id)]

    def events(self, sim_id):
        return sorted(
            (dict(r) for r in self._sims.rows("SIM.SIM_EVENTS", sim_id)),
            key=lambda r: (r["STEP"], r["ID"]),
        )

    def latest_decisions(self, sim_id, limit):
        rows = sorted(
            self._sims.rows("MEMORY.DECISIONS", sim_id),
            key=lambda r: (-r["STEP"], r["ASSET"]),
        )
        return [dict(r) for r in rows[:limit]]

    def closes_at(self, dataset, step):
        found = {}
        for asset, closes in self._closes.get(dataset, {}).items():
            earlier = [s for s in closes if s <= step]
            if earlier:
                found[asset] = closes[max(earlier)]
        return found

    def trades_by_sim(self) -> dict[int, int]:
        positions: dict[int, set] = {}
        for row in self._sims.tables["SIM.ORDERS"]:
            if row["KIND"] == "entry" and row["STATUS"] == "carried out":
                positions.setdefault(row["SIM"], set()).add(row["POSITION"])
        return {sim_id: len(found) for sim_id, found in positions.items()}

    def spent_by_sim(self) -> dict[int, float]:
        spent: dict[int, float] = {}
        for row in self._sims.tables["SIM.CALLS"]:
            if row["SIM"] is not None:
                spent[row["SIM"]] = spent.get(row["SIM"], 0.0) + (
                    row["COST_USD"] or 0.0
                )
        return spent

    def spent_on(self, sim_id):
        return self.spent_by_sim().get(sim_id, 0.0)

    def asset_key(self) -> list[dict]:
        return [dict(row) for row in self._asset_key]

    def charges(self, sim_id):
        return sorted(
            (dict(r) for r in self._sims.rows("SIM.CHARGES", sim_id)),
            key=lambda r: (r["STEP"], r["ID"]),
        )

    def decisions(self, sim_id):
        return sorted(
            (
                {k: v for k, v in r.items() if k != "CANDIDATE_TRADES"}
                for r in self._sims.rows("MEMORY.DECISIONS", sim_id)
            ),
            key=lambda r: (r["STEP"], r["ASSET"]),
        )

    def calls(self, sim_id):
        return [dict(r) for r in self._sims.rows("SIM.CALLS", sim_id)]

    def comparison_figures(self, sim_ids):
        found = {}
        for sim_id in sim_ids:
            own = {
                r["ID"]: r
                for r in self._sims.rows("MEMORY.DECISIONS", sim_id)
                if r.get("FIRST_WRITTEN_BY", sim_id) == sim_id
            }
            calls = self._sims.rows("SIM.CALLS", sim_id)
            llm = [c for c in calls if c["SERVICE"] != JEV_SERVICE]
            found[sim_id] = {
                "FULL_EVALUATIONS": sum(
                    r["KIND"] == KIND_FULL_EVALUATION for r in own.values()
                ),
                "POSITION_REVIEWS": sum(
                    r["KIND"] == KIND_POSITION_REVIEW for r in own.values()
                ),
                "LLM_USD": sum(c["COST_USD"] or 0.0 for c in llm),
                "FULL_EVALUATION_SECONDS": sum(
                    c["LATENCY_SECONDS"] or 0.0
                    for c in calls
                    if c.get("DECISION") in own
                    and own[c["DECISION"]]["KIND"] == KIND_FULL_EVALUATION
                ),
                "LLM_MODELS": sorted({c["MODEL"] for c in llm if c.get("MODEL")}),
                "JEV_VERSIONS": sorted(
                    {r["JEV_VERSION"] for r in own.values() if r.get("JEV_VERSION")}
                ),
            }
        return found

    def entry_details(self, dataset, wanted):
        known = self._entry_details.get(dataset, {})
        return {pair: dict(known[pair]) for pair in wanted if pair in known}

    def playbook(self) -> list[dict]:
        return [dict(row) for row in self._playbook]

    def spending_by_item(self) -> list[dict]:
        summed: dict[tuple, dict] = {}
        for row in self._sims.tables["SIM.CALLS"]:
            purpose = None if row["SIM"] is not None else row["PURPOSE"]
            key = (row["SIM"], purpose, row["SERVICE"])
            found = summed.setdefault(
                key,
                {
                    "SIM": key[0],
                    "PURPOSE": key[1],
                    "SERVICE": key[2],
                    "COST_USD": 0.0,
                    "CALLS": 0,
                },
            )
            found["COST_USD"] += row["COST_USD"] or 0.0
            found["CALLS"] += 1
        return list(summed.values())

    def dataset(self, dataset_id):
        return self._market.dataset(dataset_id)

    def create(self, row):
        return self._sims.create(row)

    def update(self, sim_id, **columns):
        self._sims.update(sim_id, **columns)

    def spent(self, sim_id):
        return self._sims.spent(sim_id)

    def sims_in_progress(self):
        return self._sims.sims_in_progress()

    def latest_tier_2_share(self):
        return self._sims.latest_tier_2_share()

    def bar_count(self, dataset_id, first_step, last_step):
        return self._market.bar_count(dataset_id, first_step, last_step)
