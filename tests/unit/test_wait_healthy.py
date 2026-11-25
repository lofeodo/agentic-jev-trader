"""The deployment check's wait until the services report healthy (`infra/wait_healthy.py`,
spec appendix 10, section 5). A made-up clock stands in for time, and made-up services for the
cluster: nothing here waits or reaches the network."""

import urllib.error

import pytest

from infra import wait_healthy
from infra.wait_healthy import wait_until_healthy

# Dormant until the slice's closing ticket switches it on (slice map #115).
pytestmark = pytest.mark.skip(reason="dormant: the kind-cluster slice's tests (#115)")

MEMORY = "http://memory:8765/health"
API = "http://api:8000/health"
WEB = "http://web/"


class Clock:
    """Time that moves only when slept through."""

    def __init__(self):
        self.now = 1000.0
        self.naps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float):
        self.naps.append(seconds)
        self.now += seconds


class Services:
    """Each address turns healthy after it has been asked a given number of times
    (None: never)."""

    def __init__(self, healthy_from: dict[str, int | None]):
        self.healthy_from = healthy_from
        self.asked: dict[str, int] = {url: 0 for url in healthy_from}

    def __call__(self, url: str) -> bool:
        self.asked[url] += 1
        first = self.healthy_from[url]
        return first is not None and self.asked[url] >= first


def wait(services, clock, timeout=60, every=5):
    said = []
    never = wait_until_healthy(
        list(services.healthy_from),
        timeout,
        every,
        is_healthy=services,
        clock=clock,
        sleep=clock.sleep,
        say=said.append,
    )
    return never, said


def test_services_already_healthy_end_the_wait_at_once():
    clock = Clock()
    services = Services({MEMORY: 1, API: 1, WEB: 1})

    never, said = wait(services, clock)

    assert never == []
    assert clock.naps == []
    assert said == [f"healthy: {MEMORY}", f"healthy: {API}", f"healthy: {WEB}"]


def test_the_wait_lasts_until_the_slowest_service_is_healthy_and_asks_no_more():
    clock = Clock()
    services = Services({MEMORY: 1, API: 3, WEB: 2})

    never, _ = wait(services, clock, every=5)

    assert never == []
    assert clock.naps == [5, 5]  # three rounds of asking
    assert services.asked == {MEMORY: 1, API: 3, WEB: 2}


def test_a_service_that_never_becomes_healthy_is_named_after_the_timeout():
    clock = Clock()
    services = Services({MEMORY: 1, API: None, WEB: 2})

    never, said = wait(services, clock, timeout=60, every=5)

    assert never == [API]
    assert f"healthy: {API}" not in said
    assert clock.now - 1000.0 == 60


def test_the_wait_never_sleeps_past_the_timeout():
    clock = Clock()
    services = Services({API: None})

    never, _ = wait(services, clock, timeout=12, every=5)

    assert never == [API]
    assert clock.naps == [5, 5, 2]  # the last nap is cut to the time left
    assert services.asked[API] == 4  # once more at the deadline itself


def test_a_service_healthy_only_at_the_deadline_still_counts():
    clock = Clock()
    services = Services({API: 3})

    never, _ = wait(services, clock, timeout=10, every=5)

    assert never == []


def test_the_command_ends_with_1_naming_what_never_answered(monkeypatch, capsys):
    monkeypatch.setattr(wait_healthy, "answers_healthy", lambda url: url != API)

    code = wait_healthy.main([MEMORY, API, "--timeout", "0"])

    assert code == 1
    out = capsys.readouterr().out
    assert f"healthy: {MEMORY}" in out
    assert f"not healthy after 0 seconds: {API}" in out


def test_the_command_ends_with_0_when_every_service_answered(monkeypatch):
    monkeypatch.setattr(wait_healthy, "answers_healthy", lambda url: True)

    assert wait_healthy.main([MEMORY, API, WEB, "--timeout", "0"]) == 0


class Answer:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_a_success_answer_is_healthy(monkeypatch):
    monkeypatch.setattr(
        wait_healthy.urllib.request, "urlopen", lambda url, timeout: Answer(200)
    )

    assert wait_healthy.answers_healthy(API) is True


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError(API, 503, "Service Unavailable", {}, None),
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
    ],
)
def test_an_error_answer_or_no_answer_is_not_healthy(monkeypatch, failure):
    def urlopen(url, timeout):
        raise failure

    monkeypatch.setattr(wait_healthy.urllib.request, "urlopen", urlopen)

    assert wait_healthy.answers_healthy(API) is False
