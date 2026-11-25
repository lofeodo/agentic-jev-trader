"""Starting, finding and killing a job on this computer (spec appendix 8, sections 8.7 and 8.10).

The jobs here are real programs, but harmless ones: Python sleeping, in place of a sim.
"""

import sys
import time

import psutil
import pytest

from jev_trader.jobs import (
    KubernetesBuilds,
    KubernetesLauncher,
    LocalBuilds,
    LocalLauncher,
    builds_named,
    launcher_named,
    this_process,
)


def sleeper(sim_id: int) -> list[str]:
    return [
        sys.executable,
        "-c",
        f"import time; print('sim {sim_id} job', flush=True); time.sleep(120)",
    ]


@pytest.fixture
def launcher(tmp_path):
    started = []
    launcher = LocalLauncher(tmp_path, command_for=sleeper)
    real_start = launcher.start

    def start(sim_id):
        mark = real_start(sim_id)
        started.append(mark)
        return mark

    launcher.start = start
    yield launcher
    for mark in started:
        launcher.stop(mark)


def pid_of(mark: str) -> int:
    return int(mark.split()[1])


def test_a_started_job_is_found_and_killed(launcher):
    mark = launcher.start(12)
    assert mark.startswith("pid ")
    assert launcher.is_running(mark)

    assert launcher.stop(mark) is True

    assert not launcher.is_running(mark)
    assert not psutil.pid_exists(pid_of(mark)) or (
        psutil.Process(pid_of(mark)).status() == psutil.STATUS_ZOMBIE
    )


def test_a_reused_process_number_is_not_mistaken_for_the_job(launcher):
    """Windows reuses process numbers: same number, other start time, other program."""
    mark = launcher.start(12)
    pid, started = pid_of(mark), float(mark.split()[3])
    reused = f"pid {pid} started {started - 3600}"

    assert not launcher.is_running(reused)
    assert launcher.stop(reused) is False
    assert launcher.is_running(mark)


def test_stopping_a_job_already_gone_kills_nothing(launcher):
    mark = launcher.start(12)
    launcher.stop(mark)

    assert launcher.stop(mark) is False
    assert launcher.stop(None) is False


def test_the_job_writes_to_its_own_log(launcher, tmp_path):
    launcher.start(12)
    log = tmp_path / "sim-12.log"
    for _ in range(100):
        if "sim 12 job" in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    assert "sim 12 job" in log.read_text(encoding="utf-8")


def test_a_program_records_where_it_runs():
    mark = this_process()

    assert mark.startswith(f"pid {psutil.Process().pid} started ")
    assert LocalLauncher.find(mark).pid == psutil.Process().pid


def test_the_setting_names_a_local_or_kubernetes_launcher_and_nothing_else(tmp_path):
    assert isinstance(launcher_named("local", tmp_path, "TRADING_AGENT"), LocalLauncher)
    assert isinstance(
        launcher_named("kubernetes", tmp_path, "TRADING_AGENT"), KubernetesLauncher
    )
    assert isinstance(builds_named("local", tmp_path, "TRADING_AGENT"), LocalBuilds)
    assert isinstance(
        builds_named("kubernetes", tmp_path, "TRADING_AGENT"), KubernetesBuilds
    )
    with pytest.raises(ValueError, match="local"):
        launcher_named("ssh", tmp_path, "TRADING_AGENT")
    with pytest.raises(ValueError, match="local"):
        builds_named("ssh", tmp_path, "TRADING_AGENT")


def test_a_program_in_a_cluster_job_records_its_job(monkeypatch):
    """Its process number would name nothing the API can find: it notes the Job it was
    started as, the mark its launcher gave it."""
    monkeypatch.setenv("RUNNING_ON", "job sim-12-a1b2c3")

    assert this_process() == "job sim-12-a1b2c3"


def test_a_mark_without_a_start_time_cannot_be_confirmed_so_nothing_is_killed(launcher):
    """`pid 1234` alone could name any program now, another sim's job included."""
    mark = launcher.start(12)

    assert launcher.stop(f"pid {pid_of(mark)}") is False
    assert launcher.is_running(mark)


def build_sleeper(dataset_id, settings_file, check):
    said = f"build {dataset_id} {settings_file.name} {check}"
    return [
        sys.executable,
        "-c",
        f"import time; print({said!r}, flush=True); time.sleep(120)",
    ]


@pytest.fixture
def builds(tmp_path):
    builds = LocalBuilds(tmp_path, command_for=build_sleeper)
    yield builds
    for dataset_id in (3, 4):
        builds.stop(dataset_id)


def test_a_build_job_is_started_on_its_settings_file_and_killed_by_dataset(
    builds, tmp_path
):
    builds.start(3, 'name = "made-up"\n', check=False)

    assert (tmp_path / "dataset-3.toml").read_text(encoding="utf-8") == (
        'name = "made-up"\n'
    )
    assert builds.settings_text(3) == 'name = "made-up"\n'
    mark = (tmp_path / "dataset-3.job").read_text(encoding="utf-8")
    assert LocalLauncher.find(mark) is not None  # the job, noted to be found again
    log = tmp_path / "dataset-3.log"
    for _ in range(100):
        if log.exists() and "build 3" in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    assert "build 3 dataset-3.toml False" in log.read_text(encoding="utf-8")

    assert builds.stop(3) is True
    assert builds.stop(3) is False


def test_a_build_the_api_never_started_has_no_job_and_no_settings(builds):
    assert builds.settings_text(4) is None
    assert builds.stop(4) is False
