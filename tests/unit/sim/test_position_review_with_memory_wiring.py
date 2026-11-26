"""A position review in a sim with memory, wired end to end with a fake LLM (the slice's
skeleton): code's first search over past position reviews of the same direction, the LLM's
second job, and Jev's background gaining the reviews selected. The second job's real wording,
the fresh memory stored beside the entry memory, and the rest of the slice's behaviour are
tested with the slice's own tests.

A practice sim with memory on day 2: the crypto's first screen says yes and opens a long at step
97 (memory holds no full evaluation, so the LLM is not asked), and its first position screen, at
step 98, says yes, so the position is reviewed exactly once.
"""

import pytest

from jev_trader.jev.reading import MEMORIES_RELEVANT, load_wording
from jev_trader.llm.selection import LlmFailed, LlmSelector
from jev_trader.llm.settings import load_llm_settings
from jev_trader.memory.episodes import Ended, Episode, Prices, Standing, Step
from jev_trader.memory.lookups import Episodes, Found, SearchResult
from jev_trader.memory.search import POSITION_REVIEW
from jev_trader.memory.track_record import TrackRecord
from jev_trader.sim.runner import run_sim
from jev_trader.sim.store import InMemorySimStore
from tests.unit.sim.conftest import make_market
from tests.unit.sim.test_agent_with_memory_wiring import sim_with_memory
from tests.unit.sim.test_agent_without_memory import (
    CRYPTO,
    fake_jev,
    first_position_screen_says_yes,
    opening_the_crypto,
    with_snapshots,
)
from tests.unit.sim.test_full_evaluation_with_memory import (
    FakeClock,
    ScriptedLlm,
    answers,
    asks,
    says,
    text_of,
)

PAST_REVIEW = Episode(
    id="1-60-ASSET_02",
    kind="position_review",
    asset=CRYPTO,
    asset_class="crypto",
    step=60,
    situation="Made-up earlier review's situation.",
    patterns=["hammer"],
    longer_patterns=[],
    part_of_day="morning",
    trend="up",
    volume="average",
    decided="hold",
    review=Step(bar=3, action="hold"),
    standing=Standing(
        direction="long",
        put_in=4000,
        bars_open=3,
        profit=12,
        percent=0.3,
        stop_distance=0.005,
        best=20,
        worst=-4,
    ),
    prices=Prices(after_1_bar=0.001, after_4_bars=0.002, end_of_day=0.004),
    ended=Ended(reason="jev", bars_after=5, profit=30, percent=0.75),
)


class ReviewMemory:
    """Memory holding past position reviews only: a full evaluation's search finds nothing.
    `asked` records each moment's context and each use."""

    def __init__(self, context, held, asked):
        self.context, self.held, self.asked = context, held, asked
        asked.append(("context", context))

    def search(self, **filters):
        self.asked.append(("search", filters))
        reviews = self.context.job == POSITION_REVIEW
        return SearchResult(
            episodes=[
                Found(episode=e, vector_rank=1, text_rank=1, merged_rank=1)
                for e in (self.held if reviews else [])
            ]
        )

    def read(self, episode_ids):
        self.asked.append(("read", list(episode_ids)))
        return Episodes(episodes=[e for e in self.held if e.id in episode_ids])

    def track_record(self, pattern, direction):
        return TrackRecord(
            pattern=pattern,
            direction=direction,
            asset_class="crypto",
            minimum_sample=10,
            closed_trades=0,
            groups=[],
        )


class OneReview:
    def __init__(self, script, held=(PAST_REVIEW,)):
        self.market = with_snapshots(make_market())
        self.store = InMemorySimStore()
        self.asked: list = []
        self.held = list(held)
        self.llm = ScriptedLlm(script=list(script), clock=FakeClock())
        self.sim_id = sim_with_memory(self.store, self.market)
        self.sent: list = []

    def run(self, llm=None, resumed=False):
        """Run the sim, or resume it: then no screen says yes, so nothing new is opened."""
        opening = fake_jev if resumed else opening_the_crypto
        jev, self.sent = opening(position_screen=first_position_screen_says_yes)
        llm = llm or self.llm
        run_sim(
            self.store,
            self.market,
            self.sim_id,
            jev=jev,
            lookups_at=lambda c: ReviewMemory(c, self.held, self.asked),
            selector=LlmSelector(load_llm_settings(), model=llm, clock=llm.clock),
        )

    @property
    def review(self) -> dict:
        return next(
            d
            for d in self.store.rows("MEMORY.DECISIONS", self.sim_id)
            if d["KIND"] == "position_review"
        )

    @property
    def action(self) -> dict:
        """The review's request 1, as Jev received it."""
        return next(b for b in self.sent if "action_1" in b["questions"])


def test_a_review_gets_the_past_reviews_the_llm_selected():
    run = OneReview(script=[answers(["E1"])])

    run.run()

    contexts = [a[1] for a in run.asked if a[0] == "context"]
    review_context = next(c for c in contexts if c.job == POSITION_REVIEW)
    assert (review_context.step, review_context.asset) == (98, CRYPTO)
    assert review_context.position_direction == "long"
    [call] = run.llm.calls
    first = text_of(call.messages[1])
    assert "Long, $4,000, open 0 bars" in first  # the standing
    assert (
        "The 1 past episode most like this moment" in first
    )  # fewer than 10: the real count
    assert PAST_REVIEW.situation in run.action["state"]
    assert run.review["SELECTED"] == [PAST_REVIEW.id]
    assert MEMORIES_RELEVANT in run.action["questions"]
    assert run.review["MEMORIES_RELEVANT"] is not None
    assert store_has_the_exchange(run)


def store_has_the_exchange(run) -> bool:
    exchanges = run.store.rows("SIM.LLM_EXCHANGES", run.sim_id)
    return [e["DECISION"] for e in exchanges] == [run.review["ID"]]


def test_memory_holding_no_past_review_asks_no_llm():
    run = OneReview(script=[], held=())

    run.run()

    assert run.llm.calls == []
    assert run.review["SELECTED"] is None
    assert load_wording()["past_episodes_none_yet"] in run.action["state"]
    assert MEMORIES_RELEVANT not in run.action["questions"]
    assert run.review["MEMORIES_RELEVANT"] is None


def test_the_third_failed_reply_in_a_review_stops_the_sim_and_it_can_resume():
    run = OneReview(
        script=[
            says("E1 looks closest."),
            says("Still E1."),
            asks(("pick_best_episode", {"label": "E1"})),
        ]
    )

    with pytest.raises(LlmFailed, match="position review"):
        run.run()
    sim = run.store.sim(run.sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("stopped", "LLM failed")

    resumed = ScriptedLlm(script=[answers(["E1"])], clock=FakeClock())
    run.run(resumed, resumed=True)

    sim = run.store.sim(run.sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("finished", "finished")
    assert len(resumed.calls) == 1
    assert PAST_REVIEW.situation in run.action["state"]
