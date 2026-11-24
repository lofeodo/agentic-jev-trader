"""The dataset store in Snowflake: the tables of the numbered SQL files in `infra/migrations`.

The connection must use `?` placeholders (`jev_trader.storage.snowflake.connect` does). Lists
and dictionaries go into ARRAY and VARIANT columns as JSON text read by `PARSE_JSON`.

Vectors cannot be passed as bound parameters (spec appendix 6, section 9). Snapshot rows are
written to `FEATURES.SNAPSHOTS_LOADING` with their lists as JSON text, then moved into
`FEATURES.SNAPSHOTS` by one statement per asset that casts each list to a vector and embeds
each situation text with `AI_EMBED`. Only the builder's login may call the embedding model.
"""

import json

from jev_trader.dataset.snapshots import EMBEDDING_MODEL, EMBEDDING_SIZE, FEATURE_SIZE
from jev_trader.dataset.store import DATASET_TABLES, TABLES, DatasetStatus, now

# Rows per INSERT. Snowflake moves a statement with more bound values than about 65,000 through
# a temporary stage, which the builder's role may not create, so each batch stays under that.
MOST_BOUND_VALUES = 60_000

_EMBED_SNAPSHOTS = f"""
INSERT INTO FEATURES.SNAPSHOTS
    (DATASET, ASSET, STEP, MEASUREMENTS, FEATURE_VECTOR, SITUATION_TEXT, EMBEDDING)
SELECT
    DATASET,
    ASSET,
    STEP,
    PARSE_JSON(MEASUREMENTS)::ARRAY,
    PARSE_JSON(FEATURE_VECTOR)::ARRAY::VECTOR(FLOAT, {FEATURE_SIZE}),
    SITUATION_TEXT,
    AI_EMBED('{EMBEDDING_MODEL}', SITUATION_TEXT)::VECTOR(FLOAT, {EMBEDDING_SIZE})
FROM FEATURES.SNAPSHOTS_LOADING
WHERE DATASET = ? AND ASSET = ?
"""


def _value(value):
    return json.dumps(value) if isinstance(value, dict | list) else value


def _placeholder(value) -> str:
    return "PARSE_JSON(?)" if isinstance(value, dict | list) else "?"


class SnowflakeStore:
    def __init__(self, connection):
        self.con = connection

    def _run(self, sql: str, params=()):
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def _insert(self, table: str, rows: list[dict]) -> None:
        """Plain values only (no lists): bound in batches as one array per column."""
        if not rows:
            return
        columns = list(rows[0])
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        batch = max(1, MOST_BOUND_VALUES // len(columns))
        with self.con.cursor() as cur:
            for i in range(0, len(rows), batch):
                cur.executemany(
                    sql, [[r[c] for c in columns] for r in rows[i : i + batch]]
                )

    def begin(self, name: str, columns: dict) -> tuple[int, int]:
        [(dataset_id,)] = self._run("SELECT REF.DATASET_IDS.NEXTVAL")
        [(earlier,)] = self._run(
            "SELECT COUNT(*) FROM REF.DATASETS WHERE NAME = ?", (name,)
        )
        row = {
            "ID": dataset_id,
            "NAME": name,
            "VERSION": earlier + 1,
            "STATUS": str(DatasetStatus.BEING_BUILT),
            "STARTED_AT": now(),
            **columns,
        }
        names = ", ".join(row)
        # INSERT ... SELECT, since PARSE_JSON cannot sit in a VALUES list.
        values = ", ".join(_placeholder(v) for v in row.values())
        self._run(
            f"INSERT INTO REF.DATASETS ({names}) SELECT {values}",
            [_value(v) for v in row.values()],
        )
        return dataset_id, earlier + 1

    def carry_on(self, dataset_id: int, columns: dict) -> int:
        self.update(dataset_id, **columns)
        [(version,)] = self._run(
            "SELECT VERSION FROM REF.DATASETS WHERE ID = ?", (dataset_id,)
        )
        return int(version)

    def status(self, dataset_id: int) -> tuple[str, str | None]:
        [(status, reason)] = self._run(
            "SELECT STATUS, FAILURE_REASON FROM REF.DATASETS WHERE ID = ?",
            (dataset_id,),
        )
        return status, reason

    def clear_failed(self) -> None:
        for name in DATASET_TABLES:
            self._run(
                f"DELETE FROM {name} WHERE DATASET IN "
                "(SELECT ID FROM REF.DATASETS WHERE STATUS = ?)",
                (str(DatasetStatus.FAILED),),
            )

    def update(self, dataset_id: int, **columns) -> None:
        sets = ", ".join(f"{k} = {_placeholder(v)}" for k, v in columns.items())
        self._run(
            f"UPDATE REF.DATASETS SET {sets} WHERE ID = ?",
            [_value(v) for v in columns.values()] + [dataset_id],
        )

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        for name in TABLES:
            self._insert(name, tables.get(name, []))
        self.update(dataset_id, BUILT_AT=now())

    def save_playbook(self, rows: list[dict]) -> None:
        [version] = {r["TALIB_VERSION"] for r in rows}
        [(stored,)] = self._run(
            "SELECT COUNT(*) FROM REF.PLAYBOOK WHERE TALIB_VERSION = ?", (version,)
        )
        if not stored:
            self._insert("REF.PLAYBOOK", rows)

    def stage_snapshots(self, dataset_id: int, rows: list[dict]) -> None:
        self._insert(
            "FEATURES.SNAPSHOTS_LOADING",
            [
                {
                    **r,
                    # A reading that is not a finite number would be stored wrong: refuse it.
                    "MEASUREMENTS": json.dumps(r["MEASUREMENTS"], allow_nan=False),
                    "FEATURE_VECTOR": json.dumps(r["FEATURE_VECTOR"], allow_nan=False),
                }
                for r in rows
            ],
        )

    def embed_snapshots(self, dataset_id: int, asset: str) -> int:
        with self.con.cursor() as cur:
            cur.execute(_EMBED_SNAPSHOTS, (dataset_id, asset))
            stored = cur.rowcount
        self._run(
            "DELETE FROM FEATURES.SNAPSHOTS_LOADING WHERE DATASET = ? AND ASSET = ?",
            (dataset_id, asset),
        )
        return stored

    def publish(self, dataset_id: int, without_check: bool) -> None:
        self.update(
            dataset_id,
            STATUS=str(DatasetStatus.PUBLISHED),
            PUBLISHED_WITHOUT_CHECK=without_check,
            PUBLISHED_AT=now(),
        )

    def fail(self, dataset_id: int, reason: str) -> None:
        for name in DATASET_TABLES:
            self._run(f"DELETE FROM {name} WHERE DATASET = ?", (dataset_id,))
        self.update(dataset_id, STATUS=str(DatasetStatus.FAILED), FAILURE_REASON=reason)
