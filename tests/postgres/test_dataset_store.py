"""The dataset store on Postgres, as the builder login (spec appendix 11, sections 1 and 2).

A build writes a dataset's rows and publishes it, or fails and throws them away. Snapshots are
staged, then stored with the numbers the text-to-numbers model gives their situation texts: on
Postgres that model runs on this computer (#277). Here a made-up stand-in gives the numbers, so
nothing is downloaded.
"""

from datetime import date

import pytest

from jev_trader.dataset.snapshots import EMBEDDING_SIZE, FEATURE_SIZE
from jev_trader.dataset.store import made_up_embedding
from jev_trader.storage import NotBuiltYet
from tests.postgres.helpers import numbers, parsed

pytestmark = pytest.mark.dormant


@pytest.fixture
def store(builder):
    return builder.dataset_store()


@pytest.fixture
def made_up_numbers(monkeypatch):
    """The text-to-numbers model replaced by a made-up one: the same numbers for the same text,
    as many as the model gives. The store asks the model through `text_to_numbers.embed`."""
    try:
        from jev_trader.dataset import text_to_numbers
    except ImportError:
        raise NotBuiltYet(277) from None

    def embed(texts):
        return [made_up_embedding(text) for text in texts]

    monkeypatch.setattr(text_to_numbers, "embed", embed)
    return embed


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


def test_a_dataset_is_written_published_and_read_back(store, setup_login):
    dataset_id, version = store.begin(
        "database test",
        {"FIRST_STEP": 1, "LAST_STEP": 96, "DATA_PROVIDERS": ["made up"]},
    )
    assert version == 1
    assert store.begin("database test", {"FIRST_STEP": 1})[1] == 2
    assert store.status(dataset_id) == ("being built", None)
    store.update(
        dataset_id, CHECK_RESULT={"passed": True, "assets": []}, BUILD_PROGRESS=0.5
    )
    store.save(dataset_id, tiny_tables(dataset_id))
    store.publish(dataset_id, without_check=True)

    status, without_check, check, providers = setup_login.execute(
        "SELECT STATUS, PUBLISHED_WITHOUT_CHECK, CHECK_RESULT, DATA_PROVIDERS "
        "FROM REF.DATASETS WHERE ID = %s",
        (dataset_id,),
    ).fetchone()
    assert (status, without_check) == ("published", True)
    assert parsed(check)["passed"] is True
    assert parsed(providers) == ["made up"]
    assert store.status(dataset_id) == ("published", None)
    bars = setup_login.execute(
        "SELECT STEP, CLOSE, BARS_LEFT FROM RAW.BARS WHERE DATASET = %s ORDER BY STEP",
        (dataset_id,),
    ).fetchall()
    assert bars == [(55, 101.0, 13), (56, 101.0, 12)]
    [(first_day,)] = setup_login.execute(
        "SELECT FIRST_DAY FROM KEYS.ASSET_KEY WHERE DATASET = %s", (dataset_id,)
    ).fetchall()
    assert first_day == date(2023, 7, 3)


def test_a_failed_dataset_keeps_only_its_row(store, setup_login):
    dataset_id, _ = store.begin("database test", {"FIRST_STEP": 1})
    store.save(dataset_id, tiny_tables(dataset_id))

    store.fail(dataset_id, "test finished")

    assert store.status(dataset_id) == ("failed", "test finished")
    assert setup_login.execute(
        "SELECT COUNT(*) FROM RAW.BARS WHERE DATASET = %s", (dataset_id,)
    ).fetchone() == (0,)


def test_a_dataset_the_api_added_is_carried_on_with_its_version(store):
    dataset_id, _ = store.begin("database test", {"FIRST_STEP": 1})

    assert store.carry_on(dataset_id, {"BUILD_PROGRESS": 0.1}) == 1


def test_the_playbook_is_stored_once_per_talib_version(store, setup_login):
    row = {"TALIB_VERSION": "0.0-test", "LEAN": "bullish", "SHAPE": "made up"}
    rows = [
        {**row, "PATTERN": "CDLHAMMER", "NAME": "hammer"},
        {**row, "PATTERN": "CDLDOJI", "NAME": "doji"},
    ]

    store.save_playbook(rows)
    store.save_playbook(rows)

    assert setup_login.execute(
        "SELECT COUNT(*) FROM REF.PLAYBOOK WHERE TALIB_VERSION = '0.0-test'"
    ).fetchone() == (2,)


def test_snapshots_are_stored_with_the_numbers_of_their_texts(
    store, setup_login, made_up_numbers
):
    dataset_id, _ = store.begin("database test", {"FIRST_STEP": 1})
    snapshot = {
        "DATASET": dataset_id,
        "ASSET": "ASSET_01",
        "STEP": 55,
        "MEASUREMENTS": [1.0, None] + [0.5] * 56,
        "FEATURE_VECTOR": [0.25] * FEATURE_SIZE,
        "SITUATION_TEXT": "Stock, first hour (bar 1 of 26). Volume high (1.8 times normal).",
    }
    other = {**snapshot, "STEP": 56, "SITUATION_TEXT": "Crypto, Asian hours (bar 5)."}
    store.stage_snapshots(dataset_id, [snapshot, other])

    assert store.embed_snapshots(dataset_id, "ASSET_01") == 2

    stored = setup_login.execute(
        "SELECT STEP, MEASUREMENTS, FEATURE_VECTOR, EMBEDDING FROM FEATURES.SNAPSHOTS "
        "WHERE DATASET = %s ORDER BY STEP",
        (dataset_id,),
    ).fetchall()
    assert [step for step, *_ in stored] == [55, 56]
    for (_, measured, features, embedding), row in zip(stored, [snapshot, other]):
        assert parsed(measured)[:2] == [1.0, None]
        assert numbers(features) == pytest.approx(row["FEATURE_VECTOR"])
        assert len(numbers(embedding)) == EMBEDDING_SIZE
        assert numbers(embedding) == pytest.approx(
            made_up_numbers([row["SITUATION_TEXT"]])[0], abs=1e-6
        )
    assert setup_login.execute(
        "SELECT COUNT(*) FROM FEATURES.SNAPSHOTS_LOADING WHERE DATASET = %s",
        (dataset_id,),
    ).fetchone() == (0,)

    store.fail(dataset_id, "test finished")
    assert setup_login.execute(
        "SELECT COUNT(*) FROM FEATURES.SNAPSHOTS WHERE DATASET = %s", (dataset_id,)
    ).fetchone() == (0,)


def test_rows_of_failed_builds_are_cleared(store, setup_login):
    kept, _ = store.begin("database test", {"FIRST_STEP": 1})
    thrown, _ = store.begin("database test", {"FIRST_STEP": 1})
    store.save(kept, tiny_tables(kept))
    store.save(thrown, tiny_tables(thrown))
    setup_login.execute(
        "UPDATE REF.DATASETS SET STATUS = 'failed' WHERE ID = %s", (thrown,)
    )

    store.clear_failed()

    counts = setup_login.execute(
        "SELECT DATASET, COUNT(*) FROM RAW.BARS GROUP BY DATASET"
    ).fetchall()
    assert counts == [(kept, 2)]
