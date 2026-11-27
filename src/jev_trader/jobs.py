"""Starting a sim's or a dataset build's job, and finding and killing it later (spec appendix 8,
sections 8.7, 8.10 and 8.11). Dataset builds are `LocalBuilds`, further down.

A job is the separate program that runs one sim: `python -m jev_trader.sim resume <id>`, the
same command the developer types. The API starts it through a launcher, chosen by the
`JOB_LAUNCHER` setting: `local` starts it as a program on this computer; `kubernetes` starts it
as a Job in the kind cluster, from the Python image (`KubernetesLauncher`, further down).

**Where a job runs** is noted on the sim's row (`SIM.SIMS.RUNNING_ON`) by the job itself when
it starts, and by the API the moment it launches one: `pid 1234 started 1764000000.25`, its
process number and the time that process started. The API reads it back to find the job even
after the API itself restarted. Windows reuses process numbers, so a process is taken for the
job only if its start time matches too. A mark with no start time (`pid 1234`, written before
start times were noted) cannot be confirmed, so it is never killed: such a job, if still alive,
finds its sim stopped at its next write and ends there. A Job in the cluster is noted
`job sim-12-a1b2c3`, its name.
"""

import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path, PurePath, PurePosixPath
from typing import Protocol

import psutil
from kubernetes import client as k8s
from kubernetes import config as k8s_config
from kubernetes.client import ApiException

from jev_trader.storage.snowflake import DATABASE

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
LAUNCHERS = ("local", "kubernetes")
# How long a killed job may take to be gone before the kill is reported as failed.
SECONDS_TO_DIE = 30
# psutil reports start times to a hundredth of a second or better; a mark is written with all of it.
SAME_START = 0.01
# The setting a Job in the cluster is started with: its own mark, which `this_process` gives.
RUNNING_ON = "RUNNING_ON"


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
    """Where this program runs, as a job notes it on its sim's row. In a Job in the cluster,
    the Job's own mark, which the launcher gave it: its process number would name nothing the
    API can find."""
    return os.environ.get(RUNNING_ON) or _mark(psutil.Process())


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


# --- Jobs in the kind cluster (JOB_LAUNCHER=kubernetes) ----------------------------------------
# These must match Terraform's Kubernetes part (infra/terraform/kubernetes/main.tf).
NAMESPACE = "jev-trader"
# The cluster's context in this computer's kubeconfig, for an API run outside the cluster.
KUBE_CONTEXT = "kind-jev-trader"
# The Python image's plain user (Dockerfile); its group can read the mounted settings file.
PYTHON_USER = 10001
# The ConfigMap telling every program where the database is (engine, address, port, encryption).
DATABASE_CONFIG_MAP = "postgres"
# Where a build's pod finds its settings file, carried in a ConfigMap.
SETTINGS_DIR = "/settings"
SETTINGS_KEY = "settings.toml"
# How a Job's mark on a sim's row begins: `job sim-12-a1b2c3`.
JOB_MARK = "job "
# How often a stop looks whether the removed Job is gone yet.
SECONDS_BETWEEN_LOOKS = 0.5


class _Cluster:
    """The `kubernetes` package's clients for the kind cluster: in a pod, the pod's own
    service account; elsewhere, this computer's kubeconfig. The calls used here, Jobs from
    `BatchV1Api` and ConfigMaps from `CoreV1Api`, as one object (the tests' stand-in is one)."""

    def __init__(self):
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config(context=KUBE_CONTEXT)
        self.batch, self.core = k8s.BatchV1Api(), k8s.CoreV1Api()

    def create_namespaced_job(self, namespace, body, **options):
        return self.batch.create_namespaced_job(namespace, body, **options)

    def read_namespaced_job(self, name, namespace, **options):
        return self.batch.read_namespaced_job(name, namespace, **options)

    def delete_namespaced_job(self, name, namespace, **options):
        return self.batch.delete_namespaced_job(name, namespace, **options)

    def create_namespaced_config_map(self, namespace, body, **options):
        return self.core.create_namespaced_config_map(namespace, body, **options)

    def read_namespaced_config_map(self, name, namespace, **options):
        return self.core.read_namespaced_config_map(name, namespace, **options)

    def delete_namespaced_config_map(self, name, namespace, **options):
        return self.core.delete_namespaced_config_map(name, namespace, **options)


def _image() -> str:
    """The Python image a Job runs: `JOB_IMAGE` (Terraform sets it to the API's own image), or
    else the image of this checkout's commit, as `infra/images.py build` tags it."""
    if image := os.environ.get("JOB_IMAGE"):
        return image
    # Imported here: the sim runner imports this module.
    from jev_trader.sim.runner import code_version

    version = code_version()
    if version == "unknown":
        raise ValueError("JOB_IMAGE is not set and the code's commit is unknown")
    return f"jev-trader:{version}"


def _in_image(command: list[str]) -> list[str]:
    """A command made for this computer (`sys.executable` first), with the image's own Python
    in place of this one's."""
    return ["python", *command[1:]]


def _or_none(read: Callable, *args):
    """What `read(*args)` answers, or None if the cluster has no such thing."""
    try:
        return read(*args)
    except ApiException as error:
        if error.status == 404:
            return None
        raise


class _ClusterJobs:
    """Starting, watching and stopping Jobs in the namespace, for sims and builds alike.

    A Job runs its pod once (no retry: `backoff_limit` 0) and is kept after it ends, so its
    output stays readable: `kubectl logs job/<name> -n jev-trader`. Each Job gets where the
    database is (`DATABASE_CONFIG_MAP`), its own login's password (the secret `postgres-<login>`),
    one more secret of keys (`keys`), and no service account token, so it cannot reach the
    cluster itself.
    """

    def __init__(self, client):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _Cluster()
        return self._client

    def start(
        self,
        name: str,
        command: list[str],
        login: str,
        keys: str,
        labels: dict[str, str],
        env: dict[str, str] | None = None,
        settings: str | None = None,
    ) -> None:
        """Start the Job `name` running `command` as `login`. `settings` names a ConfigMap
        to mount at SETTINGS_DIR."""
        variables = [k8s.V1EnvVar(name=k, value=v) for k, v in (env or {}).items()]
        from_settings_and_secrets = [
            k8s.V1EnvFromSource(
                config_map_ref=k8s.V1ConfigMapEnvSource(name=DATABASE_CONFIG_MAP)
            ),
            k8s.V1EnvFromSource(
                secret_ref=k8s.V1SecretEnvSource(name=f"postgres-{login}")
            ),
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=keys)),
        ]
        mounts, volumes = [], []
        if settings is not None:
            mounts.append(
                k8s.V1VolumeMount(
                    name="settings", mount_path=SETTINGS_DIR, read_only=True
                )
            )
            volumes.append(
                k8s.V1Volume(
                    name="settings",
                    config_map=k8s.V1ConfigMapVolumeSource(name=settings),
                )
            )
        pod = k8s.V1PodSpec(
            restart_policy="Never",
            # Stop kills the program at once, as a local job's stop does.
            termination_grace_period_seconds=0,
            automount_service_account_token=False,
            security_context=k8s.V1PodSecurityContext(
                run_as_non_root=True, run_as_user=PYTHON_USER, fs_group=PYTHON_USER
            ),
            containers=[
                k8s.V1Container(
                    name="job",
                    image=_image(),
                    image_pull_policy="Never",  # loaded into kind, never downloaded
                    command=command,
                    env=variables,
                    env_from=from_settings_and_secrets,
                    volume_mounts=mounts,
                )
            ],
            volumes=volumes,
        )
        job = k8s.V1Job(
            metadata=k8s.V1ObjectMeta(name=name, labels=labels),
            spec=k8s.V1JobSpec(
                backoff_limit=0,
                template=k8s.V1PodTemplateSpec(
                    metadata=k8s.V1ObjectMeta(labels=labels), spec=pod
                ),
            ),
        )
        self.client.create_namespaced_job(NAMESPACE, job)

    def is_running(self, name: str | None) -> bool:
        """Whether the Job `name` exists and has not ended (complete or failed). A Job just
        created, its pod not started yet, counts as running."""
        if name is None:
            return False
        job = _or_none(self.client.read_namespaced_job, name, NAMESPACE)
        if job is None:
            return False
        conditions = (job.status and job.status.conditions) or []
        return not any(
            c.type in ("Complete", "Failed") and c.status == "True" for c in conditions
        )

    def stop(self, name: str | None) -> bool:
        """Remove the running Job `name` and its pod, and wait until both are gone. A Job
        that has ended is kept, with its output."""
        if not self.is_running(name):
            return False
        try:
            self.client.delete_namespaced_job(
                name,
                NAMESPACE,
                propagation_policy="Foreground",  # the pod goes first, then the Job
            )
        except ApiException as error:
            if error.status == 404:
                return False  # it went by itself meanwhile
            raise JobNotKilled(
                f"the Job {name} would not be removed: {error}"
            ) from error
        deadline = time.monotonic() + SECONDS_TO_DIE
        while time.monotonic() < deadline:
            if _or_none(self.client.read_namespaced_job, name, NAMESPACE) is None:
                return True
            time.sleep(SECONDS_BETWEEN_LOOKS)
        raise JobNotKilled(f"the Job {name} was still there after {SECONDS_TO_DIE}s")


def _job_name(running_on: str | None) -> str | None:
    """The Job a mark names; None for a program on this computer (`pid ...`) or no mark."""
    if running_on and running_on.startswith(JOB_MARK):
        return running_on.removeprefix(JOB_MARK)
    return None


class KubernetesLauncher:
    """Sims' jobs as Kubernetes Jobs in the kind cluster, each running `command_for(sim_id)`
    from the Python image as the sim login, with the model keys. `client` is the `kubernetes`
    package's clients (or a stand-in for them in tests); None means ones made on first use.

    Each start makes a fresh Job, `sim-<id>-<6 random characters>`, so a resumed sim never
    waits for its old Job's name, and a sim of the same number in the other database never
    meets it. Its mark is `job <name>`. The Job is given that mark (`RUNNING_ON`), so the
    mark the sim job writes itself (`this_process`) is the same one.
    """

    def __init__(self, command_for: Callable[[int], list[str]], client=None):
        self.command_for = command_for
        self.jobs = _ClusterJobs(client)

    def start(self, sim_id: int) -> str:
        name = f"sim-{sim_id}-{secrets.token_hex(3)}"
        mark = JOB_MARK + name
        self.jobs.start(
            name,
            _in_image(self.command_for(sim_id)),
            login="sim",
            keys="models",
            labels={"app": "sim-job", "sim": str(sim_id)},
            env={RUNNING_ON: mark},
        )
        return mark

    def is_running(self, running_on: str | None) -> bool:
        return self.jobs.is_running(_job_name(running_on))

    def stop(self, running_on: str | None) -> bool:
        return self.jobs.stop(_job_name(running_on))


class KubernetesBuilds:
    """Dataset builds as Kubernetes Jobs in the kind cluster, each running the build command
    from the Python image as the builder login, with the price-data key. A build's Job and the
    ConfigMap holding its settings are both named `dataset-<id>-<database>`, so both are found
    after the API restarts with nothing stored, and the two databases' datasets of one number
    never meet. `client` is as for `KubernetesLauncher`."""

    def __init__(
        self,
        command_for: Callable[[int, PurePath, bool], list[str]],
        client=None,
        database: str = DATABASE,
    ):
        self.command_for = command_for
        self.jobs = _ClusterJobs(client)
        self.database = database

    def _name(self, dataset_id: int) -> str:
        # Names take lower-case letters, digits and dashes only.
        return f"dataset-{dataset_id}-{self.database.lower().replace('_', '-')}"

    def start(self, dataset_id: int, settings_text: str, check: bool) -> None:
        name = self._name(dataset_id)
        labels = {"app": "dataset-job", "dataset": str(dataset_id)}
        self.jobs.client.create_namespaced_config_map(
            NAMESPACE,
            k8s.V1ConfigMap(
                metadata=k8s.V1ObjectMeta(name=name, labels=labels),
                data={SETTINGS_KEY: settings_text},
            ),
        )
        # A path inside the pod, written with forward slashes on every computer.
        settings_file = PurePosixPath(SETTINGS_DIR, SETTINGS_KEY)
        try:
            self.jobs.start(
                name,
                _in_image(self.command_for(dataset_id, settings_file, check)),
                login="builder",
                keys="twelve-data",
                labels=labels,
                settings=name,
            )
        except Exception:
            # No build of these settings ever ran: they are not kept.
            _or_none(self.jobs.client.delete_namespaced_config_map, name, NAMESPACE)
            raise

    def stop(self, dataset_id: int) -> bool:
        return self.jobs.stop(self._name(dataset_id))

    def settings_text(self, dataset_id: int) -> str | None:
        config_map = _or_none(
            self.jobs.client.read_namespaced_config_map,
            self._name(dataset_id),
            NAMESPACE,
        )
        return None if config_map is None else (config_map.data or {}).get(SETTINGS_KEY)


def builds_named(name: str, folder: Path, database: str) -> Builds:
    """The dataset builds the `JOB_LAUNCHER` setting names, building into `database`."""

    def command_for(dataset_id: int, settings_file: Path, check: bool) -> list[str]:
        return dataset_job_command(dataset_id, settings_file, check, database)

    if name == "local":
        return LocalBuilds(folder, command_for)
    if name == "kubernetes":
        return KubernetesBuilds(command_for, database=database)
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
