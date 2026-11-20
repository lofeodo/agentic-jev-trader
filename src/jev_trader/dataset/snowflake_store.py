"""The dataset store in Snowflake: the tables of `infra/migrations/V2__dataset_bars.sql`.

The connection must use `?` placeholders (`jev_trader.storage.snowflake.connect` does). Lists
and dictionaries go into ARRAY and VARIANT columns as JSON text read by `PARSE_JSON`.
"""

import json

from jev_trader.dataset.store import TABLES, DatasetStatus, now

# Rows per INSERT. Snowflake moves a statement with more bound values than about 65,000 through
# a temporary stage, which the builder's role may not create, so each batch stays under that.
MOST_BOUND_VALUES = 60_000


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

    def update(self, dataset_id: int, **columns) -> None:
        sets = ", ".join(f"{k} = {_placeholder(v)}" for k, v in columns.items())
        self._run(
            f"UPDATE REF.DATASETS SET {sets} WHERE ID = ?",
            [_value(v) for v in columns.values()] + [dataset_id],
        )

    def save(self, dataset_id: int, tables: dict[str, list[dict]]) -> None:
        for name in TABLES:
            rows = tables.get(name, [])
            if not rows:
                continue
            columns = list(rows[0])
            sql = (
                f"INSERT INTO {name} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})"
            )
            batch = max(1, MOST_BOUND_VALUES // len(columns))
            with self.con.cursor() as cur:
                for i in range(0, len(rows), batch):
                    cur.executemany(
                        sql, [[r[c] for c in columns] for r in rows[i : i + batch]]
                    )
        self.update(dataset_id, BUILT_AT=now())

    def publish(self, dataset_id: int, without_check: bool) -> None:
        self.update(
            dataset_id,
            STATUS=str(DatasetStatus.PUBLISHED),
            PUBLISHED_WITHOUT_CHECK=without_check,
            PUBLISHED_AT=now(),
        )

    def fail(self, dataset_id: int, reason: str) -> None:
        for name in TABLES:
            self._run(f"DELETE FROM {name} WHERE DATASET = ?", (dataset_id,))
        self.update(dataset_id, STATUS=str(DatasetStatus.FAILED), FAILURE_REASON=reason)
