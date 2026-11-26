"""The slice's tests: a position review in a sim with memory, with the LLM's answers written by
hand (spec appendix 5, sections 5, 6 and 8; appendix 6, section 4).

One asset at one step: a practice sim with memory on day 2 whose first screen (the crypto at
step 97) says yes and opens a position, and whose first position screen (step 98) says yes, so
the position is reviewed exactly once (unless a test asks for more). Each test scripts the LLM's
replies and observes what reaches the outside: the past reviews selected, the background Jev is
sent, and the records stored.

- The LLM is the fake chat model of `test_full_evaluation_with_memory.py`, which also records
  the tools offered with each call.
- Memory is faked by hand: twelve made-up past reviews of positions in the position's own
  direction. Code's first search finds the first ten (shown as E1 to E10); any later search
  finds reviews 1, 2, 11 and 12. Past full evaluations, for the position's entry, are three more,
  held only when a test asks for them: without them the entry asks no LLM.
- The fixed messages are compared with the wording in `prompts/llm_selection.toml`, as in the
  full evaluation's tests; the exact layouts are compared with the walkthrough page in
  `tests/unit/llm/test_llm_walkthrough_page.py`.
"""

import copy
from dataclasses import dataclass, field

import pytest
from pydantic import Field

from jev_trader.jev.reading import MEMORIES_RELEVANT
from jev_trader.jev.reading import load_wording as load_jev_wording
from jev_trader.llm.selection import LlmFailed, LlmSelector
from jev_trader.llm.settings import load_llm_settings
from jev_trader.llm.wording import LlmWording, load_wording, prompt_version
from jev_trader.memory import bridge
from jev_trader.memory.episodes import Ended, Episode, Prices, Standing, Step
from jev_trader.memory.lookups import Episodes
from jev_trader.memory.search import FULL_EVALUATION, POSITION_REVIEW
from jev_trader.memory.track_record import TrackRecord
from jev_trader.sim.runner import run_sim
from jev_trader.sim.store import InMemorySimStore
from tests.unit.sim.conftest import STOCK, make_market
from tests.unit.sim.test_agent_with_memory_wiring import sim_with_memory
from tests.unit.sim.test_agent_without_memory import (
    CRYPTO,
    PLAYBOOK,
    fake_jev,
    first_position_screen_says_yes,
    with_snapshots,
)
from tests.unit.sim.test_full_evaluation_with_memory import (
    ANSWER_TOOL,
    FakeClock,
    ScriptedLlm,
    answers,
    asks,
    found,
    holds,
    read,
    says,
    sent,
    strings,
    text_of,
    tool_name,
)

ALL_TOOLS = {"search_episodes", "read_episodes", "read_track_record", ANSWER_TOOL}
# The one line an end-of-session review adds to the first message, as both walkthrough pages
# write it.
END_OF_SESSION = (
    "This is the last step of the session from which an order is carried out today. "
    "A position still open after it is held overnight."
)
REVIEW_INSTRUCTIONS = LlmWording().system_prompt(POSITION_REVIEW)


# Memory: twelve made-up past reviews, and three past full evaluations for the entry


def past_review(n: int, direction: str = "long") -> Episode:
    return Episode(
        id=f"1-{n}-{CRYPTO}",
        kind="position_review",
        asset=CRYPTO,
        asset_class="crypto",
        step=n,
        situation=f"Made-up earlier review number {n}.",
        patterns=["hammer"],
        longer_patterns=[],
        part_of_day="morning",
        trend="up",
        volume="average",
        decided="hold",
        review=Step(bar=3, action="hold"),
        standing=Standing(
            direction=direction,
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


def past_entry(n: int) -> Episode:
    return Episode(
        id=f"1-{50 + n}-{CRYPTO}",
        kind="full_evaluation",
        asset=CRYPTO,
        asset_class="crypto",
        step=50 + n,
        situation=f"Made-up earlier entry number {n}.",
        patterns=["hammer"],
        longer_patterns=[],
        part_of_day="morning",
        trend="up",
        volume="average",
        decided="no_trade",
        prices=Prices(after_1_bar=0.001, after_4_bars=0.002, end_of_day=0.004),
    )


REVIEWS = {n: past_review(n) for n in range(1, 13)}
ENTRIES = {n: past_entry(n) for n in range(1, 4)}


class Memory:
    """The made-up memory, opened for one moment at a time; `asked` records each moment's
    context and each use, code's own included."""

    def __init__(self, reviews, entries):
        self.reviews, self.entries = list(reviews), list(entries)
        self.asked: list = []

    def lookups_at(self, context):
        self.asked.append(("context", context))
        return MomentLookups(self, context)

    @property
    def contexts(self) -> list:
        return [a[1] for a in self.asked if a[0] == "context"]

    def searches(self, job) -> list[dict]:
        """The filters of each search in `job`, code's first search (no filters) included."""
        return [a[2] for a in self.asked if a[0] == "search" and a[1].job == job]

    def reads(self) -> list[list[str]]:
        return [a[1] for a in self.asked if a[0] == "read"]


class MomentLookups:
    def __init__(self, memory: Memory, context):
        self.memory, self.context = memory, context

    def search(self, **filters):
        self.memory.asked.append(("search", self.context, filters))
        if self.context.job != POSITION_REVIEW:
            return found(self.memory.entries)
        held = self.memory.reviews
        if filters:
            return found([e for e in held if e.step in (1, 2, 11, 12)])
        return found(held[:10])

    def read(self, episode_ids):
        self.memory.asked.append(("read", list(episode_ids)))
        by_id = {e.id: e for e in [*self.memory.reviews, *self.memory.entries]}
        return Episodes(episodes=[by_id[i] for i in episode_ids if i in by_id])

    def track_record(self, pattern, direction):
        self.memory.asked.append(("track_record", self.context.job, pattern, direction))
        return TrackRecord(
            pattern=pattern,
            direction=direction,
            asset_class="crypto",
            minimum_sample=10,
            closed_trades=0,
            groups=[],
        )


# The LLM: the scripted fake, recording the tools offered with each call in full


class ToolRecordingLlm(ScriptedLlm):
    offered: list = Field(default_factory=list)

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        self.offered.append({tool_name(t): t for t in tools})
        return super().bind_tools(tools, tool_choice=tool_choice, **kwargs)


def input_values(tool) -> dict[str, list]:
    """Each input of a tool as offered, with its allowed values, wherever the schema sits."""
    if isinstance(tool, dict):
        properties = tool.get("properties")
        if isinstance(properties, dict):
            return {
                name: spec.get("enum")
                for name, spec in properties.items()
                if isinstance(spec, dict)
            }
        for value in tool.values():
            found_inputs = input_values(value)
            if found_inputs:
                return found_inputs
    return {}


# One position review in a sim with memory


def opening(direction: str, position_screen=first_position_screen_says_yes):
    """A fake Jev whose first screen says yes and opens a position in `direction`, with
    `position_screen` answering the position screens."""
    return fake_jev(
        lambda n: 0.9 if n == 1 else 0.3,
        pick={f"{direction}_tight_stop": 1.0},
        position_screen=position_screen,
    )


@dataclass
class OneReview:
    reviews: tuple = tuple(REVIEWS.values())
    entries: tuple = ()
    script: list = field(default_factory=list)
    direction: str = "long"
    position_screen: object = first_position_screen_says_yes
    assets: tuple = (STOCK, CRYPTO)

    def __post_init__(self):
        self.market = with_snapshots(make_market(assets=self.assets))
        self.store = InMemorySimStore()
        self.memory = Memory(self.reviews, self.entries)
        self.llm = ToolRecordingLlm(script=list(self.script), clock=FakeClock())
        self.sim_id = sim_with_memory(self.store, self.market)
        self.sent: list = []

    def run(self, llm: ScriptedLlm | None = None, resumed: bool = False) -> None:
        """Run the sim, or resume it: then no screen says yes, so nothing new is opened, and
        the first position screen says yes again."""
        if resumed:
            jev, self.sent = fake_jev(position_screen=self.position_screen)
        else:
            jev, self.sent = opening(self.direction, self.position_screen)
        llm = llm or self.llm
        run_sim(
            self.store,
            self.market,
            self.sim_id,
            jev=jev,
            lookups_at=self.memory.lookups_at,
            selector=LlmSelector(load_llm_settings(), model=llm, clock=llm.clock),
        )

    def decisions(self, kind: str) -> list[dict]:
        return [
            d
            for d in self.store.rows("MEMORY.DECISIONS", self.sim_id)
            if d["KIND"] == kind
        ]

    @property
    def review(self) -> dict:
        return self.decisions("position_review")[0]

    @property
    def entry(self) -> dict:
        return self.decisions("full_evaluation")[0]

    def action_requests(self) -> list[dict]:
        """Each review's request 1, as Jev received it."""
        return [b for b in self.sent if "action_1" in b["questions"]]

    @property
    def background(self) -> str:
        """The background Jev was sent with the (first) review's request 1."""
        return self.action_requests()[0]["state"]

    def review_calls(self, llm: ScriptedLlm | None = None) -> list:
        """The LLM's calls in a position review: those sent the second job's instructions."""
        calls = (llm or self.llm).calls
        return [c for c in calls if text_of(c.messages[0]) == REVIEW_INSTRUCTIONS]

    @property
    def status(self) -> tuple:
        sim = self.store.sim(self.sim_id)
        return sim["STATUS"], sim["STOP_REASON"]

    def events(self, kind: str) -> list[dict]:
        return [
            e
            for e in self.store.rows("SIM.SIM_EVENTS", self.sim_id)
            if e["KIND"] == kind
        ]


def first_message(call) -> str:
    return text_of(call.messages[1])


# The first search, and the selection reaching Jev


@pytest.mark.parametrize("direction", ["long", "short"])
def test_the_first_search_is_over_past_reviews_in_the_positions_direction(direction):
    run = OneReview(
        reviews=tuple(past_review(n, direction) for n in range(1, 13)),
        direction=direction,
        script=[answers(["E2", "E1"], "E2 and E1 stood as this one does.")],
    )

    run.run()

    reviewing = [c for c in run.memory.contexts if c.job == POSITION_REVIEW]
    assert [(c.step, c.asset, c.position_direction) for c in reviewing] == [
        (98, CRYPTO, direction)
    ]
    assert run.memory.searches(POSITION_REVIEW) == [{}]  # code's own, with no narrowing
    [call] = run.llm.calls  # memory holds no full evaluation: the entry asked no LLM
    assert run.review_calls() == [call]
    assert call.tools == ALL_TOOLS
    assert call.tool_choice in (None, "auto")
    assert "E10" in first_message(call) and "E11" not in first_message(call)
    # Jev reads the two selected and no other; the review stores them, most useful first.
    assert REVIEWS[2].situation in run.background
    assert REVIEWS[1].situation in run.background
    assert REVIEWS[3].situation not in run.background
    assert run.review["SELECTED"] == [REVIEWS[2].id, REVIEWS[1].id]
    assert run.review["LLM_NOTE"] == "E2 and E1 stood as this one does."
    assert MEMORIES_RELEVANT in run.action_requests()[0]["questions"]


def test_a_review_search_offers_the_review_decisions_and_the_standing_filter():
    run = OneReview(script=[answers(["E1"])])

    run.run()

    search = input_values(run.llm.offered[0]["search_episodes"])
    assert search["decided"] == ["any", "hold", "close", "reduce", "add"]
    assert search["standing"] == ["any", "in_profit", "at_a_loss"]
    assert set(search) == {"asset", "pattern", "decided", "standing"}


def test_the_llm_narrows_a_review_search_by_decision_and_standing():
    narrowed = {"decided": "reduce", "standing": "at_a_loss"}
    run = OneReview(script=[asks(("search_episodes", narrowed)), answers(["E11"])])

    run.run()

    assert run.memory.searches(POSITION_REVIEW) == [{}, narrowed]
    after_search = run.llm.calls[1].text
    assert "E11" in after_search and "E12" in after_search
    assert REVIEWS[11].situation in run.background
    assert holds(strings(run.review), "search_episodes")


def test_a_full_evaluations_decision_is_refused_in_a_review_and_counts_as_a_lookup():
    run = OneReview(
        script=[
            asks(("search_episodes", {"decided": "long"})),
            asks(read("E1")),
            asks(read("E2")),
            asks(read("E3")),
            asks(read("E4")),
            asks(read("E5")),
            answers(["E1"]),
        ]
    )

    run.run()

    calls = run.llm.calls
    assert run.memory.searches(POSITION_REVIEW) == [{}]  # the refused one was not run
    assert sent("failed_replies", "value_not_allowed", calls[1].text)
    assert "hold" in calls[1].text and "add" in calls[1].text  # the allowed values
    assert calls[6].tools == {ANSWER_TOOL}  # the refused search was the first of six
    assert run.events("a failed reply") == []


# Limits: 6 lookups and 60 seconds, exactly as for a full evaluation


def test_at_six_lookups_the_lookup_tools_are_switched_off_in_a_review():
    search = ("search_episodes", {"asset": "same_asset"})
    track = ("read_track_record", {"pattern": "hammer", "direction": "short"})
    run = OneReview(
        script=[
            asks(search),
            asks(read("E2")),
            asks(search),
            asks(("read_track_record", {"pattern": "hammer", "direction": "long"})),
            asks(search),
            asks(read("E4"), track),  # two side by side, with one lookup left
            answers(["E1"]),
        ]
    )

    run.run()

    calls = run.llm.calls
    assert len(calls) == 7
    assert all(c.tools == ALL_TOOLS for c in calls[:6])
    assert calls[6].tools == {ANSWER_TOOL}  # the answer tool is never taken away
    assert [REVIEWS[4].id] in run.memory.reads()
    # The second of the two was refused: the review's only read of it is code's own.
    short = ("track_record", POSITION_REVIEW, "hammer", "short")
    assert run.memory.asked.count(short) == 1
    assert sent("limits", "lookups_used_up", calls[6].text)
    assert sent("limits", "answer_now_at_limit", calls[6].text)
    assert len(run.events("an LLM limit hit")) == 1
    assert run.events("a failed reply") == []
    assert run.review["LIMIT_HIT"] is not None
    assert REVIEWS[1].situation in run.background


def test_the_answer_tool_does_not_count_as_a_lookup_in_a_review():
    search = ("search_episodes", {"asset": "same_asset"})
    run = OneReview(
        script=[
            asks(search),
            asks(read("E2")),
            asks(search),
            asks(read("E3")),
            asks(search),
            asks((ANSWER_TOOL, {"episode_ids": "E2"})),  # an answer that does not fit
            asks(read("E6")),  # still the sixth lookup: the answer did not count
            answers(["E6"]),
        ]
    )

    run.run()

    calls = run.llm.calls
    assert len(calls) == 8
    assert all(c.tools == ALL_TOOLS for c in calls[:7])
    assert [REVIEWS[6].id] in run.memory.reads()  # the sixth lookup was run
    assert calls[7].tools == {ANSWER_TOOL}
    assert len(run.events("a failed reply")) == 1
    assert run.review["SELECTED"] == [REVIEWS[6].id]


def test_after_60_seconds_the_lookup_tools_are_switched_off_in_a_review():
    run = OneReview(
        script=[
            asks(("search_episodes", {"asset": "same_asset"}), seconds=10),
            asks(read("E2"), seconds=55),  # the reply arrives 65 seconds in
            answers(["E2"]),
        ]
    )

    run.run()

    calls = run.llm.calls
    assert len(calls) == 3
    assert calls[1].tools == ALL_TOOLS
    assert calls[2].tools == {ANSWER_TOOL}
    assert sent("limits", "answer_now_out_of_time", calls[2].text)
    assert len(run.events("an LLM limit hit")) == 1
    assert REVIEWS[2].situation in run.background


# Replies that do not fit


def test_failed_replies_are_counted_per_review():
    # Two failed replies in the entry's full evaluation and two in the review: neither reaches
    # three, so the sim carries on.
    run = OneReview(
        entries=tuple(ENTRIES.values()),
        script=[
            says("E1 fits."),
            says("Still E1."),
            answers(["E1"]),
            says("E2 fits."),
            asks(("pick_best_episode", {"label": "E2"})),  # a tool that does not exist
            answers(["E2"]),
        ],
    )

    run.run()

    assert run.status == ("finished", "finished")
    assert len(run.events("a failed reply")) == 4
    calls = run.review_calls()
    assert len(calls) == 3
    assert sent("failed_replies", "reask", calls[1].text)
    assert calls[1].tools == ALL_TOOLS  # every tool it still has stays on offer
    assert run.review["SELECTED"] == [REVIEWS[2].id]


def test_the_third_failed_reply_in_a_review_stops_the_sim_and_it_can_resume():
    run = OneReview(
        script=[
            says("E1 looks closest."),
            asks(("pick_best_episode", {"label": "E1"})),  # a tool that does not exist
            asks((ANSWER_TOOL, {"episode_ids": "E1 and E8"})),  # not a list; no note
        ]
    )

    with pytest.raises(LlmFailed, match="position review"):
        run.run()

    assert len(run.llm.calls) == 3
    assert run.status == ("stopped", "LLM failed")
    assert not run.action_requests()  # Jev was not asked

    resumed = ScriptedLlm(script=[answers(["E1"])], clock=FakeClock())
    run.run(resumed, resumed=True)

    assert run.status == ("finished", "finished")
    assert run.store.duplicate_ids(run.sim_id) == {}
    assert len(resumed.calls) == 1
    assert REVIEWS[1].situation in run.background


def test_an_episode_id_never_shown_is_dropped_in_a_review():
    run = OneReview(script=[answers(["E1", "E42"])])

    run.run()

    assert len(run.llm.calls) == 1  # not a failed reply: nothing is asked again
    assert len(run.events("an unknown episode ID dropped")) == 1
    assert run.events("a failed reply") == []
    assert run.review["SELECTED"] == [REVIEWS[1].id]
    assert REVIEWS[1].situation in run.background


# The first message


def test_the_first_message_holds_the_positions_standing_and_nothing_else_of_the_account():
    run = OneReview(script=[answers(["E1"])])

    run.run()

    # The standing: a long of $4,000, open 0 bars, its stop price 0.5% away.
    first = first_message(run.llm.calls[0])
    assert "Made-up situation." in first
    assert "$4,000" in first and "open 0 bars" in first and "0.5% away" in first
    assert "cash" not in first.lower() and "$10,000" not in first
    assert END_OF_SESSION not in first


def test_only_an_end_of_session_review_adds_its_line():
    # The stock opens a long at step 151, carried out at 152; its first position screen (152)
    # says yes, and bar 25 of 26 (step 175) gets the end-of-session review.
    run = OneReview(assets=(STOCK,), script=[answers(["E1"]), answers(["E2"])])

    run.run()

    reviews = run.decisions("position_review")
    assert [(r["STEP"], r["END_OF_SESSION"]) for r in reviews] == [
        (152, False),
        (175, True),
    ]
    screened, last_step = (first_message(c) for c in run.review_calls())
    assert END_OF_SESSION not in screened
    assert last_step.count(END_OF_SESSION) == 1


# A thin memory


def test_a_memory_holding_no_past_review_asks_no_llm():
    run = OneReview(reviews=())

    run.run()

    assert run.llm.calls == []
    assert run.memory.searches(POSITION_REVIEW) == [{}]
    assert load_jev_wording()["past_episodes_none_yet"] in run.background
    assert MEMORIES_RELEVANT not in run.action_requests()[0]["questions"]
    # Stored as a full evaluation stores it: no selection.
    assert run.review["SELECTED"] is None and run.review["PROMPT_VERSION"] is None


def test_fewer_than_ten_past_reviews_are_shown_with_their_real_count():
    run = OneReview(reviews=tuple(REVIEWS[n] for n in (1, 2, 3)), script=[answers([])])

    run.run()

    first = first_message(run.llm.calls[0])
    assert "3 past episodes" in first
    assert "E3" in first and "E4" not in first
    assert run.review["SELECTED"] == []
    assert not any(e.situation in run.background for e in REVIEWS.values())


# The prompt version: one fingerprint for both jobs


def test_a_review_is_sent_the_second_jobs_instructions_from_the_wording_file():
    run = OneReview(script=[answers(["E1"])])

    run.run()

    instructions = text_of(run.llm.calls[0].messages[0])
    assert sent("position_review", "system_prompt", instructions)
    assert instructions != LlmWording().system_prompt(FULL_EVALUATION)


def test_both_jobs_carry_one_prompt_version_stored_with_both_jobs_words():
    run = OneReview(
        entries=tuple(ENTRIES.values()),
        script=[answers(["E1"]), answers(["E1"])],
    )

    run.run()

    version = prompt_version()
    assert run.entry["PROMPT_VERSION"] == version
    assert run.review["PROMPT_VERSION"] == version
    assert holds(strings(run.store.sim(run.sim_id)), version)
    # The standing part stored for the version holds both jobs' instructions and tools.
    stored = strings(run.store.prompts[version])
    assert holds(stored, LlmWording().system_prompt(FULL_EVALUATION))
    assert holds(stored, REVIEW_INSTRUCTIONS)
    review_search, *_ = bridge.definitions(POSITION_REVIEW, list(PLAYBOOK))
    assert holds(stored, review_search.description)


@pytest.mark.parametrize(
    ("file", "path"),
    [
        ("llm", ("position_review", "system_prompt")),
        ("llm", ("position_review", "first_message")),
        ("llm", ("full_evaluation", "system_prompt")),
        ("tools", ("position_review", "search_episodes", "description")),
        ("tools", ("full_evaluation", "search_episodes", "description")),
    ],
)
def test_a_changed_word_in_either_job_gives_a_different_prompt_version(file, path):
    wording, tools = load_wording(), bridge.load_wording()
    edited = copy.deepcopy(wording if file == "llm" else tools)
    place = edited
    for key in path[:-1]:
        assert key in place, f"no {'.'.join(path[:-1])} in the {file} wording yet"
        place = place[key]
    place[path[-1]] += " Made-up word."

    if file == "llm":
        version = prompt_version(edited, tools)
    else:
        version = prompt_version(wording, edited)

    assert version != prompt_version(wording, tools)


def test_the_same_review_sends_the_same_messages_every_time():
    def messages_sent() -> list[list[str]]:
        run = OneReview(
            script=[asks(("search_episodes", {"standing": "in_profit"})), answers([])]
        )
        run.run()
        return [[text_of(m) for m in c.messages] for c in run.llm.calls]

    assert messages_sent() == messages_sent()


# Entry memory and fresh memory


def test_the_entry_memory_is_unchanged_while_each_reviews_fresh_memory_is_stored():
    # The position is opened on entry 1, then reviewed at steps 98 and 100.
    def reviewed_at(n):
        return 0.9 if n in (1, 3) else 0.3

    reviewed = OneReview(
        entries=tuple(ENTRIES.values()),
        position_screen=reviewed_at,
        script=[answers(["E1"]), answers(["E2"]), answers(["E3", "E1"])],
    )
    never_reviewed = OneReview(
        entries=tuple(ENTRIES.values()),
        position_screen=lambda n: 0.3,
        script=[answers(["E1"])],
    )

    reviewed.run()
    never_reviewed.run()

    # The entry's records are the same whatever the reviews did.
    assert reviewed.entry == never_reviewed.entry
    assert reviewed.entry["SELECTED"] == [ENTRIES[1].id]
    # Each review stores its own selection beside it, never the entry's.
    reviews = reviewed.decisions("position_review")
    assert [r["STEP"] for r in reviews] == [98, 100]
    assert [r["SELECTED"] for r in reviews] == [
        [REVIEWS[2].id],
        [REVIEWS[3].id, REVIEWS[1].id],
    ]
    assert None not in {r["POSITION"] for r in reviews}
    exchanges = reviewed.store.rows("SIM.LLM_EXCHANGES", reviewed.sim_id)
    assert [e["DECISION"] for e in exchanges] == [
        reviewed.entry["ID"],
        *(r["ID"] for r in reviews),
    ]
    # Jev reads each review's fresh memory, never the entry memory again.
    first, second = (b["state"] for b in reviewed.action_requests())
    assert REVIEWS[2].situation in first and REVIEWS[3].situation in second
    assert not any(ENTRIES[1].situation in b for b in (first, second))
    # The fresh memory Jev read is stored with each review, word for word.
    requests = reviewed.store.rows("SIM.JEV_REQUESTS", reviewed.sim_id)
    for review, selected in zip(reviews, (REVIEWS[2], REVIEWS[3]), strict=True):
        stored = strings([r for r in requests if r["DECISION"] == review["ID"]])
        assert holds(stored, selected.situation)
        assert not holds(stored, ENTRIES[1].situation)
