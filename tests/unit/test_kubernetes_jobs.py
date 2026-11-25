"""Sims and dataset builds as Jobs in the kind cluster, `JOB_LAUNCHER=kubernetes` (spec
appendix 8, section 8.10). A Job is Kubernetes' name for a program run once to its end.

No cluster here: `FakeBatchApi` stands in for the `kubernetes` package's `BatchV1Api`, keeping
Jobs in a dict and answering as the real one does (the same model types, the same errors for a
name already taken or a Job not found).
"""

import pytest
from kubernetes.client import (
    ApiClient,
    ApiException,
    V1Job,
    V1JobCondition,
    V1JobStatus,
    V1ObjectMeta,
)

from jev_trader.jobs import (
    JobNotKilled,
    KubernetesBuilds,
    KubernetesLauncher,
    dataset_job_command,
    sim_job_command,
)

# Dormant until the slice's closing ticket switches it on (slice map #115): it fails as
# "not built yet" until the JOB_LAUNCHER=kubernetes ticket (#200) lands.
pytestmark = pytest.mark.skip(reason="dormant: the kind-cluster slice's tests (#115)")

DATABASE = "TRADING_AGENT_TEST"


class FakeBatchApi:
    """The Jobs part of a cluster. `finish` and `fail` play a Job's program ending."""

    def __init__(self, refuse_deletes: bool = False):
        self.jobs: dict[
            tuple[str, str], dict
        ] = {}  # (namespace, name) -> the Job as sent
        self.states: dict[tuple[str, str], V1JobStatus] = {}
        self.refuse_deletes = refuse_deletes

    def create_namespaced_job(self, namespace, body, **_):
        job = ApiClient().sanitize_for_serialization(
            body
        )  # a model or a dict, as plain data
        key = (namespace, job["metadata"]["name"])
        if key in self.jobs:
            raise ApiException(status=409, reason="AlreadyExists")
        self.jobs[key] = job
        self.states[key] = V1JobStatus()  # just created: no pod yet
        return self._read(key)

    def read_namespaced_job(self, name, namespace, **_):
        return self._read((namespace, name))

    def read_namespaced_job_status(self, name, namespace, **_):
        return self._read((namespace, name))

    def delete_namespaced_job(self, name, namespace, **_):
        key = (namespace, name)
        if key not in self.jobs:
            raise ApiException(status=404, reason="NotFound")
        if self.refuse_deletes:
            raise ApiException(status=403, reason="Forbidden")
        del self.jobs[key], self.states[key]

    def _read(self, key):
        if key not in self.jobs:
            raise ApiException(status=404, reason="NotFound")
        namespace, name = key
        return V1Job(
            metadata=V1ObjectMeta(name=name, namespace=namespace),
            status=self.states[key],
        )

    # What happens in the cluster on its own.

    def the_job(self, prefix: str) -> tuple[tuple[str, str], dict]:
        """The one Job named for `prefix` (`sim-12`, `dataset-3`)."""
        [found] = [
            (key, job)
            for key, job in self.jobs.items()
            if key[1] == prefix or key[1].startswith(prefix + "-")
        ]
        return found

    def run(self, prefix: str):
        self.states[self.the_job(prefix)[0]] = V1JobStatus(active=1)

    def finish(self, prefix: str):
        self.states[self.the_job(prefix)[0]] = V1JobStatus(
            succeeded=1,
            conditions=[V1JobCondition(type="Complete", status="True")],
        )

    def fail(self, prefix: str):
        self.states[self.the_job(prefix)[0]] = V1JobStatus(
            failed=1,
            conditions=[V1JobCondition(type="Failed", status="True")],
        )


def command_of(job: dict) -> list[str]:
    """What the Job's one container runs: its command, then its arguments."""
    [container] = job["spec"]["template"]["spec"]["containers"]
    return [*container.get("command", []), *container.get("args", [])]


@pytest.fixture
def cluster():
    return FakeBatchApi()


@pytest.fixture
def launcher(cluster):
    return KubernetesLauncher(
        lambda sim_id: sim_job_command(sim_id, DATABASE), client=cluster
    )


@pytest.fixture
def builds(cluster):
    return KubernetesBuilds(
        lambda dataset_id, settings_file, check: dataset_job_command(
            dataset_id, settings_file, check, DATABASE
        ),
        client=cluster,
    )


# Sims


def test_a_sim_starts_as_a_job_named_for_it_running_the_sim_command(launcher, cluster):
    launcher.start(12)

    _, job = cluster.the_job("sim-12")
    # The command the local launcher runs, with the image's own Python in place of this
    # computer's.
    assert command_of(job) == [
        "python",
        *sim_job_command(12, DATABASE)[1:],
    ]


def test_a_job_counts_as_running_from_its_start_until_its_program_ends(
    launcher, cluster
):
    mark = launcher.start(12)

    assert launcher.is_running(mark)  # created, its pod not there yet
    cluster.run("sim-12")
    assert launcher.is_running(mark)
    cluster.finish("sim-12")
    assert not launcher.is_running(mark)


def test_a_failed_job_is_not_running(launcher, cluster):
    mark = launcher.start(12)
    cluster.run("sim-12")

    cluster.fail("sim-12")

    assert not launcher.is_running(mark)


def test_each_sim_gets_its_own_job(launcher, cluster):
    twelve = launcher.start(12)
    thirteen = launcher.start(13)
    cluster.finish("sim-12")

    assert twelve != thirteen
    assert not launcher.is_running(twelve)
    assert launcher.is_running(thirteen)


def test_a_mark_that_names_no_job_in_the_cluster_is_not_running(launcher):
    """A job on this computer (`pid ...`), no mark at all, or a Job since removed."""
    mark = launcher.start(12)
    launcher.stop(mark)

    assert not launcher.is_running("pid 1234 started 1764000000.25")
    assert not launcher.is_running(None)
    assert not launcher.is_running(mark)


def test_a_mark_from_the_cluster_cannot_be_taken_for_a_program_on_this_computer(
    launcher,
):
    assert not launcher.start(12).startswith("pid ")


def test_stopping_a_running_job_removes_it(launcher, cluster):
    mark = launcher.start(12)
    cluster.run("sim-12")

    assert launcher.stop(mark) is True

    assert cluster.jobs == {}
    assert not launcher.is_running(mark)


def test_stopping_a_job_no_longer_running_kills_nothing(launcher, cluster):
    mark = launcher.start(12)
    cluster.finish("sim-12")

    assert launcher.stop(mark) is False
    assert launcher.stop(None) is False
    assert launcher.stop("pid 1234 started 1764000000.25") is False


def test_a_job_the_cluster_will_not_remove_is_reported_not_killed():
    cluster = FakeBatchApi(refuse_deletes=True)
    launcher = KubernetesLauncher(
        lambda sim_id: sim_job_command(sim_id, DATABASE), client=cluster
    )
    mark = launcher.start(12)
    cluster.run("sim-12")

    with pytest.raises(JobNotKilled):
        launcher.stop(mark)


def test_a_sim_resumed_after_its_job_ended_starts_again(launcher, cluster):
    """Stopped and resumed, or ended and carried on: the old Job's name must not block it."""
    first = launcher.start(12)
    cluster.finish("sim-12")

    second = launcher.start(12)

    assert launcher.is_running(second)
    assert not launcher.is_running(first) or first == second


# Dataset builds


def test_a_build_starts_as_a_job_named_for_its_dataset_running_the_build_command(
    builds, cluster
):
    builds.start(3, 'name = "made-up"\n', check=False)

    _, job = cluster.the_job("dataset-3")
    command = command_of(job)
    # The local builds' command, with the image's Python, on a settings file inside the Job.
    settings_file = command[4]
    assert command == [
        "python",
        "-m",
        "jev_trader.dataset",
        "build",
        settings_file,
        "--dataset-id",
        "3",
        "--database",
        DATABASE,
        "--no-check",
    ]


def test_a_checked_build_runs_without_the_no_check_switch(builds, cluster):
    builds.start(3, 'name = "made-up"\n', check=True)

    _, job = cluster.the_job("dataset-3")
    assert "--no-check" not in command_of(job)


def test_stopping_a_running_build_removes_its_job(builds, cluster):
    builds.start(3, 'name = "made-up"\n', check=True)
    cluster.run("dataset-3")

    assert builds.stop(3) is True

    assert cluster.jobs == {}


def test_stopping_a_build_with_no_running_job_kills_nothing(builds, cluster):
    assert builds.stop(4) is False  # never started

    builds.start(3, 'name = "made-up"\n', check=True)
    cluster.finish("dataset-3")
    assert builds.stop(3) is False  # ended already
