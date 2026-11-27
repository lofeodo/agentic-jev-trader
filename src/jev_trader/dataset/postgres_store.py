"""The dataset store in Postgres, as the builder login: the same tables as in Snowflake.

`connection` is the process's one connection (`jev_trader.storage.postgres.connection`), with
`%s` placeholders. Lists and dictionaries go into `jsonb` columns (`as_param`). A dataset's rows
go in with `COPY`, Postgres's own way of loading many rows at once, inside one transaction.

Snapshots keep their two steps. `stage_snapshots` holds the rows in
`FEATURES.SNAPSHOTS_LOADING`, their lists as JSON text; `embed_snapshots` turns each situation
text of one asset into numbers on this computer, with the text-to-numbers model
(`text_to_numbers.embed`, ticket #277), and moves the rows into `FEATURES.SNAPSHOTS` in one
transaction. pgvector takes a list of numbers as text such as `[0.1,0.2]`.
"""

import json

from jev_trader.dataset import text_to_numbers
from jev_trader.dataset.store import DATASET_TABLES, TABLES, DatasetStatus, now
from jev_trader.storage.postgres import as_param, set_clause

# Situation texts turned into numbers and written per batch, so a year of one asset's snapshots
# (about 35,000) never sits in memory as numbers all at once.
EMBED_BATCH = 1_000


def vector_text(numbers) -> str:
    """A list of numbers as pgvector reads it from text."""
    return "[" + ",".join(repr(float(n)) for n in numbers) + "]"


def copy_rows(cur, table: str, rows: list[dict]) -> None:
    """Rows that share their columns into `table`, with `COPY`."""
    if not rows:
        return
    columns = list(rows[0])
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row([as_param(row[c]) for c in columns])


class PostgresStore:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()):
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def begin(self, name: str, columns: dict) -> tuple[int, int]:
        row = {
            "NAME": name,
            "STATUS": str(DatasetStatus.BEING_BUILT),
            "STARTED_AT": now(),
            **columns,
        }
        # The ID from the sequence and the version from the earlier builds, in one statement.
        [(dataset_id, version)] = self._run(
            f"INSERT INTO REF.DATASETS (ID, VERSION, {', '.join(row)}) "
            "VALUES (nextval('REF.DATASET_IDS'), "
            "(SELECT COUNT(*) + 1 FROM REF.DATASETS WHERE NAME = %s), "
            f"{', '.join('%s' for _ in row)}) RETURNING ID, VERSION",
            [name, *(as_param(v) for v in row.values())],
        )
        return dataset_id, version

    def carry_on(self, dataset_id: int, columns: dict) -> int:
        sets, values = set_clause(columns)
        [(version,)] = self._run(
            f"UPDATE REF.DATASETS SET {sets} WHERE ID = %s RETURNING VERSION",
            [*values, dataset_id],
        )
        return int(version)

    def status(self, dataset_id: int) -> tuple[str, str | None]:
        [(status, reason)] = self._run(
            "SELECT STATUS, FAILURE_REASON FROM REF.DATASETS WHERE ID = %s",
            (dataset_id,),
        )
        return status, reason

    def clear_failed(self) -> None:
        with self.con.transaction(), self.con.cursor() as cur:
            for name in DATASET_TABLES:
                cur.execute(
                    f"DELETE FROM {name} WHERE DATASET IN "
                    "(SELECT ID FROM REF.DATASETS WHERE STATUS = %s)",
                    (str(DatasetStatus.FAILED),),
                )

    def update(self, dataset_id: int, **columns) -> None:
        sets, values = set_clause(columns)
        self._run(
            f"UPDATE REF.DATASETS SET {sets} WHERE ID = %s", [*values, dataset_id]
        )

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        with self.con.transaction(), self.con.cursor() as cur:
            for name in TABLES:
                copy_rows(cur, name, tables.get(name, []))
            cur.execute(
                "UPDATE REF.DATASETS SET BUILT_AT = %s WHERE ID = %s",
                (now(), dataset_id),
            )

    def save_playbook(self, rows: list[dict]) -> None:
        [version] = {r["TALIB_VERSION"] for r in rows}
        with self.con.transaction(), self.con.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM REF.PLAYBOOK WHERE TALIB_VERSION = %s LIMIT 1",
                (version,),
            )
            if cur.fetchone() is None:
                copy_rows(cur, "REF.PLAYBOOK", rows)

    def stage_snapshots(self, dataset_id: int, rows: list[dict]) -> None:
        with self.con.transaction(), self.con.cursor() as cur:
            copy_rows(
                cur,
                "FEATURES.SNAPSHOTS_LOADING",
                [
                    {
                        **r,
                        # A reading that is not a finite number would be stored wrong: refuse it.
                        "MEASUREMENTS": json.dumps(r["MEASUREMENTS"], allow_nan=False),
                        "FEATURE_VECTOR": json.dumps(
                            r["FEATURE_VECTOR"], allow_nan=False
                        ),
                    }
                    for r in rows
                ],
            )

    def embed_snapshots(self, dataset_id: int, asset: str) -> int:
        staged = self._run(
            "SELECT STEP, SITUATION_TEXT FROM FEATURES.SNAPSHOTS_LOADING "
            "WHERE DATASET = %s AND ASSET = %s ORDER BY STEP",
            (dataset_id, asset),
        )
        with self.con.transaction(), self.con.cursor() as cur:
            for i in range(0, len(staged), EMBED_BATCH):
                part = staged[i : i + EMBED_BATCH]
                # Through the module, so a test can put made-up numbers in its place.
                embeddings = text_to_numbers.embed([text for _, text in part])
                cur.execute(
                    "INSERT INTO FEATURES.SNAPSHOTS (DATASET, ASSET, STEP, MEASUREMENTS, "
                    "FEATURE_VECTOR, SITUATION_TEXT, EMBEDDING) "
                    "SELECT l.DATASET, l.ASSET, l.STEP, l.MEASUREMENTS::jsonb, "
                    "l.FEATURE_VECTOR::vector, l.SITUATION_TEXT, e.EMBEDDING::vector "
                    "FROM FEATURES.SNAPSHOTS_LOADING l "
                    "JOIN unnest(%s::bigint[], %s::text[]) AS e(STEP, EMBEDDING) "
                    "ON e.STEP = l.STEP WHERE l.DATASET = %s AND l.ASSET = %s",
                    (
                        [step for step, _ in part],
                        [vector_text(numbers) for numbers in embeddings],
                        dataset_id,
                        asset,
                    ),
                )
            cur.execute(
                "DELETE FROM FEATURES.SNAPSHOTS_LOADING WHERE DATASET = %s AND ASSET = %s",
                (dataset_id, asset),
            )
        return len(staged)

    def publish(self, dataset_id: int, without_check: bool) -> None:
        self.update(
            dataset_id,
            STATUS=str(DatasetStatus.PUBLISHED),
            PUBLISHED_WITHOUT_CHECK=without_check,
            PUBLISHED_AT=now(),
        )

    def fail(self, dataset_id: int, reason: str) -> None:
        with self.con.transaction(), self.con.cursor() as cur:
            for name in DATASET_TABLES:
                cur.execute(f"DELETE FROM {name} WHERE DATASET = %s", (dataset_id,))
            cur.execute(
                "UPDATE REF.DATASETS SET STATUS = %s, FAILURE_REASON = %s WHERE ID = %s",
                (str(DatasetStatus.FAILED), reason, dataset_id),
            )
