"""The Comparison screen's read, `GET /comparison` (spec appendix 9 sections 6 and 8, appendix 7
section 10, appendix 8 section 8.4), on made-up measurement sims.

Every made-up sim replays two days of dataset 7 (steps 97 to 288) from $10,000. Day 2 ends at
step 192, day 3 at step 288. The dataset starts on 1 March 2025, so those are 2 and 3 March.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInBuilds, StandInLauncher

HAIKU = "anthropic:claude-haiku-5-5"
GLM = "openai:glm-5.3-flash"


@pytest.fixture
def sims():
    return InMemorySimStore()


@pytest.fixture
def api(sims):
    store = InMemoryApiStore(
        sims,
        asset_key=[
            {
                "DATASET": 7,
                "MASKED_ID": "ASSET_01",
                "TICKER": "AAPL",
                "NAME": "Apple",
                "PRICE_SCALE": 0.5,
                "FIRST_DAY": date(2025, 3, 1),
            }
        ],
    )
    return TestClient(
        create_app(
            store,
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            launcher=StandInLauncher(),
            builds=StandInBuilds(),
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def account(sims, sim_id, step, value):
    sims.tables["SIM.ACCOUNT_STEPS"].append(
        {"ID": f"{sim_id}-{step}", "SIM": sim_id, "STEP": step, "ACCOUNT_VALUE": value}
    )


def measurement(
    sims,
    repeat,
    ending,
    model=None,
    market="falling market",
    status="finished",
    day_two=None,
):
    """A measurement sim with memory (when a model is named) or without, ending at `ending`."""
    settings = {"starting_value": 10_000.0}
    if model:
        settings["llm"] = {"model": model}
    sim = sims.create(
        {
            "DATASET": 7,
            "KIND": "measurement",
            "VARIANT": "memory_on" if model else "memory_off",
            "REPEAT_NUMBER": repeat,
            "MARKET": market,
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SETTINGS": settings,
        }
    )
    reached = 288 if status == "finished" else 192
    sims.update(sim, STATUS=status, LAST_COMPLETED_STEP=reached)
    account(sims, sim, 192, 10_000.0 if day_two is None else day_two)
    if status == "finished":
        account(sims, sim, 288, ending)
    return sim


def repeats(sims, endings, model=HAIKU, market="falling market"):
    """One sim per repeat for each (model or None, endings) pair."""
    for number, ending in enumerate(endings, start=1):
        measurement(sims, number, ending, model=model, market=market)


def only_market(api):
    [market] = api.get("/comparison").json()["markets"]
    return market


def model_result(market, model):
    [found] = [m for m in market["models"] if m["model"] == model]
    return found


def test_memory_helped_when_the_difference_is_above_one_pooled_standard_deviation(
    sims, api
):
    # The spec's worked example (appendix 9, section 6).
    repeats(sims, [10_300.0, 10_400.0, 10_500.0], model=HAIKU)
    repeats(sims, [10_100.0, 10_150.0, 10_200.0], model=None)

    market = only_market(api)
    haiku = model_result(market, "claude-haiku-5-5")

    assert market["market"] == "falling market"
    assert market["without_memory"]["average_usd"] == pytest.approx(10_150.0)
    assert market["without_memory"]["standard_deviation_usd"] == pytest.approx(50.0)
    assert haiku["label"] == "Claude Haiku"
    assert haiku["with_memory"]["average_usd"] == pytest.approx(10_400.0)
    assert haiku["with_memory"]["standard_deviation_usd"] == pytest.approx(100.0)
    assert haiku["difference_usd"] == pytest.approx(250.0)
    assert haiku["threshold_usd"] == pytest.approx(79.06, abs=0.01)
    assert haiku["verdict"] == "helped"


def test_memory_hurt_when_the_difference_is_below_minus_one_pooled_standard_deviation(
    sims, api
):
    repeats(sims, [9_800.0, 9_850.0, 9_900.0], model=HAIKU)  # average 9,850, spread 50
    repeats(
        sims, [10_000.0, 10_100.0, 10_200.0], model=None
    )  # average 10,100, spread 100

    haiku = model_result(only_market(api), "claude-haiku-5-5")

    assert haiku["difference_usd"] == pytest.approx(-250.0)
    assert haiku["verdict"] == "hurt"


def test_can_t_tell_when_the_difference_is_within_the_repeats_spread(sims, api):
    repeats(
        sims, [10_000.0, 10_200.0, 10_400.0], model=HAIKU
    )  # average 10,200, spread 200
    repeats(
        sims, [9_950.0, 10_150.0, 10_350.0], model=None
    )  # average 10,150, spread 200

    haiku = model_result(only_market(api), "claude-haiku-5-5")

    assert haiku["difference_usd"] == pytest.approx(50.0)
    assert haiku["threshold_usd"] == pytest.approx(200.0)
    assert haiku["verdict"] == "can't tell"


def test_each_model_gets_its_own_verdict_against_the_shared_sims_without_memory(
    sims, api
):
    repeats(sims, [10_300.0, 10_400.0, 10_500.0], model=HAIKU)
    repeats(sims, [10_100.0, 10_200.0, 10_300.0], model=GLM)
    repeats(sims, [10_100.0, 10_150.0, 10_200.0], model=None)

    market = only_market(api)

    assert [(m["label"], m["verdict"]) for m in market["models"]] == [
        ("Claude Haiku", "helped"),
        ("GLM Flash", "can't tell"),
    ]


def test_the_two_markets_are_never_merged(sims, api):
    repeats(sims, [10_300.0, 10_400.0, 10_500.0], market="falling market")
    repeats(sims, [10_100.0, 10_150.0, 10_200.0], model=None, market="falling market")
    repeats(sims, [9_800.0, 9_850.0, 9_900.0], market="rising market")
    repeats(sims, [10_000.0, 10_100.0, 10_200.0], model=None, market="rising market")

    markets = api.get("/comparison").json()["markets"]

    assert [(m["market"], m["models"][0]["verdict"]) for m in markets] == [
        ("falling market", "helped"),
        ("rising market", "hurt"),
    ]


def test_a_sim_not_finished_stays_out_of_the_averages(sims, api):
    measurement(sims, 1, 10_300.0, model=HAIKU)
    measurement(sims, 2, 10_500.0, model=HAIKU)
    measurement(sims, 3, None, model=HAIKU, status="running")
    repeats(sims, [10_100.0, 10_200.0], model=None)

    haiku = model_result(only_market(api), "claude-haiku-5-5")

    assert haiku["with_memory"]["ending_values_usd"] == [10_300.0, 10_500.0]
    assert haiku["with_memory"]["average_usd"] == pytest.approx(10_400.0)


def test_the_verdict_waits_for_two_finished_repeats_on_each_side(sims, api):
    measurement(sims, 1, 10_300.0, model=HAIKU)
    measurement(sims, 2, None, model=HAIKU, status="running")
    repeats(sims, [10_100.0, 10_200.0], model=None)

    haiku = model_result(only_market(api), "claude-haiku-5-5")

    assert haiku["verdict"] == "waiting"
    assert haiku["threshold_usd"] is None


def test_the_performance_winner_ended_higher_by_more_than_the_repeats_spread(sims, api):
    # The spec's example (appendix 9, section 6).
    repeats(sims, [10_300.0, 10_400.0, 10_500.0], model=GLM)
    repeats(sims, [10_100.0, 10_150.0, 10_200.0], model=HAIKU)
    repeats(sims, [10_000.0, 10_000.0, 10_100.0], model=None)

    performance = only_market(api)["performance"]

    assert performance["winner"] == "glm-5.3-flash"
    assert performance["gap_usd"] == pytest.approx(250.0)
    assert performance["threshold_usd"] == pytest.approx(79.06, abs=0.01)


def test_there_is_no_performance_winner_when_the_gap_is_within_the_spread(sims, api):
    repeats(sims, [10_000.0, 10_200.0, 10_400.0], model=GLM)
    repeats(sims, [9_950.0, 10_150.0, 10_350.0], model=HAIKU)
    repeats(sims, [10_000.0, 10_000.0, 10_100.0], model=None)

    performance = only_market(api)["performance"]

    assert performance["winner"] is None
    assert performance["gap_usd"] == pytest.approx(50.0)


def evaluations_and_reviews(
    sims, sim_id, kind, count, llm_usd_each, jev_usd_each=0.01, seconds=4.0
):
    """`count` decisions of `kind`, each with one Jev call and one LLM call."""
    for n in range(count):
        decision = f"{sim_id}-{kind}-{n}"
        sims.tables["MEMORY.DECISIONS"].append(
            {
                "ID": decision,
                "SIM": sim_id,
                "FIRST_WRITTEN_BY": sim_id,
                "STEP": 100 + n,
                "ASSET": "ASSET_01",
                "KIND": kind,
                "TIER": 2,
                "JEV_VERSION": "jev-1.14.0",
            }
        )
        for service, cost in (("jev", jev_usd_each), ("anthropic", llm_usd_each)):
            sims.tables["SIM.CALLS"].append(
                {
                    "ID": f"{decision}-{service}",
                    "SIM": sim_id,
                    "PURPOSE": "pick",
                    "DECISION": decision,
                    "SERVICE": service,
                    "MODEL": None,
                    "COST_USD": cost,
                    "LATENCY_SECONDS": seconds / 2,
                }
            )


def test_the_price_winner_cost_less_in_total_per_evaluation_or_review(sims, api):
    # Haiku's LLM is cheaper ($0.0022 against $0.0025), but its sims' Jev calls cost more
    # ($0.0100 against $0.0090): in total $0.0122 against $0.0115, so GLM is the price winner.
    for number in (1, 2):
        haiku = measurement(sims, number, 10_000.0, model=HAIKU)
        evaluations_and_reviews(sims, haiku, "full_evaluation", 8, 0.0022, 0.0100)
        evaluations_and_reviews(sims, haiku, "position_review", 2, 0.0022, 0.0100)
        glm = measurement(sims, number, 10_000.0, model=GLM)
        evaluations_and_reviews(sims, glm, "full_evaluation", 6, 0.0025, 0.0090)
        evaluations_and_reviews(sims, glm, "position_review", 4, 0.0025, 0.0090)

    market = only_market(api)

    assert market["price"]["winner"] == "glm-5.3-flash"
    assert model_result(market, "claude-haiku-5-5")["usd_per_evaluation_or_review"] == (
        pytest.approx(0.0122)
    )
    assert model_result(market, "glm-5.3-flash")["usd_per_evaluation_or_review"] == (
        pytest.approx(0.0115)
    )


def test_the_price_counts_every_call_of_the_sim_screens_included(sims, api):
    haiku = measurement(sims, 1, 10_000.0, model=HAIKU)
    evaluations_and_reviews(sims, haiku, "full_evaluation", 2, 0.002, 0.008)
    sims.tables["SIM.CALLS"].append(
        {
            "ID": f"{haiku}-screen",
            "SIM": haiku,
            "PURPOSE": "screen",
            "DECISION": None,
            "SERVICE": "jev",
            "MODEL": None,
            "COST_USD": 0.004,
            "LATENCY_SECONDS": 1.0,
        }
    )

    result = model_result(only_market(api), "claude-haiku-5-5")

    # ($0.010 x 2 + $0.004) over 2 full evaluations.
    assert result["usd_per_evaluation_or_review"] == pytest.approx(0.012)


def test_seconds_per_full_evaluation_add_up_every_call_of_it(sims, api):
    haiku = measurement(sims, 1, 10_000.0, model=HAIKU)
    evaluations_and_reviews(sims, haiku, "full_evaluation", 3, 0.002, seconds=5.0)
    evaluations_and_reviews(sims, haiku, "position_review", 3, 0.002, seconds=99.0)

    result = model_result(only_market(api), "claude-haiku-5-5")

    assert result["seconds_per_full_evaluation"] == pytest.approx(5.0)


def test_each_repeat_lists_its_sims_with_their_ending_values(sims, api):
    haiku = measurement(sims, 1, 10_300.0, model=HAIKU)
    glm = measurement(sims, 1, 10_100.0, model=GLM)
    alone = measurement(sims, 1, 10_000.0)
    running = measurement(sims, 2, None, model=HAIKU, status="running")

    market = only_market(api)

    assert market["first_day"] == "2025-03-02"
    assert market["last_day"] == "2025-03-03"
    assert [
        [
            (s["sim_id"], s["label"], s["status"], s["ending_value_usd"])
            for s in r["sims"]
        ]
        for r in market["repeats"]
    ] == [
        [
            (haiku, "With memory / Claude Haiku", "finished", 10_300.0),
            (glm, "With memory / GLM Flash", "finished", 10_100.0),
            (alone, "Without memory", "finished", 10_000.0),
        ],
        [(running, "With memory / Claude Haiku", "running", None)],
    ]
    assert [r["number"] for r in market["repeats"]] == [1, 2]


def test_the_gap_over_time_is_memory_s_average_minus_without_at_each_day_s_end(
    sims, api
):
    measurement(sims, 1, 10_300.0, model=HAIKU, day_two=10_100.0)
    measurement(sims, 2, 10_500.0, model=HAIKU, day_two=10_300.0)
    measurement(sims, 1, 10_100.0, day_two=10_000.0)
    measurement(sims, 2, 10_100.0, day_two=10_000.0)

    [gap] = only_market(api)["gap_over_time"]

    assert gap["model"] == "claude-haiku-5-5"
    assert [(p["day"], p["gap_usd"]) for p in gap["points"]] == [
        ("2025-03-02", pytest.approx(200.0)),
        ("2025-03-03", pytest.approx(300.0)),
    ]


def test_the_comparison_says_so_when_the_jev_version_changed(sims, api):
    first = measurement(sims, 1, 10_300.0, model=HAIKU)
    evaluations_and_reviews(sims, first, "full_evaluation", 1, 0.002)
    second = measurement(sims, 2, 10_000.0)
    evaluations_and_reviews(sims, second, "full_evaluation", 1, 0.0)
    sims.tables["MEMORY.DECISIONS"][-1]["JEV_VERSION"] = "jev-1.15.0"

    market = only_market(api)

    assert market["jev_versions"] == ["jev-1.14.0", "jev-1.15.0"]
    assert any("Jev version changed" in note for note in market["notes"])


def test_the_comparison_says_so_when_the_provider_s_model_name_changed(sims, api):
    for number, returned in ((1, "glm-5.3-flash-0601"), (2, "glm-5.3-flash-0715")):
        sim = measurement(sims, number, 10_000.0, model=GLM)
        evaluations_and_reviews(sims, sim, "full_evaluation", 1, 0.002)
        sims.tables["SIM.CALLS"][-1]["MODEL"] = returned

    market = only_market(api)

    assert model_result(market, "glm-5.3-flash")["models_returned"] == [
        "glm-5.3-flash-0601",
        "glm-5.3-flash-0715",
    ]
    assert any("GLM Flash" in note for note in market["notes"])


def test_a_verdict_is_provisional_until_every_sim_of_the_test_period_finished(
    sims, api
):
    repeats(sims, [10_300.0, 10_400.0], model=HAIKU)
    repeats(sims, [10_100.0, 10_150.0], model=None)
    measurement(sims, 3, None, model=HAIKU, status="running")

    haiku = model_result(only_market(api), "claude-haiku-5-5")

    assert haiku["verdict"] == "helped"
    assert haiku["provisional"] is True
    assert "provisional" in haiku["says"].lower()


def test_a_verdict_is_final_once_every_sim_finished(sims, api):
    repeats(sims, [10_300.0, 10_400.0, 10_500.0], model=HAIKU)
    repeats(sims, [10_100.0, 10_150.0, 10_200.0], model=None)

    assert model_result(only_market(api), "claude-haiku-5-5")["provisional"] is False
