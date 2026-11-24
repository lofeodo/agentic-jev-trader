"""Save every table as Parquet files on this machine, before the Snowflake trial ends (spec
appendix 10, section 15).

Snowflake does the export itself: `COPY INTO` writes each table as Parquet files to the login's
own stage (a folder of files Snowflake keeps for each user, no grant needed), and `GET` downloads
them. Each save goes to a new folder, `<DATABASE>-<YYYYMMDD-HHMMSS>`, one folder per table inside
it (`SIM/SIMS/`), with `manifest.json` beside them: every table's row count, file names and
column types, so the files can be loaded into a new Snowflake account later.

Parquet has no type for Snowflake's `VARIANT`, `ARRAY` and `VECTOR` columns: they are saved as
JSON text (`VECTOR` columns cast to `ARRAY` first, `[0.029,0.068,...]`). To load one back,
`PARSE_JSON` it and cast it to the type the manifest records, e.g.
`PARSE_JSON($1:EMBEDDING)::VECTOR(FLOAT, 768)`.

Tables are copied one after another, not at one instant: save while no sim or build is writing.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

# Where the files wait on the login's own stage between `COPY INTO` and `GET`.
STAGE_ROOT = "jev_trader_saved_tables"
NOT_SAVED = (
    "METADATA (schemachange's record of applied SQL files): the API login cannot read it, "
    "and applying infra/migrations to a new account writes it again."
)
RELOADING = (
    "VARIANT, ARRAY and VECTOR columns are JSON text: PARSE_JSON each and cast it to the "
    "column's type, e.g. PARSE_JSON($1:EMBEDDING)::VECTOR(FLOAT, 768)."
)


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # as Snowflake describes it, e.g. `NUMBER(38,0)` or `VECTOR(FLOAT, 768)`


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    columns: tuple[Column, ...]


class TableSource(Protocol):
    database: str

    def tables(self) -> list[Table]: ...

    def unload(self, table: Table, stage_dir: str) -> int:
        """Write the table's files to `stage_dir` on the stage; returns the rows written."""

    def download(self, stage_dir: str, folder: Path) -> list[str]:
        """Download the files in `stage_dir` into `folder`; returns their names."""

    def clear(self, stage_root: str) -> None:
        """Delete everything under `stage_root` on the stage."""


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def unload_query(database: str, table: Table) -> str:
    """The SELECT a table is saved from, with each `VECTOR` column as an array."""
    columns = ", ".join(
        f"CAST({quoted(c.name)} AS ARRAY) AS {quoted(c.name)}"
        if c.type.upper().startswith("VECTOR")
        else quoted(c.name)
        for c in table.columns
    )
    source = ".".join(quoted(part) for part in (database, table.schema, table.name))
    return f"SELECT {columns} FROM {source}"


def save_tables(
    source: TableSource,
    folder: Path,
    saved_at: datetime,
    report: Callable[[str], None] = lambda line: None,
) -> Path:
    """Save every table `source` lists into a new dated folder under `folder`; returns it.

    `report` gets one line per table as it is saved: a big table takes minutes.
    """
    out = Path(folder) / f"{source.database}-{saved_at:%Y%m%d-%H%M%S}"
    saved = []
    source.clear(STAGE_ROOT)
    try:
        for table in source.tables():
            stage_dir = f"{STAGE_ROOT}/{table.schema}/{table.name}"
            rows = source.unload(table, stage_dir)
            report(f"{table.schema}.{table.name}: {rows} rows")
            files = (
                sorted(source.download(stage_dir, out / table.schema / table.name))
                if rows
                else []
            )
            if rows and not files:
                raise RuntimeError(
                    f"{table.schema}.{table.name}: {rows} rows written on Snowflake, "
                    "but no file came back"
                )
            saved.append(
                {
                    "schema": table.schema,
                    "name": table.name,
                    "rows": rows,
                    "files": files,
                    "columns": [asdict(c) for c in table.columns],
                }
            )
    finally:
        source.clear(STAGE_ROOT)
    manifest = {
        "database": source.database,
        "saved_at": saved_at.isoformat(),
        "total_rows": sum(t["rows"] for t in saved),
        "not_saved": NOT_SAVED,
        "reloading": RELOADING,
        "tables": saved,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return out


class SnowflakeTables:
    """The tables of one database, as a login that can read them all (the API login)."""

    def __init__(self, connection, database: str):
        self.con = connection
        self.database = database

    def _run(self, sql: str) -> list[tuple]:
        with self.con.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    def tables(self) -> list[Table]:
        db = quoted(self.database)
        found = self._run(
            f"SELECT TABLE_SCHEMA, TABLE_NAME FROM {db}.INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        tables = []
        for schema, name in found:
            described = self._run(
                f"DESCRIBE TABLE {db}.{quoted(schema)}.{quoted(name)}"
            )
            columns = tuple(Column(row[0], row[1]) for row in described)
            tables.append(Table(schema, name, columns))
        return tables

    def unload(self, table: Table, stage_dir: str) -> int:
        [result] = self._run(
            f"COPY INTO @~/{stage_dir}/data FROM ({unload_query(self.database, table)}) "
            "FILE_FORMAT = (TYPE = PARQUET) HEADER = TRUE OVERWRITE = TRUE"
        )
        return int(result[0])

    def download(self, stage_dir: str, folder: Path) -> list[str]:
        folder.mkdir(parents=True, exist_ok=True)
        target = "file://" + folder.resolve().as_posix().replace("'", "\\'") + "/"
        got = self._run(f"GET @~/{stage_dir}/ '{target}'")
        return [Path(row[0]).name for row in got]

    def clear(self, stage_root: str) -> None:
        self._run(f"REMOVE @~/{stage_root}/")
