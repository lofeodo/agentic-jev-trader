"""Saving every table to files on the developer's machine (spec appendix 10, section 15)."""

import json
from datetime import UTC, datetime

import pytest

from jev_trader.storage.save import Column, Table, save_tables, unload_query

SAVED_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)

SIMS = Table(
    "SIM",
    "SIMS",
    (Column("ID", "NUMBER(38,0)"), Column("STATUS", "VARCHAR(16777216)")),
)
SNAPSHOTS = Table(
    "FEATURES",
    "SNAPSHOTS",
    (Column("STEP", "NUMBER(38,0)"), Column("EMBEDDING", "VECTOR(FLOAT, 768)")),
)
EMPTY = Table("MEMORY", "EPISODES", (Column("ID", "NUMBER(38,0)"),))


class FakeSnowflake:
    """Tables with a row count each. Unloading puts one file per 1,000 rows on the stage."""

    def __init__(self, rows, fail_on=None):
        self.rows = rows  # {Table: row count}
        self.stage = {}  # stage folder -> file names
        self.fail_on = fail_on
        self.cleared = []

    def tables(self):
        return list(self.rows)

    def unload(self, table, stage_dir):
        if table == self.fail_on:
            raise RuntimeError("Snowflake said no")
        count = self.rows[table]
        files = -(-count // 1000)
        self.stage[stage_dir] = [f"data_0_0_{n}.snappy.parquet" for n in range(files)]
        return count

    def download(self, stage_dir, folder):
        folder.mkdir(parents=True, exist_ok=True)
        names = self.stage.get(stage_dir, [])
        for name in names:
            (folder / name).write_bytes(b"PAR1")
        return names

    def clear(self, stage_root):
        self.cleared.append(stage_root)
        self.stage = {
            k: v for k, v in self.stage.items() if not k.startswith(stage_root)
        }


def save(tmp_path, snowflake):
    return save_tables(snowflake, tmp_path, database="TRADING_AGENT", saved_at=SAVED_AT)


def test_each_table_lands_in_its_own_folder_under_one_dated_save(tmp_path):
    out = save(tmp_path, FakeSnowflake({SIMS: 2500, SNAPSHOTS: 40}))

    assert out == tmp_path / "TRADING_AGENT-20261124-153000"
    assert sorted(p.name for p in (out / "SIM" / "SIMS").iterdir()) == [
        "data_0_0_0.snappy.parquet",
        "data_0_0_1.snappy.parquet",
        "data_0_0_2.snappy.parquet",
    ]
    assert [p.name for p in (out / "FEATURES" / "SNAPSHOTS").iterdir()] == [
        "data_0_0_0.snappy.parquet"
    ]


def test_the_manifest_records_rows_files_and_column_types_for_reloading(tmp_path):
    out = save(tmp_path, FakeSnowflake({SIMS: 2500, SNAPSHOTS: 40, EMPTY: 0}))

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["database"] == "TRADING_AGENT"
    assert manifest["saved_at"] == "2026-11-24T15:30:00+00:00"
    assert manifest["total_rows"] == 2540
    tables = {f"{t['schema']}.{t['name']}": t for t in manifest["tables"]}
    assert tables["SIM.SIMS"]["rows"] == 2500
    assert len(tables["SIM.SIMS"]["files"]) == 3
    assert tables["FEATURES.SNAPSHOTS"]["columns"] == [
        {"name": "STEP", "type": "NUMBER(38,0)"},
        {"name": "EMBEDDING", "type": "VECTOR(FLOAT, 768)"},
    ]
    assert tables["MEMORY.EPISODES"] == {
        "schema": "MEMORY",
        "name": "EPISODES",
        "rows": 0,
        "files": [],
        "columns": [{"name": "ID", "type": "NUMBER(38,0)"}],
    }


def test_rows_unloaded_but_no_file_received_stops_the_save(tmp_path):
    class LosesFiles(FakeSnowflake):
        def download(self, stage_dir, folder):
            return []

    with pytest.raises(RuntimeError, match="SIM.SIMS"):
        save(tmp_path, LosesFiles({SIMS: 10}))


def test_the_copy_on_snowflake_is_cleared_before_and_after_even_on_failure(tmp_path):
    snowflake = FakeSnowflake({SIMS: 10, SNAPSHOTS: 5}, fail_on=SNAPSHOTS)

    with pytest.raises(RuntimeError, match="Snowflake said no"):
        save(tmp_path, snowflake)

    assert len(snowflake.cleared) == 2
    assert snowflake.stage == {}


def test_unload_query_quotes_names_and_turns_vectors_into_arrays():
    assert unload_query("TRADING_AGENT", SNAPSHOTS) == (
        'SELECT "STEP", CAST("EMBEDDING" AS ARRAY) AS "EMBEDDING" '
        'FROM "TRADING_AGENT"."FEATURES"."SNAPSHOTS"'
    )
