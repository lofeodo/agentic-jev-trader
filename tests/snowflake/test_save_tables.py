"""Saving every table of TRADING_AGENT_TEST as the API login (spec appendix 10, section 15).

Reads only; the files on the login's own stage are removed by the save itself.
"""

import json
from datetime import UTC, datetime

import pytest

from jev_trader.storage.save import STAGE_ROOT, SnowflakeTables, save_tables
from jev_trader.storage.snowflake import TEST_DATABASE

from .conftest import login


@pytest.fixture
def api_login():
    con = login("api")
    yield con
    con.close()


def test_every_table_is_saved_with_its_files_and_the_stage_left_empty(
    api_login, tmp_path
):
    out = save_tables(
        SnowflakeTables(api_login, TEST_DATABASE), tmp_path, datetime.now(UTC)
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    names = {f"{t['schema']}.{t['name']}" for t in manifest["tables"]}
    assert {"KEYS.ASSET_KEY", "FEATURES.SNAPSHOTS", "SIM.SIMS", "RAW.BARS"} <= names
    for table in manifest["tables"]:
        folder = out / table["schema"] / table["name"]
        assert all((folder / name).stat().st_size > 0 for name in table["files"])
        assert bool(table["files"]) == bool(table["rows"])
    with api_login.cursor() as cur:
        cur.execute(f"LIST @~/{STAGE_ROOT}/")
        assert cur.fetchall() == []
