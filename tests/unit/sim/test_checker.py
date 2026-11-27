"""The one checker, the cost estimate and the spending cap (spec appendix 8, sections 8.3, 8.5,
8.6 and 8.8; appendix 9, section 13).

Runs on the in-memory store and the made-up market of `conftest.py`: day 2 (steps 97 to 192) has
122 bars (96 crypto, 26 stock), day 3 (193 to 288) is the test period "rising market".
"""

from dataclasses import replace

import pytest

from jev_trader.jev.client import load_jev_settings
from jev_trader.llm.settings import load_call_settings, load_llm_settings
from jev_trader.sim.__main__ import main
from jev_trader.sim.checker import Refused, check_resume
from jev_trader.sim.runner import SimRequest, create_sim
from jev_trader.sim.spending import (
    SpendingSettings,
    load_spending_settings,
    spending_cap,
)
from jev_trader.sim.store import InMemorySimStore

DAY_2_BARS = 96 + 26
SETTINGS = SpendingSettings(
    ceiling_usd=75.0,
    most_sims_in_progress=4,
    cap_times_estimate=1.5,
    practice_cap_usd=0.25,
    default_tier_2_share=0.15,
    jev_tokens_per_request=3000,
    jev_requests_per_full_evaluation=2,
    llm_dollars_per_tier_2=0.0022,
    benchmark_cap_usd=1.5,
)
JEV_REQUEST = 3000 * load_jev_settings().dollars_per_million_tokens_read / 1e6


def request(**changes) -> SimRequest:
    """A practice sim of the agent without memory over day 2."""
    plain = SimRequest(
        dataset=7, variant="memory_off", kind="practice", first_step=97, last_step=192
    )
    return replace(plain, **changes)


def refusal_codes(store, market, sim_request, settings=SETTINGS) -> list[str]:
    with pytest.raises(Refused) as refused:
        create_sim(store, market, sim_request, settings)
    return [r.code for r in refused.value.refusals]


def sim_in_progress(store, *, variant="memory_off", status="running", cap=0.25):
    return store.create(
        {
            "DATASET": 7,
            "KIND": "practice",
            "VARIANT": variant,
            "FIRST_STEP": 97,
            "LAST_STEP": 192,
            "STATUS": status,
            "SPENDING_CAP": cap if variant != "buy_hold" else None,
        }
    )


def record_spending(store, sim_id, dollars):
    store.tables["SIM.CALLS"].append(
        {"ID": f"call-{dollars}", "SIM": sim_id, "COST_USD": dollars}
    )


# Refusal 1: test period days


@pytest.mark.parametrize("kind", ["practice", "tuning", "build-up", "free"])
def test_test_period_days_are_refused_to_any_sim_of_the_agent_but_a_measurement(
    market, kind
):
    sim_request = request(kind=kind, first_step=193, last_step=288)

    codes = refusal_codes(InMemorySimStore(), market, sim_request)

    assert "test_period_days" in codes


def test_the_test_period_refusal_says_which_days_and_what_to_do(market):
    with pytest.raises(Refused) as refused:
        create_sim(
            InMemorySimStore(), market, request(first_step=150, last_step=200), SETTINGS
        )

    [found] = [r for r in refused.value.refusals if r.code == "test_period_days"]
    assert '"rising market"' in found.problem and "193 to 288" in found.problem
    assert "192" in found.fix


def test_the_holding_sim_may_replay_test_period_days(market):
    store = InMemorySimStore()

    sim_id = create_sim(
        store, market, request(variant="buy_hold", kind="free", last_step=288), SETTINGS
    )

    assert store.sim(sim_id)["STATUS"] == "created"


# All refusals together


def test_every_refusal_comes_back_together_each_with_a_fix(make_market):
    market = make_market(status="being built")

    with pytest.raises(Refused) as refused:
        create_sim(
            InMemorySimStore(), market, request(first_step=193, last_step=288), SETTINGS
        )

    codes = [r.code for r in refused.value.refusals]
    assert codes == ["dataset_not_published", "test_period_days"]
    assert all(r.problem and r.fix for r in refused.value.refusals)
    assert "not published" in str(refused.value) and "test period" in str(refused.value)


def test_a_refused_sim_stores_nothing(market):
    store = InMemorySimStore()
    with pytest.raises(Refused):
        create_sim(store, market, request(first_step=193, last_step=288), SETTINGS)

    assert store.sims == {}


# Refusal 3: the ceiling


def test_a_cap_that_could_pass_the_ceiling_is_refused_saying_what_is_left(market):
    store = InMemorySimStore()
    # $0.60 paid outside any sim; a sim in progress has spent $0.05 of its $0.25 cap, so $0.20
    # more may still go. $0.85 is spoken for; a new $0.25 cap would reach $1.10.
    record_spending(store, None, 0.60)
    running = sim_in_progress(store, cap=0.25)
    record_spending(store, running, 0.05)

    with pytest.raises(Refused) as refused:
        create_sim(store, market, request(), replace(SETTINGS, ceiling_usd=1.0))

    [found] = refused.value.refusals
    assert found.code == "over_ceiling"
    assert "$1.10" in found.problem and "$1.00" in found.problem
    assert "$0.15 is left" in found.problem
    # A practice sim's cap cannot go below $0.25, so the only fix is to wait.
    assert found.fix.startswith("wait for a sim in progress to end")


@pytest.mark.parametrize(
    "changes, fix",
    [
        ({"kind": "tuning"}, "shorten the sim so its cap is $0.30 or less"),
        ({"spending_cap": 0.40}, "give a --spending-cap of $0.30 or less"),
    ],
)
def test_the_ceiling_fix_says_how_this_sims_cap_can_come_down(market, changes, fix):
    store = InMemorySimStore()
    record_spending(store, None, 0.70)

    with pytest.raises(Refused) as refused:
        # $0.30 is left under the $1.00 ceiling. A day's estimate is about $0.02; a multiple of
        # 30 makes the tuning sim's cap $0.60, so it too passes the ceiling.
        create_sim(
            store,
            market,
            request(**changes),
            replace(SETTINGS, ceiling_usd=1.0, cap_times_estimate=30.0),
        )

    [found] = [r for r in refused.value.refusals if r.code == "over_ceiling"]
    assert found.fix.startswith(fix)


def test_a_cap_that_fits_under_the_ceiling_is_allowed(market):
    store = InMemorySimStore()
    record_spending(store, None, 0.60)
    record_spending(store, sim_in_progress(store, cap=0.25), 0.05)

    create_sim(store, market, request(), replace(SETTINGS, ceiling_usd=1.10))

    assert len(store.sims) == 2


def test_sims_no_longer_in_progress_count_only_what_they_spent(market):
    store = InMemorySimStore()
    stopped = sim_in_progress(store, status="stopped", cap=0.50)
    record_spending(store, stopped, 0.10)

    create_sim(store, market, request(), replace(SETTINGS, ceiling_usd=0.35))

    assert len(store.sims) == 2


# Refusal 4: a fifth sim in progress


def test_a_fifth_sim_in_progress_is_refused_naming_the_four(market):
    store = InMemorySimStore()
    ids = [
        sim_in_progress(store, status=s)
        for s in ("running", "running", "created", "running")
    ]

    with pytest.raises(Refused) as refused:
        create_sim(store, market, request(), SETTINGS)

    [found] = refused.value.refusals
    assert found.code == "too_many_sims"
    for sim_id in ids:
        assert f"sim {sim_id} " in found.problem


def test_holding_sims_and_sims_not_in_progress_do_not_count_toward_the_four(market):
    store = InMemorySimStore()
    for _ in range(3):
        sim_in_progress(store)
    sim_in_progress(store, variant="buy_hold")
    sim_in_progress(store, status="stopped")
    sim_in_progress(store, status="finished")

    create_sim(store, market, request(), SETTINGS)


def test_a_holding_sim_is_not_refused_when_four_sims_are_in_progress(market):
    store = InMemorySimStore()
    for _ in range(4):
        sim_in_progress(store)

    create_sim(store, market, request(variant="buy_hold"), SETTINGS)


# The estimate and the cap


def test_with_no_practice_sim_yet_the_estimate_assumes_15_in_100_checks_get_a_closer_look(
    market,
):
    store = InMemorySimStore()

    sim = store.sim(create_sim(store, market, request(), SETTINGS))

    # 122 checks, each one Jev request; 15% of them (18.3) a full evaluation of 2 requests more.
    expected = DAY_2_BARS * JEV_REQUEST * (1 + 0.15 * 2)
    assert sim["ESTIMATED_COST"] == pytest.approx(expected)


def test_the_estimate_uses_the_latest_practice_sims_share_of_closer_looks(market):
    store = InMemorySimStore()
    older, latest = (
        sim_in_progress(store, status="finished"),
        sim_in_progress(store, status="finished"),
    )
    for sim_id, full_evaluations in ((older, 1), (latest, 2)):
        for n in range(10):
            kind = "full_evaluation" if n < full_evaluations else "screen"
            store.tables["MEMORY.DECISIONS"].append(
                {"ID": f"{sim_id}-{n}", "SIM": sim_id, "KIND": kind}
            )

    sim = store.sim(create_sim(store, market, request(), SETTINGS))

    assert sim["ESTIMATED_COST"] == pytest.approx(
        DAY_2_BARS * JEV_REQUEST * (1 + 0.2 * 2)
    )


@pytest.mark.parametrize("kind", ["tuning", "build-up", "measurement", "free"])
def test_a_sim_other_than_practice_gets_a_cap_of_one_and_a_half_times_its_estimate(
    kind,
):
    # The spec's example: an estimate of $3.00 gives a cap of $4.50.
    assert spending_cap("memory_on", kind, 3.00, None, SETTINGS) == 4.50


def test_a_practice_sims_cap_is_25_cents_unless_the_developer_raises_it(market):
    store = InMemorySimStore()

    plain = store.sim(create_sim(store, market, request(), SETTINGS))
    raised = store.sim(create_sim(store, market, request(spending_cap=0.40), SETTINGS))

    assert (plain["SPENDING_CAP"], raised["SPENDING_CAP"]) == (0.25, 0.40)


@pytest.mark.parametrize("given", [0.25, 0.10, 0.0])
def test_a_practice_sims_cap_can_only_be_raised(market, given):
    codes = refusal_codes(InMemorySimStore(), market, request(spending_cap=given))

    assert codes == ["cap_not_raised"]


def test_the_holding_sim_has_no_estimate_and_no_cap(market):
    store = InMemorySimStore()

    sim = store.sim(create_sim(store, market, request(variant="buy_hold"), SETTINGS))

    assert (sim["ESTIMATED_COST"], sim["SPENDING_CAP"]) == (0.0, None)


def test_the_ceiling_is_read_from_config():
    assert load_spending_settings().ceiling_usd == 75.0


# Resuming a stopped sim


def test_resuming_a_sim_is_refused_when_the_others_already_fill_the_limit():
    store = InMemorySimStore()
    stopped = sim_in_progress(store, status="stopped")
    for _ in range(4):
        sim_in_progress(store)

    [found] = check_resume(store.sim(stopped), store, SETTINGS)

    assert found.code == "too_many_sims"
    assert f"sim {stopped} " not in found.problem


def test_a_sim_left_running_when_killed_does_not_count_against_its_own_resume():
    store = InMemorySimStore()
    killed = sim_in_progress(store)
    for _ in range(3):
        sim_in_progress(store)

    assert check_resume(store.sim(killed), store, SETTINGS) == []


def test_resuming_counts_only_what_is_left_under_the_sims_own_cap():
    store = InMemorySimStore()
    stopped = sim_in_progress(store, status="stopped", cap=0.25)
    record_spending(store, stopped, 0.20)
    # $0.20 paid and $0.05 left under its cap: $0.25 at most, within a $0.25 ceiling, not
    # within $0.24.
    assert (
        check_resume(store.sim(stopped), store, replace(SETTINGS, ceiling_usd=0.25))
        == []
    )
    [found] = check_resume(
        store.sim(stopped), store, replace(SETTINGS, ceiling_usd=0.24)
    )
    assert found.code == "over_ceiling"


# The agent with memory

LLM_KEY = load_call_settings(load_llm_settings().provider).key_variable


@pytest.mark.parametrize("kind", ["tuning", "build-up", "free", "measurement"])
def test_only_practice_sims_of_the_agent_with_memory_are_built(
    market, monkeypatch, kind
):
    monkeypatch.setenv(LLM_KEY, "made-up")
    sim_request = request(variant="memory_on", kind=kind)

    assert "not_built" in refusal_codes(InMemorySimStore(), market, sim_request)


def test_a_sim_with_memory_is_refused_while_its_llm_has_no_key(market, monkeypatch):
    monkeypatch.delenv(LLM_KEY, raising=False)

    with pytest.raises(Refused) as refused:
        create_sim(InMemorySimStore(), market, request(variant="memory_on"), SETTINGS)

    [missing] = [r for r in refused.value.refusals if r.code == "llm_key_missing"]
    assert LLM_KEY in missing.problem
    assert missing.fix == f"set {LLM_KEY} in .env"


def test_a_sim_without_memory_needs_no_llm_key(market, monkeypatch):
    monkeypatch.delenv(LLM_KEY, raising=False)

    assert create_sim(InMemorySimStore(), market, request(), SETTINGS)


def test_resuming_a_sim_with_memory_is_refused_while_its_llm_has_no_key(monkeypatch):
    store = InMemorySimStore()
    stopped = sim_in_progress(store, variant="memory_on", status="stopped")
    store.sims[stopped]["SETTINGS"] = {"llm": {"model": load_llm_settings().model}}
    monkeypatch.delenv(LLM_KEY, raising=False)

    codes = [r.code for r in check_resume(store.sim(stopped), store, SETTINGS)]

    assert codes == ["llm_key_missing"]
    monkeypatch.setenv(LLM_KEY, "made-up")
    assert check_resume(store.sim(stopped), store, SETTINGS) == []


# The sim command


@pytest.fixture
def command(monkeypatch, market):
    """The sim command on the in-memory store and market, with no Snowflake."""
    store = InMemorySimStore()

    class NoDatabase:
        def sim_store(self):
            return store

        def market(self):
            return market

        def close(self):
            pass

    monkeypatch.setattr(
        "jev_trader.sim.__main__.open_database", lambda *a, **k: NoDatabase()
    )
    return store


def test_the_sim_command_prints_each_refusal_with_its_fix(command, capsys):
    for _ in range(4):
        sim_in_progress(command)

    code = main(
        [
            "start",
            "--dataset",
            "7",
            "--first-step",
            "193",
            "--last-step",
            "288",
            "--kind",
            "free",
            "--variant",
            "memory_off",
        ]
    )

    printed = capsys.readouterr().out
    assert code == 2
    assert "Refused:" in printed
    assert "test period" in printed
    assert "sims in progress" in printed
    assert "Fix:" in printed
    assert len(command.sims) == 4


def test_the_sim_command_refuses_a_cap_that_could_pass_the_ceiling(command, capsys):
    ceiling = load_spending_settings().ceiling_usd
    record_spending(command, None, ceiling - 0.10)

    code = main(
        [
            "start",
            "--dataset",
            "7",
            "--first-step",
            "97",
            "--last-step",
            "192",
            "--variant",
            "memory_off",
        ]
    )

    printed = capsys.readouterr().out
    assert code == 2
    assert f"past the ${ceiling:.2f} ceiling" in printed
    assert "$0.10 is left" in printed
    assert "Fix: wait for a sim in progress to end" in printed
    assert command.sims == {}


def test_the_sim_command_refuses_to_resume_a_fifth_sim(command, capsys):
    stopped = sim_in_progress(command, status="stopped")
    for _ in range(4):
        sim_in_progress(command)

    code = main(["resume", str(stopped)])

    printed = capsys.readouterr().out
    assert code == 2
    assert "sims in progress" in printed
    assert command.sim(stopped)["STATUS"] == "stopped"
