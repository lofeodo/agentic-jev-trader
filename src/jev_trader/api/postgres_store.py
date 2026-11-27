"""The API's reads from Postgres, as the API login: the same tables as in Snowflake.

What the API shares with the dataset builder and the sim (adding and changing a dataset's or a
sim's row, one sim's whole row, what the checker reads) goes through their Postgres stores, as
in Snowflake. `connection` is the process's one connection
(`jev_trader.storage.postgres.connection`), with `%s` placeholders.

Postgres hands column names back in lower case; each row here is keyed by the upper-case names
the Snowflake store gives, so what the API answers does not change. JSON columns (`jsonb`) come
back already read. A list of (sim, step) or (asset, step) pairs goes over as two lists, paired
up again in the query by `unnest`, so a long list is still one statement.
"""

import json

from jev_trader.api.llm_names import llm_model_of
from jev_trader.api.store import DATASET_COLUMNS, DATASET_READS, JEV_SERVICE
from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.postgres_store import PostgresStore as DatasetStore
from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.sim.market import DatasetInfo
from jev_trader.sim.postgres_store import OWN_ROWS, PostgresMarket, PostgresSimStore
from jev_trader.sim.store import KIND_FULL_EVALUATION, KIND_POSITION_REVIEW

_LONG_TERM_TREND = MEASUREMENT_NAMES.index("long_term_trend")
_VOLUME_AGAINST_NORMAL = MEASUREMENT_NAMES.index("volume_against_normal")

# Every column of a decision but its candidate trades, which no report needs.
_DECISION_COLUMNS = (
    "ID",
    "STEP",
    "ASSET",
    "KIND",
    "TIER",
    "SCREEN_ANSWER",
    "SKIPPED_BECAUSE",
    "ACTION",
    "PICK",
    "RATING",
    "SIZE_CHOSEN",
    "SIZE_AFTER_TRIMMING",
    "LIMITED_BY",
    "ANSWERS",
)

_ACCOUNT_COLUMNS = (
    "SIM",
    "STEP",
    "CASH",
    "LOAN",
    "EXPOSURE",
    "ACCOUNT_VALUE",
    "START_OF_DAY_VALUE",
    "DAILY_LOSS_REACHED",
)

_SIM_COLUMNS = (
    "ID",
    "DATASET",
    "KIND",
    "VARIANT",
    "REPEAT_NUMBER",
    "MARKET",
    "FIRST_STEP",
    "LAST_STEP",
    "STARTING_VALUE",
    "SPENDING_CAP",
    "STATUS",
    "STOP_REASON",
    "LAST_COMPLETED_STEP",
    "STARTED_AT",
    "LAST_WRITTEN_AT",
)


def _sorted_without_nulls(items) -> list[str]:
    """An aggregated list (None when nothing was aggregated) sorted, NULLs dropped."""
    return sorted(item for item in items or [] if item is not None)


class PostgresApiStore:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()) -> list[tuple]:
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _rows(self, sql: str, params=()) -> list[dict]:
        """The rows, each keyed by its columns' names in upper case."""
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            names = [d.name.upper() for d in cur.description]
            return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def total_spent(self) -> float:
        [(spent,)] = self._run("SELECT COALESCE(SUM(cost_usd), 0) FROM sim.calls")
        return float(spent)

    def sims(self) -> list[dict]:
        rows = self._run(
            f"SELECT {', '.join(_SIM_COLUMNS)}, settings -> 'llm' ->> 'model' "
            "FROM sim.sims ORDER BY id"
        )
        found = []
        for *columns, model in rows:
            row = dict(zip(_SIM_COLUMNS, columns, strict=True))
            row["LLM_MODEL"] = llm_model_of({"llm": {"model": model}})
            found.append(row)
        return found

    def sim(self, sim_id: int) -> dict | None:
        try:
            return PostgresSimStore(self.con).sim(sim_id)
        except KeyError:
            return None

    def account_values_at(
        self, wanted: list[tuple[int, int]]
    ) -> dict[tuple[int, int], float]:
        pairs = sorted(set(wanted))
        if not pairs:
            return {}
        rows = self._run(
            "SELECT DISTINCT ON (w.sim, w.step) w.sim, w.step, a.account_value "
            "FROM unnest(%s::bigint[], %s::bigint[]) AS w(sim, step) "
            "JOIN sim.account_steps a ON a.sim = w.sim AND a.step <= w.step "
            "ORDER BY w.sim, w.step, a.step DESC",
            ([sim for sim, _ in pairs], [step for _, step in pairs]),
        )
        return {(int(sim), int(step)): value for sim, step, value in rows}

    def account_steps(
        self, sim_ids: list[int], after_step: int | None = None
    ) -> dict[int, list[dict]]:
        found: dict[int, list[dict]] = {sim_id: [] for sim_id in sim_ids}
        if not sim_ids:
            return found
        rows = self._rows(
            f"SELECT {', '.join(_ACCOUNT_COLUMNS)} FROM sim.account_steps "
            "WHERE sim = ANY(%s::bigint[]) AND step > %s ORDER BY sim, step",
            (list(sim_ids), -1 if after_step is None else after_step),
        )
        for row in rows:
            found[int(row["SIM"])].append(row)
        return found

    def account_at(self, sim_id: int, step: int) -> dict | None:
        rows = self._rows(
            f"SELECT {', '.join(_ACCOUNT_COLUMNS)} FROM sim.account_steps "
            "WHERE sim = %s AND step <= %s ORDER BY step DESC LIMIT 1",
            (sim_id, step),
        )
        return rows[0] if rows else None

    def orders(self, sim_id: int) -> list[dict]:
        return self._rows("SELECT * FROM sim.orders WHERE sim = %s", (sim_id,))

    def events(self, sim_id: int) -> list[dict]:
        return self._rows(
            "SELECT id, sim, step, kind, details FROM sim.sim_events "
            "WHERE sim = %s ORDER BY step, id",
            (sim_id,),
        )

    def latest_decisions(self, sim_id: int, limit: int) -> list[dict]:
        return self._rows(
            "SELECT id, step, asset, kind, tier, screen_answer, skipped_because, action "
            f"FROM memory.decisions WHERE {OWN_ROWS} "
            "ORDER BY step DESC, asset LIMIT %s",
            (sim_id, limit),
        )

    def closes_at(self, dataset: int, step: int) -> dict[str, float]:
        rows = self._run(
            "SELECT DISTINCT ON (asset) asset, close FROM raw.bars "
            "WHERE dataset = %s AND bar_size = '15m' AND step <= %s "
            "ORDER BY asset, step DESC",
            (dataset, step),
        )
        return {asset: float(close) for asset, close in rows}

    def trades_by_sim(self) -> dict[int, int]:
        rows = self._run(
            "SELECT sim, COUNT(DISTINCT position) FROM sim.orders "
            "WHERE kind = 'entry' AND status = 'carried out' GROUP BY sim"
        )
        return {int(sim_id): int(count) for sim_id, count in rows}

    def spent_by_sim(self) -> dict[int, float]:
        rows = self._run(
            "SELECT sim, COALESCE(SUM(cost_usd), 0) FROM sim.calls "
            "WHERE sim IS NOT NULL GROUP BY sim"
        )
        return {int(sim_id): float(spent) for sim_id, spent in rows}

    def spent_on(self, sim_id: int) -> float:
        [(spent,)] = self._run(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM sim.calls WHERE sim = %s", (sim_id,)
        )
        return float(spent)

    def asset_key(self) -> list[dict]:
        return self._rows(
            "SELECT dataset, masked_id, ticker, name, price_scale, first_day "
            "FROM keys.asset_key"
        )

    def charges(self, sim_id: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM sim.charges WHERE sim = %s ORDER BY step, id", (sim_id,)
        )

    def decisions(self, sim_id: int) -> list[dict]:
        return self._rows(
            f"SELECT {', '.join(_DECISION_COLUMNS)} FROM memory.decisions "
            f"WHERE {OWN_ROWS} ORDER BY step, asset",
            (sim_id,),
        )

    def calls(self, sim_id: int) -> list[dict]:
        return self._rows(
            "SELECT decision, purpose, cost_usd, latency_seconds FROM sim.calls "
            "WHERE sim = %s",
            (sim_id,),
        )

    def decision(self, sim_id: int, decision_id: str) -> dict | None:
        rows = self._rows(
            f"SELECT * FROM memory.decisions WHERE {OWN_ROWS} AND id = %s",
            (sim_id, decision_id),
        )
        return rows[0] if rows else None

    def position_decisions(self, sim_id: int, position: int) -> list[dict]:
        rows = self._rows(
            f"SELECT * FROM memory.decisions WHERE {OWN_ROWS} AND position = %s "
            "ORDER BY step",
            (sim_id, position),
        )
        for row in rows:
            del row["CANDIDATE_TRADES"]
        return rows

    def jev_requests(self, sim_id: int, decision_ids: list[str]) -> list[dict]:
        if not decision_ids:
            return []
        return self._rows(
            "SELECT r.*, j.opening FROM sim.jev_requests r "
            "LEFT JOIN sim.jev_readings j ON j.reading_version = r.reading_version "
            "WHERE r.sim = %s AND r.decision = ANY(%s::text[]) ORDER BY r.id",
            (sim_id, list(decision_ids)),
        )

    def llm_exchange(self, sim_id: int, decision_id: str) -> dict | None:
        rows = self._rows(
            "SELECT e.*, p.system_prompt AS system_prompts, p.tools "
            "FROM sim.llm_exchanges e "
            "LEFT JOIN sim.llm_prompts p ON p.prompt_version = e.prompt_version "
            "WHERE e.sim = %s AND e.decision = %s",
            (sim_id, decision_id),
        )
        if not rows:
            return None
        row = rows[0]
        # The system prompts are JSON kept as text; every other JSON column is `jsonb`.
        prompts = row["SYSTEM_PROMPTS"]
        row["SYSTEM_PROMPTS"] = json.loads(prompts) if prompts else {}
        row["TOOLS"] = row["TOOLS"] or {}
        return row

    def closes(
        self, dataset: int, asset: str, first_step: int, last_step: int
    ) -> dict[int, float]:
        rows = self._run(
            "SELECT step, close FROM raw.bars WHERE dataset = %s AND asset = %s "
            "AND bar_size = '15m' AND step BETWEEN %s AND %s ORDER BY step",
            (dataset, asset, first_step, last_step),
        )
        return {int(step): float(close) for step, close in rows}

    def comparison_figures(self, sim_ids: list[int]) -> dict[int, dict]:
        found = {
            sim_id: {
                "FULL_EVALUATIONS": 0,
                "POSITION_REVIEWS": 0,
                "MODEL_USD": 0.0,
                "FULL_EVALUATION_SECONDS": 0.0,
                "LLM_MODELS": [],
                "JEV_VERSIONS": [],
            }
            for sim_id in sim_ids
        }
        if not sim_ids:
            return found
        ids = list(sim_ids)
        # A sim's own decisions: rows copied in with its memory were written by another sim.
        for sim_id, evaluations, reviews, versions in self._run(
            "SELECT sim, COUNT(*) FILTER (WHERE kind = %s), "
            "COUNT(*) FILTER (WHERE kind = %s), ARRAY_AGG(DISTINCT jev_version) "
            "FROM memory.decisions WHERE sim = ANY(%s::bigint[]) "
            "AND first_written_by = sim GROUP BY sim",
            (KIND_FULL_EVALUATION, KIND_POSITION_REVIEW, ids),
        ):
            figures = found[int(sim_id)]
            figures["FULL_EVALUATIONS"] = int(evaluations)
            figures["POSITION_REVIEWS"] = int(reviews)
            figures["JEV_VERSIONS"] = _sorted_without_nulls(versions)
        for sim_id, model_usd, seconds, models in self._run(
            "SELECT c.sim, COALESCE(SUM(c.cost_usd), 0), "
            "COALESCE(SUM(CASE WHEN d.kind = %s "
            "THEN COALESCE(c.latency_seconds, 0) ELSE 0 END), 0), "
            "ARRAY_AGG(DISTINCT c.model) FILTER (WHERE c.service <> %s) "
            "FROM sim.calls c LEFT JOIN memory.decisions d "
            "ON d.sim = c.sim AND d.id = c.decision AND d.first_written_by = c.sim "
            "WHERE c.sim = ANY(%s::bigint[]) GROUP BY c.sim",
            (KIND_FULL_EVALUATION, JEV_SERVICE, ids),
        ):
            figures = found[int(sim_id)]
            figures["MODEL_USD"] = float(model_usd)
            figures["FULL_EVALUATION_SECONDS"] = float(seconds)
            figures["LLM_MODELS"] = _sorted_without_nulls(models)
        return found

    def entry_details(
        self, dataset: int, wanted: list[tuple[str, int]]
    ) -> dict[tuple[str, int], dict]:
        found: dict[tuple[str, int], dict] = {}
        pairs = sorted(set(wanted))
        if not pairs:
            return found
        assets_and_steps = ([asset for asset, _ in pairs], [step for _, step in pairs])
        wanted_rows = "unnest(%s::text[], %s::bigint[]) AS w(asset, step)"
        for asset, step, asset_class, trend, volume, bar, left in self._run(
            "SELECT w.asset, w.step, a.asset_class, "
            f"(s.measurements ->> {_LONG_TERM_TREND})::double precision, "
            f"(s.measurements ->> {_VOLUME_AGAINST_NORMAL})::double precision, "
            "b.bar_number, b.bars_left "
            f"FROM {wanted_rows} "
            "JOIN features.snapshots s ON s.dataset = %s AND s.asset = w.asset "
            "AND s.step = w.step "
            "JOIN raw.bars b ON b.dataset = s.dataset AND b.asset = s.asset "
            "AND b.step = s.step AND b.bar_size = '15m' "
            "JOIN ref.assets a ON a.dataset = s.dataset AND a.masked_id = s.asset",
            (*assets_and_steps, dataset),
        ):
            found[(asset, int(step))] = {
                "ASSET_CLASS": asset_class,
                "PATTERNS": [],
                "LONG_TERM_TREND": trend,
                "VOLUME_AGAINST_NORMAL": volume,
                "BAR_NUMBER": int(bar),
                "BARS_LEFT": None if left is None else int(left),
            }
        # Newest bar first, as the situation text lists them.
        for asset, step, pattern in self._run(
            "SELECT w.asset, w.step, p.pattern "
            f"FROM {wanted_rows} "
            "JOIN features.patterns p ON p.dataset = %s AND p.asset = w.asset "
            "AND p.bar_size = '15m' "
            f"AND p.step BETWEEN w.step - {PATTERN_WINDOW_STEPS - 1} AND w.step "
            "ORDER BY w.asset, w.step, p.step DESC, p.pattern",
            (*assets_and_steps, dataset),
        ):
            names = found.get((asset, int(step)), {}).get("PATTERNS")
            if names is not None and pattern not in names:
                names.append(pattern)
        return found

    def playbook(self) -> list[dict]:
        return self._rows(
            "SELECT talib_version, pattern, lean, name, shape FROM ref.playbook"
        )

    def spending_by_item(self) -> list[dict]:
        rows = self._rows(
            "SELECT sim, CASE WHEN sim IS NULL THEN purpose END AS purpose, service, "
            "COALESCE(SUM(cost_usd), 0) AS cost_usd, COUNT(*) AS calls "
            "FROM sim.calls GROUP BY 1, 2, 3"
        )
        return [
            {
                "SIM": None if r["SIM"] is None else int(r["SIM"]),
                "PURPOSE": r["PURPOSE"],
                "SERVICE": r["SERVICE"],
                "COST_USD": float(r["COST_USD"]),
                "CALLS": int(r["CALLS"]),
            }
            for r in rows
        ]

    def datasets(self) -> list[dict]:
        return self._rows(
            f"SELECT {', '.join(DATASET_COLUMNS)} FROM ref.datasets ORDER BY id DESC"
        )

    def dataset_rows(self, table: str, dataset_id: int) -> list[dict]:
        if table not in DATASET_READS:
            raise ValueError(f"the API does not read {table} whole")
        return self._rows(f"SELECT * FROM {table} WHERE dataset = %s", (dataset_id,))

    def daily_bars(self, dataset_id: int, asset: str) -> list[dict]:
        return self._rows(
            "SELECT step, day, close FROM raw.bars "
            "WHERE dataset = %s AND asset = %s AND bar_size = '1d' ORDER BY step",
            (dataset_id, asset),
        )

    # Shared with the dataset builder and the sim, through their stores.

    def begin_dataset(self, name: str, columns: dict) -> tuple[int, int]:
        return DatasetStore(self.con).begin(name, columns)

    def update_dataset(self, dataset_id: int, **columns) -> None:
        DatasetStore(self.con).update(dataset_id, **columns)

    def dataset(self, dataset_id: int) -> DatasetInfo:
        return PostgresMarket(self.con).dataset(dataset_id)

    def create(self, row: dict) -> int:
        return PostgresSimStore(self.con).create(row)

    def update(self, sim_id: int, **columns) -> None:
        PostgresSimStore(self.con).update(sim_id, **columns)

    def spent(self, sim_id: int) -> float:
        return self.spent_on(sim_id)

    def sims_in_progress(self) -> list[dict]:
        return PostgresSimStore(self.con).sims_in_progress()

    def latest_tier_2_share(self) -> float | None:
        return PostgresSimStore(self.con).latest_tier_2_share()

    def base_memory_sim(self, dataset: int) -> int | None:
        return PostgresSimStore(self.con).base_memory_sim(dataset)

    def memory_last_step(self, sim_id: int) -> int | None:
        return PostgresSimStore(self.con).memory_last_step(sim_id)

    def bar_count(self, dataset_id: int, first_step: int, last_step: int) -> int:
        return PostgresMarket(self.con).bar_count(dataset_id, first_step, last_step)
