"""Starting a sim's job, and finding and killing it later (spec appendix 8, sections 8.7 and 8.10).

A job is the separate program that runs one sim: `python -m jev_trader.sim resume <id>`, the
same command the developer types. The API starts it through a launcher, chosen by the
`JOB_LAUNCHER` setting: `local` starts it as a program on this computer; `kubernetes` (a Job in
the kind cluster) comes with the cluster ticket.

**Where a job runs** is noted on the sim's row (`SIM.SIMS.RUNNING_ON`) by the job itself when
it starts, and by the API the moment it launches one: `pid 1234 started 1764000000.25`, its
process number and the time that process started. The API reads it back to find the job even
after the API itself restarted. Windows reuses process numbers, so a process is taken for the
job only if its start time matches too. A mark with no start time (`pid 1234`, written before
start times were noted) is matched by its command line instead.
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


class Launcher(Protocol):
    def start(self, sim_id: int) -> str:
        """Start the sim's job; returns where it runs, as noted on the sim's row."""

    def is_running(self, running_on: str | None) -> bool:
        """Whether the job noted by `running_on` is still running."""

    def stop(self, running_on: str | None) -> bool:
        """Kill the job noted by `running_on` and wait until it is gone. Returns False, killing
        nothing, if no such job is running (gone already, or the number now names another program)."""


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

    def __init__(self, log_dir: Path, command_for: Callable[[int], list[str]]):
        self.log_dir = log_dir
        self.command_for = command_for
        self._started: list[
            subprocess.Popen
        ] = []  # kept, so Python does not warn on exit

    def start(self, sim_id: int) -> str:
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
        with open(self.log_dir / f"sim-{sim_id}.log", "ab") as log:
            job = subprocess.Popen(
                self.command_for(sim_id),
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
            if len(words) >= 4 and words[2] == "started":
                same = abs(process.create_time() - float(words[3])) < SAME_START
            else:
                same = "jev_trader.sim" in " ".join(process.cmdline())
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
        return True


def launcher_named(name: str, log_dir: Path, database: str) -> Launcher:
    """The launcher the `JOB_LAUNCHER` setting names, starting sims on `database`."""
    if name == "local":
        return LocalLauncher(log_dir, lambda sim_id: sim_job_command(sim_id, database))
    if name == "kubernetes":
        raise ValueError(
            "JOB_LAUNCHER=kubernetes comes with the cluster ticket; use local for now"
        )
    raise ValueError(
        f"JOB_LAUNCHER must be one of {', '.join(LAUNCHERS)}, not {name!r}"
    )
