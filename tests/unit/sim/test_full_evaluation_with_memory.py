"""The slice's tests: a full evaluation in a sim with memory, with the LLM's answers written by
hand (spec appendix 5, sections 6 to 8). Dormant until the slice's closing ticket (#105).

One asset at one step: a practice sim with memory on day 2 whose first screen (the crypto at
step 97) says yes and every later one no, so the LLM selects past episodes exactly once. Each
test scripts the LLM's replies as a small conversation and observes what reaches the outside:
the episodes selected, the background Jev is sent, and the records stored.

- The LLM is a fake chat model: it answers from its script and records each call's messages
  and the tools offered with it. A reply may say how many seconds it took, on a fake clock,
  and a script entry may be an error instead of a reply (a call to the provider that fails).
- Memory is faked by hand: twelve made-up past episodes. Code's first search finds the first
  ten (shown as E1 to E10); any later search finds episodes 1, 2, 11 and 12, so the two new
  ones continue the numbering (E11, E12).
- The fixed messages are compared with the wording in `prompts/llm_selection.toml`: its words
  around any filled-in value, so the tests hold whatever the words and value names.
- A call to the provider that fails may be retried by the provider's own client, below the
  model, or by code above it: the tests hold either way.
"""

import copy
import json
import string
from dataclasses import dataclass, field

import anthropic
import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from jev_trader.llm.selection import LlmFailed, LlmSelector
from jev_trader.llm.settings import load_llm_settings
from jev_trader.llm.wording import load_wording, prompt_version
from jev_trader.memory import bridge
from jev_trader.memory.episodes import Episode
from jev_trader.memory.lookups import Episodes, Found, SearchResult
from jev_trader.memory.track_record import TrackRecord
from jev_trader.sim.runner import run_sim
from jev_trader.sim.store import TABLES, InMemorySimStore
from tests.unit.sim.conftest import make_market
from tests.unit.sim.test_agent_with_memory_wiring import sim_with_memory
from tests.unit.sim.test_agent_without_memory import (
    CRYPTO,
    fake_jev,
    practice,
    with_snapshots,
)

pytestmark = pytest.mark.dormant

LOOKUP_TOOLS = {"search_episodes", "read_episodes", "read_track_record"}
ANSWER_TOOL = "select_episodes"
ALL_TOOLS = LOOKUP_TOOLS | {ANSWER_TOOL}
MODEL = load_llm_settings().name


# Memory: twelve made-up past episodes


def past(n: int) -> Episode:
    return Episode(
        id=f"1-{n}-ASSET_02",
        kind="full_evaluation",
        asset=CRYPTO,
        asset_class="crypto",
        step=n,
        situation=f"Made-up earlier situation number {n}.",
        patterns=["hammer"],
        longer_patterns=[],
        part_of_day="morning",
        trend="up",
        volume="average",
        decided="no_trade",
    )


EPISODES = {n: past(n) for n in range(1, 13)}
FIRST_SEARCH = [EPISODES[n] for n in range(1, 11)]  # shown as E1 to E10
LATER_SEARCH = [EPISODES[n] for n in (1, 2, 11, 12)]  # E1, E2, then E11, E12


def found(episodes):
    return SearchResult(
        episodes=[
            Found(episode=e, vector_rank=r, text_rank=r, merged_rank=r)
            for r, e in enumerate(episodes, start=1)
        ]
    )


class FakeLookups:
    """Memory's lookups for one moment; `asked` records each use, code's own included."""

    def __init__(self, held, asked):
        self.held, self.asked = held, asked

    def search(self, **filters):
        self.asked.append(("search", filters))
        if not self.held:
            return found([])
        return found(LATER_SEARCH if filters else FIRST_SEARCH)

    def read(self, episode_ids):
        self.asked.append(("read", list(episode_ids)))
        by_id = {e.id: e for e in EPISODES.values()}
        return Episodes(episodes=[by_id[i] for i in episode_ids if i in by_id])

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


# The LLM: a fake chat model over a script, on a fake clock


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


@dataclass
class Call:
    """One call to the LLM: the messages sent, the tools offered, and how a tool call was
    asked for (None or "auto": not forced)."""

    messages: list[BaseMessage]
    tools: set[str]
    tool_choice: object

    @property
    def text(self) -> str:
        return "\n".join(text_of(m) for m in self.messages)


def text_of(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        part if isinstance(part, str) else str(part.get("text", ""))
        for part in message.content
    )


def tool_name(tool) -> str:
    if isinstance(tool, dict):
        return tool.get("name") or tool.get("function", {}).get("name") or tool["title"]
    return getattr(tool, "name", None) or tool.__name__


class ScriptedLlm(BaseChatModel):
    """Answers each call with the next entry of `script`: (seconds the reply takes, the reply),
    where the reply is an `AIMessage` or an error to raise."""

    script: list
    clock: FakeClock
    calls: list = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        names = [tool_name(t) for t in tools]
        return self.bind(tool_names=names, tool_choice=tool_choice, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(
            Call(
                list(messages),
                set(kwargs.get("tool_names", ())),
                kwargs.get("tool_choice"),
            )
        )
        if not self.script:
            raise AssertionError(f"the LLM was called {len(self.calls)} times")
        seconds, reply = self.script.pop(0)
        self.clock.now += seconds
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])


def asks(*tool_calls: tuple[str, dict], seconds: float = 2.0):
    """A reply holding these tool calls, side by side."""
    return (
        seconds,
        AIMessage(
            content="",
            tool_calls=[
                {"name": name, "args": args, "id": f"call_{n}", "type": "tool_call"}
                for n, (name, args) in enumerate(tool_calls, start=1)
            ],
        ),
    )


def answers(episode_ids, note="Made-up note.", seconds: float = 2.0):
    return asks(
        (ANSWER_TOOL, {"episode_ids": episode_ids, "note": note}), seconds=seconds
    )


def says(sentence: str, seconds: float = 2.0):
    return (seconds, AIMessage(content=sentence))


def provider_fails():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return (1.0, anthropic.APIConnectionError(request=request))


SEARCH = ("search_episodes", {"asset": "same_asset"})
TRACK_LONG = ("read_track_record", {"pattern": "hammer", "direction": "long"})
TRACK_SHORT = ("read_track_record", {"pattern": "hammer", "direction": "short"})


def read(*labels):
    return ("read_episodes", {"episode_ids": list(labels)})


def sent(section: str, key: str, text: str) -> bool:
    """Whether `text` holds the fixed message the wording file has under `section` and `key`:
    its words, in order, whatever value is filled in between them."""
    wording = load_wording()[section][key]
    assert wording, f"{section}.{key} has no wording yet"
    at = 0
    for words, *_ in string.Formatter().parse(wording):
        at = text.find(words, at)
        if at == -1:
            return False
        at += len(words)
    return True


# One full evaluation in a sim with memory


@dataclass
class OneEvaluation:
    held: tuple = tuple(EPISODES.values())
    script: list = field(default_factory=list)

    def __post_init__(self):
        self.market = with_snapshots(make_market())
        self.store = InMemorySimStore()
        self.asked: list = []
        self.clock = FakeClock()
        self.llm = ScriptedLlm(script=list(self.script), clock=self.clock)
        self.sim_id = sim_with_memory(self.store, self.market)
        self.sent: list = []

    def run(self, llm: ScriptedLlm | None = None) -> None:
        jev, self.sent = answers_jev_once()
        llm = llm or self.llm
        run_sim(
            self.store,
            self.market,
            self.sim_id,
            jev=jev,
            lookups_at=lambda context: FakeLookups(list(self.held), self.asked),
            selector=LlmSelector(load_llm_settings(), model=llm, clock=llm.clock),
        )

    @property
    def background(self) -> str:
        """The background Jev was sent with the full evaluation's pick question."""
        return pick_background(self.sent)

    @property
    def status(self) -> tuple:
        sim = self.store.sim(self.sim_id)
        return sim["STATUS"], sim["STOP_REASON"]

    @property
    def decision(self) -> dict:
        return next(
            d
            for d in self.store.rows("MEMORY.DECISIONS", self.sim_id)
            if d["KIND"] == "full_evaluation"
        )

    def events(self, kind: str) -> list[dict]:
        return [
            e
            for e in self.store.rows("SIM.SIM_EVENTS", self.sim_id)
            if e["KIND"] == kind
        ]

    def stored(self) -> list[str]:
        """Every text stored for the sim, in any table a step writes."""
        return strings([self.store.rows(t, self.sim_id) for t in TABLES])

    def llm_reads(self) -> list:
        """The reads in full asked of memory, code's reading of the selected ones included."""
        return [a[1] for a in self.asked if a[0] == "read"]


def pick_background(bodies: list[dict]) -> str:
    return next(b["state"] for b in bodies if "pick_1" in b["questions"])


def answers_jev_once():
    """A fake Jev whose first screen says yes and every later one no."""
    return fake_jev(lambda n: 0.9 if n == 1 else 0.3)


def strings(value) -> list[str]:
    """Every string inside a stored value, reading into JSON held as text."""
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in strings(v)]
    if isinstance(value, str):
        try:
            inner = json.loads(value)
        except ValueError:
            return [value]
        return [value, *strings(inner)] if isinstance(inner, dict | list) else [value]
    return [] if value is None else [str(value)]


def holds(texts: list[str], wanted: str) -> bool:
    return any(wanted in t for t in texts)


@pytest.fixture(autouse=True)
def memory_on_runs(monkeypatch):
    """The runner's "not built yet" guard lifted, as in the skeleton's wiring test."""
    monkeypatch.setattr(
        "jev_trader.sim.runner.BUILT_VARIANTS",
        ("buy_hold", "memory_off", "memory_on"),
        raising=False,
    )


def situations_in_order(background: str, *numbers: int) -> bool:
    places = [background.find(EPISODES[n].situation) for n in numbers]
    return -1 not in places and places == sorted(places)


# The cases


def test_the_llm_answers_at_once():
    run = OneEvaluation(script=[answers(["E3", "E1"], "E3 and E1 share the hammer.")])

    run.run()

    assert len(run.llm.calls) == 1
    first = run.llm.calls[0]
    assert first.tools == ALL_TOOLS
    assert first.tool_choice in (None, "auto")  # no tool call is forced
    assert "Made-up situation." in first.text
    assert "E10" in first.text and "E11" not in first.text
    # Jev reads the two selected, in the LLM's order, and no other.
    assert situations_in_order(run.background, 3, 1)
    assert EPISODES[2].situation not in run.background
    assert run.llm_reads() == [[EPISODES[3].id, EPISODES[1].id]]  # code's own read
    stored = strings(run.decision)
    for wanted in (EPISODES[3].id, EPISODES[1].id, "E3 and E1 share the hammer."):
        assert holds(stored, wanted)
    assert holds(stored, prompt_version()) and holds(stored, MODEL)
    assert run.events("an LLM limit hit") == []
    # The exchange is stored word for word: the first message as it was sent.
    first_message = text_of(first.messages[-1])
    assert holds(run.stored(), first_message)
    # Each call to the LLM is recorded with its model and its retries.
    llm_calls = [
        c for c in run.store.rows("SIM.CALLS", run.sim_id) if c["SERVICE"] != "jev"
    ]
    assert [(c["MODEL"], c["RETRIES"]) for c in llm_calls] == [(MODEL, 0)]


def test_the_llm_searches_again_opens_episodes_and_reads_the_track_record():
    run = OneEvaluation(
        script=[
            asks(SEARCH),
            asks(read("E1", "E11")),
            asks(TRACK_LONG),
            answers(["E11", "E1"]),
        ]
    )

    run.run()

    assert len(run.llm.calls) == 4
    assert all(c.tools == ALL_TOOLS for c in run.llm.calls)
    assert ("search", {"asset": "same_asset"}) in run.asked
    # The later search shows two new episodes, numbered on; those already shown keep theirs.
    after_search = run.llm.calls[1].text
    assert "E11" in after_search and "E12" in after_search
    assert not any("E13" in c.text for c in run.llm.calls)
    # The read in full reaches memory as stored decision IDs, and its records reach the LLM.
    assert [EPISODES[1].id, EPISODES[11].id] in run.llm_reads()
    assert EPISODES[11].situation in run.llm.calls[2].text
    assert situations_in_order(run.background, 11, 1)
    stored = strings(run.decision)
    for wanted in ("search_episodes", "read_episodes", "read_track_record"):
        assert holds(stored, wanted)
    assert run.events("an LLM limit hit") == []


def test_at_six_lookups_the_lookup_tools_are_switched_off():
    run = OneEvaluation(
        script=[
            asks(SEARCH),
            asks(read("E2")),
            asks(SEARCH),
            asks(TRACK_LONG),
            asks(SEARCH),
            asks(read("E4"), TRACK_SHORT),  # two side by side, with one lookup left
            answers(["E1"]),
        ]
    )

    run.run()

    calls = run.llm.calls
    assert len(calls) == 7
    assert all(c.tools == ALL_TOOLS for c in calls[:6])
    assert calls[6].tools == {ANSWER_TOOL}  # the answer is never taken away
    # The first of the two is run, the second refused, then the fixed stop message.
    assert [EPISODES[4].id] in run.llm_reads()
    assert run.asked.count(("track_record", "hammer", "short")) == 1  # code's own only
    assert sent("limits", "lookups_used_up", calls[6].text)
    assert sent("limits", "answer_now_at_limit", calls[6].text)
    assert len(run.events("an LLM limit hit")) == 1
    assert run.events("a failed reply") == []
    assert EPISODES[1].situation in run.background


def test_after_60_seconds_the_lookup_tools_are_switched_off():
    run = OneEvaluation(
        script=[
            asks(SEARCH, seconds=10),
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
    assert EPISODES[2].situation in run.background


def test_a_sentence_instead_of_a_tool_call_is_a_failed_reply_and_asked_again():
    run = OneEvaluation(script=[says("I think E1 and E2 fit best."), answers(["E2"])])

    run.run()

    calls = run.llm.calls
    assert len(calls) == 2
    assert calls[1].tools == ALL_TOOLS  # every tool it still has stays on offer
    assert sent("failed_replies", "reask", calls[1].text)
    assert len(run.events("a failed reply")) == 1
    assert run.status == ("finished", "finished")
    # Code reads no IDs out of the sentence: only the answer's.
    assert EPISODES[2].situation in run.background
    assert EPISODES[1].situation not in run.background


def test_the_third_failed_reply_stops_the_sim_and_it_can_resume():
    run = OneEvaluation(
        script=[
            says("E1 looks closest."),
            asks(("pick_best_episode", {"label": "E1"})),  # a tool that does not exist
            asks((ANSWER_TOOL, {"episode_ids": "E1 and E8"})),  # not a list; no note
        ]
    )

    with pytest.raises(LlmFailed):
        run.run()

    assert len(run.llm.calls) == 3
    assert run.status == ("stopped", "LLM failed")
    assert run.sent and not any("pick_1" in b["questions"] for b in run.sent)

    run.run(ScriptedLlm(script=[answers(["E1"])], clock=FakeClock()))

    assert run.status == ("finished", "finished")
    assert run.store.duplicate_ids(run.sim_id) == {}
    assert EPISODES[1].situation in run.background


def test_an_episode_id_never_shown_is_dropped_and_the_rest_kept():
    run = OneEvaluation(script=[answers(["E1", "E42"])])

    run.run()

    assert len(run.llm.calls) == 1  # not a failed reply: nothing is asked again
    assert len(run.events("an unknown episode ID dropped")) == 1
    assert run.events("a failed reply") == []
    assert run.llm_reads() == [[EPISODES[1].id]]
    assert EPISODES[1].situation in run.background


def memory_off_background() -> str:
    """The background of the same full evaluation by the agent without memory."""
    market = with_snapshots(make_market())
    store = InMemorySimStore()
    jev, sent_to_jev = answers_jev_once()
    run_sim(store, market, practice(store, market), jev=jev)
    return pick_background(sent_to_jev)


def test_an_answer_of_none_is_told_to_jev_apart_from_memory_holding_none():
    none_selected = OneEvaluation(script=[answers([], "Nothing shown is alike.")])
    none_yet = OneEvaluation(held=())  # the LLM is not asked: its script is empty

    none_selected.run()
    none_yet.run()

    assert len(none_selected.llm.calls) == 1 and none_yet.llm.calls == []
    assert none_selected.llm_reads() == []
    # Jev still gets the track record, and is told none was selected, in words of its own.
    assert ("track_record", "hammer", "long") in none_selected.asked
    backgrounds = {
        none_selected.background,
        none_yet.background,
        memory_off_background(),
    }
    assert len(backgrounds) == 3
    assert not any(e.situation in none_selected.background for e in EPISODES.values())
    assert holds(strings(none_selected.decision), "Nothing shown is alike.")


def test_a_provider_call_failing_after_three_retries_stops_the_sim_and_it_can_resume():
    # Enough failures for the first try and three retries, wherever the retrying is done.
    run = OneEvaluation(script=[provider_fails() for _ in range(4)])

    with pytest.raises(LlmFailed):
        run.run()

    assert run.status == ("stopped", "LLM failed")

    run.run(ScriptedLlm(script=[answers(["E1"])], clock=FakeClock()))

    assert run.status == ("finished", "finished")
    assert run.store.duplicate_ids(run.sim_id) == {}
    assert EPISODES[1].situation in run.background


# The prompt version


def test_the_same_wording_gives_the_same_prompt_version():
    assert prompt_version(load_wording(), bridge.load_wording()) == prompt_version()


@pytest.mark.parametrize("changed", ["llm", "tools"])
def test_a_changed_word_gives_a_different_prompt_version(changed):
    wording, tools = load_wording(), bridge.load_wording()
    edited = copy.deepcopy(wording if changed == "llm" else tools)
    if changed == "llm":
        text = edited["full_evaluation"]["system_prompt"]
        edited["full_evaluation"]["system_prompt"] = text + " Made-up word."
        version = prompt_version(edited, tools)
    else:
        description = edited["read_track_record"]["description"]
        edited["read_track_record"]["description"] = description + " Made-up word."
        version = prompt_version(wording, edited)

    assert version != prompt_version(wording, tools)
