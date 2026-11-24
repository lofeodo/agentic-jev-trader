"""Starting, stopping and resuming sims through the API (spec appendix 8, sections 8.7 and 8.10).

The jobs are stand-ins: the launcher notes what it was asked to start and kill. The real
launcher is tested in `tests/unit/test_jobs.py`, and the whole path by hand (section 8.14).
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.broker import AssetClass
from jev_trader.sim.market import DatasetInfo, InMemoryMarket, Period
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInLauncher

NOW = datetime(2026, 11, 24, 12, 0)
CEILING = 75.0


def dataset(status="published"):
    """Dataset 7: day 1 (steps 1 to 96) is the warm-up; day 3 (steps 193 to 288) a test period."""
    return DatasetInfo(
        dataset_id=7,
        status=status,
        first_step=1,
        last_step=288,
        periods=(
            Period("warm-up", "warm-up", 1, 96),
            Period("test", "rising market", 193, 288),
        ),
        assets={"ASSET_01": AssetClass.CRYPTO},
    )


@pytest.fixture
def sims():
    return InMemorySimStore()


@pytest.fixture
def launcher():
    return StandInLauncher()


def make_store(sims, status="published"):
    return InMemoryApiStore(
        sims,
        asset_key=[
            {
                "DATASET": 7,
                "MASKED_ID": "ASSET_01",
                "NAME": "Bitcoin",
                "FIRST_DAY": date(2025, 3, 1),
            }
        ],
        market=InMemoryMarket(datasets=[dataset(status)], bars={7: {}}),
    )


@pytest.fixture
def api(sims, launcher):
    return client(make_store(sims), launcher)


def client(store, launcher):
    return TestClient(
        create_app(
            store,
            spending_ceiling=CEILING,
            not_responding_after=timedelta(minutes=7),
            clock=lambda: NOW,
            launcher=launcher,
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def free_sim(**fields):
    return {"dataset": 7, "kind": "free", "variant": "buy_hold", **fields}


def paid_call(sims, sim_id, cost):
    sims.tables["SIM.CALLS"].append(
        {"ID": f"call-{len(sims.tables['SIM.CALLS'])}", "SIM": sim_id, "COST_USD": cost}
    )


# Starting


def test_a_sim_is_stored_then_its_job_started(api, sims, launcher):
    answer = api.post(
        "/sims", json=free_sim(first_day="2025-03-02", last_day="2025-03-02")
    )

    assert answer.status_code == 202
    [sim_id] = answer.json()["sim_ids"]
    assert launcher.started == [sim_id]
    sim = sims.sim(sim_id)
    # Real days become steps: 2 March is day 2, steps 97 to 192.
    assert (sim["FIRST_STEP"], sim["LAST_STEP"]) == (97, 192)
    assert (sim["KIND"], sim["VARIANT"]) == ("free", "buy_hold")
    assert sim["STATUS"] == "running"
    assert sim["RUNNING_ON"] in launcher.running
    assert sim["STARTED_AT"] == NOW


def test_a_measurement_runs_over_its_test_period(api, sims):
    answer = api.post(
        "/sims", json=free_sim(kind="measurement", market="rising market")
    )

    [sim_id] = answer.json()["sim_ids"]
    sim = sims.sim(sim_id)
    assert (sim["FIRST_STEP"], sim["LAST_STEP"], sim["MARKET"]) == (
        193,
        288,
        "rising market",
    )


def test_a_sim_with_no_days_given_runs_from_the_end_of_the_warm_up(api, sims):
    [sim_id] = api.post("/sims", json=free_sim(kind="measurement")).json()["sim_ids"]

    assert (sims.sim(sim_id)["FIRST_STEP"], sims.sim(sim_id)["LAST_STEP"]) == (97, 288)


@pytest.mark.parametrize("kind", ["practice", "tuning"])
def test_the_app_never_starts_a_practice_or_tuning_sim(api, sims, launcher, kind):
    answer = api.post("/sims", json=free_sim(kind=kind, last_day="2025-03-02"))

    assert answer.status_code == 409
    [refusal] = answer.json()["refusals"]
    assert refusal["code"] == "command_line_only"
    assert "command line" in refusal["message"]
    assert sims.sims == {} and launcher.started == []


def test_a_request_the_checker_refuses_stores_nothing_and_starts_nothing(
    api, sims, launcher
):
    answer = api.post(
        "/sims", json=free_sim(last_day="2025-03-03")
    )  # day 3 is a test period

    assert answer.status_code == 409
    [refusal] = answer.json()["refusals"]
    assert "test period" in refusal["message"]
    assert sims.sims == {} and launcher.started == []


def test_no_sim_starts_on_a_dataset_not_published(sims, launcher):
    answer = client(make_store(sims, status="being built"), launcher).post(
        "/sims", json=free_sim()
    )

    assert answer.status_code == 409
    assert "not published" in answer.json()["refusals"][0]["message"]


def test_an_unknown_test_period_is_refused(api):
    answer = api.post("/sims", json=free_sim(kind="measurement", market="flat market"))

    assert answer.status_code == 409
    assert "rising market" in answer.json()["refusals"][0]["message"]


# Stopping


def started(api):
    return api.post("/sims", json=free_sim(last_day="2025-03-02")).json()["sim_ids"][0]


def test_stop_kills_the_job_then_marks_the_sim_stopped_by_hand(api, sims, launcher):
    sim_id = started(api)
    job = sims.sim(sim_id)["RUNNING_ON"]

    answer = api.post(f"/sims/{sim_id}/stop")

    assert answer.status_code == 200
    assert answer.json()["status"] == "stopped"
    assert launcher.killed == [job]
    sim = sims.sim(sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "stopped by hand")
    assert sim["ENDED_AT"] == NOW


def test_a_sim_whose_job_is_already_gone_is_still_marked_stopped(api, sims, launcher):
    sim_id = started(api)
    launcher.running.clear()  # the job died on its own: the sim shows as not responding

    api.post(f"/sims/{sim_id}/stop")

    assert sims.sim(sim_id)["STATUS"] == "stopped"
    assert launcher.killed == []


@pytest.mark.parametrize("status", ["stopped", "finished", "failed"])
def test_a_sim_not_in_progress_has_nothing_to_stop(api, sims, launcher, status):
    sim_id = started(api)
    sims.sims[sim_id]["STATUS"] = status

    answer = api.post(f"/sims/{sim_id}/stop")

    assert answer.status_code == 409
    assert status in answer.json()["refusals"][0]["message"]
    assert launcher.killed == []


def test_stopping_an_unknown_sim_says_so(api):
    assert api.post("/sims/99/stop").status_code == 404


# Resuming


def stopped_by_hand(api):
    sim_id = started(api)
    api.post(f"/sims/{sim_id}/stop")
    return sim_id


def test_resume_starts_the_same_sim_again(api, sims, launcher):
    sim_id = stopped_by_hand(api)

    answer = api.post(f"/sims/{sim_id}/resume", json={})

    assert answer.status_code == 202
    assert answer.json()["status"] == "running"
    assert launcher.started == [sim_id, sim_id]
    sim = sims.sim(sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("running", None)
    assert sim["RUNNING_ON"] in launcher.running
    assert sim["STARTED_AT"] == NOW


def test_a_not_responding_sim_is_resumed_after_its_old_job_is_killed(
    api, sims, launcher
):
    sim_id = started(api)
    hung = sims.sim(sim_id)["RUNNING_ON"]
    sims.update(sim_id, STARTED_AT=NOW - timedelta(minutes=8))

    answer = api.post(f"/sims/{sim_id}/resume", json={})

    assert answer.status_code == 202
    assert launcher.killed == [hung]
    assert sims.sim(sim_id)["RUNNING_ON"] != hung


@pytest.mark.parametrize(
    ("status", "words"),
    [("running", "still running"), ("finished", "finished"), ("created", "created")],
)
def test_only_a_stopped_or_not_responding_sim_is_resumed(
    api, sims, launcher, status, words
):
    sim_id = started(api)
    sims.sims[sim_id]["STATUS"] = status

    answer = api.post(f"/sims/{sim_id}/resume", json={})

    assert answer.status_code == 409
    assert words in answer.json()["refusals"][0]["message"]
    assert launcher.started == [sim_id]


def stopped_by_cap(api, sims, cap=1.00, spent=1.00):
    sim_id = stopped_by_hand(api)
    sims.update(
        sim_id,
        SPENDING_CAP=cap,
        STOPPED_BY_CAP=True,
        STOP_REASON="spending cap",
    )
    paid_call(sims, sim_id, spent)
    return sim_id


def test_a_sim_stopped_by_its_cap_resumes_only_with_a_new_cap(api, sims, launcher):
    sim_id = stopped_by_cap(api, sims)

    refused = api.post(f"/sims/{sim_id}/resume", json={})
    assert refused.status_code == 409
    assert refused.json()["refusals"][0]["code"] == "needs_new_cap"

    answer = api.post(f"/sims/{sim_id}/resume", json={"spending_cap_usd": 2.50})

    assert answer.status_code == 202
    sim = sims.sim(sim_id)
    assert (sim["SPENDING_CAP"], sim["STOPPED_BY_CAP"]) == (2.50, False)
    assert sim["STATUS"] == "running"


def test_a_new_cap_must_be_above_what_the_sim_has_spent(api, sims):
    sim_id = stopped_by_cap(api, sims, spent=1.00)

    answer = api.post(f"/sims/{sim_id}/resume", json={"spending_cap_usd": 0.90})

    assert answer.status_code == 409
    assert "$1.00" in answer.json()["refusals"][0]["message"]


def test_a_new_cap_that_could_take_spending_past_the_ceiling_is_refused(api, sims):
    """$70 paid in all, another sim in progress may still spend $3: $2 of room is left,
    and this sim has spent $1 of it already, so its cap can be at most $3."""
    sim_id = stopped_by_cap(api, sims, spent=1.00)
    paid_call(sims, None, 67.00)  # the benchmark and other sims
    other = started(api)
    sims.update(other, SPENDING_CAP=5.00)
    paid_call(sims, other, 2.00)

    refused = api.post(f"/sims/{sim_id}/resume", json={"spending_cap_usd": 3.50})
    assert refused.status_code == 409
    [refusal] = refused.json()["refusals"]
    assert refusal["code"] == "over_ceiling"
    assert "$3.00 or less" in refusal["message"]

    assert (
        api.post(f"/sims/{sim_id}/resume", json={"spending_cap_usd": 3.00}).status_code
        == 202
    )


def test_a_new_cap_is_only_for_a_sim_the_cap_stopped(api, sims):
    sim_id = stopped_by_hand(api)

    answer = api.post(f"/sims/{sim_id}/resume", json={"spending_cap_usd": 5.00})

    assert answer.status_code == 409
    assert answer.json()["refusals"][0]["code"] == "cap_not_reached"
