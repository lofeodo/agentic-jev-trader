"""The selection step: the LLM picks which past episodes Jev reads in a full evaluation or a
position review (spec appendix 5, sections 4 to 8; appendix 10, section 2).

Code runs the first search and hands its one-line summaries to a `Selector`, with the moment
being looked at (`Situation`; in a position review it also carries the position's standing,
which makes the selection the LLM's second job). Both jobs share everything but the job's
standing instructions, its first message and its two job-specific tool descriptions. The
selector may look further through memory's lookups (`MemoryLookups`, for one moment: the sim,
the step, the asset and the job are filled in by code) and returns a `Selection`: the chosen
episodes' IDs, most useful first, and a one-line note, with what the decision record stores
about how they were chosen.

The real selector, `LlmSelector`, is a small LangGraph graph of our own: a call to the LLM
(through `LlmClient`, one call at a time), then its reply handled (lookups run or refused, or the
reply asked again), and round again until the LLM answers with `select_episodes`. The answer
tool never counts and is never taken away. At 6 lookups or 60 seconds (timed by a `WallClock`,
so tests can run on a fake one) the three lookup tools are switched off and a fixed message asks
for the answer. A reply code cannot use is a **failed reply** and gets a fixed re-ask; the third
in one full evaluation or position review raises `LlmFailed`, as does a call to the provider
still failing after its retries. Either stops the sim.

The LLM sees episodes by short labels (E1, E2, ...) numbered in the order they first appear in
the evaluation; code maps them back to stored decision IDs. Every message after the standing
instructions is kept word for word; the instructions and the tools, the same for every
evaluation of one prompt version, are stored once per version (`standing_part`).

Choices the spec leaves to the build:

- The lookups are called as plain (blocking) calls, as the agent's steps are; the memory bridge
  itself is asynchronous, so the real lookups wrap it (`jev_trader.memory.bridge.Connection`).
- A reply holding a lookup tool after the limit has switched it off is a failed reply: the tool
  was not on offer. Lookups asked side by side in the reply that reaches the limit are refused
  one by one, and are not failed replies.
- The 60 seconds run from when the selection starts (after code's first search) and are checked
  after each call and before each lookup. A lookup asked for after them is refused with the
  time's stop message, which is then not sent again.
- A failed reply runs none of its lookups. Each of its tool calls is answered with the re-ask,
  or with the refusal saying what is wrong for an answer that does not fit.
- A lookup input that is not allowed (an unknown input, a missing one, a value off its list, or
  an episode ID not shown) is refused with the allowed values, and counted.
- A lookup the memory server fails is answered with the server's message, and counted.
- The smaller slips are kept on the selection (`slips`, stored with the exchange) and logged;
  the three the spec names as notable moments become events (`events`).
"""

import json
import logging
import operator
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Annotated, Protocol, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    messages_to_dict,
)
from langgraph.graph import END, START, StateGraph

from jev_trader.llm.clients import (
    LlmCall,
    LlmClient,
    LlmFailed,
)
from jev_trader.llm.settings import LlmSettings
from jev_trader.llm.wording import ANSWER_TOOL, LlmWording
from jev_trader.memory import render
from jev_trader.memory.bridge import (
    LOOKUP_TOOLS,
    MemoryToolFailed,
    ToolDefinition,
    definitions,
)
from jev_trader.memory.episodes import Episode, Standing
from jev_trader.memory.lookups import MOST_READ, Episodes, Found, SearchResult
from jev_trader.memory.search import (
    FULL_EVALUATION,
    POSITION_REVIEW,
    RESULTS,
    Filters,
    Job,
)
from jev_trader.memory.track_record import TrackRecord

log = logging.getLogger(__name__)

SEARCH, READ, TRACK_RECORD = LOOKUP_TOOLS
# Far above what the limits allow (6 lookups, 3 failed replies, the answer), so LangGraph's own
# step cap never stops a selection.
GRAPH_STEPS = 200

# The notable moments the spec logs in SIM_EVENTS (appendix 6, section 8).
LIMIT_HIT_EVENT = "an LLM limit hit"
FAILED_REPLY_EVENT = "a failed reply"
UNKNOWN_ID_EVENT = "an unknown episode ID dropped"


@dataclass(frozen=True)
class SelectionLimits:
    """The selection's limits, stored with each sim (appendix 5, section 6)."""

    results_per_search: int = RESULTS
    most_selected: int = MOST_READ
    most_lookups: int = 6  # not counting the first search; the answer never counts
    seconds: float = 60.0
    failed_replies_to_stop: int = 3  # the third in one evaluation stops the sim
    note_length: int = 200


class LimitHit(StrEnum):
    LOOKUPS = "lookups"  # 6 lookups used
    TIME = "time"  # 60 seconds up


class MemoryLookups(Protocol):
    """Memory's three read-only lookups for one moment, as the agent and the selector use them."""

    def search(self, **filters: str) -> SearchResult: ...

    def read(self, episode_ids: list[str]) -> Episodes: ...

    def track_record(self, pattern: str, direction: str) -> TrackRecord: ...


@dataclass(frozen=True)
class ReviewedPosition:
    """The open position a position review selects for: its standing (from
    `jev_trader.jev.reading.PositionView.standing`) and whether this is a stock's
    end-of-session review."""

    standing: Standing
    end_of_session: bool = False


@dataclass(frozen=True)
class Situation:
    """The moment the LLM selects for: the asset looked at (masked) and its class, the step,
    the situation text Jev reads, the candle patterns it names, and the playbook (each
    pattern's lean and shape). In a position review, also the open position."""

    asset: str
    asset_class: str
    step: int
    text: str
    patterns: tuple[str, ...]
    playbook: dict[str, tuple[str, str]]
    position: ReviewedPosition | None = None

    @property
    def job(self) -> Job:
        return FULL_EVALUATION if self.position is None else POSITION_REVIEW


@dataclass(frozen=True)
class Lookup:
    """One lookup the LLM made, in order: its tool and inputs, the episode IDs it returned,
    how long it took, and the reason it was refused if it was."""

    tool: str
    inputs: dict
    episode_ids: tuple[str, ...]
    latency_seconds: float
    refused: str | None = None


@dataclass(frozen=True)
class Shown:
    """An episode the LLM was shown: its label ("E1"), its ranks, which search found it first,
    and whether it was opened in full."""

    episode_id: str
    label: str
    vector_rank: int | None
    text_rank: int | None
    merged_rank: int
    from_first_search: bool
    opened: bool = False


@dataclass(frozen=True)
class Event:
    """A notable moment for `SIM_EVENTS`: its kind and details."""

    kind: str
    details: dict


@dataclass(frozen=True)
class Selection:
    """What the selection chose, and how, for the decision record.

    `episode_ids` are stored decision IDs, most useful first: none is a valid answer.
    `limit_hit` says which limit was reached, if one was. `failed_replies` holds each
    reply code could not use, word for word, and `exchange` every message sent and received
    after the standing instructions. `calls` holds what each call to the LLM took, in order,
    each recorded in SIM.CALLS. `slips` names each smaller slip carried on from, and `events`
    the notable moments to log.
    """

    episode_ids: tuple[str, ...]
    note: str
    shown: tuple[Shown, ...] = ()
    lookups: tuple[Lookup, ...] = ()
    limit_hit: LimitHit | None = None
    failed_replies: tuple[str, ...] = ()
    exchange: tuple[dict, ...] = ()
    model: str | None = None
    prompt_version: str | None = None
    calls: tuple[LlmCall, ...] = ()
    slips: tuple[str, ...] = ()
    events: tuple[Event, ...] = ()


class Selector(Protocol):
    def select(
        self, situation: Situation, lookups: MemoryLookups, first_search: SearchResult
    ) -> Selection: ...


class StandInSelector:
    """Selects no episode and looks nothing up."""

    def select(
        self, situation: Situation, lookups: MemoryLookups, first_search: SearchResult
    ) -> Selection:
        return Selection(episode_ids=(), note="")


class WallClock(Protocol):
    """Where the selection reads the time taken from, for its 60 seconds (not the dataset's
    step clock), and how it waits between a failed call's tries."""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemWallClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def wording_within(limits: SelectionLimits) -> LlmWording:
    """The LLM's texts, naming `limits`."""
    return LlmWording(
        most_lookups=limits.most_lookups,
        most_selected=limits.most_selected,
        note_length=limits.note_length,
    )


def standing_part(
    limits: SelectionLimits, patterns: list[str]
) -> tuple[str, dict[Job, str], dict[Job, list[dict]]]:
    """What every exchange of one prompt version opens with, the same for every full
    evaluation and every position review of it: the version, then by job its standing
    instructions and its four tools as the first call offers them (`patterns`: every candle
    pattern name in the playbook). Stored once per version."""
    wording = wording_within(limits)
    jobs = (FULL_EVALUATION, POSITION_REVIEW)
    tools = {
        job: [_tool(d) for d in (*definitions(job, patterns), wording.answer_tool())]
        for job in jobs
    }
    return wording.version, {job: wording.system_prompt(job) for job in jobs}, tools


class LlmSelector:
    """The LLM's selection: a tool loop over `model` (by default the client `settings` names),
    within `limits`, timed by `clock`, in the words of `wording`, whose prompt version every
    selection carries."""

    def __init__(
        self,
        settings: LlmSettings,
        model: BaseChatModel | None = None,
        limits: SelectionLimits | None = None,
        clock: WallClock | None = None,
    ):
        self.settings = settings
        self.limits = limits or SelectionLimits()
        self.clock = clock or SystemWallClock()
        self.client = LlmClient(
            settings, model, now=self.clock.monotonic, sleep=self.clock.sleep
        )
        self.wording = wording_within(self.limits)
        self.prompt_version = self.wording.version

    def select(
        self, situation: Situation, lookups: MemoryLookups, first_search: SearchResult
    ) -> Selection:
        return _Evaluation(self, situation, lookups).run(first_search)


# One evaluation's tool loop


class _Turns(TypedDict):
    """The graph's state: the number of calls made. Everything else the evaluation keeps
    itself, in order."""

    turns: Annotated[int, operator.add]


@dataclass
class _Answer:
    labels: list[str]
    note: str


@dataclass
class _Reply:
    """A reply, sorted: a usable answer, the lookups asked for, and why it is a failed reply
    (None if it is not one)."""

    message: AIMessage
    answer: _Answer | None = None
    lookups: list[dict] = field(default_factory=list)
    failed_because: str | None = None
    answer_does_not_fit: set[str] = field(default_factory=set)  # tool call IDs


class _NotAllowed(Exception):
    """A lookup input that is not allowed: the input and its allowed values."""

    def __init__(self, input_name: str, allowed: list[str]):
        super().__init__(f"{input_name} must be one of {allowed}")
        self.input_name, self.allowed = input_name, allowed


class _Evaluation:
    """One full evaluation's or position review's selection: its messages, labels, lookups and
    slips."""

    def __init__(
        self, selector: LlmSelector, situation: Situation, lookups: MemoryLookups
    ):
        self.selector, self.situation, self.memory = selector, situation, lookups
        self.limits, self.clock = selector.limits, selector.clock
        self.wording = selector.wording
        self.reader = render.Reader(asset=situation.asset, now=situation.step)
        self.definitions = {
            d.name: d for d in definitions(situation.job, list(situation.playbook))
        }
        self.shown: dict[str, Shown] = {}  # by label, in the order first shown
        self.labels: dict[str, str] = {}  # stored ID to label
        self.explained: set[str] = set()
        self.messages: list[BaseMessage] = []
        self.lookups: list[Lookup] = []
        self.used = 0
        self.limit_hit: LimitHit | None = None
        self.told_to_answer = False  # the limit's stop message has been sent
        self.failed: list[str] = []
        self.calls: list[LlmCall] = []
        self.slips: list[str] = []
        self.events: list[Event] = []
        self.reply: _Reply | None = None
        self.started = self.clock.monotonic()

    # The graph: call, then handle the reply, until an answer

    def run(self, first_search: SearchResult) -> Selection:
        graph = StateGraph(_Turns)
        graph.add_node("call", self._call)
        graph.add_node("handle", self._handle)
        graph.add_edge(START, "call")
        graph.add_conditional_edges("call", self._after_call)
        graph.add_edge("handle", "call")
        self.messages = [
            SystemMessage(self.wording.system_prompt(self.situation.job)),
            HumanMessage(self._first_message(first_search)),
        ]
        graph.compile().invoke({"turns": 0}, {"recursion_limit": GRAPH_STEPS})
        return self._selection(self.reply.answer)

    def _after_call(self, state: _Turns) -> str:
        return END if self.reply.answer is not None else "handle"

    def _call(self, state: _Turns) -> dict:
        offered = self._offered()
        reply = self.selector.client.call(self.messages, [_tool(d) for d in offered])
        self.calls.append(reply.call)
        self.messages.append(reply.message)
        self._check_time()
        self.reply = self._sort(reply.message, {d.name for d in offered})
        others = (
            len(reply.message.tool_calls) + len(reply.message.invalid_tool_calls) - 1
        )
        if self.reply.answer is not None and others:
            self._slip("an answer sent with other tool calls: they were not run")
        return {"turns": 1}

    def _handle(self, state: _Turns) -> dict:
        reply = self.reply
        if reply.failed_because is not None:
            self._failed_reply(reply)
        else:
            for call in reply.lookups:
                text = self._lookup(call)
                self.messages.append(ToolMessage(text, tool_call_id=call["id"]))
            self._check_time()
        if self.limit_hit is not None and not self.told_to_answer:
            self.told_to_answer = True
            self.messages.append(HumanMessage(self._stop_message()))
        return {}

    # A reply, sorted

    def _offered(self) -> list[ToolDefinition]:
        lookups = [] if self.limit_hit else [self.definitions[n] for n in LOOKUP_TOOLS]
        return [*lookups, self.wording.answer_tool()]

    def _sort(self, message: AIMessage, offered: set[str]) -> _Reply:
        """Sort a reply against the tools offered with the call it answers."""
        reply = _Reply(message)
        calls = list(message.tool_calls)
        if not calls and not message.invalid_tool_calls:
            reply.failed_because = "a sentence instead of a tool call"
            return reply
        for call in calls:
            if call["name"] == ANSWER_TOOL:
                answer = _read_answer(call["args"])
                if answer is None:
                    reply.answer_does_not_fit.add(call["id"])
                elif reply.answer is None:
                    reply.answer = answer
            elif call["name"] in offered:
                reply.lookups.append(call)
        if reply.answer is not None:
            return reply
        not_offered = [c["name"] for c in calls if c["name"] not in offered]
        if message.invalid_tool_calls:
            reply.failed_because = "a tool call whose inputs could not be read"
        elif not_offered:
            reply.failed_because = f"a call to a tool not on offer: {not_offered[0]}"
        elif reply.answer_does_not_fit:
            reply.failed_because = "an answer that is not a list of IDs and a note"
        return reply

    def _failed_reply(self, reply: _Reply) -> None:
        self.failed.append(word_for_word(reply.message))
        self._event(
            FAILED_REPLY_EVENT, number=len(self.failed), why=reply.failed_because
        )
        if len(self.failed) >= self.limits.failed_replies_to_stop:
            job = self.situation.job.replace("_", " ")
            raise LlmFailed(
                f"failed reply number {len(self.failed)} in one {job} "
                f"({self.situation.asset}, step {self.situation.step}): "
                f"{reply.failed_because}"
            )
        reask = self.wording.reask(lookups_left=self.limit_hit is None)
        # Each tool call is answered by its ID; one that came without an ID cannot be, so the
        # re-ask then also goes as a message of its own.
        calls = [*reply.message.tool_calls, *reply.message.invalid_tool_calls]
        answered = [call for call in calls if call.get("id")]
        for call in answered:
            text = (
                self.wording.answer_does_not_fit()
                if call["id"] in reply.answer_does_not_fit
                else reask
            )
            self.messages.append(ToolMessage(text, tool_call_id=call["id"]))
        if len(answered) < len(calls) or not calls:
            self.messages.append(HumanMessage(reask))

    # The limits

    def _check_time(self) -> None:
        late = self.clock.monotonic() - self.started >= self.limits.seconds
        if late and self.limit_hit is None:
            self._hit(LimitHit.TIME)

    def _hit(self, limit: LimitHit) -> None:
        self.limit_hit = limit
        self._event(LIMIT_HIT_EVENT, limit=str(limit))

    def _event(self, kind: str, **details) -> None:
        """A notable moment, logged and kept for SIM_EVENTS."""
        details = {"asset": self.situation.asset, **details}
        self.events.append(Event(kind, details))
        log.info("%s: %s", kind, details)

    def _stop_message(self) -> str:
        if self.limit_hit is LimitHit.LOOKUPS:
            return self.wording.answer_now_at_limit()
        return self.wording.answer_now_out_of_time()

    # Lookups

    def _lookup(self, call: dict) -> str:
        """Run one lookup the LLM asked for, or refuse it; returns what the LLM is told."""
        name, args = call["name"], dict(call["args"])
        self._check_time()
        if self.limit_hit is LimitHit.TIME:
            # The refusal is the time's stop message itself: it is not sent again.
            self.told_to_answer = True
            return self._refused(name, args, "time", self._stop_message())
        if self.used >= self.limits.most_lookups:
            return self._refused(name, args, "lookups", self.wording.lookups_used_up())
        self.used += 1
        started = self.clock.monotonic()
        refused = None
        try:
            text, found = self._run_lookup(name, args)
        except _NotAllowed as error:
            text, found, refused = self._not_allowed(error), (), str(error)
            self._slip(f"a value not allowed in {name}: {error}")
        except MemoryToolFailed as error:
            text, found, refused = str(error), (), str(error)
            self._slip(f"a lookup the memory server failed: {error}")
        self.lookups.append(
            Lookup(name, args, found, self.clock.monotonic() - started, refused)
        )
        if self.used >= self.limits.most_lookups and self.limit_hit is None:
            self._hit(LimitHit.LOOKUPS)
        return text

    def _refused(self, name: str, args: dict, why: str, text: str) -> str:
        self.lookups.append(Lookup(name, args, (), 0.0, why))
        return text

    def _not_allowed(self, error: _NotAllowed) -> str:
        return self.wording.value_not_allowed(error.input_name, error.allowed)

    def _run_lookup(self, name: str, args: dict) -> tuple[str, tuple[str, ...]]:
        self._check_inputs(self.definitions[name], args)
        if name == SEARCH:
            result = self.memory.search(**args)
            summaries = self._summaries(result.episodes, from_first_search=False)
            named = [p for f in result.episodes for p in f.episode.patterns]
            text = self.wording.search_result(
                Filters(**args),
                summaries,
                self._pattern_notes(named),
                self.situation.job,
            )
            return text, tuple(f.episode.id for f in result.episodes)
        if name == READ:
            return self._read(args["episode_ids"])
        record = self.memory.track_record(args["pattern"], args["direction"])
        return render.track_record(record), ()

    def _check_inputs(self, definition: ToolDefinition, args: dict) -> None:
        """Refuse an input not in the definition, a missing one, a value off its list, or an
        episode ID not shown in this evaluation."""
        properties = definition.input_schema["properties"]
        for name in args:
            if name not in properties:
                raise _NotAllowed(name, list(properties))
        for name in definition.input_schema["required"]:
            if name not in args:
                raise _NotAllowed(name, self._allowed(properties, name))
        for name, value in args.items():
            allowed = properties[name].get("enum")
            if allowed is not None and value not in allowed:
                raise _NotAllowed(name, allowed)
        if definition.name == READ:
            labels = args["episode_ids"]
            fits = (
                isinstance(labels, list)
                and 1 <= len(labels) <= MOST_READ
                and all(
                    isinstance(label, str) and label in self.shown for label in labels
                )
            )
            if not fits:
                raise _NotAllowed("episode_ids", list(self.shown))

    def _allowed(self, properties: dict, name: str) -> list[str]:
        """An input's allowed values: its list, or for episode IDs the labels shown."""
        return properties.get(name, {}).get("enum") or list(self.shown)

    def _read(self, labels: list[str]) -> tuple[str, tuple[str, ...]]:
        wanted = list(dict.fromkeys(self.shown[label].episode_id for label in labels))
        read = self.memory.read(wanted).episodes
        blocks = []
        for episode in read:
            label = self.labels[episode.id]
            self.shown[label] = replace(self.shown[label], opened=True)
            blocks.append(render.full_episode(episode, label, self.reader))
        named = [p for e in read for p in (*e.patterns, *e.longer_patterns)]
        text = "\n\n".join(blocks) + self._pattern_notes(named)
        return text, tuple(e.id for e in read)

    # What the LLM is shown

    def _first_message(self, first_search: SearchResult) -> str:
        s = self.situation
        summaries = self._summaries(first_search.episodes, from_first_search=True)
        named = [
            *s.patterns,
            *(p for f in first_search.episodes for p in f.episode.patterns),
        ]
        notes = self._pattern_notes(named)
        if s.position is None:
            return self.wording.first_message(
                s.asset, s.asset_class, s.text, summaries, notes
            )
        return self.wording.review_first_message(
            s.asset,
            s.asset_class,
            s.text,
            s.position.standing,
            s.position.end_of_session,
            summaries,
            notes,
        )

    def _summaries(self, found: list[Found], from_first_search: bool) -> list[str]:
        return [
            render.summary_line(
                f.episode, self._label(f, from_first_search), self.reader
            )
            for f in found
        ]

    def _label(self, found: Found, from_first_search: bool) -> str:
        """The episode's label: the one it was first shown with, or the next number."""
        episode: Episode = found.episode
        if episode.id not in self.labels:
            label = f"E{len(self.labels) + 1}"
            self.labels[episode.id] = label
            self.shown[label] = Shown(
                episode_id=episode.id,
                label=label,
                vector_rank=found.vector_rank,
                text_rank=found.text_rank,
                merged_rank=found.merged_rank,
                from_first_search=from_first_search,
            )
        return self.labels[episode.id]

    def _pattern_notes(self, names) -> str:
        """The notes on the patterns named that are not yet explained in this evaluation."""
        playbook = self.situation.playbook
        fresh = [
            n for n in dict.fromkeys(names) if n not in self.explained and n in playbook
        ]
        self.explained.update(fresh)
        return self.wording.pattern_notes(fresh, playbook)

    # The answer, and what is stored

    def _selection(self, answer: _Answer) -> Selection:
        labels = list(dict.fromkeys(answer.labels))
        if len(labels) < len(answer.labels):
            self._slip("repeated episode IDs removed")
        known = []
        for label in labels:
            if label in self.shown:
                known.append(label)
                continue
            self._event(UNKNOWN_ID_EVENT, episode_id=label)
        if len(known) > self.limits.most_selected:
            self._slip(
                f"more than {self.limits.most_selected} selected: the first kept"
            )
            known = known[: self.limits.most_selected]
        note = answer.note
        if len(note) > self.limits.note_length:
            self._slip(f"a note over {self.limits.note_length} characters cut")
            note = note[: self.limits.note_length]
        return Selection(
            episode_ids=tuple(self.shown[label].episode_id for label in known),
            note=note,
            shown=tuple(self.shown.values()),
            lookups=tuple(self.lookups),
            limit_hit=self.limit_hit,
            failed_replies=tuple(self.failed),
            exchange=tuple(messages_to_dict(self.messages[1:])),
            model=self.calls[-1].model,
            prompt_version=self.selector.prompt_version,
            calls=tuple(self.calls),
            slips=tuple(self.slips),
            events=tuple(self.events),
        )

    def _slip(self, slip: str) -> None:
        self.slips.append(slip)
        log.info("An LLM slip carried on from: %s", slip)


def _tool(definition: ToolDefinition) -> dict:
    return {
        "name": definition.name,
        "description": definition.description,
        "input_schema": definition.input_schema,
    }


def _read_answer(args: dict) -> _Answer | None:
    """The answer's IDs and note, or None when it is not a list of IDs plus a note."""
    labels, note = args.get("episode_ids"), args.get("note")
    if not isinstance(labels, list) or not isinstance(note, str):
        return None
    if not all(isinstance(label, str) for label in labels):
        return None
    return _Answer(labels, note)


def word_for_word(message: AIMessage) -> str:
    """A reply as received, its text and any tool calls, for the record."""
    calls = [
        {"name": c["name"], "args": c["args"]}
        for c in [*message.tool_calls, *message.invalid_tool_calls]
    ]
    return json.dumps(
        {"content": message.content, "tool_calls": calls}, ensure_ascii=False
    )
