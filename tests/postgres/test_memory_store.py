"""The memory server's reads on Postgres, as the memory login (spec appendix 5, sections 3 and
4; appendix 11, sections 1 and 2).

One made-up memory is written to the local Postgres. The memory login, whose role can only read,
then answers every lookup, and each answer must equal the in-memory stand-in's: the search finds
the same episodes in the same order as before, with `pgvector` comparing the text numbers.
"""

import psycopg
import pytest

from jev_trader.memory.lookups import Lookups
from jev_trader.memory.search import Filters
from jev_trader.memory.store import NoSnapshot, UnknownSim
from tests.postgres.helpers import connect
from tests.postgres.made_up_memory import LATER, NOW, written_memory

pytestmark = pytest.mark.dormant


@pytest.fixture
def written(sim_db, setup_login, made_up_dataset):
    return written_memory(sim_db, setup_login, made_up_dataset)


def answers(lookups: Lookups, sim: int, step: int = NOW) -> dict:
    review = {"job": "position_review", "position_direction": "long"}
    searches = {
        "any": ("ASSET_01", {}, {}),
        "same asset": ("ASSET_01", {"asset": "same_asset"}, {}),
        "same class": ("ASSET_01", {"asset": "same_asset_class"}, {}),
        "stock": ("ASSET_02", {"asset": "same_asset_class"}, {}),
        "hammer": ("ASSET_01", {"pattern": "hammer"}, {}),
        "long": ("ASSET_01", {"decided": "long"}, {}),
        "no trade": ("ASSET_01", {"decided": "no_trade"}, {}),
        "reviews": ("ASSET_01", {}, review),
        "closed reviews": ("ASSET_01", {"decided": "close"}, review),
        "in profit": ("ASSET_01", {"standing": "in_profit"}, review),
        "short reviews": ("ASSET_01", {}, {**review, "position_direction": "short"}),
    }
    found = {}
    for name, (asset, filters, job) in searches.items():
        result = lookups.search(
            sim,
            step,
            asset,
            job.get("job", "full_evaluation"),
            Filters(**filters),
            job.get("position_direction"),
        )
        found[name] = result.model_dump()
    every = [f"{sim}-{s}-{a}" for s, a in ((120, "ASSET_01"), (140, "ASSET_01"))]
    found["read"] = lookups.read(sim, step, every).model_dump()
    for asset, pattern, direction in (
        ("ASSET_01", "hammer", "long"),
        ("ASSET_01", "doji", "short"),
        ("ASSET_02", "doji", "long"),
    ):
        found[f"track record {asset} {pattern}"] = lookups.track_record(
            sim, step, asset, pattern, direction
        ).model_dump()
    return found


def test_the_real_reads_answer_as_the_stand_in_does(written, memory_db):
    expected = answers(Lookups(written.store), written.sim)
    real = answers(Lookups(memory_db.memory_store()), written.sim)

    # Not vacuous: the made-up memory gives each lookup something to find.
    assert all(
        expected[k]["episodes"] for k in expected if not k.startswith("track record")
    )
    assert expected["track record ASSET_01 hammer"]["closed_trades"] == 11
    assert expected["track record ASSET_02 doji"]["closed_trades"] == 1
    for name in expected:
        assert real[name] == expected[name], name


def test_a_search_lists_the_episodes_in_the_same_order(written, memory_db):
    """The order is the answer: the closest episode first, by both rankings."""
    filters = Filters()
    expected = Lookups(written.store).search(
        written.sim, NOW, "ASSET_01", "full_evaluation", filters
    )
    real = Lookups(memory_db.memory_store()).search(
        written.sim, NOW, "ASSET_01", "full_evaluation", filters
    )

    order = [
        (f.episode.id, f.vector_rank, f.text_rank, f.merged_rank)
        for f in expected.episodes
    ]
    assert len(order) > 2
    assert [
        (f.episode.id, f.vector_rank, f.text_rank, f.merged_rank) for f in real.episodes
    ] == order


def test_a_later_step_sees_what_completed_since(written, memory_db):
    """The trade decided at NOW - 20 closes after NOW: a lookup at a later step counts it."""
    lookups = Lookups(memory_db.memory_store())
    stand_in = Lookups(written.store)

    now = lookups.track_record(written.sim, NOW, "ASSET_01", "hammer", "long")
    later = lookups.track_record(written.sim, LATER, "ASSET_01", "hammer", "long")

    assert later.closed_trades == now.closed_trades + 1
    assert later == stand_in.track_record(
        written.sim, LATER, "ASSET_01", "hammer", "long"
    )


def test_an_unknown_sim_or_a_missing_snapshot_is_named(written, memory_db):
    store = memory_db.memory_store()

    with pytest.raises(UnknownSim):
        store.sim(written.sim + 1000)
    with pytest.raises(NoSnapshot):
        store.snapshot(written.dataset, "ASSET_01", NOW + 1)


def test_the_memory_login_can_read_and_cannot_write(written):
    with connect("memory") as con:
        decisions = con.execute(
            "SELECT COUNT(*) FROM MEMORY.DECISIONS WHERE SIM = %s", (written.sim,)
        ).fetchone()
        assert decisions == (len(written.store.decisions_table),)
        for statement in (
            "UPDATE MEMORY.DECISIONS SET ACTION = 'close'",
            "DELETE FROM MEMORY.OUTCOMES",
            "UPDATE SIM.SIMS SET STATUS = 'failed'",
            "DELETE FROM FEATURES.SNAPSHOTS",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                con.execute(statement)
