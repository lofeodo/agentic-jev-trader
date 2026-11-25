"""Starting a sim's or a dataset build's job, and finding and killing it later (spec appendix 8,
sections 8.7, 8.10 and 8.11). Dataset builds are `LocalBuilds`, further down.

A job is the separate program that runs one sim: `python -m jev_trader.sim resume <id>`, the
same command the developer types. The API starts it through a launcher, chosen by the
`JOB_LAUNCHER` setting: `local` starts it as a program on this computer; `kubernetes` starts it
as a Job in the kind cluster (its launcher and builds are in place, and refuse to start a job
until the cluster's launcher ticket fills them in).

**Where a job runs** is noted on the sim's row (`SIM.SIMS.RUNNING_ON`) by the job itself when
it starts, and by the API the moment it launches one: `pid 1234 started 1764000000.25`, its
process number and the time that process started. The API reads it back to find the job even
after the API itself restarted. Windows reuses process numbers, so a process is taken for the
job only if its start time matches too. A mark with no start time (`pid 1234`, written before
start times were noted) cannot be confirmed, so it is never killed: such a job, if still alive,
finds its sim stopped at its next write and ends there.
"""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import psutil

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
LAUNCHERS = ("local", "kubernetes")
# How long a killed job may take to be gone before the kill is reported as failed.
SECONDS_TO_DIE = 30
# psutil reports start times to a hundredth of a second or better; a mark is written with all of it.
SAME_START = 0.01


class JobNotKilled(Exception):
    """The job was found but would not die: no right to end it, or still alive after the wait."""


class Launcher(Protocol):
    def start(self, sim_id: int) -> str:
        """Start the sim's job; returns where it runs, as noted on the sim's row."""

    def is_running(self, running_on: str | None) -> bool:
        """Whether the job noted by `running_on` is still running."""

    def stop(self, running_on: str | None) -> bool:
        """Kill the job noted by `running_on` and wait until it is gone. Returns False, killing
        nothing, if no such job is running (gone already, or the number now names another program).
        Raises `JobNotKilled` if it is running and will not die."""


def this_process() -> str:
    """Where this program runs, as a job notes it on its sim's row."""
    return _mark(psutil.Process())


def _mark(process: psutil.Process) -> str:
    return f"pid {process.pid} started {process.create_time()!r}"


def sim_job_command(sim_id: int, database: str) -> list[str]:
    """The command that runs a sim, from its first step or after its last stored one."""
    return [
        sys.executable,
        "-m",
        "jev_trader.sim",
        "resume",
        str(sim_id),
        "--database",
        database,
    ]


class LocalLauncher:
    """Jobs as programs on this computer, each writing what it prints to `log_dir/sim-<id>.log`.

    A job runs on its own: it has no window, ignores the API's Ctrl+C, and outlives the API.
    It runs this checkout's code, whichever copy of the package is installed.
    """

    def __init__(
        self,
        log_dir: Path,
        command_for: Callable[[int], list[str]] | None,
        log_prefix: str = "sim",
    ):
        self.log_dir = log_dir
        self.command_for = command_for
        self.log_prefix = log_prefix
        self._started: list[
            subprocess.Popen
        ] = []  # kept, so Python does not warn on exit

    def start(self, sim_id: int) -> str:
        if self.command_for is None:
            raise ValueError("this launcher runs only the commands it is given")
        return self.run(sim_id, self.command_for(sim_id))

    def run(self, job_id: int, command: list[str]) -> str:
        """Start `command` as job `job_id`, printing to `log_dir/<log_prefix>-<job_id>.log`."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                p for p in (str(SRC), os.environ.get("PYTHONPATH")) if p
            ),
            "PYTHONUNBUFFERED": "1",
        }
        if sys.platform == "win32":
            detached = {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            }
        else:
            detached = {"start_new_session": True}
        with open(self.log_dir / f"{self.log_prefix}-{job_id}.log", "ab") as log:
            job = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=REPO_ROOT,
                env=env,
                **detached,
            )
        self._started.append(job)
        return _mark(psutil.Process(job.pid))

    @staticmethod
    def find(running_on: str | None) -> psutil.Process | None:
        """The process `running_on` names, if it is still running and is that job."""
        if not running_on or not running_on.startswith("pid "):
            return None
        words = running_on.split()
        try:
            process = psutil.Process(int(words[1]))
            if process.status() == psutil.STATUS_ZOMBIE:
                return None
            same = (
                len(words) >= 4
                and words[2] == "started"
                and abs(process.create_time() - float(words[3])) < SAME_START
            )
        except (ValueError, IndexError, psutil.Error):
            return None
        return process if same else None

    def is_running(self, running_on: str | None) -> bool:
        return self.find(running_on) is not None

    def stop(self, running_on: str | None) -> bool:
        process = self.find(running_on)
        if process is None:
            return False
        try:
            for child in process.children(recursive=True):
                child.kill()
            process.kill()
            process.wait(timeout=SECONDS_TO_DIE)
        except psutil.NoSuchProcess:
            pass  # it ended by itself meanwhile
        except (psutil.AccessDenied, psutil.TimeoutExpired) as error:
            raise JobNotKilled(
                f"the job at {running_on} would not die: {error}"
            ) from error
        return True


def dataset_job_command(
    dataset_id: int, settings_file: Path, check: bool, database: str
) -> list[str]:
    """The command that builds a dataset the API asked for, carrying on its row."""
    command = [
        sys.executable,
        "-m",
        "jev_trader.dataset",
        "build",
        str(settings_file),
        "--dataset-id",
        str(dataset_id),
        "--database",
        database,
    ]
    return command if check else [*command, "--no-check"]


class Builds(Protocol):
    """Dataset builds the API starts and stops (spec appendix 8, section 8.11)."""

    def start(self, dataset_id: int, settings_text: str, check: bool) -> None:
        """Start the build of the dataset row `dataset_id` from these settings (TOML)."""

    def stop(self, dataset_id: int) -> bool:
        """Kill the dataset's build job and wait until it is gone. False if none is running.
        Raises `JobNotKilled` if it will not die."""

    def settings_text(self, dataset_id: int) -> str | None:
        """The settings the API started the build from, or None for a build it did not start."""


class LocalBuilds:
    """Dataset builds as programs on this computer. A build's files sit together in `folder`:
    `dataset-<id>.toml` its settings, `dataset-<id>.job` where its job runs (so it is found
    after the API restarts) and `dataset-<id>.log` what it prints. The datasets table has no
    column for where a build runs, so the mark lives here; a build started from the command
    line has none, and is stopped from the app at its next stage (it checks its row)."""

    def __init__(
        self,
        folder: Path,
        command_for: Callable[[int, Path, bool], list[str]],
    ):
        self.folder = folder
        self.command_for = command_for
        # Only its `run` and `stop` are used: each build's command is made here.
        self.jobs = LocalLauncher(folder, command_for=None, log_prefix="dataset")

    def _file(self, dataset_id: int, ending: str) -> Path:
        return self.folder / f"dataset-{dataset_id}.{ending}"

    def start(self, dataset_id: int, settings_text: str, check: bool) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        settings_file = self._file(dataset_id, "toml")
        settings_file.write_text(settings_text, encoding="utf-8")
        mark = self.jobs.run(
            dataset_id, self.command_for(dataset_id, settings_file, check)
        )
        self._file(dataset_id, "job").write_text(mark, encoding="utf-8")

    def _mark(self, dataset_id: int) -> str | None:
        path = self._file(dataset_id, "job")
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def stop(self, dataset_id: int) -> bool:
        return self.jobs.stop(self._mark(dataset_id))

    def settings_text(self, dataset_id: int) -> str | None:
        path = self._file(dataset_id, "toml")
        return path.read_text(encoding="utf-8") if path.exists() else None


class NotBuiltYet(NotImplementedError):
    """A part of the kind cluster that is in place but not built yet."""


def _kubernetes_not_built() -> NotBuiltYet:
    return NotBuiltYet(
        "JOB_LAUNCHER=kubernetes is not built yet: jobs cannot start in the kind cluster;"
        " use JOB_LAUNCHER=local for now"
    )


class KubernetesLauncher:
    """Sims' jobs as Kubernetes Jobs in the kind cluster, each running `command_for(sim_id)`
    from the Python image. Not built yet: every call refuses."""

    def __init__(self, command_for: Callable[[int], list[str]]):
        self.command_for = command_for

    def start(self, sim_id: int) -> str:
        raise _kubernetes_not_built()

    def is_running(self, running_on: str | None) -> bool:
        raise _kubernetes_not_built()

    def stop(self, running_on: str | None) -> bool:
        raise _kubernetes_not_built()


class KubernetesBuilds:
    """Dataset builds as Kubernetes Jobs in the kind cluster, each running the build command
    from the Python image. Not built yet: starting or stopping one refuses, and it holds no
    build's settings."""

    def __init__(self, command_for: Callable[[int, Path, bool], list[str]]):
        self.command_for = command_for

    def start(self, dataset_id: int, settings_text: str, check: bool) -> None:
        raise _kubernetes_not_built()

    def stop(self, dataset_id: int) -> bool:
        raise _kubernetes_not_built()

    def settings_text(self, dataset_id: int) -> str | None:
        return None


def builds_named(name: str, folder: Path, database: str) -> Builds:
    """The dataset builds the `JOB_LAUNCHER` setting names, building into `database`."""

    def command_for(dataset_id: int, settings_file: Path, check: bool) -> list[str]:
        return dataset_job_command(dataset_id, settings_file, check, database)

    if name == "local":
        return LocalBuilds(folder, command_for)
    if name == "kubernetes":
        return KubernetesBuilds(command_for)
    raise _unknown(name)


def launcher_named(name: str, log_dir: Path, database: str) -> Launcher:
    """The launcher the `JOB_LAUNCHER` setting names, starting sims on `database`."""

    def command_for(sim_id: int) -> list[str]:
        return sim_job_command(sim_id, database)

    if name == "local":
        return LocalLauncher(log_dir, command_for)
    if name == "kubernetes":
        return KubernetesLauncher(command_for)
    raise _unknown(name)


def _unknown(name: str) -> ValueError:
    return ValueError(
        f"JOB_LAUNCHER must be one of {', '.join(LAUNCHERS)}, not {name!r}"
    )
