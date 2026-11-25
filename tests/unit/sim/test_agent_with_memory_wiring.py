"""The agent with memory's frame, wired end to end with stand-ins (the slice's skeleton): a full
evaluation runs memory's first search and the stand-in selection (which selects none), reaches
Jev, and stores its decision record. What the LLM and the background do with memory is tested
with the slice's own tests.

Runs on the in-memory store and the made-up market of `conftest.py`, with the fake Jev of
`test_agent_without_memory.py` and memory's lookups faked by hand.
"""

from dataclasses import replace

import pytest

from jev_trader.jev.reading import MEMORIES_RELEVANT, PastEpisodes, Reading
from jev_trader.llm.selection import Selection, StandInSelector
from jev_trader.llm.wording import ANSWER_TOOL, LlmWording, prompt_version
from jev_trader.memory.bridge import LOOKUP_TOOLS
from jev_trader.memory.episodes import Episode
from jev_trader.memory.lookups import Episodes, Found, SearchResult
from jev_trader.memory.track_record import TrackRecord
from jev_trader.sim.runner import run_sim, settings_document
from jev_trader.sim.store import InMemorySimStore
from tests.unit.sim.test_agent_without_memory import (
    CRYPTO,
    DATASET,
    fake_jev,
    practice,
    with_snapshots,
)

PAST = Episode(
    id="1-100-ASSET_02",
    kind="full_evaluation",
    asset=CRYPTO,
    asset_class="crypto",
    step=100,
    situation="Made-up earlier situation.",
    patterns=["hammer"],
    longer_patterns=[],
    part_of_day="morning",
    trend="up",
    volume="average",
    decided="no_trade",
)


class FakeLookups:
    """Memory's lookups for one moment, over a fixed memory; `asked` records each use."""

    def __init__(self, context, held, asked):
        self.context, self.held, self.asked = context, held, asked

    def search(self, **filters):
        self.asked.append(("search", self.context.step, self.context.asset))
        return SearchResult(
            episodes=[
                Found(episode=e, vector_rank=1, text_rank=1, merged_rank=1)
                for e in self.held
            ]
        )

    def read(self, episode_ids):
        self.asked.append(("read", episode_ids))
        return Episodes(episodes=[e for e in self.held if e.id in episode_ids])

    def track_record(self, pattern, direction):
        self.asked.append(("track_record", pattern, direction))
        return TrackRecord(
            pattern=pattern,
            direction=direction,
            asset_class="crypto",
            minimum_sample=10,
            closed_trades=0,
            groups=[],
        )


def fake_memory(held=()):
    asked = []
    return (lambda context: FakeLookups(context, list(held), asked)), asked


def sim_with_memory(store, market):
    """A practice sim with memory on day 2, its row written as the runner reads it."""
    sim_id = practice(store, market)
    store.sims[sim_id]["VARIANT"] = "memory_on"
    store.sims[sim_id]["SETTINGS"] = settings_document(10_000.0, "memory_on")
    return sim_id


def test_a_full_evaluation_with_memory_reaches_jev_and_is_stored(
    market,
):
    market = with_snapshots(market)
    store = InMemorySimStore()
    jev, sent = fake_jev(lambda n: 0.9)  # every screen says yes
    lookups_at, asked = fake_memory([PAST])
    sim_id = sim_with_memory(store, market)

    run_sim(store, market, sim_id, jev=jev, lookups_at=lookups_at)

    assert store.sim(sim_id)["STATUS"] == "finished"
    evaluations = [
        d
        for d in store.rows("MEMORY.DECISIONS", sim_id)
        if d["KIND"] == "full_evaluation"
    ]
    assert evaluations and {d["PICK"] for d in evaluations} == {"no_trade"}
    assert ("search", 100, CRYPTO) in asked
    assert not [a for a in asked if a[0] == "read"]  # the stand-in selects none
    assert any("pick_1" in body["questions"] for body in sent)


def test_a_sim_with_memory_stores_its_llm_limits_and_prompt_version():
    settings = settings_document(10_000.0, "memory_on")

    assert settings["llm"] == {"model": "anthropic:claude-haiku-5-5"}
    assert settings["selection_limits"]["most_lookups"] == 6
    assert settings["prompt_version"] == prompt_version()
    assert "llm" not in settings_document(10_000.0, "memory_off")


class Chooses(StandInSelector):
    def __init__(self, chosen):
        self.chosen, self.asked = chosen, 0

    def select(self, situation, lookups, first_search):
        self.asked += 1
        return Selection(episode_ids=self.chosen, note="Made-up note.")


@pytest.mark.parametrize(
    ("held", "chosen", "state"),
    [
        ((), (), PastEpisodes.NONE_YET),
        ((PAST,), (), PastEpisodes.NONE_SELECTED),
        ((PAST,), (PAST.id,), PastEpisodes.SELECTED),
    ],
)
def test_each_nothing_to_show_case_is_its_own_state(
    market, monkeypatch, held, chosen, state
):
    seen, original = [], Reading.pick_request

    def pick_request(self, asset, account, playbook, trades, orders, memory=None):
        seen.append(memory)
        return original(self, asset, account, playbook, trades, orders, memory)

    monkeypatch.setattr(Reading, "pick_request", pick_request)
    market = with_snapshots(market)
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    lookups_at, _ = fake_memory(held)
    selector = Chooses(chosen)
    sim_id = sim_with_memory(store, market)

    run_sim(store, market, sim_id, jev=jev, lookups_at=lookups_at, selector=selector)

    sent = [m for m in seen if m is not None]  # the reading version's samples have none
    assert sent and {m.past_episodes for m in sent} == {state}
    assert (selector.asked > 0) == (state is not PastEpisodes.NONE_YET)
    if state is PastEpisodes.SELECTED:
        assert sent[0].episodes == (PAST,)


@pytest.mark.parametrize(
    ("held", "chosen", "asked"),
    [((), (), False), ((PAST,), (), False), ((PAST,), (PAST.id,), True)],
)
def test_the_pick_asks_whether_the_episodes_shown_fit_only_when_some_are(
    market, held, chosen, asked
):
    market = with_snapshots(market)
    store = InMemorySimStore()
    jev, sent = fake_jev(lambda n: 0.9)
    lookups_at, _ = fake_memory(held)
    sim_id = sim_with_memory(store, market)

    run_sim(
        store,
        market,
        sim_id,
        jev=jev,
        lookups_at=lookups_at,
        selector=Chooses(chosen),
    )

    picks = [b for b in sent if "pick_1" in b["questions"]]
    assert picks
    assert all((MEMORIES_RELEVANT in b["questions"]) == asked for b in picks)
    evaluations = [
        d
        for d in store.rows("MEMORY.DECISIONS", sim_id)
        if d["KIND"] == "full_evaluation"
    ]
    fits = {d["MEMORIES_RELEVANT"] for d in evaluations}
    assert fits == ({0.9} if asked else {None})


def test_the_standing_instructions_and_tools_are_stored_once_per_prompt_version(
    market,
):
    market = with_snapshots(market)
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    lookups_at, _ = fake_memory([PAST])
    sim_id = sim_with_memory(store, market)

    run_sim(store, market, sim_id, jev=jev, lookups_at=lookups_at)

    [(version, (system_prompt, tools))] = store.prompts.items()
    assert version == prompt_version()
    assert system_prompt == LlmWording().system_prompt()
    assert [t["name"] for t in tools] == [*LOOKUP_TOOLS, ANSWER_TOOL]


def test_a_sim_whose_llm_wording_changed_cannot_carry_on(market):
    market = with_snapshots(market)
    store = InMemorySimStore()
    jev, _ = fake_jev()
    lookups_at, _ = fake_memory()
    sim_id = sim_with_memory(store, market)
    store.sims[sim_id]["SETTINGS"]["prompt_version"] = "an older one"

    with pytest.raises(ValueError, match="prompt version"):
        run_sim(store, market, sim_id, jev=jev, lookups_at=lookups_at)


def test_the_track_record_is_read_for_the_last_4_bars_patterns_only(market):
    market = with_snapshots(market)
    market.notes["doji"] = ("bearish", "A made-up shape.")
    for assets in market.snapshots_by_step[DATASET].values():
        for asset, snapshot in assets.items():
            assets[asset] = replace(
                snapshot, patterns=("hammer", "doji"), window_patterns=("hammer",)
            )
    store = InMemorySimStore()
    jev, _ = fake_jev(lambda n: 0.9)
    lookups_at, asked = fake_memory([PAST])
    sim_id = sim_with_memory(store, market)

    run_sim(store, market, sim_id, jev=jev, lookups_at=lookups_at)

    read = {a[1] for a in asked if a[0] == "track_record"}
    assert read == {"hammer"}  # the latest daily bar's doji is left out
