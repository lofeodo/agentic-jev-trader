"""Fewer trips to the database (spec appendix 11, section 4), seen on a pretend line to it.

RDS is in Montreal: every wait for an answer costs time. So a program opens one connection and
keeps it; a save sends its statements together and waits once; and the memory lookups of one
step read what does not change within the step (the sim's row, a snapshot, ...) once. The line
(`wire.Line`) counts connections and statements and, for the save, makes every answer late.
"""

import time
from collections import Counter

import pytest

from jev_trader.memory.lookups import Lookups
from jev_trader.memory.search import Filters
from jev_trader.sim import records as records_of
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from tests.postgres.helpers import database, env_through
from tests.postgres.made_up_memory import LATER, NOW, written_memory
from tests.postgres.wire import Line

pytestmark = pytest.mark.dormant

# How late each answer arrives on the pretend line: about a trip to Montreal and back, made
# long enough that one trip more or less is plain to see.
DELAY = 0.3


def opened_through(line: Line, login: str):
    return database(login, env_through(line.port))


def test_a_sim_keeps_one_connection_for_its_whole_run(made_up_dataset):
    dataset_id = made_up_dataset(days=3, assets=2)
    with Line() as line:
        sim_db = opened_through(line, "sim")
        store, market = sim_db.sim_store(), sim_db.market()
        sim_id = create_sim(
            store, market, SimRequest(dataset_id, "buy_hold", "practice", 97, 288)
        )

        run_sim(store, market, sim_id, steps_per_write=20)
        store.sim(sim_id)
        sim_db.close()

    assert line.connections == 1
    assert len(line.statements) > 10


def test_a_save_goes_to_the_database_in_one_trip(sim_db, made_up_dataset):
    store, market = sim_db.sim_store(), sim_db.market()
    sim_id = create_sim(
        store,
        market,
        SimRequest(made_up_dataset(days=2, assets=2), "buy_hold", "practice", 97, 192),
    )
    store.update(sim_id, STATUS="running")
    decision = records_of.decision_row(sim_id, 1, 97, "ASSET_01", None)
    rows = {
        "SIM.ACCOUNT_STEPS": [
            {
                "ID": f"{sim_id}-97",
                "SIM": sim_id,
                "STEP": 97,
                "CASH": 10_000.0,
                "LOAN": 0.0,
                "EXPOSURE": 0.0,
                "ACCOUNT_VALUE": 10_000.0,
                "START_OF_DAY_VALUE": 10_000.0,
                "DAILY_LOSS_REACHED": False,
            }
        ],
        "SIM.SIM_EVENTS": [
            {"ID": f"{sim_id}-97-test", "SIM": sim_id, "STEP": 97, "KIND": "test"}
        ],
        "MEMORY.DECISIONS": [decision],
    }
    with Line(delay=DELAY) as line:
        far = opened_through(line, "sim").sim_store()
        far.sim(sim_id)  # the connection is open before the timing starts
        line.clear()

        began = time.perf_counter()
        far.write_steps(sim_id, None, 97, rows, {"made_up": True})
        took = time.perf_counter() - began
        far.con.close()

    # Begin, the sim's row, three tables' rows and commit: several statements, one wait.
    assert len(line.statements) >= 4
    assert took < 1.5 * DELAY, f"the save took {took:.2f} s: more than one trip"
    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] == 97


def test_one_steps_memory_lookups_read_nothing_twice(
    sim_db, setup_login, made_up_dataset
):
    """The lookups of one step, as the agent makes them for two assets: searches, a reading in
    full and track records. No statement is sent twice with the same values."""
    written = written_memory(sim_db, setup_login, made_up_dataset)
    sim = written.sim
    with Line() as line:
        memory_db = opened_through(line, "memory")
        lookups = Lookups(memory_db.memory_store())
        lookups.store.sim(sim)  # the connection is open before the count starts
        line.clear()

        for asset in ("ASSET_01", "ASSET_02"):
            found = lookups.search(
                sim, NOW, asset, "full_evaluation", Filters(asset="same_asset")
            )
            lookups.search(
                sim, NOW, asset, "position_review", Filters(asset="same_asset"), "long"
            )
            lookups.read(sim, NOW, [f.episode.id for f in found.episodes][:2])
            for pattern in ("hammer", "doji"):
                lookups.track_record(sim, NOW, asset, pattern, "long")
        one_step = list(line.statements)

        # The next step reads afresh: what completed in between is seen.
        later = lookups.track_record(sim, LATER, "ASSET_01", "hammer", "long")
        memory_db.close()

    repeated = {s: n for s, n in Counter(one_step).items() if n > 1}
    assert one_step
    assert repeated == {}, f"read more than once in one step: {repeated}"
    assert later == Lookups(written.store).track_record(
        sim, LATER, "ASSET_01", "hammer", "long"
    )
