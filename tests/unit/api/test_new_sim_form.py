"""The New trading sim form's two questions to the API (spec appendix 7, section 8; appendix 8,
sections 3 to 6): `GET /sims/check` (may this sim start, and what would it cost?) and `POST /sims`
for each kind of sim the app starts: measurement, build-up and free.

The dataset is made up: four days of one crypto asset with a bar at every step. Day 1 (steps 1
to 96) is the warm-up; day 2 (97 to 192) holds the base memory, a finished build-up sim; day 3
(193 to 288) is free; day 4 (289 to 384) is the test period "rising market". No test calls a
paid service: the jobs are stand-ins and the money is rows in `SIM.CALLS`.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.llm_names import llm_model
from jev_trader.api.store import InMemoryApiStore
from jev_trader.broker import AssetClass, Bar
from jev_trader.llm.models import load_model_settings
from jev_trader.sim.market import DatasetInfo, InMemoryMarket, Period
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInBuilds, StandInLauncher

NOW = datetime(2026, 11, 24, 12, 0)
CEILING = 75.0
DATASET = 7
HAIKU, GLM = "claude-haiku-5-5", "glm-5.3-flash"
DAY_3 = {"first_day": "2025-03-03", "last_day": "2025-03-03"}  # free days
# Days 3 and 4: free days running on into the test period.
DAYS_INTO_TEST_PERIOD = {"first_day": "2025-03-03", "last_day": "2025-03-04"}


def dataset(status="published"):
    return DatasetInfo(
        dataset_id=DATASET,
        status=status,
        first_step=1,
        last_step=384,
        periods=(
            Period("warm-up", "warm-up", 1, 96),
            Period("test", "rising market", 289, 384),
        ),
        assets={"ASSET_01": AssetClass.CRYPTO},
    )


def make_store(sims, status="published"):
    bars = [
        Bar(step=s, open=100.0, high=100.0, low=100.0, close=100.0)
        for s in range(1, 385)
    ]
    return InMemoryApiStore(
        sims,
        asset_key=[
            {
                "DATASET": DATASET,
                "MASKED_ID": "ASSET_01",
                "NAME": "Bitcoin",
                "FIRST_DAY": date(2025, 3, 1),
            }
        ],
        market=InMemoryMarket(
            datasets=[dataset(status)], bars={DATASET: {"ASSET_01": bars}}
        ),
    )


def client(store, launcher):
    return TestClient(
        create_app(
            store,
            spending_ceiling=CEILING,
            not_responding_after=timedelta(minutes=7),
            clock=lambda: NOW,
            launcher=launcher,
            builds=StandInBuilds(),
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def add_base_memory(sims, record_step=150):
    """A finished build-up sim on day 2, whose memory holds one decision at `record_step`."""
    sim_id = sims.create(
        {
            "DATASET": DATASET,
            "KIND": "build-up",
            "VARIANT": "memory_off",
            "FIRST_STEP": 97,
            "LAST_STEP": 192,
            "STATUS": "finished",
            "SPENDING_CAP": 1.00,
        }
    )
    sims.tables["MEMORY.DECISIONS"].append(
        {
            "ID": f"decision-{sim_id}",
            "SIM": sim_id,
            "STEP": record_step,
            "KIND": "full evaluation",
            "OUTCOMES_KNOWN_FROM": None,
        }
    )
    return sim_id


@pytest.fixture
def sims():
    sims = InMemorySimStore()
    add_base_memory(sims)
    return sims


@pytest.fixture
def launcher():
    return StandInLauncher()


@pytest.fixture
def api(sims, launcher):
    return client(make_store(sims), launcher)


def free_sim(**fields):
    return {
        "dataset": DATASET,
        "kind": "free",
        "variant": "memory_on",
        **DAY_3,
        **fields,
    }


def measurement(**fields):
    return {
        "dataset": DATASET,
        "kind": "measurement",
        "variant": "memory_on",
        "market": "rising market",
        "models": [HAIKU, GLM],
        **fields,
    }


def build_up(**fields):
    return {
        "dataset": DATASET,
        "kind": "build-up",
        "variant": "memory_off",
        "first_day": "2025-03-02",
        "last_day": "2025-03-03",
        **fields,
    }


def check(api, wanted):
    answer = api.get("/sims/check", params=wanted)
    assert answer.status_code == 200, answer.text
    return answer.json()


def codes(refusals):
    return {r["code"] for r in refusals}


def paid_call(sims, sim_id, cost):
    sims.tables["SIM.CALLS"].append(
        {"ID": f"call-{len(sims.tables['SIM.CALLS'])}", "SIM": sim_id, "COST_USD": cost}
    )


def sim_in_progress(sims, cap=0.25):
    return sims.create(
        {
            "DATASET": DATASET,
            "KIND": "practice",
            "VARIANT": "memory_off",
            "FIRST_STEP": 193,
            "LAST_STEP": 288,
            "STATUS": "running",
            "SPENDING_CAP": cap,
        }
    )


def snapshot(sims):
    """Everything stored, to show that a check changed none of it. Empty tables are left out:
    reading a table the in-memory store has never written makes an empty one."""
    return (
        {i: dict(row) for i, row in sims.sims.items()},
        {name: [dict(r) for r in rows] for name, rows in sims.tables.items() if rows},
    )


def new_agent_sims(sims, before):
    """The sims of the agent (not the sim holding the five assets) created since `before`, by ID."""
    return {
        i: row
        for i, row in sims.sims.items()
        if i not in before[0] and row["VARIANT"] != "buy_hold"
    }


# The check stores nothing and answers the money


@pytest.mark.parametrize("wanted", [free_sim(), measurement(), build_up()])
def test_the_check_stores_nothing_and_starts_nothing(api, sims, launcher, wanted):
    before = snapshot(sims)

    check(api, wanted)

    assert snapshot(sims) == before
    assert launcher.started == []


def test_a_refused_check_stores_nothing_either(api, sims, launcher):
    before = snapshot(sims)

    answer = check(api, free_sim(models=["gpt-9"], **DAYS_INTO_TEST_PERIOD))

    assert answer["refusals"]
    assert snapshot(sims) == before
    assert launcher.started == []


def test_the_check_answers_an_estimate_and_a_cap_of_one_and_a_half_times_it(api):
    answer = check(api, free_sim())

    assert answer["refusals"] == []
    assert answer["estimate_usd"] > 0
    # One and a half times the estimate, rounded up to a whole cent: never below it, and less
    # than a cent above it (an estimate of $3.00 gives a cap of $4.50).
    one_and_a_half = answer["estimate_usd"] * 1.5
    assert one_and_a_half <= answer["spending_cap_usd"] < one_and_a_half + 0.01
    assert answer["spending_cap_usd"] == round(answer["spending_cap_usd"], 2)
    assert answer["ceiling_usd"] == CEILING


def test_what_is_left_takes_off_money_paid_and_what_sims_in_progress_may_still_spend(
    api, sims
):
    """$12 paid in all ($10 outside sims, $2 by a sim in progress whose cap is $5): that sim may
    still spend $3, so $75 - $12 - $3 = $60 is left for new sims."""
    paid_call(sims, None, 10.00)  # the benchmark, say
    other = sim_in_progress(sims, cap=5.00)
    paid_call(sims, other, 2.00)

    answer = check(api, free_sim())

    assert answer["left_under_ceiling_usd"] == pytest.approx(60.00)


def test_a_measurement_with_both_models_costs_more_than_with_one(api):
    both = check(api, measurement())
    one = check(api, measurement(models=[HAIKU]))

    assert both["estimate_usd"] > one["estimate_usd"] > 0


# Each refusal the form lists, with a code and a fix in plain words


def assert_refused(refusals, code, *words):
    """`code` is among `refusals`, its message says what to change and holds every one of
    `words`."""
    found = [r for r in refusals if r["code"] == code]
    assert found, f"no {code} refusal in {codes(refusals)}"
    message = found[0]["message"]
    assert "Fix:" in message, message
    for word in words:
        assert word in message, message


def test_test_period_days_are_refused_in_a_free_sim(api):
    assert_refused(
        check(api, free_sim(**DAYS_INTO_TEST_PERIOD))["refusals"],
        "test_period_days",
        "rising market",
    )


def test_test_period_days_are_refused_in_a_build_up_sim(api):
    answer = check(api, build_up(last_day="2025-03-04"))

    assert_refused(answer["refusals"], "test_period_days", "rising market")


def test_a_measurement_may_use_its_test_period(api):
    answer = check(api, measurement())

    assert answer["refusals"] == []
    assert answer["estimate_usd"] > 0


def test_a_memory_holding_records_from_after_the_first_day_is_refused(launcher):
    sims = InMemorySimStore()
    # A decision recorded on day 3, the free sim's first day.
    add_base_memory(sims, record_step=200)
    api = client(make_store(sims), launcher)

    assert_refused(check(api, free_sim())["refusals"], "memory_from_the_future", "200")


def test_a_cap_that_could_take_spending_past_the_ceiling_is_refused(api, sims):
    assert check(api, free_sim())["spending_cap_usd"] > 0.01
    paid_call(sims, None, 74.99)  # $0.01 is left under the ceiling

    answer = check(api, free_sim())

    assert_refused(answer["refusals"], "over_ceiling", "$75.00", "$0.01 or less")
    assert answer["left_under_ceiling_usd"] == pytest.approx(0.01)


def test_a_fifth_sim_at_once_is_refused_naming_the_sims_in_progress(api, sims):
    in_progress = [sim_in_progress(sims) for _ in range(4)]

    assert_refused(
        check(api, free_sim())["refusals"],
        "too_many_sims",
        *(f"sim {sim_id}" for sim_id in in_progress),
    )


def test_a_dataset_not_published_is_refused(sims, launcher):
    api = client(make_store(sims, status="being built"), launcher)

    assert_refused(
        check(api, free_sim())["refusals"], "dataset_not_published", "not published"
    )


def test_an_unknown_model_is_refused_naming_the_models_there_are(api):
    assert_refused(
        check(api, free_sim(models=["gpt-9"]))["refusals"],
        "unknown_model",
        "gpt-9",
        HAIKU,
        GLM,
    )


def test_a_model_name_is_known_whatever_its_capitals(api):
    """The spec writes `GLM-5.3-Flash`; the settings store `glm-5.3-flash`."""
    answer = check(api, free_sim(models=["GLM-5.3-Flash"]))

    assert answer["refusals"] == []
    assert answer["estimate_usd"] > 0


def test_every_refusal_comes_back_together(launcher):
    """A free sim wrong in all six ways at once."""
    sims = InMemorySimStore()
    add_base_memory(sims, record_step=300)
    for _ in range(4):
        sim_in_progress(sims)
    paid_call(sims, None, 74.99)
    api = client(make_store(sims, status="being built"), launcher)

    answer = check(api, free_sim(models=["gpt-9"], **DAYS_INTO_TEST_PERIOD))

    assert codes(answer["refusals"]) >= {
        "test_period_days",
        "memory_from_the_future",
        "over_ceiling",
        "too_many_sims",
        "dataset_not_published",
        "unknown_model",
    }
    for refusal in answer["refusals"]:
        assert "Fix:" in refusal["message"], refusal


# Starting each kind, and the Model choice


def start(api, wanted):
    answer = api.post("/sims", json=wanted)
    assert answer.status_code == 202, answer.text
    return answer.json()["sim_ids"]


def test_a_measurement_with_both_models_creates_three_sims(api, sims, launcher):
    """Memory with each model, and one no-memory sim the two share."""
    before = snapshot(sims)

    sim_ids = start(api, measurement())

    created = new_agent_sims(sims, before)
    assert set(created) <= set(sim_ids)
    assert sorted(
        (row["VARIANT"], llm_model(row)) for row in created.values()
    ) == sorted([("memory_off", None), ("memory_on", GLM), ("memory_on", HAIKU)])
    for row in created.values():
        assert (row["KIND"], row["FIRST_STEP"], row["LAST_STEP"]) == (
            "measurement",
            289,
            384,
        )
        assert row["STATUS"] == "running"
    assert set(created) <= set(launcher.started)


def test_a_measurement_with_one_model_is_a_pair(api, sims):
    before = snapshot(sims)

    start(api, measurement(models=[GLM]))

    created = new_agent_sims(sims, before)
    assert sorted((row["VARIANT"], llm_model(row)) for row in created.values()) == [
        ("memory_off", None),
        ("memory_on", GLM),
    ]


def test_a_free_sim_uses_the_default_model_when_none_is_named(api, sims):
    before = snapshot(sims)

    start(api, free_sim())

    [row] = new_agent_sims(sims, before).values()
    assert (row["KIND"], row["VARIANT"]) == ("free", "memory_on")
    assert llm_model(row) == load_model_settings().default_model


def test_a_free_sim_uses_the_one_model_named(api, sims):
    before = snapshot(sims)

    start(api, free_sim(models=[GLM]))

    [row] = new_agent_sims(sims, before).values()
    assert llm_model(row) == GLM


def test_a_free_sim_with_its_partner_plays_the_same_days_the_other_way(api, sims):
    before = snapshot(sims)

    start(api, free_sim(partner=True))

    created = new_agent_sims(sims, before)
    assert sorted(row["VARIANT"] for row in created.values()) == [
        "memory_off",
        "memory_on",
    ]
    assert {(row["FIRST_STEP"], row["LAST_STEP"]) for row in created.values()} == {
        (193, 288)
    }


def test_a_build_up_sim_starts_without_memory(api, sims):
    before = snapshot(sims)

    start(api, build_up())

    [row] = new_agent_sims(sims, before).values()
    assert (row["KIND"], row["VARIANT"]) == ("build-up", "memory_off")
    assert (row["FIRST_STEP"], row["LAST_STEP"]) == (97, 288)


@pytest.mark.parametrize("kind", ["practice", "tuning"])
def test_practice_and_tuning_are_still_refused_from_the_api(api, sims, launcher, kind):
    before = snapshot(sims)
    wanted = free_sim(kind=kind, variant="memory_off")

    assert "command_line_only" in codes(check(api, wanted)["refusals"])
    answer = api.post("/sims", json=wanted)

    assert answer.status_code == 409
    assert "command_line_only" in codes(answer.json()["refusals"])
    assert snapshot(sims) == before and launcher.started == []


# The check and the start agree


def test_what_a_start_creates_costs_what_the_check_said(api, sims):
    answer = check(api, measurement())
    before = snapshot(sims)

    start(api, measurement())

    created = new_agent_sims(sims, before).values()
    assert sum(row["ESTIMATED_COST"] for row in created) == pytest.approx(
        answer["estimate_usd"]
    )
    assert sum(row["SPENDING_CAP"] for row in created) == pytest.approx(
        answer["spending_cap_usd"]
    )


# Each setup makes one refusal: it may add rows to `sims`, and returns the dataset's status and
# the sim wanted.


def setup_test_period_days(sims):
    return "published", free_sim(**DAYS_INTO_TEST_PERIOD)


def setup_future_memory(sims):
    add_base_memory(sims, record_step=250)  # the newest build-up sim is the base memory
    return "published", free_sim()


def setup_over_ceiling(sims):
    paid_call(sims, None, 74.99)
    return "published", free_sim()


def setup_fifth_sim(sims):
    for _ in range(4):
        sim_in_progress(sims)
    return "published", free_sim()


def setup_unpublished_dataset(sims):
    return "being built", free_sim()


def setup_unknown_model(sims):
    return "published", measurement(models=[HAIKU, "gpt-9"])


def setup_free_sim_with_two_models(sims):
    return "published", free_sim(models=[HAIKU, GLM])  # a free sim uses one model


def setup_practice(sims):
    return "published", free_sim(kind="practice", variant="memory_off")


@pytest.mark.parametrize(
    "setup",
    [
        setup_test_period_days,
        setup_future_memory,
        setup_over_ceiling,
        setup_fifth_sim,
        setup_unpublished_dataset,
        setup_unknown_model,
        setup_free_sim_with_two_models,
        setup_practice,
    ],
)
def test_whatever_the_check_refuses_the_start_refuses_too(sims, launcher, setup):
    status, wanted = setup(sims)
    api = client(make_store(sims, status=status), launcher)
    before = snapshot(sims)

    refused = codes(check(api, wanted)["refusals"])
    answer = api.post("/sims", json=wanted)

    assert refused
    assert answer.status_code == 409
    assert codes(answer.json()["refusals"]) == refused
    assert snapshot(sims) == before and launcher.started == []
