"""The sim's store and market in Snowflake: the tables of `infra/migrations/V4__sim_tables.sql`.

The connection must use `?` placeholders (`jev_trader.storage.snowflake.connect` does) and log
in as the sim login, which reads REF, RAW, FEATURES and SIM and writes SIM and MEMORY.

**The step transaction** (spec appendix 6, section 6). `write_steps` opens a transaction and
first moves the sim's last completed step with an UPDATE that matches only if it still reads
what the writer last saw and the sim is running. Snowflake locks the table for that UPDATE until
the transaction ends: a second copy of the sim waits for it, then finds the step moved and stores
nothing. Other sims' writes wait their turn the same way, for the length of one write. Then the rows go in, and
the transaction commits; anything that fails rolls it all back. If the program dies with the
transaction open, Snowflake undoes it after 5 idle minutes when it blocks another transaction
(otherwise after 4 hours), so a restart may wait up to 5 minutes.

Lists and dictionaries go into VARIANT columns as JSON text read by `PARSE_JSON`, which cannot
sit in a VALUES list, so such rows go in as `INSERT ... SELECT ... FROM VALUES`.
"""

import json

from jev_trader.broker import AssetClass, Bar
from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import PATTERN_WINDOW_STEPS
from jev_trader.dataset.snapshots import FoundPatterns
from jev_trader.dataset.snowflake_store import MOST_BOUND_VALUES
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

# The bars a sim steps through: one per asset per step.
FIFTEEN_MINUTES = "15m"
# Where the typical move, as a share of the price, sits in a snapshot's measurements (from 0).
_TYPICAL_MOVE = MEASUREMENT_NAMES.index("typical_move_share_of_price")
_JSON_COLUMNS = {"SETTINGS", "ACCOUNT_STATE", "DETAILS"}
# A sim's own rows of a memory table, bound to its ID: those it wrote, not those it copied from
# the memory it started from. Every report on what one sim did reads through this.
OWN_ROWS = "SIM = ? AND FIRST_WRITTEN_BY = SIM"


def _is_json(value) -> bool:
    return isinstance(value, dict | list)


def _value(value):
    return json.dumps(value) if _is_json(value) else value


def _set_clause(columns: dict) -> tuple[str, list]:
    """An UPDATE's `SET ...` text for `columns` and the values it binds, JSON parsed."""
    sets = ", ".join(
        f"{k} = PARSE_JSON(?)" if _is_json(v) else f"{k} = ?"
        for k, v in columns.items()
    )
    return sets, [_value(v) for v in columns.values()]


class _Connection:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()):
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []


class SnowflakeSimStore(_Connection):
    def create(self, row: dict) -> int:
        [(sim_id,)] = self._run("SELECT SIM.SIM_IDS.NEXTVAL")
        row = {
            "ID": sim_id,
            "STATUS": str(SimStatus.CREATED),
            "CREATED_AT": now(),
            **row,
        }
        placeholders = ", ".join(
            "PARSE_JSON(?)" if _is_json(v) else "?" for v in row.values()
        )
        self._run(
            f"INSERT INTO SIM.SIMS ({', '.join(row)}) SELECT {placeholders}",
            [_value(v) for v in row.values()],
        )
        return sim_id

    def sim(self, sim_id: int) -> dict:
        with self.con.cursor() as cur:
            cur.execute("SELECT * FROM SIM.SIMS WHERE ID = ?", (sim_id,))
            found = cur.fetchone()
            if found is None:
                raise KeyError(f"no sim {sim_id}")
            names = [d[0] for d in cur.description]
        row = dict(zip(names, found, strict=True))
        for name in _JSON_COLUMNS & row.keys():
            if isinstance(row[name], str):
                row[name] = json.loads(row[name])
        return row

    def update(self, sim_id: int, **columns) -> None:
        sets, values = _set_clause(columns)
        self._run(
            f"UPDATE SIM.SIMS SET {sets} WHERE ID = ? AND STATUS <> ?",
            values + [sim_id, str(SimStatus.FINISHED)],
        )

    def write_steps(
        self, sim_id, after_step, through_step, rows, state, outcomes_known=None
    ) -> None:
        with self.con.cursor() as cur:
            cur.execute("BEGIN TRANSACTION")
            try:
                cur.execute(
                    "UPDATE SIM.SIMS SET LAST_COMPLETED_STEP = ?, "
                    "ACCOUNT_STATE = PARSE_JSON(?), LAST_WRITTEN_AT = ? "
                    "WHERE ID = ? AND EQUAL_NULL(LAST_COMPLETED_STEP, ?) AND STATUS = ?",
                    (
                        through_step,
                        json.dumps(state),
                        now(),
                        sim_id,
                        after_step,
                        str(SimStatus.RUNNING),
                    ),
                )
                if cur.rowcount != 1:
                    raise StepAlreadyWritten(
                        f"sim {sim_id}: its last completed step is no longer {after_step}, "
                        "or it is not running"
                    )
                for name in TABLES:
                    table_rows = rows.get(name, [])
                    if not table_rows:
                        continue
                    if name in REPLACED_BY_ID:
                        _delete_ids(cur, name, sim_id, [r["ID"] for r in table_rows])
                    _insert(cur, name, table_rows)
                if outcomes_known:
                    _set_outcomes_known(cur, sim_id, outcomes_known)
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise

    def duplicate_ids(self, sim_id: int) -> dict[str, int]:
        found = {}
        for name in TABLES:
            [(duplicated,)] = self._run(
                f"SELECT COUNT(*) FROM (SELECT ID FROM {name} WHERE SIM = ? "
                "GROUP BY ID HAVING COUNT(*) > 1)",
                (sim_id,),
            )
            if duplicated:
                found[name] = duplicated
        return found

    def base_memory_sim(self, dataset: int) -> int | None:
        [(sim_id,)] = self._run(
            "SELECT MAX(ID) FROM SIM.SIMS WHERE DATASET = ? AND KIND = 'build-up' "
            "AND STATUS = ?",
            (dataset, str(SimStatus.FINISHED)),
        )
        return sim_id

    def memory_last_step(self, sim_id: int) -> int | None:
        [(latest,)] = self._run(
            "SELECT MAX(STEP) FROM ("
            "SELECT GREATEST(STEP, COALESCE(OUTCOMES_KNOWN_FROM, STEP)) AS STEP "
            "FROM MEMORY.DECISIONS WHERE SIM = ? "
            "UNION ALL SELECT KNOWN_FROM FROM MEMORY.OUTCOMES WHERE SIM = ?)",
            (sim_id, sim_id),
        )
        return latest

    def start_with_memory(self, sim_id: int, memory_from: int, **columns) -> None:
        """One transaction: the row's UPDATE (which matches only a sim with no step stored that
        is not finished) first, then per memory table a DELETE of what the sim's memory held and
        an INSERT ... SELECT of the source's rows with SIM changed. The columns are read from
        the table, so a column added later is copied too."""
        sets, values = _set_clause(columns)
        with self.con.cursor() as cur:
            cur.execute("BEGIN TRANSACTION")
            try:
                cur.execute(
                    f"UPDATE SIM.SIMS SET {sets} WHERE ID = ? "
                    "AND LAST_COMPLETED_STEP IS NULL AND STATUS <> ?",
                    values + [sim_id, str(SimStatus.FINISHED)],
                )
                if cur.rowcount != 1:
                    raise StepAlreadyWritten(
                        f"sim {sim_id} has stored a step or is finished: its memory is "
                        "not copied again"
                    )
                for table in MEMORY_TABLES:
                    cur.execute(f"SELECT * FROM {table} LIMIT 0")
                    names = [d[0] for d in cur.description]
                    picked = ", ".join("?" if n == "SIM" else n for n in names)
                    cur.execute(f"DELETE FROM {table} WHERE SIM = ?", (sim_id,))
                    cur.execute(
                        f"INSERT INTO {table} ({', '.join(names)}) "
                        f"SELECT {picked} FROM {table} WHERE SIM = ?",
                        (sim_id, memory_from),
                    )
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise

    def save_reading(self, version: str, opening: str) -> None:
        self._run(
            "MERGE INTO SIM.JEV_READINGS AS stored "
            "USING (SELECT ? AS READING_VERSION, ? AS OPENING, ? AS CREATED_AT) AS new "
            "ON stored.READING_VERSION = new.READING_VERSION "
            "WHEN NOT MATCHED THEN INSERT (READING_VERSION, OPENING, CREATED_AT) "
            "VALUES (new.READING_VERSION, new.OPENING, new.CREATED_AT)",
            (version, opening, now()),
        )

    def save_prompt(self, version: str, system_prompt: str, tools: list[dict]) -> None:
        self._run(
            "MERGE INTO SIM.LLM_PROMPTS AS stored "
            "USING (SELECT ? AS PROMPT_VERSION, ? AS SYSTEM_PROMPT, ? AS TOOLS, "
            "? AS CREATED_AT) AS new "
            "ON stored.PROMPT_VERSION = new.PROMPT_VERSION "
            "WHEN NOT MATCHED THEN INSERT (PROMPT_VERSION, SYSTEM_PROMPT, TOOLS, CREATED_AT) "
            "VALUES (new.PROMPT_VERSION, new.SYSTEM_PROMPT, PARSE_JSON(new.TOOLS), "
            "new.CREATED_AT)",
            (version, system_prompt, json.dumps(tools), now()),
        )

    def spent(self, sim_id: int) -> float:
        [(total,)] = self._run(
            "SELECT COALESCE(SUM(COST_USD), 0) FROM SIM.CALLS WHERE SIM = ?", (sim_id,)
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
            "LEFT JOIN SIM.CALLS c ON c.SIM = s.ID WHERE s.STATUS IN (?, ?) "
            "GROUP BY s.ID, s.KIND, s.VARIANT, s.STATUS, s.SPENDING_CAP ORDER BY s.ID",
            IN_PROGRESS,
        )
        return [
            {**dict(zip(columns, row, strict=True)), "SPENT": float(row[-1])}
            for row in rows
        ]

    def latest_tier_2_share(self) -> float | None:
        found = self._run(
            "SELECT COUNT_IF(d.KIND = ?) / COUNT(*) FROM MEMORY.DECISIONS d "
            "JOIN SIM.SIMS s ON s.ID = d.SIM "
            "WHERE s.KIND = 'practice' AND s.VARIANT <> 'buy_hold' AND d.KIND IN (?, ?) "
            "AND d.FIRST_WRITTEN_BY = d.SIM "
            "GROUP BY d.SIM ORDER BY d.SIM DESC LIMIT 1",
            (KIND_FULL_EVALUATION, KIND_SCREEN, KIND_FULL_EVALUATION),
        )
        return float(found[0][0]) if found else None

    def screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        [(asked, yes)] = self._run(
            "SELECT COUNT(SCREEN_ANSWER), COUNT_IF(SCREEN_ANSWER >= ?) "
            f"FROM MEMORY.DECISIONS WHERE {OWN_ROWS} AND KIND IN (?, ?)",
            (cut_off, sim_id, *SCREENED_KINDS),
        )
        return int(asked), int(yes)

    def position_screen_counts(self, sim_id: int, cut_off: float) -> tuple[int, int]:
        [(asked, yes)] = self._run(
            "SELECT COUNT(SCREEN_ANSWER), COUNT_IF(SCREEN_ANSWER >= ?) "
            f"FROM MEMORY.DECISIONS WHERE {OWN_ROWS} AND KIND IN (?, ?)",
            (cut_off, sim_id, *POSITION_KINDS),
        )
        return int(asked), int(yes)

    def position_review_counts(self, sim_id: int) -> dict[str, int]:
        [(reviews, end_of_session, closes, reduces, adds)] = self._run(
            "SELECT COUNT(*), COUNT_IF(END_OF_SESSION), COUNT_IF(ACTION = ?), "
            "COUNT_IF(ACTION = ?), COUNT_IF(ACTION = ?) FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} AND KIND = ?",
            (ACTION_CLOSE, ACTION_REDUCE, ACTION_ADD, sim_id, KIND_POSITION_REVIEW),
        )
        return {
            "reviews": int(reviews),
            "end_of_session": int(end_of_session),
            ACTION_CLOSE: int(closes),
            ACTION_REDUCE: int(reduces),
            ACTION_ADD: int(adds),
        }

    def full_evaluation_counts(self, sim_id: int) -> tuple[int, int]:
        [(evaluations, entries)] = self._run(
            "SELECT COUNT(*), COUNT_IF(ACTION = ?) FROM MEMORY.DECISIONS "
            f"WHERE {OWN_ROWS} AND KIND = ?",
            (ACTION_ENTRY, sim_id, KIND_FULL_EVALUATION),
        )
        return int(evaluations), int(entries)


def _delete_ids(cur, table: str, sim_id: int, ids: list[str]) -> None:
    batch = 1_000  # IDs per IN list
    for i in range(0, len(ids), batch):
        part = ids[i : i + batch]
        cur.execute(
            f"DELETE FROM {table} WHERE SIM = ? AND ID IN ({', '.join('?' for _ in part)})",
            [sim_id, *part],
        )


def _set_outcomes_known(cur, sim_id: int, known: dict[str, int]) -> None:
    """Mark decisions complete: each one's step from which all its outcomes are known."""
    pairs = sorted(known.items())
    batch = MOST_BOUND_VALUES // 2 - 1
    for i in range(0, len(pairs), batch):
        part = pairs[i : i + batch]
        cur.execute(
            "UPDATE MEMORY.DECISIONS d SET OUTCOMES_KNOWN_FROM = k.COLUMN2 "
            f"FROM (VALUES {', '.join('(?, ?)' for _ in part)}) AS k "
            "WHERE d.SIM = ? AND d.ID = k.COLUMN1",
            [value for pair in part for value in pair] + [sim_id],
        )


def _insert(cur, table: str, rows: list[dict]) -> None:
    """Insert rows that share their columns, in batches under the bound-value limit."""
    columns = list(rows[0])
    batch = max(1, MOST_BOUND_VALUES // len(columns))
    json_columns = {c for c in columns if any(_is_json(r[c]) for r in rows)}
    if not json_columns:
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        for i in range(0, len(rows), batch):
            cur.executemany(sql, [[r[c] for c in columns] for r in rows[i : i + batch]])
        return
    # Rows with JSON: one statement per batch, the JSON parsed from the VALUES list.
    picked = ", ".join(
        f"PARSE_JSON(COLUMN{n})" if c in json_columns else f"COLUMN{n}"
        for n, c in enumerate(columns, start=1)
    )
    row_marks = f"({', '.join('?' for _ in columns)})"
    for i in range(0, len(rows), batch):
        part = rows[i : i + batch]
        cur.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) SELECT {picked} "
            f"FROM VALUES {', '.join(row_marks for _ in part)}",
            [_value(r[c]) for r in part for c in columns],
        )


class SnowflakeMarket(_Connection):
    def dataset(self, dataset_id: int) -> DatasetInfo:
        found = self._run(
            "SELECT STATUS, FIRST_STEP, LAST_STEP FROM REF.DATASETS WHERE ID = ?",
            (dataset_id,),
        )
        if not found:
            raise KeyError(f"no dataset {dataset_id}")
        [(status, first_step, last_step)] = found
        periods = self._run(
            "SELECT KIND, NAME, FIRST_STEP, LAST_STEP FROM REF.DATASET_PERIODS "
            "WHERE DATASET = ? ORDER BY FIRST_STEP",
            (dataset_id,),
        )
        assets = self._run(
            "SELECT MASKED_ID, ASSET_CLASS FROM REF.ASSETS WHERE DATASET = ? "
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
            "WHERE DATASET = ? AND BAR_SIZE = ? AND STEP BETWEEN ? AND ?",
            (dataset_id, FIFTEEN_MINUTES, first_step, last_step),
        )
        return int(count)

    def bars(self, dataset_id: int, first_step: int, last_step: int) -> BarsByStep:
        by_step: BarsByStep = {}
        for asset, step, open_, high, low, close in self._run(
            "SELECT ASSET, STEP, OPEN, HIGH, LOW, CLOSE FROM RAW.BARS "
            "WHERE DATASET = ? AND BAR_SIZE = ? AND STEP BETWEEN ? AND ? "
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
            f"s.MEASUREMENTS[{_TYPICAL_MOVE}]::FLOAT, b.BARS_LEFT, b.CLOSE "
            "FROM FEATURES.SNAPSHOTS s JOIN RAW.BARS b ON b.DATASET = s.DATASET "
            "AND b.ASSET = s.ASSET AND b.STEP = s.STEP AND b.BAR_SIZE = ? "
            "WHERE s.DATASET = ? AND s.STEP BETWEEN ? AND ?",
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
            "SELECT ASSET, BAR_SIZE, STEP FROM RAW.BARS WHERE DATASET = ? "
            "AND BAR_SIZE IN ('1h', '1d') AND STEP BETWEEN ? AND ? "
            "UNION ALL SELECT ASSET, BAR_SIZE, MAX(STEP) FROM RAW.BARS WHERE DATASET = ? "
            "AND BAR_SIZE IN ('1h', '1d') AND STEP < ? GROUP BY ASSET, BAR_SIZE",
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
            "WHERE DATASET = ? AND STEP BETWEEN ? AND ? "
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
                "WHERE d.ID = ?",
                (dataset_id,),
            )
        }
