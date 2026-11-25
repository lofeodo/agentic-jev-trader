"""Sims and dataset builds as Jobs in the kind cluster, `JOB_LAUNCHER=kubernetes` (spec
appendix 8, section 8.10). A Job is Kubernetes' name for a program run once to its end; the
cluster runs that program in a pod (the running copy of the image), which the Job creates.

No cluster here: `FakeCluster` stands in for the `kubernetes` package's API clients, keeping
Jobs (and ConfigMaps, small stored files a Job can read) in dicts and answering as the real
ones do: the same model types, the same errors for a name already taken or a thing not found.
It answers both the Jobs calls (`BatchV1Api`) and the ConfigMap calls (`CoreV1Api`), so the one
`client` stands for whichever the launcher uses.
"""

import pytest
from kubernetes.client import (
    ApiClient,
    ApiException,
    V1ConfigMap,
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
SETTINGS = 'name = "made-up"\ntickers = ["SPY"]\n'
# Deleting a Job with either of these also deletes its pod, so the program stops. Without one,
# the API's default for Jobs leaves the pod running.
REMOVES_THE_POD = ("Foreground", "Background")


def plain(thing) -> dict:
    """A model or a dict, as the plain data the cluster stores."""
    return ApiClient().sanitize_for_serialization(thing)


class FakeCluster:
    """A cluster's Jobs and ConfigMaps. `run`, `finish` and `fail` play a Job's program."""

    def __init__(self, refuse_deletes: bool = False):
        # (namespace, name) -> the Job as sent
        self.jobs: dict[tuple[str, str], dict] = {}
        self.states: dict[tuple[str, str], V1JobStatus] = {}
        self.config_maps: dict[tuple[str, str], dict] = {}
        # (name, propagation_policy) of each Job deleted
        self.deleted: list[tuple[str, str | None]] = []
        self.refuse_deletes = refuse_deletes

    # Jobs (BatchV1Api)

    def create_namespaced_job(self, namespace, body, **_):
        job = plain(body)
        key = (namespace, job["metadata"]["name"])
        if key in self.jobs:
            raise ApiException(status=409, reason="AlreadyExists")
        self.jobs[key] = job
        # Just created: no pod yet, so nothing counted in its status.
        self.states[key] = V1JobStatus()
        return self._read(key)

    def read_namespaced_job(self, name, namespace, **_):
        return self._read((namespace, name))

    def read_namespaced_job_status(self, name, namespace, **_):
        return self._read((namespace, name))

    def delete_namespaced_job(self, name, namespace, propagation_policy=None, **kw):
        key = (namespace, name)
        if key not in self.jobs:
            raise ApiException(status=404, reason="NotFound")
        if self.refuse_deletes:
            raise ApiException(status=403, reason="Forbidden")
        body = plain(kw.get("body") or {})
        policy = propagation_policy or body.get("propagationPolicy")
        self.deleted.append((name, policy))
        del self.jobs[key], self.states[key]

    def _read(self, key):
        if key not in self.jobs:
            raise ApiException(status=404, reason="NotFound")
        namespace, name = key
        return V1Job(
            metadata=V1ObjectMeta(name=name, namespace=namespace),
            status=self.states[key],
        )

    # ConfigMaps (CoreV1Api)

    def create_namespaced_config_map(self, namespace, body, **_):
        config_map = plain(body)
        key = (namespace, config_map["metadata"]["name"])
        if key in self.config_maps:
            raise ApiException(status=409, reason="AlreadyExists")
        self.config_maps[key] = config_map
        return V1ConfigMap(data=config_map.get("data"))

    def read_namespaced_config_map(self, name, namespace, **_):
        key = (namespace, name)
        if key not in self.config_maps:
            raise ApiException(status=404, reason="NotFound")
        return V1ConfigMap(data=self.config_maps[key].get("data"))

    def delete_namespaced_config_map(self, name, namespace, **_):
        if self.config_maps.pop((namespace, name), None) is None:
            raise ApiException(status=404, reason="NotFound")

    # What happens in the cluster on its own

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


def sim_command(sim_id: int) -> list[str]:
    return sim_job_command(sim_id, DATABASE)


def build_command(dataset_id, settings_file, check) -> list[str]:
    return dataset_job_command(dataset_id, settings_file, check, DATABASE)


@pytest.fixture
def cluster():
    return FakeCluster()


@pytest.fixture
def launcher(cluster):
    return KubernetesLauncher(sim_command, client=cluster)


@pytest.fixture
def builds(cluster):
    return KubernetesBuilds(build_command, client=cluster)


# Sims


def test_a_sim_starts_as_a_job_named_for_it_running_the_sim_command(launcher, cluster):
    launcher.start(12)

    _, job = cluster.the_job("sim-12")
    # The command the local launcher runs, with the image's own Python in place of this
    # computer's.
    assert command_of(job) == ["python", *sim_command(12)[1:]]


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


def test_stopping_a_running_job_removes_it_and_its_pod(launcher, cluster):
    mark = launcher.start(12)
    cluster.run("sim-12")

    assert launcher.stop(mark) is True

    assert cluster.jobs == {}
    [(_, policy)] = cluster.deleted
    assert policy in REMOVES_THE_POD
    assert not launcher.is_running(mark)


def test_stopping_a_job_no_longer_running_kills_nothing(launcher, cluster):
    mark = launcher.start(12)
    cluster.finish("sim-12")

    assert launcher.stop(mark) is False
    assert launcher.stop(None) is False
    assert launcher.stop("pid 1234 started 1764000000.25") is False


def test_a_job_the_cluster_will_not_remove_is_reported_not_killed():
    cluster = FakeCluster(refuse_deletes=True)
    launcher = KubernetesLauncher(sim_command, client=cluster)
    mark = launcher.start(12)
    cluster.run("sim-12")

    with pytest.raises(JobNotKilled):
        launcher.stop(mark)


def test_a_sim_resumed_after_its_job_ended_starts_again(launcher, cluster):
    """Stopped and resumed, or ended and carried on: the old Job's name must not block it.
    Reusing the name (after removing the old Job) and taking a fresh one are both fine."""
    first = launcher.start(12)
    cluster.finish("sim-12")

    second = launcher.start(12)

    assert launcher.is_running(second)
    if second != first:
        assert not launcher.is_running(first)


# Dataset builds


def strings_in(thing) -> list[str]:
    """Every text value anywhere in a Job or ConfigMap, as plain data."""
    if isinstance(thing, str):
        return [thing]
    if isinstance(thing, dict):
        thing = list(thing.values())
    if isinstance(thing, list):
        return [text for part in thing for text in strings_in(part)]
    return []


def settings_reaching(job: dict, cluster: FakeCluster) -> bool:
    """Whether the settings text reaches the Job: written in the Job itself, or in a
    ConfigMap the Job names."""
    if SETTINGS in strings_in(job):
        return True
    named = strings_in(job["spec"]["template"]["spec"])
    return any(
        SETTINGS in strings_in(config_map.get("data")) and name in named
        for (_, name), config_map in cluster.config_maps.items()
    )


def test_a_build_starts_as_a_job_named_for_its_dataset_running_the_build_command(
    builds, cluster
):
    builds.start(3, SETTINGS, check=False)

    _, job = cluster.the_job("dataset-3")
    command = command_of(job)
    # The local builds' command, with the image's Python, on a settings file inside the pod.
    settings_file = command[4]
    assert command == ["python", *build_command(3, settings_file, False)[1:]]
    assert "--no-check" in command


def test_a_build_job_carries_its_settings(builds, cluster):
    builds.start(3, SETTINGS, check=True)

    _, job = cluster.the_job("dataset-3")
    assert settings_reaching(job, cluster)
    assert builds.settings_text(3) == SETTINGS


def test_a_build_the_api_never_started_has_no_settings(builds):
    assert builds.settings_text(4) is None


def test_a_checked_build_runs_without_the_no_check_switch(builds, cluster):
    builds.start(3, SETTINGS, check=True)

    _, job = cluster.the_job("dataset-3")
    assert "--no-check" not in command_of(job)


def test_stopping_a_running_build_removes_its_job_and_its_pod(builds, cluster):
    builds.start(3, SETTINGS, check=True)
    cluster.run("dataset-3")

    assert builds.stop(3) is True

    assert cluster.jobs == {}
    [(_, policy)] = cluster.deleted
    assert policy in REMOVES_THE_POD


def test_stopping_a_build_with_no_running_job_kills_nothing(builds, cluster):
    assert builds.stop(4) is False  # never started

    builds.start(3, SETTINGS, check=True)
    cluster.finish("dataset-3")
    assert builds.stop(3) is False  # ended already
