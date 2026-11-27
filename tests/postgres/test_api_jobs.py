"""Start, Stop and Resume through the API with real jobs, on the local Postgres (spec appendix
8, section 8.14; appendix 11, section 1).

A holding sim on a made-up dataset: no paid call. The local Postgres answers so fast that the
job would finish before it could be stopped, so the job reaches it through a pretend far-away
line (`wire.Line`), and stores one step per write: it runs long enough to be stopped halfway.
The job is a program of its own, reading its database from the environment, which points it at
the line.
"""

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.jobs import LocalLauncher, builds_named, sim_job_command
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from tests.postgres.helpers import LOCAL_ENV, REPO_ROOT, TEST_DATABASE, records
from tests.postgres.wire import Line

# Each answer reaches the job this late: about a tenth of a second a step.
JOB_LINE_DELAY = 0.02


def wait_until(check, seconds, what):
    deadline = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < deadline, f"waited {seconds} s for {what}"
        time.sleep(1)


@pytest.fixture
def slow_line():
    with Line(delay=JOB_LINE_DELAY) as line:
        yield line


def test_a_restarted_api_finds_and_kills_the_job_and_the_sim_resumes_to_the_same_records(
    sim_db, api_db, setup_login, made_up_dataset, tmp_path, monkeypatch, slow_line
):
    for name, value in LOCAL_ENV.items():
        monkeypatch.setenv(name, value)  # the job's database
    monkeypatch.setenv(
        "POSTGRES_PORT", str(slow_line.port)
    )  # reached through the slow line
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT / "src"))  # this checkout's code
    store, market = sim_db.sim_store(), sim_db.market()
    dataset_id = made_up_dataset(days=2)  # day 2, steps 97 to 192, is the sim
    never_stopped = create_sim(
        store, market, SimRequest(dataset_id, "buy_hold", "free", 97, 192)
    )
    run_sim(store, market, never_stopped, steps_per_write=20)
    started_sims = []

    def fresh_api():
        """A newly started API: it knows its jobs only from the database."""
        launcher = LocalLauncher(
            tmp_path,
            lambda sim_id: (
                sim_job_command(sim_id, TEST_DATABASE) + ["--steps-per-write", "1"]
            ),
        )
        app = create_app(
            api_db.api_store(),
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            launcher=launcher,
            builds=builds_named("local", tmp_path, TEST_DATABASE),
        )
        return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1))

    try:
        started = fresh_api().post(
            "/sims", json={"dataset": dataset_id, "kind": "free", "variant": "buy_hold"}
        )
        assert started.status_code == 202, started.text
        [sim_id] = started.json()["sim_ids"]
        started_sims.append(sim_id)

        wait_until(
            lambda: (store.sim(sim_id)["LAST_COMPLETED_STEP"] or 0) >= 120,
            120,
            "the job to store some steps",
        )
        job = LocalLauncher.find(store.sim(sim_id)["RUNNING_ON"])
        assert job is not None, "the job notes where it runs"

        stopped = fresh_api().post(f"/sims/{sim_id}/stop")

        assert stopped.status_code == 200, stopped.text
        assert not job.is_running()
        sim = store.sim(sim_id)
        assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "stopped by hand")
        stopped_after = sim["LAST_COMPLETED_STEP"]
        assert stopped_after < 192

        resumed = fresh_api().post(f"/sims/{sim_id}/resume", json={})
        assert resumed.status_code == 202, resumed.text
        wait_until(
            lambda: store.sim(sim_id)["STATUS"] in ("finished", "failed", "stopped"),
            300,
            "the resumed sim to end",
        )

        assert store.sim(sim_id)["STATUS"] == "finished", (
            tmp_path / f"sim-{sim_id}.log"
        ).read_text(encoding="utf-8", errors="replace")
        assert records(setup_login, sim_id) == records(setup_login, never_stopped)
        assert store.duplicate_ids(sim_id) == {}
        assert setup_login.execute(
            "SELECT KIND, STEP FROM SIM.SIM_EVENTS WHERE SIM = %s", (sim_id,)
        ).fetchall() == [("restarted", stopped_after + 1)]
    finally:
        for sim_id in started_sims:  # a failed run leaves no job behind
            LocalLauncher(tmp_path, sim_job_command).stop(
                store.sim(sim_id)["RUNNING_ON"]
            )
