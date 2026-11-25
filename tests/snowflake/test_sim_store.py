"""How a step is written, against the real test database (spec appendix 6, sections 6 and 11).

Hand-run: needs `infra/migrations/V4__sim_tables.sql` applied to TRADING_AGENT_TEST and the
builder's and the sim's keys in `SNOWFLAKE_LOCAL_DIR`. Made-up datasets only.

    conda run -n agentic-jev-trader python -m pytest tests/snowflake/test_sim_store.py -s

The test that kills a sim while it writes can wait up to 5 minutes: Snowflake undoes a dead
program's open transaction only after it has blocked another one for 5 minutes.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from jev_trader.broker import load_stop_price_settings, load_trading_costs
from jev_trader.jev.client import JevReply
from jev_trader.jev.full_evaluation import Evaluation, candidate_trades
from jev_trader.jev.position_review import Review
from jev_trader.jev.reading import JevRequest, Reading
from jev_trader.llm.selection import SelectionLimits, standing_part
from jev_trader.risk import load_risk_profile
from jev_trader.sim import records as records_of
from jev_trader.sim import snowflake_store
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.store import TABLES, InMemorySimStore, StepAlreadyWritten

REPO_ROOT = Path(__file__).resolve().parents[2]
KILLED_SIM = Path(__file__).with_name("killed_sim.py")


def new_sim(store, market, dataset_id, remove_sims, last_step):
    request = SimRequest(
        dataset=dataset_id,
        variant="buy_hold",
        kind="practice",
        first_step=97,
        last_step=last_step,
    )
    sim_id = create_sim(store, market, request)
    remove_sims.append(sim_id)
    return sim_id


def records(con, sim_id):
    """Every record of a sim, table by table, without the sim's ID: comparable across sims."""
    found = {}
    with con.cursor() as cur:
        for table in TABLES:
            if table == "SIM.SIM_EVENTS":
                continue
            cur.execute(
                f"SELECT * EXCLUDE (ID, SIM) FROM {table} WHERE SIM = ?", (sim_id,)
            )
            found[table] = sorted(cur.fetchall(), key=repr)
    return found


@pytest.fixture
def two_day_sim(sim_login, made_up_dataset, remove_sims):
    """A holding sim over two days after a one-day warm-up, on two assets: 192 steps."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    dataset_id = made_up_dataset(days=3, assets=2)

    def make():
        return new_sim(store, market, dataset_id, remove_sims, last_step=288)

    return store, market, make


def test_a_holding_sim_over_a_published_dataset_runs_to_the_end(two_day_sim, sim_login):
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
    with sim_login.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM SIM.ACCOUNT_STEPS WHERE SIM = ?", (sim_id,))
        assert cur.fetchone() == (192,)


def test_a_screens_records_are_written_and_its_cost_is_summed(
    sim_login, made_up_dataset, remove_sims
):
    """Needs `infra/migrations/V5__jev_requests_and_decisions.sql`, V6 and V7 applied."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    sim_id = new_sim(store, market, made_up_dataset(days=2), remove_sims, last_step=192)
    store.update(sim_id, STATUS="running")
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
    with sim_login.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM SIM.JEV_READINGS WHERE READING_VERSION = ?",
            (reading.version,),
        )
        assert cur.fetchone() == (1,)
        cur.execute(
            "SELECT BACKGROUND_AFTER_OPENING, QUESTIONS:screen:instructions::VARCHAR "
            "FROM SIM.JEV_REQUESTS WHERE SIM = ?",
            (sim_id,),
        )
        assert cur.fetchone() == ("The rest.", "Worth a look?")
        cur.execute(
            "SELECT SCREEN_ANSWER FROM MEMORY.DECISIONS WHERE SIM = ?", (sim_id,)
        )
        assert cur.fetchone() == (0.62,)


def test_the_llms_standing_instructions_are_stored_once_per_prompt_version(sim_login):
    """Needs `infra/migrations/V10__llm_prompts_and_fit_question.sql` applied."""
    store = SnowflakeSimStore(sim_login)
    version, system_prompt, tools = standing_part(SelectionLimits(), ["hammer"])

    store.save_prompt(version, system_prompt, tools)
    store.save_prompt(version, system_prompt, tools)  # stored once

    with sim_login.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), MIN(SYSTEM_PROMPT), MIN(TOOLS[3]:name::VARCHAR) "
            "FROM SIM.LLM_PROMPTS WHERE PROMPT_VERSION = ?",
            (version,),
        )
        assert cur.fetchone() == (1, system_prompt, "select_episodes")


def test_a_full_evaluation_is_written_beside_a_screen_and_both_are_counted(
    sim_login, made_up_dataset, remove_sims
):
    """Needs `infra/migrations/V6__full_evaluation_columns.sql` and V7 applied."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    sim_id = new_sim(store, market, made_up_dataset(days=2), remove_sims, last_step=192)
    store.update(sim_id, STATUS="running")
    no = JevReply('{"answers":{"screen":{"noul":0.2}}}', "jev-1", 10, 2, 0.0, 0.1, 0)
    yes = JevReply('{"answers":{"screen":{"noul":0.8}}}', "jev-1", 10, 2, 0.0, 0.1, 0)
    trades = candidate_trades(100.0, 0.5, load_stop_price_settings())
    evaluation = Evaluation(
        candidates=trades,
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
    with sim_login.cursor() as cur:
        cur.execute(
            "SELECT KIND, PICK, ANSWERS:pick_1:long_tight_stop::FLOAT, "
            "ARRAY_SIZE(CANDIDATE_TRADES), SIZE_AFTER_TRIMMING, LIMITED_BY, ACTION "
            "FROM MEMORY.DECISIONS WHERE SIM = ? AND TIER = 2",
            (sim_id,),
        )
        assert cur.fetchone() == (
            "full_evaluation",
            "long_tight_stop",
            0.7,
            6,
            2500.0,
            "trade_risk",
            "entry",
        )


def test_position_screens_and_reviews_are_written_and_counted(
    sim_login, made_up_dataset, remove_sims
):
    """Needs `infra/migrations/V7__position_review_columns.sql` applied."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    sim_id = new_sim(store, market, made_up_dataset(days=2), remove_sims, last_step=192)
    store.update(sim_id, STATUS="running")
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
    with sim_login.cursor() as cur:
        cur.execute(
            "SELECT KIND, POSITION, PICK, STANDING:bars_open::NUMBER, END_OF_SESSION, "
            "THESIS_INTACT, REDUCE_SHARE, ACTION "
            "FROM MEMORY.DECISIONS WHERE SIM = ? AND TIER = 2",
            (sim_id,),
        )
        assert cur.fetchone() == (
            "position_review",
            5,
            "reduce",
            3,
            True,
            0.6,
            0.375,
            "reduce",
        )


def test_outcomes_are_written_and_mark_their_decision_complete_in_a_later_step(
    sim_login, made_up_dataset, remove_sims
):
    """Needs `infra/migrations/V8__episode_outcomes.sql` applied."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    sim_id = new_sim(store, market, made_up_dataset(days=2), remove_sims, last_step=192)
    store.update(sim_id, STATUS="running")
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

    with sim_login.cursor() as cur:
        cur.execute(
            "SELECT OUTCOMES_KNOWN_FROM FROM MEMORY.DECISIONS WHERE SIM = ?", (sim_id,)
        )
        assert cur.fetchone() == (98,)
        cur.execute(
            "SELECT KIND, VALUE:price::FLOAT, KNOWN_FROM FROM MEMORY.OUTCOMES "
            "WHERE SIM = ?",
            (sim_id,),
        )
        assert cur.fetchone() == ("price_after_1_bar", 100.2, 98)


def _request_of(sim):
    return SimRequest(
        dataset=sim["DATASET"],
        variant=sim["VARIANT"],
        kind=sim["KIND"],
        first_step=sim["FIRST_STEP"],
        last_step=sim["LAST_STEP"],
        starting_value=sim["STARTING_VALUE"],
    )


def test_a_write_stopped_halfway_stores_nothing(two_day_sim, monkeypatch):
    store, market, make = two_day_sim
    sim_id = make()
    inserts = 0
    insert = snowflake_store._insert

    def fails_on_the_second_table(*args, **kwargs):
        nonlocal inserts
        inserts += 1
        if inserts == 2:
            raise RuntimeError("stopped halfway through the write")
        return insert(*args, **kwargs)

    monkeypatch.setattr(snowflake_store, "_insert", fails_on_the_second_table)
    with pytest.raises(RuntimeError, match="halfway"):
        run_sim(store, market, sim_id, steps_per_write=10)

    assert store.sim(sim_id)["LAST_COMPLETED_STEP"] is None
    with store.con.cursor() as cur:
        for table in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE SIM = ?", (sim_id,))
            assert cur.fetchone() == (0,), table


def test_two_copies_of_one_sim_cannot_both_write_a_step(
    two_day_sim, sim_login, another_sim_login
):
    store, _market, make = two_day_sim
    sim_id = make()
    store.update(sim_id, STATUS="running")
    row = {"ID": f"{sim_id}-97", "SIM": sim_id, "STEP": 97, "CASH": 1.0, "LOAN": 0.0}
    row |= {"EXPOSURE": 0.0, "ACCOUNT_VALUE": 1.0, "START_OF_DAY_VALUE": 1.0}
    row |= {"DAILY_LOSS_REACHED": False}
    rows = {"SIM.ACCOUNT_STEPS": [row]}

    # Copy one moves the last completed step and holds its transaction open.
    with sim_login.cursor() as first:
        first.execute("BEGIN TRANSACTION")
        first.execute(
            "UPDATE SIM.SIMS SET LAST_COMPLETED_STEP = 97 "
            "WHERE ID = ? AND LAST_COMPLETED_STEP IS NULL",
            (sim_id,),
        )
        # Copy two, on its own connection, tries the same step and waits for the lock.
        second = SnowflakeSimStore(another_sim_login)
        outcome = {}

        def second_copy():
            try:
                second.write_steps(sim_id, None, 97, rows, {})
                outcome["result"] = "wrote"
            except StepAlreadyWritten:
                outcome["result"] = "refused"

        thread = threading.Thread(target=second_copy)
        thread.start()
        time.sleep(5)
        assert thread.is_alive(), "the second copy should be waiting for the lock"
        first.execute("COMMIT")
        thread.join(timeout=120)

    assert outcome == {"result": "refused"}
    with sim_login.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM SIM.ACCOUNT_STEPS WHERE SIM = ?", (sim_id,))
        assert cur.fetchone() == (0,)


@pytest.mark.parametrize("when", ["mid-step", "while-writing"])
def test_a_sim_killed_and_restarted_ends_with_the_same_records(
    two_day_sim, sim_login, when
):
    store, market, make = two_day_sim
    never_stopped = make()
    run_sim(store, market, never_stopped, steps_per_write=20)

    killed = make()
    # The third write (steps 137 to 156) never lands.
    finished = subprocess.run(
        [sys.executable, str(KILLED_SIM), str(killed), "20", when, "3"],
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        timeout=300,
    )
    assert finished.returncode == 9, "the sim should have been killed"
    assert store.sim(killed)["LAST_COMPLETED_STEP"] == 136

    run_sim(store, market, killed, steps_per_write=20)  # may wait for Snowflake to undo

    assert records(sim_login, killed) == records(sim_login, never_stopped)
    assert store.duplicate_ids(killed) == {}
    with sim_login.cursor() as cur:
        cur.execute("SELECT KIND, STEP FROM SIM.SIM_EVENTS WHERE SIM = ?", (killed,))
        assert cur.fetchall() == [("restarted", 137)]


def test_the_duplicate_count_finds_an_id_stored_twice(two_day_sim, sim_login):
    store, _market, make = two_day_sim
    sim_id = make()
    with sim_login.cursor() as cur:
        for _ in range(2):
            cur.execute(
                "INSERT INTO SIM.SIM_EVENTS (ID, SIM, STEP, KIND) VALUES (?, ?, 97, 'test')",
                (f"{sim_id}-97-test-1", sim_id),
            )

    assert store.duplicate_ids(sim_id) == {"SIM.SIM_EVENTS": 1}


def test_what_the_checker_reads_spending_sims_in_progress_and_the_tier_2_share(
    sim_login, made_up_dataset, remove_sims
):
    """Needs V5 and V6 applied. The latest practice sim of the agent is the one made here."""
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    dataset_id = made_up_dataset(days=2, assets=2)
    sim_id = new_sim(store, market, dataset_id, remove_sims, last_step=192)
    store.update(sim_id, STATUS="running", VARIANT="memory_off", SPENDING_CAP=0.25)
    paid_before = store.total_spent()
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

    assert store.total_spent() == pytest.approx(paid_before + 0.07)
    [mine] = [s for s in store.sims_in_progress() if s["ID"] == sim_id]
    assert mine == {
        "ID": sim_id,
        "KIND": "practice",
        "VARIANT": "memory_off",
        "STATUS": "running",
        "SPENDING_CAP": 0.25,
        "SPENT": pytest.approx(0.07),
    }
    # One screen of two led to a full evaluation.
    assert store.latest_tier_2_share() == pytest.approx(0.5)
    # Two crypto assets with a bar at every step of day 2.
    assert market.bar_count(dataset_id, 97, 192) == 2 * 96
