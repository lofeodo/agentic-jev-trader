"""How a step is written: all or nothing, one writer at a time, and a restart that loses nothing.

Spec appendix 6, section 6. The real database is covered by the hand-run `tests/snowflake` group;
these run the same rules on the in-memory stand-in.
"""

from datetime import datetime

import pytest

from jev_trader.jobs import this_process
from jev_trader.sim.runner import (
    DuplicateRecords,
    SimRequest,
    create_sim,
    run_sim,
)
from jev_trader.sim.store import InMemorySimStore, SimulatedKill, StepAlreadyWritten


def new_sim(store, market):
    request = SimRequest(
        dataset=7, variant="buy_hold", kind="practice", first_step=97, last_step=288
    )
    return create_sim(store, market, request)


def without_events(tables):
    return {name: rows for name, rows in tables.items() if name != "SIM.SIM_EVENTS"}


def never_stopped(market, steps_per_write):
    store = InMemorySimStore()
    run_sim(store, market, new_sim(store, market), steps_per_write=steps_per_write)
    return store


@pytest.mark.parametrize("steps_per_write", [1, 40])
@pytest.mark.parametrize("killed_on_write", [1, 2, 3])
def test_a_sim_killed_while_writing_and_restarted_ends_with_the_same_records(
    market, steps_per_write, killed_on_write
):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    store.kill_on_write(killed_on_write)
    with pytest.raises(SimulatedKill):
        run_sim(store, market, sim_id, steps_per_write=steps_per_write)
    assert store.sim(sim_id)["STATUS"] == "running"  # as a killed program leaves it

    run_sim(store, market, sim_id, steps_per_write=steps_per_write)

    expected = never_stopped(market, steps_per_write)
    assert without_events(store.all_rows()) == without_events(expected.all_rows())
    assert store.sim(sim_id)["STATUS"] == "finished"


def test_a_restart_is_stored_as_a_notable_moment(market):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    store.kill_on_write(3)
    with pytest.raises(SimulatedKill):
        run_sim(store, market, sim_id)

    run_sim(store, market, sim_id)

    [event] = store.rows("SIM.SIM_EVENTS", sim_id)
    # Steps 97 and 98 were stored; step 99 was being written when the sim was killed.
    assert (event["KIND"], event["STEP"], event["DETAILS"]) == (
        "restarted",
        99,
        {"after_step": 98},
    )


def test_a_kill_halfway_through_a_write_stores_nothing_of_it(market):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    store.kill_on_write(1)
    with pytest.raises(SimulatedKill):
        run_sim(store, market, sim_id, steps_per_write=10)

    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] is None
    assert all(rows == [] for rows in store.all_rows(sim_id).values())


def test_two_copies_of_one_sim_cannot_both_write_a_step(market):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    store.update(sim_id, STATUS="running")
    row = {"ID": "1-97", "SIM": sim_id, "STEP": 97}
    store.write_steps(sim_id, None, 97, {"SIM.ACCOUNT_STEPS": [row]}, {})

    # The second copy also saw no completed step when it started.
    with pytest.raises(StepAlreadyWritten):
        store.write_steps(sim_id, None, 97, {"SIM.ACCOUNT_STEPS": [row]}, {})
    assert len(store.rows("SIM.ACCOUNT_STEPS", sim_id)) == 1


def test_nothing_is_written_to_a_finished_sim(market):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    run_sim(store, market, sim_id)

    with pytest.raises(ValueError, match="finished"):
        run_sim(store, market, sim_id)
    with pytest.raises(StepAlreadyWritten):
        store.write_steps(sim_id, 288, 289, {}, {})
    # A second copy marking it running again, late, changes nothing.
    store.update(sim_id, STATUS="running", RUNNING_ON="pid 2")
    assert store.sim(sim_id)["STATUS"] == "finished"


def test_a_sim_with_a_record_id_stored_twice_ends_failed(market):
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    # A stray row with the ID the sim gives its account at step 200.
    store.tables["SIM.ACCOUNT_STEPS"].append({"ID": f"{sim_id}-200", "SIM": sim_id})

    with pytest.raises(DuplicateRecords, match="SIM.ACCOUNT_STEPS"):
        run_sim(store, market, sim_id)
    assert store.sim(sim_id)["STATUS"] == "failed"


def test_a_running_sim_notes_where_its_job_runs_and_when_it_last_started(market):
    """So the API can find and kill the job (appendix 8, section 8.7), and tell a freshly
    resumed sim from one gone quiet."""
    store = InMemorySimStore()
    sim_id = new_sim(store, market)
    store.kill_on_write(2)
    with pytest.raises(SimulatedKill):
        run_sim(store, market, sim_id)
    long_ago = datetime(2026, 1, 1)  # the first start, long before the restart
    store.update(sim_id, STARTED_AT=long_ago)

    run_sim(store, market, sim_id)

    sim = store.sim(sim_id)
    assert sim["RUNNING_ON"] == this_process()
    assert sim["STARTED_AT"] > long_ago
