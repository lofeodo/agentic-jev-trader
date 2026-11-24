"""The agent without memory: a practice sim that screens every asset at every step, and on a yes
runs the full evaluation, which can place a trade.

Runs on the in-memory store and the made-up market of `conftest.py`, with hand-written fake
answers from Jev. Day 2 is steps 97 to 192: the crypto has 96 bars, the stock 26 (151 to 176).
Prices sit at 100 and the typical move is $0.50, so the stop prices are 0.5%, 1% and 1.5% away.
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
from jev_trader.sim.__main__ import screen_report
from jev_trader.sim.agent import AgentWithoutMemory
from jev_trader.sim.market import InMemoryMarket, Snapshot
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import InMemorySimStore, SimulatedKill

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


def choice_answer(criteria: dict, probabilities: dict) -> dict:
    given = {name: probabilities.get(name, 0.0) for name in criteria}
    return {
        "type": "choice",
        "choice": max(given, key=given.get),
        "confidence": 0.5,
        "probabilities": given,
    }


RATING = {
    "type": "score",
    "score": 2.7,
    "confidence": 0.4,
    "legend": {str(n): "level" for n in range(5)},
    "probabilities": {"0": 0.05, "1": 0.1, "2": 0.1, "3": 0.65, "4": 0.1},
}


def fake_jev(answer=lambda n: 0.3, tokens=1000, pick=None, size=None):
    """A client over fake answers; `sent` holds each request body as Jev received it.

    `answer(n)` is the answer to the n-th screen request, retries counted (an int is an error
    status, and then fails the pick or size request that follows it too). The
    pick and the size are answered with the probabilities given by option name: by default
    no trade, and all on the second smallest size. `pick` may also be a function of the
    pick request's number (1 for the first).
    """
    sent = []
    pick = pick or {"no_trade": 1.0}
    size = size or {"size_40_percent": 1.0}

    def pick_for_this_request():
        if not callable(pick):
            return pick
        return pick(sum(1 for b in sent if "pick_1" in b["questions"]))

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        result = answer(sum(1 for b in sent if "screen" in b["questions"]))
        if isinstance(result, int):
            return httpx2.Response(result, json={"error": "made-up failure"})
        answers = {}
        for name, question in body["questions"].items():
            if question["type"] == "noul":
                answers[name] = {"type": "noul", "noul": result}
            elif question["type"] == "score":
                answers[name] = RATING
            else:
                given = pick_for_this_request() if name.startswith("pick") else size
                answers[name] = choice_answer(question["criteria"], given)
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": answers,
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
    agent = AgentWithoutMemory(
        1,
        DATASET,
        192,
        screening_market,
        jev,
        Reading(costs, risk),
        load_stop_price_settings(),
        random_seed=0,
    )

    rows = agent.on_step(100, broker, {CRYPTO: bar})

    assert sent == []
    [decision] = rows["MEMORY.DECISIONS"]
    assert (decision["TIER"], decision["SKIPPED_BECAUSE"]) == (0, "daily_loss")


@pytest.mark.parametrize("answer", [0.49, 0.5, 0.9])
def test_the_screens_number_is_stored_whatever_it_is(screening_market, answer):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: answer)
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    asked = [d for d in store.rows("MEMORY.DECISIONS", sim_id) if d["TIER"] >= 1]
    assert len(asked) == SCREENS_ASKED
    assert {d["SCREEN_ANSWER"] for d in asked} == {answer}
    assert {d["JEV_VERSION"] for d in asked} == {"jev-1.14.0"}


def test_below_the_cut_off_nothing_more_is_asked(screening_market):
    store = InMemorySimStore()
    jev, sent = fake_jev(lambda n: 0.49)
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    assert {d["TIER"] for d in store.rows("MEMORY.DECISIONS", sim_id)} == {0, 1}
    assert all(list(body["questions"]) == ["screen"] for body in sent)
    assert store.rows("SIM.ORDERS", sim_id) == []


# The full evaluation (spec appendix 4, sections 3.1 and 5)


def decisions_at(store, sim_id, step):
    return {
        d["ASSET"]: d
        for d in store.rows("MEMORY.DECISIONS", sim_id)
        if d["STEP"] == step
    }


def test_a_full_evaluation_ending_in_no_trade_is_stored_as_an_episode(
    screening_market,
):
    store = InMemorySimStore()
    jev, sent = fake_jev(lambda n: 0.9)
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    decision = decisions_at(store, sim_id, 97)[CRYPTO]
    assert (decision["KIND"], decision["TIER"]) == ("full_evaluation", 2)
    assert (decision["PICK"], decision["ACTION"]) == ("no_trade", "nothing")
    assert len(decision["CANDIDATE_TRADES"]) == 6
    assert set(decision["ANSWERS"]) == {f"pick_{n}" for n in range(1, 6)}
    assert decision["SIZE_CHOSEN"] is None
    # A screen, then the pick: no size is asked after no trade.
    assert [next(iter(b["questions"])) for b in sent[:2]] == ["screen", "pick_1"]
    assert store.rows("SIM.ORDERS", sim_id) == []


def test_a_yes_and_a_long_pick_place_an_order_of_jevs_size(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(
        lambda n: 0.9,
        pick={"long_tight_stop": 0.5, "long_medium_stop": 0.2, "no_trade": 0.3},
        size={"size_20_percent": 0.5, "size_40_percent": 0.5},
    )
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    decision = decisions_at(store, sim_id, 97)[CRYPTO]
    assert (decision["PICK"], decision["ACTION"]) == ("long_tight_stop", "entry")
    # Half on $2,000 and half on $4,000 of a $10,000 account.
    assert decision["SIZE_CHOSEN"] == pytest.approx(3000)
    assert decision["SIZE_AFTER_TRIMMING"] == pytest.approx(3000)
    assert decision["LIMITED_BY"] is None
    assert decision["RATING"] == 2.7
    assert set(decision["ANSWERS"]) == {
        *(f"pick_{n}" for n in range(1, 6)),
        "size_small_first",
        "size_large_first",
        "rating",
    }
    orders = store.rows("SIM.ORDERS", sim_id)
    [entry] = [o for o in orders if o["DECISION"] == decision["ID"]]
    assert entry["KIND"] == "entry"
    assert (entry["STATUS"], entry["STEP_DECIDED"], entry["STEP_CARRIED_OUT"]) == (
        "carried out",
        97,
        98,
    )
    assert entry["AMOUNT_CHOSEN"] == pytest.approx(3000)
    # The position is held by code alone until the sim's last step closes it.
    [close] = [
        o for o in orders if o["KIND"] == "close" and o["POSITION"] == entry["POSITION"]
    ]
    assert (close["REASON"], close["DECISION"]) == ("sim_ended", None)


def test_code_trims_a_size_above_the_trade_risk_limit(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(
        lambda n: 0.9,
        pick={"short_wide_stop": 1.0},
        size={"size_200_percent": 1.0},
    )
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    decision = decisions_at(store, sim_id, 97)[CRYPTO]
    assert decision["PICK"] == "short_wide_stop"
    assert decision["SIZE_CHOSEN"] == pytest.approx(20_000)
    # A stop price 1.5% away loses $100, 1% of the account, on about $6,667.
    assert decision["SIZE_AFTER_TRIMMING"] == pytest.approx(10_000 / 1.5)
    assert decision["LIMITED_BY"] == "trade_risk"


def test_the_decision_trails_stages_are_stored(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9, pick={"long_tight_stop": 1.0})
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    decision = decisions_at(store, sim_id, 97)[CRYPTO]
    requests = [
        r
        for r in store.rows("SIM.JEV_REQUESTS", sim_id)
        if r["DECISION"] == decision["ID"]
    ]
    calls = [
        r for r in store.rows("SIM.CALLS", sim_id) if r["DECISION"] == decision["ID"]
    ]
    assert [r["PURPOSE"] for r in requests] == ["screen", "pick", "size"]
    assert [c["PURPOSE"] for c in calls] == ["screen", "pick", "size"]
    assert decision["SCREEN_ANSWER"] == 0.9  # screen
    assert decision["PICK"] == "long_tight_stop"  # pick
    assert decision["SIZE_CHOSEN"] is not None  # size
    assert "SIZE_AFTER_TRIMMING" in decision and "LIMITED_BY" in decision  # limits
    orders = [
        o for o in store.rows("SIM.ORDERS", sim_id) if o["DECISION"] == decision["ID"]
    ]
    assert [o["KIND"] for o in orders] == ["entry"]  # order
    assert requests[2]["BACKGROUND_AFTER_OPENING"].endswith(
        "# The trade picked\nLong, tight stop price: buy at the next bar's open, about "
        "$100.00. Code sells if the price falls to $99.50, 0.5% below."
    )


def test_an_asset_with_an_open_position_is_left_to_code(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9, pick={"long_tight_stop": 1.0})
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    crypto = [d for d in store.rows("MEMORY.DECISIONS", sim_id) if d["ASSET"] == CRYPTO]
    # Step 97 opens it (carried out at 98); open positions are reviewed from ticket #100 on.
    assert [d["STEP"] for d in crypto] == [97]


def test_other_assets_see_the_open_position(screening_market):
    store = InMemorySimStore()
    jev, sent = fake_jev(
        lambda n: 0.9,
        pick={"long_tight_stop": 1.0},
        size={"size_40_percent": 1.0},
    )
    sim_id = practice(store, screening_market)

    run_sim(store, screening_market, sim_id, jev=jev)

    stock_screen = next(
        b["state"]
        for b in sent
        if "screen" in b["questions"] and "# The asset: ASSET_01" in b["state"]
    )
    # $4,000 bought at $100.05 (slippage) plus a $4 fee is worth $3,998 at $100. Sold now at
    # $99.95 for $3,996 less a $4 fee: -$12 in all. Bars 99 to 151 came since step 98's entry.
    assert (
        "# Open positions\nASSET_02 (crypto): long, $3,998, opened 53 bars ago, "
        "now -$12 (-0.3%) after trading costs." in stock_screen
    )
    assert "Open positions: 1, worth $3,998." in stock_screen


def test_the_order_of_jevs_options_comes_from_the_random_seed(screening_market):
    orders = {}
    for seed in (0, 1):
        store = InMemorySimStore()
        jev, sent = fake_jev(lambda n: 0.9)
        run_sim(
            store,
            screening_market,
            practice(store, screening_market, random_seed=seed),
            jev=jev,
        )
        pick = next(b["questions"] for b in sent if "pick_1" in b["questions"])
        copies = [list(pick[f"pick_{n}"]["criteria"]) for n in range(1, 6)]
        assert all(len(set(c)) == 7 for c in copies)
        orders[seed] = copies
    assert orders[0] != orders[1]


def test_a_sim_killed_with_positions_open_resumes_to_the_same_records(
    screening_market,
):
    def opening_trades():
        # Only the first screen says yes: the crypto opens at step 98, and the stock's screens
        # from step 151 on show it among the open positions.
        yes_once = fake_jev(
            lambda n: 0.9 if n == 1 else 0.3, pick={"long_tight_stop": 1.0}
        )
        return yes_once[0]

    expected = InMemorySimStore()
    run_sim(
        expected,
        screening_market,
        practice(expected, screening_market),
        jev=opening_trades(),
    )
    store = InMemorySimStore()
    sim_id = practice(store, screening_market)
    store.kill_on_write(60)  # the write of step 156, redone after the restart
    with pytest.raises(SimulatedKill):
        run_sim(store, screening_market, sim_id, jev=opening_trades())

    # The crypto is open by then, so the resumed sim's screens all say no, as before the kill.
    run_sim(store, screening_market, sim_id, jev=fake_jev()[0])

    compared = ("SIM.JEV_REQUESTS", "MEMORY.DECISIONS", "SIM.ORDERS")
    got, want = store.all_rows(sim_id), expected.all_rows(sim_id)
    assert {t: got[t] for t in compared} == {t: want[t] for t in compared}
    assert any(
        "opened 58 bars ago" in r["BACKGROUND_AFTER_OPENING"]
        for r in got["SIM.JEV_REQUESTS"]
    )


def test_a_malformed_pick_answer_stops_the_sim(screening_market):
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9, pick={"no_trade": 1.5})
    sim_id = practice(store, screening_market)

    with pytest.raises(JevFailed, match="pick_1"):
        run_sim(store, screening_market, sim_id, jev=jev)


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


def test_the_scan_fails_when_an_unscaled_bar_reaches_jev(market):
    real_price = 523.18
    market.bars_by_asset[DATASET][CRYPTO] = [
        Bar(b.step, real_price, real_price, real_price, real_price)
        for b in market.bars_by_asset[DATASET][CRYPTO]
    ]
    unmasked = with_snapshots(market)
    store = InMemorySimStore()
    jev, sent = fake_jev()
    run_sim(store, unmasked, practice(store, unmasked), jev=jev)

    with pytest.raises(MaskingLeak, match="unscaled price"):
        assert_masked(sent[0]["state"], real_values(prices=[real_price]))


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


def test_the_practice_sim_reports_its_share_of_yes_answers(screening_market):
    store = InMemorySimStore()
    # One screen in three says yes: 40 of the 120 asked, 33.3%, above the 30% rule.
    jev, _ = fake_jev(lambda n: 0.5 if n % 3 == 0 else 0.49)
    sim_id = practice(store, screening_market)
    run_sim(store, screening_market, sim_id, jev=jev)

    lines = screen_report(store, store.sim(sim_id))

    assert lines[0] == "Screens: 120 asked, 40 said yes (33.3%)."
    assert "30%" in lines[1]


def test_the_practice_sim_reports_its_full_evaluations_and_trades_opened(
    screening_market,
):
    store = InMemorySimStore()
    # Every screen says yes. The first pick (the crypto, step 97) opens a long, so the crypto is
    # not screened again; the second (the stock, step 151) is no trade; the third (step 152)
    # opens a short in the stock, which is then not screened again.
    picks = [{"long_tight_stop": 1.0}, {"no_trade": 1.0}, {"short_tight_stop": 1.0}]
    jev, _ = fake_jev(lambda n: 0.9, pick=lambda n: picks[n - 1])
    sim_id = practice(store, screening_market)
    run_sim(store, screening_market, sim_id, jev=jev)

    lines = screen_report(store, store.sim(sim_id))

    assert lines[0] == "Screens: 3 asked, 3 said yes (100.0%)."
    assert "Full evaluations: 3, trades opened: 2." in lines


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
