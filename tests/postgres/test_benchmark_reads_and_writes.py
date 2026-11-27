"""The LLM benchmark's reads and writes on Postgres (spec appendix 9, section 8).

The benchmark reads the build-up sim's last days of decisions as the sim login, and writes each
call it makes to `SIM.CALLS` with the purpose "benchmark" and no sim. No model is called: the
fake runner's attempt stands in for a real one.
"""

import pytest

from jev_trader.benchmark.made_up import FakeRunner, made_up_moments
from jev_trader.benchmark.moments import BuildUpSim, NoSavedMoments
from jev_trader.benchmark.records import DatabaseAttemptLog
from jev_trader.llm.models import load_model_settings
from jev_trader.llm.settings import LlmSettings
from jev_trader.memory.outcomes import EPISODE_KINDS
from tests.postgres.made_up_memory import made_up, write


def build_up_sim(sim_db, dataset, status="finished"):
    return sim_db.sim_store().create(
        {
            "DATASET": dataset,
            "KIND": "build-up",
            "VARIANT": "memory_on",
            "FIRST_STEP": 97,
            "LAST_STEP": 576,
            "STARTING_VALUE": 10_000.0,
            "SETTINGS": {},
            "STATUS": status,
            "LAST_COMPLETED_STEP": 576,
        }
    )


def test_the_build_up_sims_full_evaluations_and_reviews_are_the_candidates(
    sim_db, setup_login, made_up_dataset
):
    dataset = made_up_dataset(days=6, assets=0)
    sim = build_up_sim(sim_db, dataset)
    memory = made_up(sim, dataset)
    write(memory, setup_login)

    candidates = BuildUpSim(sim_db, sim).candidates()

    expected = sorted(
        (row["ASSET"], row["STEP"], row["KIND"])
        for row in memory.store.decisions_table
        if row["KIND"] in EPISODE_KINDS
    )
    assert expected, "the made-up memory holds episodes"
    assert sorted((c.asset, c.step, c.job) for c in candidates) == expected
    reviews = [c for c in candidates if c.position is not None]
    assert {c.job for c in reviews} == {"position_review"}
    assert {c.position.standing.direction for c in reviews} == {"long", "short"}


def test_only_a_finished_build_up_sim_is_drawn_from(sim_db, made_up_dataset):
    dataset = made_up_dataset(days=1)
    running = build_up_sim(sim_db, dataset, status="running")

    with pytest.raises(NoSavedMoments, match="running"):
        BuildUpSim(sim_db, running)
    with pytest.raises(NoSavedMoments, match="no sim"):
        BuildUpSim(sim_db, running + 1000)


def test_each_call_of_an_attempt_is_kept_in_the_calls_table(
    sim_db, setup_login, tmp_path
):
    settings = load_model_settings()
    model = LlmSettings(model=settings.setting(next(iter(settings.models))))
    attempt = FakeRunner().run(made_up_moments()[0], model, pass_number=2)

    DatabaseAttemptLog(sim_db.connection, tmp_path, run="20261127T120000Z").keep(
        attempt
    )

    rows = setup_login.execute(
        "SELECT sim, purpose, service, cost_usd FROM sim.calls"
    ).fetchall()
    assert rows == [(None, "benchmark", "fake", attempt.calls[0].cost_usd)]
    assert len(list((tmp_path / "20261127T120000Z").iterdir())) == 1
