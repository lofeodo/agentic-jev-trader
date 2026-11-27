"""Starting from a memory: the base memory copy and the memory-date rule (spec appendix 5,
section 2; appendix 6, sections 6 and 7; appendix 8, section 8.6 refusal 2; appendix 10, section
13; ADR 0007).

A memory is the records a sim left behind: its decisions (episodes) and their outcomes. Every
sim with memory starts from its own copy of one, by default the base memory (what the build-up
sim left). Runs on the in-memory store and the made-up market of `conftest.py`: day 2 is steps 97
to 192, day 3 (193 to 288) the test period.

A sim with memory needs its LLM's key, so the tests set a made-up one.
"""

import pytest

from jev_trader.api.store import InMemoryApiStore
from jev_trader.llm.settings import load_call_settings, load_llm_settings
from jev_trader.sim.__main__ import main, open_memory
from jev_trader.sim.checker import Refused
from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import MEMORY_TABLES, InMemorySimStore, SimulatedKill


@pytest.fixture(autouse=True)
def llm_key(monkeypatch):
    monkeypatch.setenv(
        load_call_settings(load_llm_settings().provider).key_variable, "made-up"
    )


def left_memory(
    store,
    *,
    kind="build-up",
    variant="memory_off",
    status="finished",
    dataset=7,
    first_step=97,
    last_step=144,
    decided_at=(100, 120),
    known_from=None,
):
    """A sim that left a memory: one decision at each of `decided_at`, each with an outcome
    known 4 steps later (or at `known_from`)."""
    sim_id = store.create(
        {
            "DATASET": dataset,
            "KIND": kind,
            "VARIANT": variant,
            "FIRST_STEP": first_step,
            "LAST_STEP": last_step,
            "STATUS": status,
        }
    )
    for step in decided_at:
        decision = f"{sim_id}-{step}-ASSET_02"
        known = known_from or step + 4
        store.tables["MEMORY.DECISIONS"].append(
            {
                "ID": decision,
                "SIM": sim_id,
                "FIRST_WRITTEN_BY": sim_id,
                "DATASET": dataset,
                "ASSET": "ASSET_02",
                "STEP": step,
                "KIND": "full_evaluation",
                "ACTION": "nothing",
                "SCREEN_ANSWER": 0.9,
                "OUTCOMES_KNOWN_FROM": known,
            }
        )
        store.tables["MEMORY.OUTCOMES"].append(
            {
                "ID": f"{decision}-price_after_4_bars",
                "SIM": sim_id,
                "FIRST_WRITTEN_BY": sim_id,
                "DECISION": decision,
                "KIND": "price_after_4_bars",
                "VALUE": {"price": 100.0, "change": 0.0},
                "KNOWN_FROM": known,
            }
        )
    return sim_id


def with_memory(**changes) -> SimRequest:
    """A practice sim with memory over the second half of day 2."""
    return SimRequest(
        **{
            "dataset": 7,
            "variant": "memory_on",
            "kind": "practice",
            "first_step": 145,
            "last_step": 192,
            **changes,
        }
    )


def refusal_codes(store, market, sim_request) -> list[str]:
    with pytest.raises(Refused) as refused:
        create_sim(store, market, sim_request)
    return [r.code for r in refused.value.refusals]


# The memory-date rule


def test_a_memory_with_a_record_at_the_sims_first_step_is_refused(market):
    store = InMemorySimStore()
    source = left_memory(store, last_step=96 + 20, decided_at=(100,), known_from=145)

    with pytest.raises(Refused) as refused:
        create_sim(store, market, with_memory(memory_from=source))

    [refusal] = refused.value.refusals
    assert refusal.code == "memory_from_the_future"
    assert "step 145" in refusal.problem
    assert "after step 145" in refusal.fix


def test_a_memory_recorded_wholly_before_the_first_step_is_allowed(market):
    store = InMemorySimStore()
    source = left_memory(store, decided_at=(100, 120), known_from=144)

    sim_id = create_sim(store, market, with_memory(memory_from=source))

    assert store.sim(sim_id)["MEMORY_FROM_SIM"] == source


def test_a_sim_still_running_its_memory_is_refused(market):
    store = InMemorySimStore()
    source = left_memory(store, kind="practice", status="running")

    assert refusal_codes(store, market, with_memory(memory_from=source)) == [
        "memory_not_finished"
    ]


def test_a_sim_ending_at_or_after_the_first_step_is_refused(market):
    store = InMemorySimStore()
    source = left_memory(store, last_step=145)

    assert refusal_codes(store, market, with_memory(memory_from=source)) == [
        "memory_ends_too_late"
    ]


def test_a_memory_from_another_dataset_is_refused(market):
    store = InMemorySimStore()
    source = left_memory(store, kind="practice", dataset=8)

    assert refusal_codes(store, market, with_memory(memory_from=source)) == [
        "memory_other_dataset"
    ]


def test_an_unknown_memory_is_refused(market):
    assert refusal_codes(InMemorySimStore(), market, with_memory(memory_from=42)) == [
        "memory_not_found"
    ]


# Which memory a sim starts from


def test_a_sim_with_memory_starts_from_the_base_memory_by_default(market):
    store = InMemorySimStore()
    left_memory(store)  # an older build-up sim
    base = left_memory(store)
    left_memory(store, status="failed")
    left_memory(store, kind="practice")

    sim_id = create_sim(store, market, with_memory())

    assert store.sim(sim_id)["MEMORY_FROM_SIM"] == base


def test_a_sim_with_memory_is_refused_while_there_is_no_base_memory(market):
    store = InMemorySimStore()
    left_memory(store, kind="practice")

    assert refusal_codes(store, market, with_memory()) == ["no_base_memory"]


def test_the_rehearsal_starts_a_practice_sim_from_its_first_sims_memory(market):
    store = InMemorySimStore()
    first_day = left_memory(store, kind="practice")

    sim_id = create_sim(store, market, with_memory(memory_from=first_day))

    assert store.sim(sim_id)["MEMORY_FROM_SIM"] == first_day


@pytest.mark.parametrize("kind", ["free", "build-up", "tuning"])
def test_only_a_practice_sim_starts_from_a_memory_other_than_the_base_memory(
    market, kind
):
    store = InMemorySimStore()
    practice = left_memory(store, kind="practice")

    codes = refusal_codes(store, market, with_memory(kind=kind, memory_from=practice))

    assert "not_base_memory" in codes


def test_a_sim_that_counts_is_refused_an_older_build_up_sims_memory(market):
    store = InMemorySimStore()
    older = left_memory(store)
    left_memory(store)  # the base memory

    codes = refusal_codes(store, market, with_memory(kind="free", memory_from=older))

    assert "not_base_memory" in codes


@pytest.mark.parametrize(
    "kind, variant",
    [("practice", "buy_hold"), ("practice", "memory_on"), ("free", "memory_on")],
)
def test_a_practice_sim_starts_only_from_a_rehearsal_memory_or_the_base_memory(
    market, kind, variant
):
    store = InMemorySimStore()
    other = left_memory(store, kind=kind, variant=variant)

    codes = refusal_codes(store, market, with_memory(memory_from=other))

    assert codes == ["not_rehearsal_memory"]


def test_a_practice_sim_may_start_from_the_base_memory(market):
    store = InMemorySimStore()
    base = left_memory(store)

    sim_id = create_sim(store, market, with_memory(memory_from=base))

    assert store.sim(sim_id)["MEMORY_FROM_SIM"] == base


@pytest.mark.parametrize("variant", ["memory_off", "buy_hold"])
def test_a_sim_that_reads_no_memory_is_refused_a_memory_to_start_from(market, variant):
    store = InMemorySimStore()
    source = left_memory(store)

    codes = refusal_codes(
        store, market, with_memory(variant=variant, memory_from=source)
    )

    assert codes == ["reads_no_memory"]


def test_a_sim_without_memory_starts_from_none(market):
    store = InMemorySimStore()
    left_memory(store)

    sim_id = create_sim(store, market, with_memory(variant="memory_off"))

    assert store.sim(sim_id)["MEMORY_FROM_SIM"] is None


# The copy, made when the sim first starts


def started_from(store, market, source, first_step=145):
    """A sim whose row names `source`'s memory. The agent with memory cannot run yet, so a
    holding sim (which calls nothing paid) stands in: the copy does not depend on the variant."""
    sim_id = create_sim(
        store,
        market,
        SimRequest(
            dataset=7,
            variant="buy_hold",
            kind="practice",
            first_step=first_step,
            last_step=192,
        ),
    )
    store.sims[sim_id]["MEMORY_FROM_SIM"] = source
    return sim_id


def test_a_sim_starts_with_every_record_of_its_memory_under_its_original_id(market):
    store = InMemorySimStore()
    source = left_memory(store)
    sim_id = started_from(store, market, source)

    run_sim(store, market, sim_id, steps_per_write=96)

    for table in MEMORY_TABLES:
        copied = store.rows(table, sim_id)
        assert [{**r, "SIM": source} for r in copied] == store.rows(table, source)
        assert {r["FIRST_WRITTEN_BY"] for r in copied} == {source}
    assert store.sim(sim_id)["STATUS"] == "finished"


def test_the_memory_it_copied_from_is_left_as_it_was(market):
    store = InMemorySimStore()
    source = left_memory(store)
    before = {t: store.rows(t, source) for t in MEMORY_TABLES}

    run_sim(store, market, started_from(store, market, source), steps_per_write=96)

    assert {t: store.rows(t, source) for t in MEMORY_TABLES} == before


def test_a_sim_killed_before_its_first_step_is_stored_is_copied_again_not_twice(
    market,
):
    store = InMemorySimStore()
    source = left_memory(store)
    sim_id = started_from(store, market, source)
    store.kill_on_write(1)
    with pytest.raises(SimulatedKill):
        run_sim(store, market, sim_id, steps_per_write=96)

    run_sim(store, market, sim_id, steps_per_write=96)

    assert len(store.rows("MEMORY.DECISIONS", sim_id)) == 2
    assert store.duplicate_ids(sim_id) == {}


def test_the_job_checks_the_memory_again_before_copying_it(market):
    store = InMemorySimStore()
    source = left_memory(store)
    sim_id = started_from(store, market, source)
    store.sims[source]["STATUS"] = "running"  # changed since the sim was created

    with pytest.raises(Refused, match="not finished"):
        run_sim(store, market, sim_id, steps_per_write=96)

    assert store.rows("MEMORY.DECISIONS", sim_id) == []
    assert store.sim(sim_id)["STATUS"] == "created"


# A sim's own records, apart from the ones it copied


def test_a_sims_report_counts_only_the_decisions_it_made(market):
    store = InMemorySimStore()
    source = left_memory(store, kind="practice")
    sim_id = started_from(store, market, source)  # a holding sim decides nothing
    run_sim(store, market, sim_id, steps_per_write=96)

    assert store.full_evaluation_counts(source) == (2, 0)
    assert store.full_evaluation_counts(sim_id) == (0, 0)
    assert store.screen_counts(sim_id, 0.5) == (0, 0)
    assert store.latest_tier_2_share() == 1.0  # the source's, not the copy's


def test_the_sim_page_lists_only_the_decisions_the_sim_made(market):
    store = InMemorySimStore()
    source = left_memory(store, kind="practice")
    sim_id = started_from(store, market, source)
    run_sim(store, market, sim_id, steps_per_write=96)
    api = InMemoryApiStore(store, asset_key=[])

    assert api.decisions(sim_id) == []
    assert api.latest_decisions(sim_id, 10) == []
    assert len(api.decisions(source)) == 2


# The sim command


@pytest.fixture
def command(monkeypatch, market):
    """The sim command on the in-memory store and market, with no Snowflake, no Jev and no
    memory server; it creates the sim and runs no step."""
    store = InMemorySimStore()

    class Nothing:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

        def lookups_at(self, context):
            raise AssertionError("no step runs")

    def runs_no_step(*args, **kwargs):
        raise ValueError("the test runs no step")

    class NoDatabase(Nothing):
        def sim_store(self):
            return store

        def market(self):
            return market

    monkeypatch.setattr("jev_trader.sim.__main__.open_database", NoDatabase)
    monkeypatch.setattr("jev_trader.sim.__main__.JevClient", Nothing)
    monkeypatch.setattr("jev_trader.sim.__main__.open_memory", Nothing)
    monkeypatch.setattr("jev_trader.sim.__main__.run_sim", runs_no_step)
    return store


def test_the_command_starts_a_practice_sim_from_the_rehearsals_first_sims_memory(
    command, capsys
):
    first_day = left_memory(
        command, kind="practice", first_step=1, last_step=96, decided_at=(50, 60)
    )

    main(
        ["practice", "--dataset", "7", "--first-step", "97"]
        + ["--memory-from", str(first_day)]
    )

    [sim] = [s for s in command.sims.values() if s["ID"] != first_day]
    assert (sim["KIND"], sim["VARIANT"], sim["MEMORY_FROM_SIM"]) == (
        "practice",
        "memory_on",
        first_day,
    )
    assert f"from a copy of sim {first_day}'s memory" in capsys.readouterr().out


def test_the_command_prints_why_a_memory_is_refused(command, capsys):
    first_day = left_memory(command, kind="practice", decided_at=(100,))

    code = main(
        ["practice", "--dataset", "7", "--first-step", "97"]
        + ["--memory-from", str(first_day)]
    )

    printed = capsys.readouterr().out
    assert code == 2
    assert "the agent would remember its own future" in printed
    assert "Fix: start this sim after step" in printed


def test_the_command_refuses_a_sim_with_memory_while_the_memory_server_is_down(
    command, capsys, monkeypatch
):
    class Down:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise ConnectionError("made-up: nothing listens")

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr("jev_trader.sim.__main__.open_memory", open_memory)
    monkeypatch.setattr("jev_trader.sim.__main__.Connection", Down)
    first_day = left_memory(
        command, kind="practice", first_step=1, last_step=96, decided_at=(50, 60)
    )

    code = main(
        ["practice", "--dataset", "7", "--first-step", "97"]
        + ["--memory-from", str(first_day)]
    )

    printed = capsys.readouterr().out
    assert code == 2
    assert "the memory server at http://127.0.0.1:8765 did not answer" in printed
    assert "python -m jev_trader.memory serve" in printed
    assert list(command.sims) == [first_day]  # no sim row left behind
