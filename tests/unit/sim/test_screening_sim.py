"""The agent without memory, part one: a practice sim that screens every asset at every step.

Runs on the in-memory store and the made-up market of `conftest.py`, with hand-written fake
answers from Jev. Day 2 is steps 97 to 192: the crypto has 96 bars, the stock 26 (151 to 176).
"""

import json
from dataclasses import replace

import httpx2
import pytest

from jev_trader.broker import (
    AssetClass,
    Bar,
    Broker,
    load_stop_price_settings,
    load_trading_costs,
)
from jev_trader.jev.client import JevClient, JevFailed, load_jev_settings
from jev_trader.jev.masking import MaskingLeak, assert_masked, real_values
from jev_trader.jev.reading import Reading
from jev_trader.risk import load_risk_profile
from jev_trader.sim.agent import ScreeningAgent
from jev_trader.sim.market import InMemoryMarket, Snapshot
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import InMemorySimStore

DATASET = 7
STOCK, CRYPTO = "ASSET_01", "ASSET_02"
PLAYBOOK = {"hammer": ("bullish", "A small body at the top of the bar.")}
SCREENS_ASKED = 96 + 24  # the stock's last two bars of the session are not asked


def with_snapshots(market, situation="Made-up situation."):
    snapshots = {}
    for asset, bars in market.bars_by_asset[DATASET].items():
        for bar in bars:
            bars_left = None
            if asset == STOCK:
                bars_left = (176 - bar.step) % 96 if bar.step <= 176 else 0
            snapshots.setdefault(bar.step, {})[asset] = Snapshot(
                situation_text=situation,
                typical_move=0.5,
                bars_left=bars_left,
                patterns=("hammer",),
            )
    return InMemoryMarket(
        market.datasets,
        market.bars_by_asset,
        snapshots={DATASET: snapshots},
        playbook=PLAYBOOK,
    )


def fake_jev(answer=lambda n: 0.3, tokens=1000):
    """A client over fake answers; `sent` holds each request body as Jev received it."""
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        result = answer(len(sent))
        if isinstance(result, int):
            return httpx2.Response(result, json={"error": "made-up failure"})
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {"screen": {"type": "noul", "noul": result}},
                "usage": {"input_tokens": tokens, "output_tokens": 20},
            },
        )

    client = JevClient(
        load_jev_settings(),
        api_key="stand-in-key",
        transport=httpx2.MockTransport(handler),
        backoff_seconds=0,
    )
    return client, sent


def practice(store, market, **changes):
    request = SimRequest(
        dataset=DATASET,
        variant="memory_off",
        kind="practice",
        first_step=97,
        last_step=192,
    )
    return create_sim(store, market, replace(request, **changes))


@pytest.fixture
def screening_market(market):
    return with_snapshots(market)


def test_every_asset_with_a_bar_is_screened_at_every_step(screening_market):
    store, jev_sent = InMemorySimStore(), None
    jev, jev_sent = fake_jev()
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    assert store.sim(sim_id)["STATUS"] == "finished"
    assert len(jev_sent) == SCREENS_ASKED
    decisions = store.rows("MEMORY.DECISIONS", sim_id)
    assert len([d for d in decisions if d["ASSET"] == CRYPTO]) == 96
    assert len([d for d in decisions if d["ASSET"] == STOCK]) == 26


def test_no_screen_is_asked_in_a_stocks_last_two_bars(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev()
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    by_step = {
        d["STEP"]: d
        for d in store.rows("MEMORY.DECISIONS", sim_id)
        if d["ASSET"] == STOCK
    }
    assert by_step[174]["TIER"] == 1
    for step in (175, 176):
        assert by_step[step]["TIER"] == 0
        assert by_step[step]["SCREEN_ANSWER"] is None
        assert by_step[step]["SKIPPED_BECAUSE"] == "session_end"


def test_no_screen_is_asked_once_the_daily_loss_limit_is_reached(screening_market):
    jev, sent = fake_jev()
    costs, risk = load_trading_costs(), load_risk_profile()
    broker = Broker(
        cash=10_000.0,
        asset_classes={CRYPTO: AssetClass.CRYPTO},
        costs=costs,
        stop_settings=load_stop_price_settings(),
        risk=risk,
        daily_loss_reached=True,
    )
    bar = Bar(100, 100.0, 100.0, 100.0, 100.0)
    broker.on_bar(CRYPTO, bar)
    agent = ScreeningAgent(1, DATASET, 192, screening_market, jev, Reading(costs, risk))

    rows = agent.on_step(100, broker, {CRYPTO: bar})

    assert sent == []
    [decision] = rows["MEMORY.DECISIONS"]
    assert (decision["TIER"], decision["SKIPPED_BECAUSE"]) == (0, "daily_loss")


@pytest.mark.parametrize("answer", [0.49, 0.5, 0.9])
def test_the_screens_number_is_stored_whatever_it_is_and_nothing_is_traded(
    screening_market, answer
):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: answer)
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    asked = [d for d in store.rows("MEMORY.DECISIONS", sim_id) if d["TIER"] == 1]
    assert {d["SCREEN_ANSWER"] for d in asked} == {answer}
    assert {d["JEV_VERSION"] for d in asked} == {"jev-1.14.0"}
    assert store.rows("SIM.ORDERS", sim_id) == []


def test_requests_and_answers_are_stored_word_for_word(screening_market):
    store = InMemorySimStore()
    jev, sent = fake_jev()
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    version = store.sim(sim_id)["SETTINGS"]["reading_version"]
    opening = store.readings[version]
    rows = sorted(
        store.rows("SIM.JEV_REQUESTS", sim_id), key=lambda r: (r["STEP"], r["ASSET"])
    )
    assert len(rows) == SCREENS_ASKED
    assert {r["READING_VERSION"] for r in rows} == {version}
    assert [opening + "\n\n" + r["BACKGROUND_AFTER_OPENING"] for r in rows] == [
        body["state"] for body in sent
    ]
    assert [r["QUESTIONS"] for r in rows] == [body["questions"] for body in sent]
    assert json.loads(rows[0]["ANSWER"])["answers"]["screen"]["noul"] == 0.3


def test_each_call_records_its_figures(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(tokens=1000)
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    calls = store.rows("SIM.CALLS", sim_id)
    assert len(calls) == SCREENS_ASKED
    call = calls[0]
    assert (call["SERVICE"], call["PURPOSE"], call["MODEL"]) == (
        "jev",
        "screen",
        "jev-1.14.0",
    )
    assert (call["TOKENS_IN"], call["TOKENS_OUT"], call["RETRIES"]) == (1000, 20, 0)
    assert call["COST_USD"] == pytest.approx(0.000042)
    assert call["LATENCY_SECONDS"] >= 0


def test_everything_sent_passes_the_masking_scan(screening_market):
    store = InMemorySimStore()
    jev, sent = fake_jev()
    run_sim(store, screening_market, practice(store, screening_market), jev=jev)

    real = real_values(prices=[187.44])
    for body in sent:
        assert_masked(json.dumps(body["questions"]), real)
        assert_masked(body["state"], real)


@pytest.mark.parametrize(
    "leak", ["AAPL rose.", "On 2025-03-10 it rose.", "It traded at $187.44."]
)
def test_the_scan_fails_when_a_real_value_reaches_jev(market, leak):
    leaky = with_snapshots(market, situation=leak)
    store = InMemorySimStore()
    jev, sent = fake_jev()
    run_sim(store, leaky, practice(store, leaky), jev=jev)

    with pytest.raises(MaskingLeak):
        assert_masked(sent[0]["state"], real_values(prices=[187.44]))


def test_the_same_sim_sends_the_same_requests_every_time(screening_market):
    first_store, second_store = InMemorySimStore(), InMemorySimStore()
    second_store.create({"STATUS": "finished"})  # so the second sim has another ID
    first_jev, first = fake_jev()
    second_jev, second = fake_jev()

    run_sim(
        first_store,
        screening_market,
        practice(first_store, screening_market),
        jev=first_jev,
    )
    run_sim(
        second_store,
        screening_market,
        practice(second_store, screening_market),
        jev=second_jev,
    )

    assert first == second


def test_a_call_failing_after_three_retries_stops_the_sim_and_it_can_resume(
    screening_market,
):
    store = InMemorySimStore()
    # The first screen works; the second call fails on its first try and all three retries.
    failing_jev, sent = fake_jev(lambda n: 429 if 2 <= n <= 5 else 0.3)
    sim_id = practice(store, screening_market)

    with pytest.raises(JevFailed, match="after 3 retries"):
        run_sim(store, screening_market, sim_id, jev=failing_jev)

    sim = store.sim(sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "Jev failed")
    assert "429" in sim["FAILURE_REASON"]
    assert sim["LAST_COMPLETED_STEP"] == 97
    assert len(sent) == 5

    working_jev, _ = fake_jev()
    run_sim(store, screening_market, sim_id, jev=working_jev)

    assert store.sim(sim_id)["STATUS"] == "finished"
    assert store.duplicate_ids(sim_id) == {}
    assert len(store.rows("SIM.CALLS", sim_id)) == SCREENS_ASKED


def test_a_practice_sim_stops_at_25_cents(screening_market):
    store = InMemorySimStore()
    # 2 million tokens a call at $0.042 per million: $0.084 a call, so the third reaches $0.25.
    jev, sent = fake_jev(tokens=2_000_000)
    sim_id = practice(store, screening_market)

    result = run_sim(store, screening_market, sim_id, jev=jev)

    sim = store.sim(sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "spending cap")
    assert sim["STOPPED_BY_CAP"] is True
    assert sim["SPENDING_CAP"] == 0.25
    assert result.stopped_by_cap
    assert len(sent) == 3
    assert [e["KIND"] for e in store.rows("SIM.SIM_EVENTS", sim_id)] == [
        "spending cap reached"
    ]
    with pytest.raises(ValueError, match="cap"):
        run_sim(store, screening_market, sim_id, jev=jev)


def test_a_practice_sim_is_at_most_one_replayed_day(screening_market):
    with pytest.raises(ValueError, match="one replayed day"):
        practice(InMemorySimStore(), screening_market, first_step=97, last_step=193)


def test_a_practice_sim_cannot_use_test_period_days(screening_market):
    with pytest.raises(ValueError, match="test period"):
        practice(InMemorySimStore(), screening_market, first_step=193, last_step=288)


def test_only_practice_sims_of_the_agent_are_built_so_far(screening_market):
    with pytest.raises(ValueError, match="practice"):
        practice(InMemorySimStore(), screening_market, kind="tuning")


def test_a_sim_of_the_agent_refuses_a_changed_wording(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev()
    sim_id = practice(store, screening_market)
    store.sims[sim_id]["SETTINGS"]["reading_version"] = "another"

    with pytest.raises(ValueError, match="reading version"):
        run_sim(store, screening_market, sim_id, jev=jev)
