"""The sim's store and market in Postgres, as the sim login: the same tables as in Snowflake.

`connection` is the process's one connection (`jev_trader.storage.postgres.connection`), with
`%s` placeholders; the store and the market share it. Lists and dictionaries go into `jsonb`
columns. Postgres hands column names back in lower case: a sim's row is keyed in upper case,
as Snowflake's was.

**The save** (spec appendix 6, section 6; appendix 11, section 4). `write_steps` sends its
statements in one round trip (`transaction_in_one_trip`): begin; the guard; the sim's row, its
last completed step moved and its account saved; each table's new rows; the outcomes now
known; commit. The guard locks the sim's row and fails, inside the database, unless the last
completed step still reads what the writer last saw and the sim is running: a second copy of
the sim waits for the first one's save to end, then finds the step moved, and its whole save
is thrown away. If the program dies with its save under way, Postgres throws the save away
when the connection drops.

An order's row is rewritten as it goes from waiting to carried out or cancelled: an order
whose ID is stored replaces its row (`ON CONFLICT ... DO UPDATE`), and every other row is
added. Snowflake's `MERGE ... WHEN NOT MATCHED` (store once) is `ON CONFLICT DO NOTHING`, and
`COUNT_IF(x)` is `COUNT(*) FILTER (WHERE x)`, which counts no rows as 0.
"""

import json

import psycopg

from jev_trader.broker import AssetClass, Bar
from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.dataset.snapshots import FoundPatterns
from jev_trader.sim.market import (
    BarsByStep,
    DatasetInfo,
    Period,
    Playbook,
    Snapshot,
    SnapshotsByStep,
)
from jev_trader.sim.store import (
    ACTION_ADD,
    ACTION_CLOSE,
    ACTION_ENTRY,
    ACTION_REDUCE,
    IN_PROGRESS,
    KIND_FULL_EVALUATION,
    KIND_POSITION_REVIEW,
    KIND_SCREEN,
    MEMORY_TABLES,
    POSITION_KINDS,
    REPLACED_BY_ID,
    SCREENED_KINDS,
    TABLES,
    SimStatus,
    StepAlreadyWritten,
    now,
)
from jev_trader.storage.postgres import as_param, set_clause

# The bars a sim steps through: one per asset per step.
FIFTEEN_MINUTES = "15m"
# Where the typical move, as a share of the price, sits in a snapshot's measurements (from 0).
_TYPICAL_MOVE = MEASUREMENT_NAMES.index("typical_move_share_of_price")
# A sim's own rows of a memory table, bound to its ID: those it wrote, not those it copied from
# the memory it started from. Every report on what one sim did reads through this.
OWN_ROWS = "SIM = %s AND FIRST_WRITTEN_BY = SIM"
# What the save's guard says when it stops the save.
_NOT_AFTER = "step already written"


def _guard(sim_id: int, after_step: int | None) -> str:
    """The save's first statement: lock the sim's row, and fail unless its last completed step
    still reads `after_step` and it is running. A `DO` block, so the check runs inside the
    database; it takes no bound values, so both numbers are written in as whole numbers."""
    after = "NULL" if after_step is None else str(int(after_step))
    return (
        "DO $$ BEGIN PERFORM 1 FROM SIM.SIMS "
        f"WHERE ID = {int(sim_id)} AND LAST_COMPLETED_STEP IS NOT DISTINCT FROM {after} "
        f"AND STATUS = '{SimStatus.RUNNING}' FOR UPDATE; "
        f"IF NOT FOUND THEN RAISE EXCEPTION '{_NOT_AFTER}'; END IF; END $$"
    )


def _insert(cur, table: str, rows: list[dict]) -> None:
    """Rows that share their columns; an order replaces its earlier row of the same ID."""
    columns = list(rows[0])
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join('%s' for _ in columns)})"
    )
    if table in REPLACED_BY_ID:
        sql += " ON CONFLICT (ID) DO UPDATE SET " + ", ".join(
            f"{c} = EXCLUDED.{c}" for c in columns if c != "ID"
        )
    cur.executemany(sql, [[as_param(r[c]) for c in columns] for r in rows])


class _Connection:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()):
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []


class PostgresSimStore(_Connection):
    def create(self, row: dict) -> int:
        row = {"STATUS": str(SimStatus.CREATED), "CREATED_AT": now(), **row}
        [(sim_id,)] = self._run(
            f"INSERT INTO SIM.SIMS (ID, {', '.join(row)}) "
            f"VALUES (nextval('SIM.SIM_IDS'), {', '.join('%s' for _ in row)}) "
            "RETURNING ID",
            [as_param(v) for v in row.values()],
        )
        return sim_id

    def sim(self, sim_id: int) -> dict:
        with self.con.cursor() as cur:
            cur.execute("SELECT * FROM SIM.SIMS WHERE ID = %s", (sim_id,))
            found = cur.fetchone()
            if found is None:
                raise KeyError(f"no sim {sim_id}")
            names = [d.name.upper() for d in cur.description]
        return dict(zip(names, found, strict=True))

    def update(self, sim_id: int, **columns) -> None:
        sets, values = set_clause(columns)
        self._run(
            f"UPDATE SIM.SIMS SET {sets} WHERE ID = %s AND STATUS <> %s",
            [*values, sim_id, str(SimStatus.FINISHED)],
        )

    def write_steps(
        self,
        sim_id: int,
        after_step: int | None,
        through_step: int,
        rows: dict[str, list[dict]],
        state: dict,
        outcomes_known: dict[str, int] | None = None,
    ) -> None:
        try:
            with self.con.transaction_in_one_trip() as cur:
                cur.execute(_guard(sim_id, after_step))
                cur.execute(
                    "UPDATE SIM.SIMS SET LAST_COMPLETED_STEP = %s, ACCOUNT_STATE = %s, "
                    "LAST_WRITTEN_AT = %s WHERE ID = %s",
                    (through_step, as_param(state), now(), sim_id),
                )
                for name in TABLES:
                    if rows.get(name):
                        _insert(cur, name, rows[name])
                if outcomes_known:
                    ids, steps = zip(*sorted(outcomes_known.items()), strict=True)
                    cur.execute(
                        "UPDATE MEMORY.DECISIONS d SET OUTCOMES_KNOWN_FROM = k.STEP "
                        "FROM unnest(%s::text[], %s::bigint[]) AS k(ID, STEP) "
                        "WHERE d.SIM = %s AND d.ID = k.ID",
                        (list(ids), list(steps), sim_id),
                    )
        except psycopg.errors.RaiseException as error:
            if error.diag.message_primary != _NOT_AFTER:
                raise
            raise StepAlreadyWritten(
                f"sim {sim_id}: its last completed step is no longer {after_step}, "
                "or it is not running"
            ) from error

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        counts = " UNION ALL ".join(
            f"SELECT '{name}', COUNT(*) FROM (SELECT ID FROM {name} WHERE SIM = %s "
            "GROUP BY ID HAVING COUNT(*) > 1) AS twice"
            for name in TABLES
        )
        return {
            name: duplicated
            for name, duplicated in self._run(counts, [sim_id] * len(TABLES))
            if duplicated
        }

    def base_memory_sim(self, dataset: int) -> int | None:
        [(sim_id,)] = self._run(
            "SELECT MAX(ID) FROM SIM.SIMS WHERE DATASET = %s AND KIND = 'build-up' "
            "AND VARIANT <> 'buy_hold' AND STATUS = %s",
            (dataset, str(SimStatus.FINISHED)),
        )
        return sim_id

    def memory_last_step(self, sim_id: int) -> int | None:
        [(latest,)] = self._run(
            "SELECT MAX(STEP) FROM ("
            "SELECT GREATEST(STEP, OUTCOMES_KNOWN_FROM) AS STEP "
            "FROM MEMORY.DECISIONS WHERE SIM = %s "
            "UNION ALL SELECT KNOWN_FROM FROM MEMORY.OUTCOMES WHERE SIM = %s) AS steps",
            (sim_id, sim_id),
        )
        return latest

    def start_with_memory(self, sim_id: int, memory_from: int, **columns) -> None:
        """One transaction: the row's UPDATE (which matches only a sim with no step stored that
        is not finished) first, then per memory table a DELETE of what the sim's memory held and
        an INSERT ... SELECT of the source's rows with SIM changed. The columns are read from
        the table, so a column added later is copied too."""
        sets, values = set_clause(columns)
        with self.con.transaction(), self.con.cursor() as cur:
            cur.execute(
                f"UPDATE SIM.SIMS SET {sets} WHERE ID = %s "
                "AND LAST_COMPLETED_STEP IS NULL AND STATUS <> %s",
                [*values, sim_id, str(SimStatus.FINISHED)],
            )
            if cur.rowcount != 1:
                raise StepAlreadyWritten(
                    f"sim {sim_id} has stored a step or is finished: its memory is "
                    "not copied again"
                )
            for table in MEMORY_TABLES:
                cur.execute(f"SELECT * FROM {table} LIMIT 0")
                names = [d.name for d in cur.description]
                picked = ", ".join("%s" if n == "sim" else n for n in names)
                cur.execute(f"DELETE FROM {table} WHERE SIM = %s", (sim_id,))
                cur.execute(
                    f"INSERT INTO {table} ({', '.join(names)}) "
                    f"SELECT {picked} FROM {table} WHERE SIM = %s",
                    (sim_id, memory_from),
                )

    def save_reading(self, version: str, opening: str) -> None:
        self._run(
            "INSERT INTO SIM.JEV_READINGS (READING_VERSION, OPENING, CREATED_AT) "
            "VALUES (%s, %s, %s) ON CONFLICT (READING_VERSION) DO NOTHING",
            (version, opening, now()),
        )

    def save_prompt(
        self,
        version: str,
        system_prompts: dict[str, str],
        tools: dict[str, list[dict]],
    ) -> None:
        """SYSTEM_PROMPT holds both jobs' standing instructions as JSON text, by job, and TOOLS
        both jobs' tools, by job."""
        self._run(
            "INSERT INTO SIM.LLM_PROMPTS (PROMPT_VERSION, SYSTEM_PROMPT, TOOLS, CREATED_AT) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (PROMPT_VERSION) DO NOTHING",
            (version, json.dumps(system_prompts), as_param(tools), now()),
        )

    def spent(self, sim_id: int) -> float:
        [(total,)] = self._run(
            "SELECT COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS WHERE SIM = %s", (sim_id,)
        )
        return float(total)

    def total_spent(self) -> float:
        [(total,)] = self._run("SELECT COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS")
        return float(total)

    def sims_in_progress(self) -> list[dict]:
        columns = ("ID", "KIND", "VARIANT", "STATUS", "SPENDING_CAP", "SPENT")
        rows = self._run(
            "SELECT s.ID, s.KIND, s.VARIANT, s.STATUS, s.SPENDING_CAP, "
            "COALESCE(SUM(c.COST_USD), 0) FROM SIM.SIMS s "
            "LEFT JOIN SIM.CALLS c ON c.SIM = s.ID WHERE s.STATUS IN (%s, %s) "
            "GROUP BY s.ID, s.KIND, s.VARIANT, s.STATUS, s.SPENDING_CAP ORDER BY s.ID",
            IN_PROGRESS,
        )
        return [
            {**dict(zip(columns, row, strict=True)), "SPENT": float(row[-1])}
            for row in rows
        ]

    def latest_tier_2_share(self) -> float | None:
        found = self._run(
            "SELECT COUNT(*) FILTER (WHERE d.KIND = %s)::float / COUNT(*) "
            "FROM MEMORY.DECISIONS d JOIN SIM.SIMS s ON s.ID = d.SIM "
            "WHERE s.KIND = 'practice' AND s.VARIANT <> 'buy_hold' AND d.KIND IN (%s, %s) "
            "AND d.FIRST_WRITTEN_BY = d.SIM "
            "GROUP BY d.SIM ORDER BY d.SIM DESC LIMIT 1",
            (KIND_FULL_EVALUATION, KIND_SCREEN, KIND_FULL_EVALUATION),
        )
        return float(found[0][0]) if found else None

    def _screen_answer_counts(
        self, sim_id: int, cut_off: float, kinds
    ) -> tuple[int, int]:
        [(asked, yes)] = self._run(
            "SELECT COUNT(SCREEN_ANSWER), COUNT(*) FILTER (WHERE SCREEN_ANSWER >= %s) "
            f"FROM MEMORY.DECISIONS WHERE {OWN_ROWS} AND KIND IN (%s, %s)",
            (cut_off, sim_id, *kinds),
        )
        return int(asked), int(yes)

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        return self._screen_answer_counts(sim_id, cut_off, SCREENED_KINDS)

    def position_screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        return self._screen_answer_counts(sim_id, cut_off, POSITION_KINDS)

    def position_review_counts(self, sim_id: int) -> dict[str, int]:
        [(reviews, end_of_session, closes, reduces, adds)] = self._run(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE END_OF_SESSION), "
            "COUNT(*) FILTER (WHERE ACTION = %s), COUNT(*) FILTER (WHERE ACTION = %s), "
            "COUNT(*) FILTER (WHERE ACTION = %s) FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} AND KIND = %s",
            (ACTION_CLOSE, ACTION_REDUCE, ACTION_ADD, sim_id, KIND_POSITION_REVIEW),
        )
        return {
            "reviews": reviews,
            "end_of_session": end_of_session,
            ACTION_CLOSE: closes,
            ACTION_REDUCE: reduces,
            ACTION_ADD: adds,
        }

    def full_evaluation_counts(self, sim_id: int) -> tuple[int, int]:
        [(evaluations, entries)] = self._run(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE ACTION = %s) FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} AND KIND = %s",
            (ACTION_ENTRY, sim_id, KIND_FULL_EVALUATION),
        )
        return evaluations, entries


class PostgresMarket(_Connection):
    def dataset(self, dataset_id: int) -> DatasetInfo:
        found = self._run(
            "SELECT STATUS, FIRST_STEP, LAST_STEP FROM REF.DATASETS WHERE ID = %s",
            (dataset_id,),
        )
        if not found:
            raise KeyError(f"no dataset {dataset_id}")
        [(status, first_step, last_step)] = found
        periods = self._run(
            "SELECT KIND, NAME, FIRST_STEP, LAST_STEP FROM REF.DATASET_PERIODS "
            "WHERE DATASET = %s ORDER BY FIRST_STEP",
            (dataset_id,),
        )
        assets = self._run(
            "SELECT MASKED_ID, ASSET_CLASS FROM REF.ASSETS WHERE DATASET = %s "
            "ORDER BY MASKED_ID",
            (dataset_id,),
        )
        return DatasetInfo(
            dataset_id=dataset_id,
            status=status,
            first_step=first_step,
            last_step=last_step,
            periods=tuple(Period(*p) for p in periods),
            assets={masked: AssetClass(cls) for masked, cls in assets},
        )

    def bar_count(self, dataset_id: int, first_step: int, last_step: int) -> int:
        [(count,)] = self._run(
            "SELECT COUNT(*) FROM RAW.BARS "
            "WHERE DATASET = %s AND BAR_SIZE = %s AND STEP BETWEEN %s AND %s",
            (dataset_id, FIFTEEN_MINUTES, first_step, last_step),
        )
        return count

    def bars(self, dataset_id: int, first_step: int, last_step: int) -> BarsByStep:
        by_step: BarsByStep = {}
        for asset, step, open_, high, low, close in self._run(
            "SELECT ASSET, STEP, OPEN, HIGH, LOW, CLOSE FROM RAW.BARS "
            "WHERE DATASET = %s AND BAR_SIZE = %s AND STEP BETWEEN %s AND %s "
            "ORDER BY STEP, ASSET",
            (dataset_id, FIFTEEN_MINUTES, first_step, last_step),
        ):
            by_step.setdefault(step, {})[asset] = Bar(step, open_, high, low, close)
        return by_step

    def snapshots(
        self, dataset_id: int, first_step: int, last_step: int
    ) -> SnapshotsByStep:
        found = self._found_patterns(dataset_id, first_step, last_step)
        by_step: SnapshotsByStep = {}
        for asset, step, situation, share, bars_left, close in self._run(
            "SELECT s.ASSET, s.STEP, s.SITUATION_TEXT, "
            f"(s.MEASUREMENTS ->> {_TYPICAL_MOVE})::float, b.BARS_LEFT, b.CLOSE "
            "FROM FEATURES.SNAPSHOTS s JOIN RAW.BARS b ON b.DATASET = s.DATASET "
            "AND b.ASSET = s.ASSET AND b.STEP = s.STEP AND b.BAR_SIZE = %s "
            "WHERE s.DATASET = %s AND s.STEP BETWEEN %s AND %s",
            (FIFTEEN_MINUTES, dataset_id, first_step, last_step),
        ):
            lists = found[asset].pattern_lists(step) if asset in found else None
            window = (
                []
                if lists is None
                else [name for name, _ in sorted(lists.window, key=lambda p: p[1])]
            )
            longer = [] if lists is None else [*lists.hourly, *lists.daily]
            by_step.setdefault(step, {})[asset] = Snapshot(
                situation_text=situation,
                typical_move=None if share is None else share * close,
                bars_left=bars_left,
                patterns=tuple(dict.fromkeys(window + longer)),
                window_patterns=tuple(dict.fromkeys(window)),
            )
        return by_step

    def _found_patterns(
        self, dataset_id: int, first_step: int, last_step: int
    ) -> dict[str, FoundPatterns]:
        """Each asset's stored patterns, as the dataset build read them for its situation texts:
        the pattern window, and the latest finished hourly and daily bars."""
        ends: dict[str, dict[str, list[int]]] = {}
        for asset, size, step in self._run(
            "SELECT ASSET, BAR_SIZE, STEP FROM RAW.BARS WHERE DATASET = %s "
            "AND BAR_SIZE IN ('1h', '1d') AND STEP BETWEEN %s AND %s "
            "UNION ALL SELECT ASSET, BAR_SIZE, MAX(STEP) FROM RAW.BARS WHERE DATASET = %s "
            "AND BAR_SIZE IN ('1h', '1d') AND STEP < %s GROUP BY ASSET, BAR_SIZE",
            (dataset_id, first_step, last_step, dataset_id, first_step),
        ):
            ends.setdefault(asset, {"1h": [], "1d": []})[size].append(step)
        earliest = min(
            [first_step - PATTERN_WINDOW_STEPS + 1]
            + [s for sizes in ends.values() for steps in sizes.values() for s in steps]
        )
        names: dict[str, dict[tuple[str, int], list[str]]] = {}
        for asset, size, step, pattern in self._run(
            "SELECT ASSET, BAR_SIZE, STEP, PATTERN FROM FEATURES.PATTERNS "
            "WHERE DATASET = %s AND STEP BETWEEN %s AND %s "
            "ORDER BY ASSET, BAR_SIZE, STEP, PATTERN",
            (dataset_id, earliest, last_step),
        ):
            names.setdefault(asset, {}).setdefault((size, step), []).append(pattern)
        return {
            asset: FoundPatterns(
                names.get(asset, {}),
                {"1h": sorted(sizes["1h"]), "1d": sorted(sizes["1d"])},
            )
            for asset, sizes in ends.items()
        }

    def playbook(self, dataset_id: int) -> Playbook:
        return {
            name: (lean, shape)
            for name, lean, shape in self._run(
                "SELECT p.NAME, p.LEAN, p.SHAPE FROM REF.PLAYBOOK p "
                "JOIN REF.DATASETS d ON d.TALIB_VERSION = p.TALIB_VERSION "
                "WHERE d.ID = %s",
                (dataset_id,),
            )
        }
