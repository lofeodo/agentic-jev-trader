"""Start, Stop and Resume through the API with real jobs, against the test database (spec
appendix 8, section 8.14).

Hand-run: needs the builder's, the sim's and the API's keys in `SNOWFLAKE_LOCAL_DIR`. A holding
sim on a made-up dataset: no paid call. It stores one step per write so that it runs long enough
to be stopped halfway, and takes a few minutes; a Stop that lands while the job is writing can
add up to 5 more (Snowflake undoes the dead job's open write only then).

    conda run -n agentic-jev-trader python -m pytest tests/snowflake/test_api_jobs.py -s

The job reads the Snowflake login from the environment, or from `.env` in the checkout.
"""

import time
from datetime import timedelta

from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.snowflake_store import SnowflakeApiStore
from jev_trader.jobs import LocalLauncher, sim_job_command
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.storage.snowflake import TEST_DATABASE

from .conftest import ENV, login
from .test_sim_store import records


def wait_until(check, seconds, what):
    deadline = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < deadline, f"waited {seconds} s for {what}"
        time.sleep(2)


def test_a_restarted_api_finds_and_kills_the_job_and_the_sim_resumes_to_the_same_records(
    sim_login, made_up_dataset, remove_sims, tmp_path, monkeypatch
):
    for name, value in ENV.items():
        if value is not None:
            monkeypatch.setenv(name, value)  # the job's login
    api_login = login("api")
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)
    dataset_id = made_up_dataset(days=2)  # day 2, steps 97 to 192, is the sim
    never_stopped = create_sim(
        store, market, SimRequest(dataset_id, "buy_hold", "free", 97, 192)
    )
    remove_sims.append(never_stopped)
    run_sim(store, market, never_stopped, steps_per_write=20)

    def fresh_api():
        """A newly started API: it knows its jobs only from the database."""
        launcher = LocalLauncher(
            tmp_path,
            lambda sim_id: sim_job_command(sim_id, TEST_DATABASE)
            + ["--steps-per-write", "1"],
        )
        app = create_app(
            SnowflakeApiStore(api_login),
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            launcher=launcher,
        )
        return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1))

    try:
        started = fresh_api().post(
            "/sims", json={"dataset": dataset_id, "kind": "free", "variant": "buy_hold"}
        )
        assert started.status_code == 202, started.text
        [sim_id] = started.json()["sim_ids"]
        remove_sims.append(sim_id)

        wait_until(
            lambda: (store.sim(sim_id)["LAST_COMPLETED_STEP"] or 0) >= 120,
            300,
            "the job to store some steps",
        )
        job = LocalLauncher.find(store.sim(sim_id)["RUNNING_ON"])
        assert job is not None, "the job notes where it runs"

        began = time.monotonic()
        stopped = fresh_api().post(f"/sims/{sim_id}/stop")
        print(f"\nStop answered in {time.monotonic() - began:.1f} s.")

        assert stopped.status_code == 200, stopped.text
        assert not job.is_running()
        sim = store.sim(sim_id)
        assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "stopped by hand")
        stopped_after = sim["LAST_COMPLETED_STEP"]
        assert stopped_after < 192
        print(f"Stopped after step {stopped_after}.")

        resumed = fresh_api().post(f"/sims/{sim_id}/resume", json={})
        assert resumed.status_code == 202, resumed.text
        wait_until(
            lambda: store.sim(sim_id)["STATUS"] in ("finished", "failed", "stopped"),
            900,
            "the resumed sim to end",
        )

        assert store.sim(sim_id)["STATUS"] == "finished", (
            tmp_path / f"sim-{sim_id}.log"
        ).read_text(encoding="utf-8", errors="replace")
        assert records(sim_login, sim_id) == records(sim_login, never_stopped)
        assert store.duplicate_ids(sim_id) == {}
        with sim_login.cursor() as cur:
            cur.execute("SELECT KIND, STEP FROM SIM.SIM_EVENTS WHERE SIM = ?", (sim_id,))
            assert cur.fetchall() == [("restarted", stopped_after + 1)]
    finally:
        for sim_id in remove_sims[1:]:  # a failed run leaves no job behind
            LocalLauncher(tmp_path, sim_job_command).stop(
                store.sim(sim_id)["RUNNING_ON"]
            )
        api_login.close()
