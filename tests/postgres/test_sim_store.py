"""How a sim's steps are written on Postgres, as the sim login (spec appendix 6, sections 6 and
11; appendix 11, sections 1 and 4). Made-up datasets only.

The test that kills a sim while it writes may find the killed write landed whole: the write goes
to the database in one trip, so the program can die after the database has it all. Either way
nothing is half written, and the resumed sim ends with the same records.
"""

import os
import subprocess
import sys
import threading
import time

import psycopg
import pytest

from jev_trader.broker import load_stop_price_settings, load_trading_costs
from jev_trader.jev.client import JevReply
from jev_trader.jev.full_evaluation import Evaluation, candidate_trades
from jev_trader.jev.position_review import Review
from jev_trader.jev.reading import JevRequest, Reading
from jev_trader.llm.selection import SelectionLimits, standing_part
from jev_trader.risk import load_risk_profile
from jev_trader.sim import records as records_of
from jev_trader.sim.postgres_store import PostgresSimStore
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import TABLES, InMemorySimStore, StepAlreadyWritten
from jev_trader.storage import postgres
from tests.postgres.helpers import LOCAL_ENV, REPO_ROOT, TEST_DATABASE, connect, parsed

pytestmark = pytest.mark.dormant

KILLED_SIM = REPO_ROOT / "tests" / "postgres" / "killed_sim.py"


def new_sim(store, market, dataset_id, last_step):
    request = SimRequest(
        dataset=dataset_id,
        variant="buy_hold",
        kind="practice",
        first_step=97,
        last_step=last_step,
    )
    return create_sim(store, market, request)


def records(con, sim_id):
    """Every record of a sim, table by table, without the sim's ID: comparable across sims."""
    found = {}
    for table in TABLES:
        if table == "SIM.SIM_EVENTS":
            continue
        with con.cursor() as cur:
            cur.execute(f"SELECT * FROM {table} WHERE SIM = %s", (sim_id,))
            names = [d.name for d in cur.description]
            rows = [
                {n: v for n, v in zip(names, row) if n not in ("id", "sim")}
                for row in cur.fetchall()
            ]
        found[table] = sorted(rows, key=repr)
    return found


@pytest.fixture
def sims(sim_db):
    return sim_db.sim_store(), sim_db.market()


@pytest.fixture
def two_day_sim(sims, made_up_dataset):
    """A holding sim over two days after a one-day warm-up, on two assets: 192 steps."""
    store, market = sims
    dataset_id = made_up_dataset(days=3, assets=2)

    def make():
        return new_sim(store, market, dataset_id, last_step=288)

    return store, market, make


@pytest.fixture
def running_sim(sims, made_up_dataset):
    store, market = sims
    sim_id = new_sim(store, market, made_up_dataset(days=2, assets=2), 192)
    store.update(sim_id, STATUS="running")
    return store, sim_id


def _request_of(sim):
    return SimRequest(
        dataset=sim["DATASET"],
        variant=sim["VARIANT"],
        kind=sim["KIND"],
        first_step=sim["FIRST_STEP"],
        last_step=sim["LAST_STEP"],
        starting_value=sim["STARTING_VALUE"],
    )


def account_row(sim_id, step):
    row = {"ID": f"{sim_id}-{step}", "SIM": sim_id, "STEP": step, "CASH": 1.0}
    row |= {"LOAN": 0.0, "EXPOSURE": 0.0, "ACCOUNT_VALUE": 1.0}
    return row | {"START_OF_DAY_VALUE": 1.0, "DAILY_LOSS_REACHED": False}


def test_a_holding_sim_over_a_published_dataset_runs_to_the_end(
    two_day_sim, setup_login
):
    store, market, make = two_day_sim
    sim_id = make()

    result = run_sim(store, market, sim_id, steps_per_write=50)

    sim = store.sim(sim_id)
    assert (sim["STATUS"], sim["LAST_COMPLETED_STEP"]) == ("finished", 288)
    assert store.duplicate_ids(sim_id) == {}
    # The same sim on the in-memory stand-in, fed the same bars, ends the same.
    memory = InMemorySimStore()
    expected = run_sim(memory, market, create_sim(memory, market, _request_of(sim)))
    assert result.ending_value == pytest.approx(expected.ending_value, abs=1e-6)
    assert setup_login.execute(
        "SELECT COUNT(*) FROM SIM.ACCOUNT_STEPS WHERE SIM = %s", (sim_id,)
    ).fetchone() == (192,)


def test_the_market_reads_a_published_dataset(sims, made_up_dataset):
    _store, market = sims
    dataset_id = made_up_dataset(days=2, assets=2)

    info = market.dataset(dataset_id)
    bars = market.bars(dataset_id, 97, 100)

    assert info.status == "published"
    assert market.bar_count(dataset_id, 97, 192) == 2 * 96
    assert sorted(bars) == [97, 98, 99, 100]
    assert sorted(bars[97]) == ["ASSET_01", "ASSET_02"]


def test_a_screens_records_are_written_and_its_cost_is_summed(running_sim, setup_login):
    store, sim_id = running_sim
    reply = JevReply(
        '{"answers":{"screen":{"noul":0.62}}}', "jev-1", 10, 2, 0.5, 0.1, 0
    )
    reading = Reading(load_trading_costs(), load_risk_profile())
    request = JevRequest(
        reading.opening + "\n\nThe rest.",
        {"screen": {"type": "noul", "instructions": "Worth a look?"}},
    )

    store.save_reading(reading.version, reading.opening)
    store.save_reading(reading.version, reading.opening)  # stored once
    store.write_steps(
        sim_id,
        None,
        97,
        {
            "MEMORY.DECISIONS": [
                records_of.decision_row(sim_id, 1, 97, "ASSET_01", None, reply)
            ],
            "SIM.JEV_REQUESTS": [
                records_of.jev_request_row(
                    sim_id, 97, "ASSET_01", reading, request, reply
                )
            ],
            "SIM.CALLS": [records_of.jev_call_row(sim_id, 97, "ASSET_01", reply)],
        },
        {},
    )

    assert store.spent(sim_id) == pytest.approx(0.5)
    assert setup_login.execute(
        "SELECT COUNT(*) FROM SIM.JEV_READINGS WHERE READING_VERSION = %s",
        (reading.version,),
    ).fetchone() == (1,)
    after_opening, questions = setup_login.execute(
        "SELECT BACKGROUND_AFTER_OPENING, QUESTIONS FROM SIM.JEV_REQUESTS WHERE SIM = %s",
        (sim_id,),
    ).fetchone()
    assert after_opening == "The rest."
    assert parsed(questions)["screen"]["instructions"] == "Worth a look?"
    assert setup_login.execute(
        "SELECT SCREEN_ANSWER FROM MEMORY.DECISIONS WHERE SIM = %s", (sim_id,)
    ).fetchone() == (0.62,)


def test_the_llms_standing_instructions_are_stored_once_per_prompt_version(
    sim_db, setup_login
):
    store = sim_db.sim_store()
    version, system_prompts, tools = standing_part(SelectionLimits(), ["hammer"])

    store.save_prompt(version, system_prompts, tools)
    store.save_prompt(version, system_prompts, tools)  # stored once

    stored = setup_login.execute(
        "SELECT SYSTEM_PROMPT, TOOLS FROM SIM.LLM_PROMPTS WHERE PROMPT_VERSION = %s",
        (version,),
    ).fetchall()
    [(system_prompt, stored_tools)] = stored
    assert parsed(system_prompt)["position_review"] == system_prompts["position_review"]
    assert parsed(stored_tools)["full_evaluation"][3]["name"] == "select_episodes"


def test_a_full_evaluation_is_written_beside_a_screen_and_both_are_counted(
    running_sim, setup_login
):
    store, sim_id = running_sim
    no = JevReply('{"answers":{"screen":{"noul":0.2}}}', "jev-1", 10, 2, 0.0, 0.1, 0)
    yes = JevReply('{"answers":{"screen":{"noul":0.8}}}', "jev-1", 10, 2, 0.0, 0.1, 0)
    evaluation = Evaluation(
        candidates=candidate_trades(100.0, 0.5, load_stop_price_settings()),
        answers={"pick_1": {"long_tight_stop": 0.7, "no_trade": 0.3}},
        pick="long_tight_stop",
        rating=2.5,
        size_chosen=3000.0,
        size_after_trimming=2500.0,
        limited_by="trade_risk",
    )

    store.write_steps(
        sim_id,
        None,
        97,
        {
            "MEMORY.DECISIONS": [
                records_of.decision_row(sim_id, 1, 97, "ASSET_01", None, no),
                records_of.decision_row(
                    sim_id, 1, 97, "ASSET_02", None, yes, evaluation, "entry"
                ),
            ]
        },
        {},
    )

    assert store.screen_counts(sim_id, 0.5) == (2, 1)
    assert store.full_evaluation_counts(sim_id) == (1, 1)
    kind, pick, answers, trades, trimmed, limited_by, action = setup_login.execute(
        "SELECT KIND, PICK, ANSWERS, CANDIDATE_TRADES, SIZE_AFTER_TRIMMING, "
        "LIMITED_BY, ACTION FROM MEMORY.DECISIONS WHERE SIM = %s AND TIER = 2",
        (sim_id,),
    ).fetchone()
    assert (kind, pick, trimmed, limited_by, action) == (
        "full_evaluation",
        "long_tight_stop",
        2500.0,
        "trade_risk",
        "entry",
    )
    assert parsed(answers)["pick_1"]["long_tight_stop"] == 0.7
    assert len(parsed(trades)) == 6


def test_position_screens_and_reviews_are_written_and_counted(running_sim, setup_login):
    store, sim_id = running_sim
    held = JevReply(
        '{"answers":{"position_screen":{"noul":0.2}}}', "jev-1", 10, 2, 0.0, 0.1, 0
    )
    review = Review(
        standing={"direction": "long", "bars_open": 3, "profit": 18.0},
        end_of_session=True,
        answers={"action_1": {"hold": 0.3, "reduce": 0.7}, "thesis_intact": 0.6},
        action="reduce",
        thesis_intact=0.6,
        reduce_share=0.375,
    )

    store.write_steps(
        sim_id,
        None,
        97,
        {
            "MEMORY.DECISIONS": [
                records_of.decision_row(sim_id, 1, 97, "ASSET_03", "daily_loss"),
                records_of.position_decision_row(
                    sim_id, 1, 97, "ASSET_01", 4, None, held
                ),
                records_of.position_decision_row(
                    sim_id, 1, 97, "ASSET_02", 5, None, None, review, "reduce"
                ),
            ]
        },
        {},
    )

    assert store.position_screen_counts(sim_id, 0.5) == (1, 0)
    assert store.position_review_counts(sim_id) == {
        "reviews": 1,
        "end_of_session": 1,
        "close": 0,
        "reduce": 1,
        "add": 0,
    }
    row = setup_login.execute(
        "SELECT KIND, POSITION, PICK, STANDING, END_OF_SESSION, THESIS_INTACT, "
        "REDUCE_SHARE, ACTION FROM MEMORY.DECISIONS WHERE SIM = %s AND TIER = 2",
        (sim_id,),
    ).fetchone()
    kind, position, pick, standing, *rest = row
    assert (kind, position, pick) == ("position_review", 5, "reduce")
    assert parsed(standing)["bars_open"] == 3
    assert tuple(rest) == (True, 0.6, 0.375, "reduce")


def test_a_sim_without_reviews_counts_each_kind_as_none(running_sim):
    """The end-of-run report reads the counts of a sim that never reviewed a position (#258)."""
    store, sim_id = running_sim

    assert store.position_review_counts(sim_id) == {
        "reviews": 0,
        "end_of_session": 0,
        "close": 0,
        "reduce": 0,
        "add": 0,
    }
    assert store.position_screen_counts(sim_id, 0.5) == (0, 0)
    assert store.screen_counts(sim_id, 0.5) == (0, 0)
    assert store.full_evaluation_counts(sim_id) == (0, 0)
    assert store.spent(sim_id) == 0


def test_outcomes_are_written_and_mark_their_decision_complete_in_a_later_step(
    running_sim, setup_login
):
    store, sim_id = running_sim
    decision = records_of.decision_row(sim_id, 1, 97, "ASSET_01", None)
    outcome = {
        "ID": f"{decision['ID']}-price_after_1_bar",
        "SIM": sim_id,
        "FIRST_WRITTEN_BY": sim_id,
        "DECISION": decision["ID"],
        "KIND": "price_after_1_bar",
        "VALUE": {"price": 100.2, "change": 0.002},
        "KNOWN_FROM": 98,
    }

    store.write_steps(sim_id, None, 97, {"MEMORY.DECISIONS": [decision]}, {})
    store.write_steps(
        sim_id, 97, 98, {"MEMORY.OUTCOMES": [outcome]}, {}, {decision["ID"]: 98}
    )

    assert setup_login.execute(
        "SELECT OUTCOMES_KNOWN_FROM FROM MEMORY.DECISIONS WHERE SIM = %s", (sim_id,)
    ).fetchone() == (98,)
    kind, value, known_from = setup_login.execute(
        "SELECT KIND, VALUE, KNOWN_FROM FROM MEMORY.OUTCOMES WHERE SIM = %s",
        (sim_id,),
    ).fetchone()
    assert (kind, parsed(value)["price"], known_from) == (
        "price_after_1_bar",
        100.2,
        98,
    )


def test_an_order_rewritten_in_a_later_step_is_stored_once(running_sim, setup_login):
    store, sim_id = running_sim
    order = {
        "ID": f"{sim_id}-97-ASSET_01-1",
        "SIM": sim_id,
        "POSITION": 1,
        "INSTRUMENT": "ASSET_01_SPOT",
        "KIND": "entry",
        "REASON": "jev",
        "STEP_DECIDED": 97,
        "STATUS": "waiting",
    }

    store.write_steps(sim_id, None, 97, {"SIM.ORDERS": [order]}, {})
    store.write_steps(
        sim_id, 97, 98, {"SIM.ORDERS": [{**order, "STATUS": "carried out"}]}, {}
    )

    assert setup_login.execute(
        "SELECT STATUS FROM SIM.ORDERS WHERE SIM = %s", (sim_id,)
    ).fetchall() == [("carried out",)]
    assert store.duplicate_ids(sim_id) == {}


def test_a_write_that_fails_halfway_stores_nothing_and_the_next_one_works(
    running_sim, setup_login
):
    store, sim_id = running_sim
    event = {"ID": f"{sim_id}-97-test", "SIM": sim_id, "STEP": "not a step"}
    event |= {"KIND": "test"}

    with pytest.raises(psycopg.Error):
        store.write_steps(
            sim_id,
            None,
            97,
            {
                "SIM.ACCOUNT_STEPS": [account_row(sim_id, 97)],
                "SIM.SIM_EVENTS": [event],
            },
            {},
        )

    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] is None
    for table in TABLES:
        assert setup_login.execute(
            f"SELECT COUNT(*) FROM {table} WHERE SIM = %s", (sim_id,)
        ).fetchone() == (0,), table
    # The one connection is still good for the next write.
    store.write_steps(
        sim_id, None, 97, {"SIM.ACCOUNT_STEPS": [account_row(sim_id, 97)]}, {}
    )
    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] == 97


def test_two_copies_of_one_sim_cannot_both_write_a_step(running_sim, setup_login):
    _store, sim_id = running_sim
    rows = {"SIM.ACCOUNT_STEPS": [account_row(sim_id, 97)]}
    # Copy two is another program: its own connection as the sim login.
    second = PostgresSimStore(
        postgres.OneConnection(postgres.settings("sim", TEST_DATABASE, LOCAL_ENV))
    )
    outcome = {}

    def second_copy():
        try:
            second.write_steps(sim_id, None, 97, rows, {})
            outcome["result"] = "wrote"
        except StepAlreadyWritten:
            outcome["result"] = "refused"

    # Copy one moves the last completed step and holds its transaction open.
    with connect("sim") as first:
        first.execute("BEGIN")
        first.execute(
            "UPDATE SIM.SIMS SET LAST_COMPLETED_STEP = 97 "
            "WHERE ID = %s AND LAST_COMPLETED_STEP IS NULL",
            (sim_id,),
        )
        thread = threading.Thread(target=second_copy)
        thread.start()
        time.sleep(2)
        assert thread.is_alive(), "the second copy should be waiting for the lock"
        first.execute("COMMIT")
        thread.join(timeout=60)
    second.con.close()

    assert outcome == {"result": "refused"}
    assert setup_login.execute(
        "SELECT COUNT(*) FROM SIM.ACCOUNT_STEPS WHERE SIM = %s", (sim_id,)
    ).fetchone() == (0,)


@pytest.mark.parametrize("when", ["mid-step", "while-writing"])
def test_a_sim_killed_and_restarted_ends_with_the_same_records(
    two_day_sim, setup_login, when
):
    store, market, make = two_day_sim
    never_stopped = make()
    run_sim(store, market, never_stopped, steps_per_write=20)

    killed = make()
    # The third write (steps 137 to 156) is under way when the program dies.
    finished = subprocess.run(
        [sys.executable, str(KILLED_SIM), str(killed), "20", when, "3"],
        check=False,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)]),
        },
        timeout=120,
    )
    assert finished.returncode == 9, "the sim should have been killed"
    killed_after = store.sim(killed)["LAST_COMPLETED_STEP"]
    if when == "mid-step":
        assert killed_after == 136
    else:
        assert killed_after in (136, 156)  # the third write landed whole, or not at all

    run_sim(store, market, killed, steps_per_write=20)

    assert records(setup_login, killed) == records(setup_login, never_stopped)
    assert store.duplicate_ids(killed) == {}
    assert setup_login.execute(
        "SELECT KIND, STEP FROM SIM.SIM_EVENTS WHERE SIM = %s", (killed,)
    ).fetchall() == [("restarted", killed_after + 1)]


def test_an_id_stored_twice_is_refused_or_counted(two_day_sim, setup_login):
    store, _market, make = two_day_sim
    sim_id = make()
    event = {"ID": f"{sim_id}-97-test-1", "SIM": sim_id, "STEP": 97, "KIND": "test"}
    insert = "INSERT INTO SIM.SIM_EVENTS (ID, SIM, STEP, KIND) VALUES (%s, %s, %s, %s)"
    setup_login.execute(insert, tuple(event.values()))
    try:
        setup_login.execute(insert, tuple(event.values()))
    except psycopg.errors.UniqueViolation:
        return  # the table cannot hold an ID twice

    assert store.duplicate_ids(sim_id) == {"SIM.SIM_EVENTS": 1}


def test_what_the_checker_reads_spending_sims_in_progress_and_the_tier_2_share(
    sims, made_up_dataset
):
    store, market = sims
    dataset_id = made_up_dataset(days=2, assets=2)
    sim_id = new_sim(store, market, dataset_id, last_step=192)
    store.update(sim_id, STATUS="running", VARIANT="memory_off", SPENDING_CAP=0.25)
    no = JevReply('{"answers":{"screen":{"noul":0.2}}}', "jev-1", 10, 2, 0.03, 0.1, 0)
    yes = JevReply('{"answers":{"screen":{"noul":0.8}}}', "jev-1", 10, 2, 0.04, 0.1, 0)
    evaluation = Evaluation(
        candidates=candidate_trades(100.0, 0.5, load_stop_price_settings()),
        answers={"pick_1": {"long_tight_stop": 0.7, "no_trade": 0.3}},
        pick="long_tight_stop",
        rating=2.5,
        size_chosen=3000.0,
        size_after_trimming=2500.0,
        limited_by="trade_risk",
    )
    assert store.total_spent() == 0
    store.write_steps(
        sim_id,
        None,
        97,
        {
            "MEMORY.DECISIONS": [
                records_of.decision_row(sim_id, 1, 97, "ASSET_01", None, no),
                records_of.decision_row(
                    sim_id, 1, 97, "ASSET_02", None, yes, evaluation, "entry"
                ),
            ],
            "SIM.CALLS": [
                records_of.jev_call_row(sim_id, 97, "ASSET_01", no),
                records_of.jev_call_row(sim_id, 97, "ASSET_02", yes),
            ],
        },
        {},
    )

    assert store.total_spent() == pytest.approx(0.07)
    assert store.sims_in_progress() == [
        {
            "ID": sim_id,
            "KIND": "practice",
            "VARIANT": "memory_off",
            "STATUS": "running",
            "SPENDING_CAP": 0.25,
            "SPENT": pytest.approx(0.07),
        }
    ]
    # One screen of two led to a full evaluation.
    assert store.latest_tier_2_share() == pytest.approx(0.5)
