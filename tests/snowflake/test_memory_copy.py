"""Copying a memory into a new sim, against the real test database (spec appendix 6, sections 6,
7 and 11; appendix 10, section 9).

A memory is the records a sim left behind in the `MEMORY` tables: its decisions and their
outcomes. A sim with memory starts from its own copy of one, made in the same transaction that
marks it running. Every record keeps its ID in the copy.

Hand-run: needs migrations V4 to V8 applied to TRADING_AGENT_TEST and the builder's and the sim's
keys in `SNOWFLAKE_LOCAL_DIR`. Made-up rows only.

    conda run -n agentic-jev-trader python -m pytest tests/snowflake/test_memory_copy.py
"""

import pytest

from jev_trader.sim import snowflake_store
from jev_trader.sim.snowflake_store import SnowflakeSimStore
from jev_trader.sim.store import MEMORY_TABLES, StepAlreadyWritten


def sim_row(dataset_id, **changes):
    return {
        "DATASET": dataset_id,
        "KIND": "practice",
        "VARIANT": "buy_hold",
        "FIRST_STEP": 97,
        "LAST_STEP": 144,
        "STARTING_VALUE": 10_000.0,
        "SETTINGS": {"made_up": True},
        **changes,
    }


def memory_rows(sim_id, dataset_id):
    """Two decisions, one with its position's standing (a VARIANT column), each with an outcome."""
    decisions, outcomes = [], []
    for step in (100, 120):
        decision = f"{sim_id}-{step}-ASSET_01"
        decisions.append(
            {
                "ID": decision,
                "SIM": sim_id,
                "FIRST_WRITTEN_BY": sim_id,
                "DATASET": dataset_id,
                "ASSET": "ASSET_01",
                "STEP": step,
                "KIND": "position_review",
                "TIER": 2,
                "ACTION": "hold",
                "STANDING": {"direction": "long", "bars_open": step - 97},
                "OUTCOMES_KNOWN_FROM": step + 4,
            }
        )
        outcomes.append(
            {
                "ID": f"{decision}-price_after_4_bars",
                "SIM": sim_id,
                "FIRST_WRITTEN_BY": sim_id,
                "DECISION": decision,
                "KIND": "price_after_4_bars",
                "VALUE": {"price": 100.2, "change": 0.002},
                "KNOWN_FROM": step + 4,
            }
        )
    return {"MEMORY.DECISIONS": decisions, "MEMORY.OUTCOMES": outcomes}


def memory_of(con, sim_id):
    """Every row of a sim's memory without its SIM column, by table, in ID order."""
    found = {}
    with con.cursor() as cur:
        for table in MEMORY_TABLES:
            cur.execute(
                f"SELECT * EXCLUDE (SIM) FROM {table} WHERE SIM = ? ORDER BY ID",
                (sim_id,),
            )
            found[table] = cur.fetchall()
    return found


@pytest.fixture
def left_memory(sim_login, made_up_dataset, remove_sims):
    """A finished sim that left two decisions and their outcomes; returns the store, the
    dataset and the sim."""
    store = SnowflakeSimStore(sim_login)
    dataset_id = made_up_dataset(days=2)
    source = store.create(sim_row(dataset_id, KIND="build-up", STATUS="finished"))
    remove_sims.append(source)
    with sim_login.cursor() as cur:
        for table, rows in memory_rows(source, dataset_id).items():
            snowflake_store._insert(cur, table, rows)
    return store, dataset_id, source


def new_sim(store, dataset_id, source, remove_sims):
    sim_id = store.create(sim_row(dataset_id, FIRST_STEP=145, MEMORY_FROM_SIM=source))
    remove_sims.append(sim_id)
    return sim_id


def test_a_copied_memory_keeps_every_record_and_its_original_id(
    left_memory, sim_login, remove_sims
):
    store, dataset_id, source = left_memory
    sim_id = new_sim(store, dataset_id, source, remove_sims)

    store.start_with_memory(sim_id, source, STATUS="running")

    copied = memory_of(sim_login, sim_id)
    assert copied == memory_of(sim_login, source)
    assert [len(rows) for rows in copied.values()] == [2, 2]
    assert store.sim(sim_id)["STATUS"] == "running"
    assert store.duplicate_ids(sim_id) == {}


def test_a_memory_copied_again_before_the_first_step_is_not_doubled(
    left_memory, sim_login, remove_sims
):
    store, dataset_id, source = left_memory
    sim_id = new_sim(store, dataset_id, source, remove_sims)

    store.start_with_memory(sim_id, source, STATUS="running")
    store.start_with_memory(sim_id, source, STATUS="running")

    assert memory_of(sim_login, sim_id) == memory_of(sim_login, source)


def test_no_copy_is_made_once_the_sim_has_stored_a_step(
    left_memory, sim_login, remove_sims
):
    store, dataset_id, source = left_memory
    sim_id = new_sim(store, dataset_id, source, remove_sims)
    store.start_with_memory(sim_id, source, STATUS="running")
    store.write_steps(sim_id, None, 145, {}, {"made_up": True})

    with pytest.raises(StepAlreadyWritten):
        store.start_with_memory(sim_id, source, STATUS="running")

    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] == 145


def test_the_memory_date_rule_reads_the_latest_step_and_the_base_memory(left_memory):
    store, dataset_id, source = left_memory

    assert store.memory_last_step(source) == 124
    assert store.base_memory_sim(dataset_id) == source
