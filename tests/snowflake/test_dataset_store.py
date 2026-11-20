"""The dataset store against the real test database, TRADING_AGENT_TEST (hand-run).

Needs the tables of `infra/migrations/V2__dataset_bars.sql` and `V3__dataset_snapshots.sql` applied (`snowflake_admin.py
migrate`) and a login that writes REF, KEYS and RAW, such as the builder's. Made-up rows only.
"""

import os
from datetime import date

import pytest
from dotenv import dotenv_values

from jev_trader.dataset.snowflake_store import SnowflakeStore
from jev_trader.storage.snowflake import TEST_DATABASE, connect

ENV = {**dotenv_values(".env"), **os.environ}


@pytest.fixture
def store():
    con = connect(
        "builder",
        database=TEST_DATABASE,
        env=ENV,
        user=ENV["SNOWFLAKE_USER"],
        private_key_file=ENV["SNOWFLAKE_PRIVATE_KEY_FILE"],
    )
    yield SnowflakeStore(con)
    con.close()


def tiny_tables(dataset_id):
    bar = {
        "DATASET": dataset_id,
        "ASSET": "ASSET_01",
        "BAR_SIZE": "15m",
        "STEP": 55,
        "DAY": 1,
        "BAR_NUMBER": 1,
        "BARS_LEFT": 13,
        "OPEN": 100.0,
        "HIGH": 102.0,
        "LOW": 98.0,
        "CLOSE": 101.0,
        "VOLUME": 100.0,
    }
    return {
        "REF.ASSETS": [
            {"DATASET": dataset_id, "MASKED_ID": "ASSET_01", "ASSET_CLASS": "stock"}
        ],
        "KEYS.ASSET_KEY": [
            {
                "DATASET": dataset_id,
                "MASKED_ID": "ASSET_01",
                "TICKER": "XYZ",
                "PROVIDER_SYMBOL": "XYZ",
                "NAME": "Made-up Corp",
                "PRICE_SCALE": 2.0,
                "VOLUME_SCALE": 0.1,
                "FIRST_DAY": date(2023, 7, 3),
            }
        ],
        "RAW.BARS": [bar, {**bar, "STEP": 56, "BAR_NUMBER": 2, "BARS_LEFT": 12}],
    }


def test_a_dataset_is_written_published_and_read_back(store):
    dataset_id, version = store.begin(
        "hand-run test",
        {"FIRST_STEP": 1, "LAST_STEP": 96, "DATA_PROVIDERS": ["made up"]},
    )
    assert version >= 1
    store.update(
        dataset_id, CHECK_RESULT={"passed": True, "assets": []}, BUILD_PROGRESS=0.5
    )
    store.save(dataset_id, tiny_tables(dataset_id))
    store.publish(dataset_id, without_check=True)

    [(status, without_check, passed)] = store._run(
        "SELECT STATUS, PUBLISHED_WITHOUT_CHECK, CHECK_RESULT:passed::BOOLEAN "
        "FROM REF.DATASETS WHERE ID = ?",
        (dataset_id,),
    )
    assert (status, without_check, passed) == ("published", True, True)
    bars = store._run(
        "SELECT STEP, CLOSE, BARS_LEFT FROM RAW.BARS WHERE DATASET = ? ORDER BY STEP",
        (dataset_id,),
    )
    assert bars == [(55, 101.0, 13), (56, 101.0, 12)]
    [(first_day,)] = store._run(
        "SELECT FIRST_DAY FROM KEYS.ASSET_KEY WHERE DATASET = ?", (dataset_id,)
    )
    assert first_day == date(2023, 7, 3)

    # Clean up the test database: a failed dataset keeps only its row.
    store.fail(dataset_id, "hand-run test finished")
    assert store._run(
        "SELECT COUNT(*) FROM RAW.BARS WHERE DATASET = ?", (dataset_id,)
    ) == [(0,)]


def test_snapshots_are_written_as_arrays_cast_to_vectors_and_embedded(store):
    # Calls the embedding model on two short texts: a tiny share of a credit.
    dataset_id, _ = store.begin("hand-run snapshots", {"FIRST_STEP": 1})
    snapshot = {
        "DATASET": dataset_id,
        "ASSET": "ASSET_01",
        "STEP": 55,
        "MEASUREMENTS": [1.0, None] + [0.5] * 56,
        "FEATURE_VECTOR": [0.25] * 58,
        "SITUATION_TEXT": "Stock, first hour (bar 1 of 26). Volume high (1.8 times normal).",
    }
    store.stage_snapshots(
        dataset_id,
        [
            snapshot,
            {
                **snapshot,
                "STEP": 56,
                "SITUATION_TEXT": "Crypto, Asian hours (bar 5 of 96).",
            },
        ],
    )
    assert store.embed_snapshots(dataset_id, "ASSET_01") == 2

    stored = store._run(
        "SELECT STEP, IS_NULL_VALUE(MEASUREMENTS[1]), ARRAY_SIZE(FEATURE_VECTOR::ARRAY), "
        "ARRAY_SIZE(EMBEDDING::ARRAY), VECTOR_COSINE_SIMILARITY(EMBEDDING, EMBEDDING) "
        "FROM FEATURES.SNAPSHOTS WHERE DATASET = ? ORDER BY STEP",
        (dataset_id,),
    )
    assert [row[:4] for row in stored] == [(55, True, 58, 768), (56, True, 58, 768)]
    assert stored[0][4] == pytest.approx(1.0)
    assert store._run(
        "SELECT COUNT(*) FROM FEATURES.SNAPSHOTS_LOADING WHERE DATASET = ?",
        (dataset_id,),
    ) == [(0,)]

    store.fail(dataset_id, "hand-run test finished")
    assert store._run(
        "SELECT COUNT(*) FROM FEATURES.SNAPSHOTS WHERE DATASET = ?", (dataset_id,)
    ) == [(0,)]
