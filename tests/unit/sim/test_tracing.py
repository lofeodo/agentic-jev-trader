"""Tracing a sample of full evaluations to LangSmith (spec appendix 9, section 14).

LangSmith is reached through a stand-in web connection on the client, so nothing leaves this
computer: one that refuses everything (HTTP 429, as past the free plan's allowance), and one that
accepts and keeps what it was sent. The made-up market and fake Jev are the agent's
(`test_agent_without_memory.py`): every screen says yes, so every look at an asset with no
position is a full evaluation.
"""

import json

import pytest
import requests
from langsmith import Client, tracing_context
from requests.adapters import BaseAdapter

from jev_trader.sim import tracing as tracing_module
from jev_trader.sim.runner import run_sim
from jev_trader.sim.store import InMemorySimStore
from jev_trader.sim.tracing import Tracing, load_tracing_settings
from tests.unit.sim.test_agent_without_memory import fake_jev, practice, with_snapshots


class StandInLangSmith(BaseAdapter):
    """LangSmith's web address, answering every request with `status`; keeps what it was sent."""

    def __init__(self, status: int):
        super().__init__()
        self.status = status
        self.sent: list[requests.PreparedRequest] = []

    def send(self, request, **kwargs):
        self.sent.append(request)
        response = requests.Response()
        response.status_code = self.status
        response.headers["retry-after"] = "0"
        response._content = b"{}"
        response.url, response.request = request.url, request
        return response

    def close(self):
        pass


def client_over(adapter: StandInLangSmith, **settings) -> Client:
    session = requests.Session()
    client = Client(
        api_key="stand-in-key",
        api_url="https://langsmith.invalid",
        session=session,
        tracing_sampling_rate=1.0,
        **settings,
    )
    session.mount("https://", adapter)  # after the client mounts its own
    return client


def full_evaluations(store, sim_id) -> int:
    return sum(
        1
        for row in store.rows("MEMORY.DECISIONS", sim_id)
        if row["KIND"] == "full_evaluation"
    )


@pytest.fixture
def yes_market(market):
    return with_snapshots(market)


def test_a_sim_carries_on_when_langsmith_refuses_every_trace(yes_market):
    refusing = StandInLangSmith(429)
    client = client_over(refusing)
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    sim_id = practice(store, yes_market)

    result = run_sim(store, yes_market, sim_id, jev=jev, tracing=Tracing(client))
    client.flush()

    assert store.sim(sim_id)["STATUS"] == "finished"
    assert result.steps_stored > 0
    assert full_evaluations(store, sim_id) > 0
    assert any(r.method == "POST" for r in refusing.sent)  # it was refused, not unasked


def test_a_sim_carries_on_when_a_trace_cannot_be_opened(yes_market, monkeypatch):
    def broken_trace(*args, **kwargs):
        raise RuntimeError("made-up LangSmith failure")

    monkeypatch.setattr(tracing_module, "trace", broken_trace)
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    sim_id = practice(store, yes_market)
    tracing = Tracing(client_over(StandInLangSmith(200)))

    run_sim(store, yes_market, sim_id, jev=jev, tracing=tracing)

    assert store.sim(sim_id)["STATUS"] == "finished"
    assert full_evaluations(store, sim_id) > 0


def test_each_full_evaluation_is_one_trace_and_checks_get_none(yes_market):
    accepting = StandInLangSmith(200)
    # Sent one run at a time, as it happens, so each can be read back.
    client = client_over(accepting, auto_batch_tracing=False)
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    sim_id = practice(store, yes_market)

    run_sim(store, yes_market, sim_id, jev=jev, tracing=Tracing(client))

    started = [
        json.loads(r.body)
        for r in accepting.sent
        if r.method == "POST" and r.url.endswith("/runs")
    ]
    traces = [run for run in started if run.get("parent_run_id") is None]
    assert traces
    assert len(traces) == full_evaluations(store, sim_id)
    assert {run["name"] for run in traces} == {"full_evaluation"}
    steps = {run["name"] for run in started if run.get("parent_run_id")}
    assert steps == {"jev_pick"}  # the fake Jev picks no trade, so no size is asked


def test_the_share_traced_is_set_by_sim_kind(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "stand-in-key")
    with tracing_context(enabled=True):  # LangSmith's switch, as `.env` would set it
        practice_rate = Tracing.for_kind("practice").client.tracing_sample_rate
        measurement_rate = Tracing.for_kind("measurement").client.tracing_sample_rate

    assert practice_rate == 1.0
    assert measurement_rate == pytest.approx(1 / 30)
    assert load_tracing_settings().one_in["measurement"] == 30


def test_tracing_does_nothing_without_a_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with tracing_context(enabled=True):
        assert Tracing.for_kind("practice").client is None


def test_tracing_is_off_in_automatic_tests(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "stand-in-key")

    assert Tracing.for_kind("practice").client is None
