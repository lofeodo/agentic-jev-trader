"""Loading a Parquet save of Snowflake into Postgres (spec appendix 11, section 2).

The move's one-off step: a `storage save` taken from Snowflake (one folder per table of Parquet
files, and `manifest.json` with each table's rows, files and column types) goes into the
Postgres tables Alembic made, every row as it was saved. The tables must be empty: the load
refuses a database that already holds rows, so nothing is loaded twice.

**The text-to-numbers check first.** The saved snapshots carry the 768 numbers Snowflake's model
gave each situation text, and they load as they are. Before that, the same model on this
computer (`dataset.text_to_numbers`) turns a handful of the saved texts into numbers again; each
pair must point the same way to within a cosine similarity of 0.999 (how alike two lists of
numbers are, from -1 to 1: 1 is the same list, give or take its length), the tolerance of `tests/postgres/test_text_to_numbers.py`. Below it, nothing is loaded: stop and ask
the developer.

**How the files go in.** Each table's files are read with pyarrow, a batch at a time, and sent
with Postgres's `COPY ... FROM STDIN` (rows streamed in, far faster than one `INSERT` each).
The snapshots are gigabytes of text, a long upload over a home connection to RDS, and a
connection dropped that long into one transaction lost everything (the first load into RDS
did). So each table goes in `CHUNK_ROWS` rows at a time, each chunk committed on its own, and a
load that stops part-way carries on where it stopped (`resume`): a table's rows go in the
save's own order, so the rows already there are the save's first ones, and the load skips that
many. A vector's numbers go as the shortest text that gives back the same 4-byte number
(`_short_vector`), about half the size of Snowflake's. The values need little
work: Snowflake's whole numbers (`NUMBER(38,0)`, saved as decimals) become Python integers; its
times without a time zone (`TIMESTAMP_NTZ`), which Parquet marks as UTC, keep their clock time
and lose the mark; its `VARIANT`, `ARRAY` and `VECTOR` columns, saved as JSON text, go in as that
text, which Postgres reads as `jsonb` or as pgvector's `vector`. Times were saved to the
millisecond, so that is all the load can give back. Each table's ID numbering (`ref.dataset_ids`,
`sim.sim_ids`) then carries on from the highest ID loaded.

**Then the check.** Each table's rows are counted against the manifest, and some rows are read
back and compared value by value with the saved ones: every sim, and a spread of episodes
(memory's decisions), their outcomes and snapshots. `check_load` runs it on its own too, for a
database loaded before, or restored from a `pg_dump` file.

The load logs in as the setup login, which owns every table.
"""

import json
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

LEAST_SIMILARITY = 0.999
MODEL_CHECK_EPISODES = 5
BATCH_ROWS = 2_000
# Rows committed together while loading: a dropped connection loses at most this many.
CHUNK_ROWS = 10_000
SNAPSHOTS = ("FEATURES", "SNAPSHOTS")
# The tables whose rows are read back and compared, and how many of each (None: all).
SPOT_CHECKS = {
    ("SIM", "SIMS"): None,
    ("MEMORY", "DECISIONS"): 25,
    ("MEMORY", "OUTCOMES"): 25,
    SNAPSHOTS: 10,
}
# Each ID numbering, and the column it numbers.
SEQUENCES = {"ref.dataset_ids": "ref.datasets.id", "sim.sim_ids": "sim.sims.id"}
JSON_TYPES = ("VARIANT", "ARRAY", "OBJECT")


class LoadRefused(Exception):
    """The load cannot go ahead; the message says why and what to do."""


@dataclass(frozen=True)
class SavedTable:
    schema: str
    name: str
    rows: int
    files: tuple[str, ...]
    # (name, Snowflake type), as the manifest has them
    columns: tuple[tuple[str, str], ...]

    @property
    def postgres_name(self) -> str:
        return f"{self.schema.lower()}.{self.name.lower()}"

    @property
    def column_names(self) -> list[str]:
        return [name for name, _ in self.columns]

    @property
    def postgres_columns(self) -> str:
        """The columns as a statement lists them: `id, name, ...`."""
        return ", ".join(name.lower() for name in self.column_names)

    @cached_property
    def column_types(self) -> dict[str, str]:
        return {name: kind.upper() for name, kind in self.columns}

    def folder(self, save: Path) -> Path:
        return Path(save) / self.schema / self.name


def read_manifest(folder: Path) -> list[SavedTable]:
    manifest = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    return [
        SavedTable(
            t["schema"],
            t["name"],
            int(t["rows"]),
            tuple(t["files"]),
            tuple((c["name"], c["type"]) for c in t["columns"]),
        )
        for t in manifest["tables"]
    ]


def _short_vector(text: str) -> str:
    """A saved vector's JSON text, each number written with the 9 significant digits that give
    back the same 4-byte number pgvector keeps (Snowflake wrote 16)."""
    import numpy as np

    numbers = np.asarray(json.loads(text), dtype=np.float32).tolist()
    return "[" + ",".join(f"{n:.9g}" for n in numbers) + "]"


def _as_postgres(column):
    """A Parquet column as the values Postgres takes: decimals as whole numbers, times with
    their UTC mark dropped (the clock time stays)."""
    import pyarrow as pa

    kind = column.type
    if pa.types.is_decimal(kind) and kind.scale == 0:
        return column.cast(pa.int64())
    if pa.types.is_timestamp(kind) and kind.tz is not None:
        return column.cast(pa.timestamp(kind.unit))
    return column


def saved_rows(
    folder: Path,
    table: SavedTable,
    files: tuple[str, ...] | None = None,
    skip: int = 0,
    short_vectors: bool = False,
) -> Iterator[list[tuple]]:
    """The table's saved rows, a batch at a time, each a tuple in the manifest's column order,
    from row `skip` on (whole files before it are not read). `short_vectors` writes vectors as
    `_short_vector` does, for sending."""
    import pyarrow.parquet as pq

    names = table.column_names
    vectors = [
        i
        for i, name in enumerate(names)
        if table.column_types[name].startswith("VECTOR")
    ]
    for file in table.files if files is None else files:
        parquet = pq.ParquetFile(table.folder(folder) / file)
        if skip >= parquet.metadata.num_rows:
            skip -= parquet.metadata.num_rows
            continue
        for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=names):
            if skip >= batch.num_rows:
                skip -= batch.num_rows
                continue
            columns = [
                _as_postgres(batch.column(name)).to_pylist()[skip:] for name in names
            ]
            skip = 0
            if short_vectors:
                for i in vectors:
                    columns[i] = [
                        None if v is None else _short_vector(v) for v in columns[i]
                    ]
            yield list(zip(*columns))


# --- The text-to-numbers check ----------------------------------------------------------------


def cosine(a, b) -> float:
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norms


def _spread(items, count: int) -> list:
    """`count` items spread evenly over `items` (all of them if there are fewer)."""
    if len(items) <= count:
        return list(items)
    return [items[i * len(items) // count] for i in range(count)]


def model_check_episodes(
    folder: Path, tables: list[SavedTable]
) -> list[tuple[str, list]]:
    """`MODEL_CHECK_EPISODES` saved snapshots spread over the save, `(situation text,
    Snowflake's numbers)`; fewer only if the save holds fewer, none if it holds no snapshots."""
    snapshots = next(
        (t for t in tables if (t.schema, t.name) == SNAPSHOTS and t.rows), None
    )
    if snapshots is None:
        return []
    places = _spread(range(snapshots.rows), MODEL_CHECK_EPISODES)
    names = snapshots.column_names
    rows = [dict(zip(names, row)) for row in _picked_rows(folder, snapshots, places)]
    return [(row["SITUATION_TEXT"], json.loads(row["EMBEDDING"])) for row in rows]


def _picked_rows(folder: Path, table: SavedTable, places) -> list[tuple]:
    """The saved rows at `places` (0 is the first row of the first file), reading only the
    files that hold them."""
    import pyarrow.parquet as pq

    wanted, picked, first = set(places), [], 0
    for file in table.files:
        rows = pq.ParquetFile(table.folder(folder) / file).metadata.num_rows
        if any(first <= place < first + rows for place in wanted):
            place = first
            for batch in saved_rows(folder, table, (file,)):
                picked += [row for i, row in enumerate(batch, place) if i in wanted]
                place += len(batch)
        first += rows
    return picked


def model_check(
    episodes: list[tuple[str, list]], embed: Callable[[list[str]], list[list[float]]]
) -> list[float]:
    """How closely the local model's numbers match Snowflake's, one similarity per episode."""
    local = embed([text for text, _ in episodes])
    return [cosine(mine, saved) for mine, (_, saved) in zip(local, episodes)]


# --- Loading ---------------------------------------------------------------------------------


def _postgres_columns(connection) -> dict[str, list[str]]:
    """Every table Alembic made, `schema.name`, and its columns."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('ref', 'keys', 'raw', 'features', 'sim', 'memory') "
            "ORDER BY table_schema, table_name, ordinal_position"
        )
        found: dict[str, list[str]] = {}
        for schema, name, column in cursor.fetchall():
            found.setdefault(f"{schema}.{name}", []).append(column)
    return found


def _check_tables_match(connection, tables: list[SavedTable]) -> None:
    in_postgres = _postgres_columns(connection)
    if not in_postgres:
        raise LoadRefused(
            "The database has no tables: make them first with Alembic "
            "(`python -m alembic upgrade head`, CLAUDE.md)."
        )
    saved = {t.postgres_name for t in tables}
    problems = [
        f"{name}: in Postgres, not in the save" for name in in_postgres.keys() - saved
    ]
    problems += [
        f"{name}: in the save, not in Postgres" for name in saved - in_postgres.keys()
    ]
    for table in tables:
        have = set(in_postgres.get(table.postgres_name, ()))
        want = {name.lower() for name, _ in table.columns}
        if have and have != want:
            problems.append(
                f"{table.postgres_name}: columns differ "
                f"(only in the save: {sorted(want - have)}, "
                f"only in Postgres: {sorted(have - want)})"
            )
    if problems:
        raise LoadRefused(
            "The save's tables do not match Postgres's:\n  " + "\n  ".join(problems)
        )


def _refuse_rows(connection, tables: list[SavedTable]) -> None:
    with connection.cursor() as cursor:
        holding = []
        for table in tables:
            cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {table.postgres_name})")
            if cursor.fetchone()[0]:
                holding.append(table.postgres_name)
    if holding:
        raise LoadRefused(
            "These tables already hold rows, so nothing was loaded: "
            + ", ".join(holding)
            + ". Loading again means emptying the database first, which cannot be undone."
        )


def _row_counts(connection, tables: list[SavedTable]) -> dict[str, int]:
    with connection.cursor() as cursor:
        counts = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table.postgres_name}")
            counts[table.postgres_name] = cursor.fetchone()[0]
    return counts


def check_ready(
    connection, tables: list[SavedTable], resume: bool = False
) -> dict[str, int]:
    """LoadRefused unless `connection`'s tables are the save's, with the same columns, and
    empty; with `resume`, holding at most the save's rows (a load stopped part-way). Returns
    each table's rows already in."""
    _check_tables_match(connection, tables)
    if not resume:
        _refuse_rows(connection, tables)
    counts = _row_counts(connection, tables)
    over = [
        f"{t.postgres_name} ({counts[t.postgres_name]} rows, the save {t.rows})"
        for t in tables
        if counts[t.postgres_name] > t.rows
    ]
    if over:
        raise LoadRefused(
            "These tables hold more rows than the save, so they hold something else and "
            "the load cannot carry on: " + ", ".join(over)
        )
    return counts


def load_save(
    connection,
    folder: Path,
    report: Callable[[str], None] = lambda line: None,
    resume: bool = False,
) -> list[SavedTable]:
    """Load every table of the save in `folder` into the tables of `connection` (a psycopg
    connection as the setup login), `CHUNK_ROWS` rows per transaction. The tables must be
    empty; with `resume`, a load that stopped part-way carries on from the rows already in.
    Returns the tables loaded."""
    tables = read_manifest(folder)
    counts = check_ready(connection, tables, resume)
    for table in tables:
        already = counts[table.postgres_name]
        if already < table.rows:
            _copy_in_chunks(connection, folder, table, already, report)
        report(f"{table.postgres_name}: {table.rows} rows")
    with connection.transaction(), connection.cursor() as cursor:
        for sequence, column in SEQUENCES.items():
            table, _, name = column.rpartition(".")
            # The next ID is one past the highest loaded; 1 for a table loaded empty.
            cursor.execute(
                f"SELECT setval('{sequence}', COALESCE(MAX({name}), 1), MAX({name}) IS NOT NULL) "
                f"FROM {table}"
            )
    with connection.cursor() as cursor:
        # Fresh statistics, so Postgres plans its reads of the new rows well.
        cursor.execute("ANALYZE")
    return tables


def _copy_in_chunks(
    connection, folder: Path, table: SavedTable, already: int, report
) -> None:
    """The table's saved rows from row `already` on, `CHUNK_ROWS` per committed `COPY`."""
    statement = f"COPY {table.postgres_name} ({table.postgres_columns}) FROM STDIN"
    pending: list[tuple] = []
    copied = already
    for batch in saved_rows(folder, table, skip=already, short_vectors=True):
        pending += batch
        while len(pending) >= CHUNK_ROWS:
            chunk, pending = pending[:CHUNK_ROWS], pending[CHUNK_ROWS:]
            _copy_chunk(connection, statement, chunk)
            copied += len(chunk)
            report(f"{table.postgres_name}: {copied} of {table.rows} rows")
    if pending:
        _copy_chunk(connection, statement, pending)


def _copy_chunk(connection, statement: str, chunk: list[tuple]) -> None:
    with (
        connection.transaction(),
        connection.cursor() as cursor,
        cursor.copy(statement) as copy,
    ):
        for row in chunk:
            copy.write_row(row)


# --- Checking a load -------------------------------------------------------------------------


def _primary_key(connection, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
            "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = %s::regclass AND i.indisprimary",
            (table,),
        )
        return [row[0] for row in cursor.fetchall()]


def _comparable(value, snowflake_type: str):
    """A value, saved or read back, in a form both sides share."""
    if value is None:
        return None
    if snowflake_type.startswith("VECTOR"):
        import numpy as np

        # pgvector keeps 4-byte numbers, as Snowflake's VECTOR(FLOAT, n) does.
        numbers = json.loads(value) if isinstance(value, str) else value
        return np.asarray(numbers, dtype=np.float32).tolist()
    if snowflake_type.startswith(JSON_TYPES) and isinstance(value, str):
        return json.loads(value)
    return value


def _spot_check(
    connection, folder: Path, table: SavedTable, count: int | None
) -> list[str]:
    key = _primary_key(connection, table.postgres_name)
    names = table.column_names
    places = range(table.rows) if count is None else _spread(range(table.rows), count)
    picked = _picked_rows(folder, table, places)
    columns = table.postgres_columns
    where = " AND ".join(f"{column} = %s" for column in key)
    problems = []
    with connection.cursor() as cursor:
        for row in picked:
            values = dict(zip(names, row))
            wanted = [values[column.upper()] for column in key]
            cursor.execute(
                f"SELECT {columns} FROM {table.postgres_name} WHERE {where}", wanted
            )
            found = cursor.fetchall()
            if len(found) != 1:
                problems.append(
                    f"{table.postgres_name} {wanted}: {len(found)} rows found"
                )
                continue
            for name, saved_value, loaded in zip(names, row, found[0]):
                kind = table.column_types[name]
                if _comparable(saved_value, kind) != _comparable(loaded, kind):
                    problems.append(f"{table.postgres_name} {wanted}: {name} differs")
    return problems


def check_load(
    connection, folder: Path, report: Callable[[str], None] = lambda line: None
) -> list[str]:
    """Compare the tables of `connection` with the save in `folder`: every table's row count,
    and the rows of `SPOT_CHECKS` value by value. Returns what differs (nothing: they match)."""
    tables = read_manifest(folder)
    problems = []
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table.postgres_name}")
            [count] = cursor.fetchone()
            match = "matches" if count == table.rows else "DIFFERS"
            report(
                f"{table.postgres_name}: {count} rows, the save {table.rows}: {match}"
            )
            if count != table.rows:
                problems.append(
                    f"{table.postgres_name}: {count} rows, the save {table.rows}"
                )
    for table in tables:
        count = SPOT_CHECKS.get((table.schema, table.name), 0)
        if count == 0 or not table.rows:
            continue
        found = _spot_check(connection, folder, table, count)
        checked = table.rows if count is None else min(count, table.rows)
        report(
            f"{table.postgres_name}: {checked} rows compared value by value: "
            + ("all match" if not found else f"{len(found)} differences")
        )
        problems += found
    return problems
