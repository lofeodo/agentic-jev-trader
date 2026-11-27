"""Loading a Parquet save of Snowflake into Postgres (spec appendix 11, section 2).

The move's one-off step: a `storage save` taken from Snowflake (one folder per table of Parquet
files, and `manifest.json` with each table's rows, files and column types) goes into the
Postgres tables Alembic made, every row as it was saved. The tables must be empty: the load
refuses a database that already holds rows, so nothing is loaded twice.

**The text-to-numbers check first.** The saved snapshots carry the 768 numbers Snowflake's model
gave each situation text, and they load as they are. Before that, the same model on this
computer (`dataset.text_to_numbers`) turns a handful of the saved texts into numbers again; each
pair must point the same way to within a cosine similarity of 0.999 (1 is identical), the
tolerance of `tests/postgres/test_text_to_numbers.py`. Below it, nothing is loaded: stop and ask
the developer.

**How the files go in.** Each table's files are read with pyarrow, a batch at a time, and sent
with Postgres's `COPY ... FROM STDIN` (rows streamed in, far faster than one `INSERT` each), all
tables in one transaction: a load that fails leaves the tables empty. The values need little
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
from pathlib import Path

LEAST_SIMILARITY = 0.999
MODEL_CHECK_EPISODES = 5
BATCH_ROWS = 2_000
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
    columns: tuple[
        tuple[str, str], ...
    ]  # (name, Snowflake type), as the manifest has them

    @property
    def postgres_name(self) -> str:
        return f"{self.schema.lower()}.{self.name.lower()}"

    def column_type(self, column: str) -> str:
        return dict(self.columns)[column].upper()


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
    folder: Path, table: SavedTable, files: tuple[str, ...] | None = None
) -> Iterator[list[tuple]]:
    """The table's saved rows, a batch at a time, each a tuple in the manifest's column order."""
    import pyarrow.parquet as pq

    names = [name for name, _ in table.columns]
    for file in table.files if files is None else files:
        parquet = pq.ParquetFile(Path(folder) / table.schema / table.name / file)
        for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=names):
            columns = [_as_postgres(batch.column(name)).to_pylist() for name in names]
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
    """A handful of saved snapshots, `(situation text, Snowflake's numbers)`, one from each of
    files spread over the save."""
    snapshots = next(
        (t for t in tables if (t.schema, t.name) == SNAPSHOTS and t.rows), None
    )
    if snapshots is None:
        return []
    episodes = []
    for file in _spread(list(snapshots.files), MODEL_CHECK_EPISODES):
        batch = next(saved_rows(folder, snapshots, (file,)))
        names = [name for name, _ in snapshots.columns]
        row = dict(zip(names, batch[0]))
        episodes.append((row["SITUATION_TEXT"], json.loads(row["EMBEDDING"])))
    return episodes


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


def check_ready(connection, tables: list[SavedTable]) -> None:
    """LoadRefused unless `connection`'s tables are the save's, with the same columns, and
    empty."""
    _check_tables_match(connection, tables)
    _refuse_rows(connection, tables)


def load_save(
    connection, folder: Path, report: Callable[[str], None] = lambda line: None
) -> list[SavedTable]:
    """Load every table of the save in `folder` into the empty tables of `connection` (a psycopg
    connection as the setup login), in one transaction. Returns the tables loaded."""
    tables = read_manifest(folder)
    check_ready(connection, tables)
    with connection.transaction(), connection.cursor() as cursor:
        for table in tables:
            columns = ", ".join(name.lower() for name, _ in table.columns)
            copied = 0
            with cursor.copy(
                f"COPY {table.postgres_name} ({columns}) FROM STDIN"
            ) as copy:
                for batch in saved_rows(folder, table):
                    for row in batch:
                        copy.write_row(row)
                    copied += len(batch)
            report(f"{table.postgres_name}: {copied} rows")
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
    names = [name for name, _ in table.columns]
    wanted_places = set(
        range(table.rows) if count is None else _spread(range(table.rows), count)
    )
    picked, place = [], 0
    for batch in saved_rows(folder, table):
        picked += [row for i, row in enumerate(batch, place) if i in wanted_places]
        place += len(batch)
    columns = ", ".join(name.lower() for name in names)
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
                kind = table.column_type(name)
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
