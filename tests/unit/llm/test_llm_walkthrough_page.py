"""The LLM walkthrough page matches what is sent (spec appendix 10, section 18).

The page's own code writes the standing instructions, the tools, the fixed messages, the first
message of its made-up full evaluation and the search the LLM asks for in its second scenario.
This test runs that code with Node and compares it, word for word, with what the selection sends
from the same story, through a scripted fake LLM. A past episode in full is compared in
`tests/unit/memory/test_render.py`.

The second job (tab "Always sent" and tab 6: a position review) is compared the same way: its
standing instructions, its two own tool descriptions, and its first message, at a review and at
an end-of-session review.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from jev_trader.llm.selection import LlmSelector, ReviewedPosition, Situation
from jev_trader.llm.settings import load_llm_settings
from jev_trader.llm.wording import ANSWER_TOOL, LlmWording
from jev_trader.memory.bridge import definitions
from jev_trader.memory.episodes import Ended, Episode, Prices, Standing, Step, Trade
from jev_trader.memory.lookups import Found, SearchResult
from jev_trader.memory.search import FULL_EVALUATION, POSITION_REVIEW
from tests.unit.sim.test_full_evaluation_with_memory import (
    FakeClock,
    ScriptedLlm,
    answers,
    asks,
    text_of,
)

PAGE = Path(__file__).parents[3] / "docs" / "llm-prompt-walkthrough.html"
FILTERS = "same asset, bullish engulfing, any decision"
PRINT_THE_STORY = f"""
const evaluation = makeEvaluation(CURRENT, PLAYBOOK);
const first = firstMessage(FIRST_SEARCH, evaluation);
const found = searchResult(SECOND_SEARCH, evaluation, "{FILTERS}");
console.log(JSON.stringify({{
  systemPrompt: systemPrompt(),
  tools: TOOLS.map(t => [t.name, t.description]),
  fixed: {{ LOOKUPS_USED_UP, ANSWER_NOW_AT_LIMIT, ANSWER_NOW_OUT_OF_TIME, REASK,
    REASK_AT_LIMIT, VALUE_NOT_ALLOWED, ANSWER_DOES_NOT_FIT }},
  current: CURRENT, playbook: PLAYBOOK, episodes: EPISODES,
  firstSearch: FIRST_SEARCH.map(e => e.key), secondSearch: SECOND_SEARCH.map(e => e.key),
  first, found,
  reviewSystemPrompt: reviewSystemPrompt(),
  reviewTools: REVIEW_TOOLS.map(t => [t.name, t.description]),
  reviews: REVIEWS, reviewCurrent: REVIEW_CURRENT,
  positionNow: POSITION_NOW, positionAtClose: POSITION_AT_CLOSE,
  reviewFirstSearch: REVIEW_FIRST_SEARCH.map(e => e.key),
  reviewFirst: reviewFirstMessage(REVIEW_FIRST_SEARCH, makeEvaluation(REVIEW_CURRENT, PLAYBOOK),
    POSITION_NOW),
  reviewFirstAtClose: reviewFirstMessage(REVIEW_FIRST_SEARCH.slice(0, 2),
    makeEvaluation(REVIEW_CURRENT, PLAYBOOK), POSITION_AT_CLOSE, true),
}}));
"""
NOW = 1000 * 96  # the step of the page's full evaluation
REASONS = {"choice": "jev", "stop": "stop_price"}


@pytest.fixture(scope="module")
def story(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    html = PAGE.read_text(encoding="utf-8")
    portable = html.split("<script>")[1].split("PAGE (throwaway shell")[0]
    script = tmp_path_factory.mktemp("page") / "story.js"
    script.write_text(portable + "*/" + PRINT_THE_STORY, encoding="utf-8")
    done = subprocess.run(
        [node, str(script)],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(done.stdout)


def episode(e: dict) -> Episode:
    """One of the page's made-up past full evaluations, as memory stores it."""
    trade, ended, after = e.get("trade"), e.get("ended"), e.get("after")
    part_of_day, trend, volume = e["setting"]
    return Episode(
        id=f"made-up-{e['key']}",
        kind="full_evaluation",
        asset=e["asset"],
        asset_class=e["assetClass"],
        step=NOW - e["stepsAgo"],
        situation=e["situation"],
        patterns=e["patterns"],
        longer_patterns=e.get("patternsOnLongerBars", []),
        part_of_day=part_of_day,
        trend=trend.removeprefix("long-term trend "),
        volume=volume.removeprefix("volume "),
        decided=trade["direction"] if trade else "no_trade",
        trade=trade
        and Trade(
            direction=trade["direction"],
            stop=trade["stop"],
            stop_distance=trade["stopPercent"] / 100,
            dollars=trade["dollars"],
        ),
        ended=ended
        and Ended(
            reason=REASONS[ended["reason"]],
            bars_after=ended["bars"],
            profit=ended["profit"],
            percent=ended["percent"],
            best=ended["best"],
            worst=ended["worst"],
        ),
        prices=after
        and Prices(
            after_1_bar=after["oneBar"] / 100,
            after_4_bars=after["fourBars"] / 100,
            end_of_day=after["endOfDay"] / 100,
        ),
    )


def found(story, keys) -> SearchResult:
    return SearchResult(
        episodes=[
            Found(
                episode=episode(story["episodes"][k]),
                vector_rank=rank,
                text_rank=rank,
                merged_rank=rank,
            )
            for rank, k in enumerate(keys, start=1)
        ]
    )


class PageMemory:
    """Memory holding the page's episodes: code's first search finds its first list, and the
    LLM's search its second."""

    def __init__(self, story):
        self.story = story

    def search(self, **filters):
        keys = "secondSearch" if filters else "firstSearch"
        return found(self.story, self.story[keys])


def situation(story) -> Situation:
    current = story["current"]
    return Situation(
        asset=current["asset"],
        asset_class=current["assetClass"],
        step=NOW,
        text=current["situation"],
        patterns=tuple(current["patterns"]),
        playbook={n: (p["lean"], p["shape"]) for n, p in story["playbook"].items()},
    )


@pytest.fixture(scope="module")
def sent(story):
    """The page's second scenario, as the selection sends it: the first message, then one
    search for the same asset and a bullish engulfing, then the answer."""
    search = {"asset": "same_asset", "pattern": "bullish engulfing"}
    clock = FakeClock()
    llm = ScriptedLlm(
        script=[asks(("search_episodes", search)), answers([])], clock=clock
    )
    selector = LlmSelector(load_llm_settings(), model=llm, clock=clock)
    memory = PageMemory(story)
    selector.select(situation(story), memory, memory.search())
    return llm.calls


def test_the_standing_instructions_are_the_pages_word_for_word(story, sent):
    assert LlmWording().system_prompt() == story["systemPrompt"]
    assert text_of(sent[0].messages[0]) == story["systemPrompt"]


def test_the_tools_are_described_as_on_the_page(story):
    ours = [
        *definitions(FULL_EVALUATION, list(story["playbook"])),
        LlmWording().answer_tool(),
    ]
    assert [(d.name, d.description) for d in ours] == [tuple(t) for t in story["tools"]]
    assert ours[-1].name == ANSWER_TOOL


def test_the_first_message_is_the_pages_word_for_word(story, sent):
    assert text_of(sent[0].messages[-1]) == story["first"]


def test_a_search_the_llm_asks_for_is_the_pages_word_for_word(story, sent):
    assert text_of(sent[1].messages[-1]) == story["found"]


def test_the_fixed_messages_are_the_pages_word_for_word(story):
    w, page = LlmWording(), story["fixed"]
    assert w.lookups_used_up() == page["LOOKUPS_USED_UP"]
    assert w.answer_now_at_limit() == page["ANSWER_NOW_AT_LIMIT"]
    assert w.answer_now_out_of_time() == page["ANSWER_NOW_OUT_OF_TIME"]
    assert w.reask(lookups_left=True) == page["REASK"]
    assert w.reask(lookups_left=False) == page["REASK_AT_LIMIT"]
    assert w.answer_does_not_fit() == page["ANSWER_DOES_NOT_FIT"]
    allowed = ["any", "same_asset", "same_asset_class"]
    assert w.value_not_allowed("asset", allowed) == page["VALUE_NOT_ALLOWED"]


# The second job: a position review (the slice "position review with memory")

SHARES = {"a quarter": 0.25, "half": 0.5, "three quarters": 0.75}
REDUCED = re.compile(r"reduce by (.+) \(that part: ([+-])\$([\d,]+)\)")
ADDED = re.compile(r"add \$([\d,]+)")
HANDLED = re.compile(r"bars? (\d+)(?: to (\d+))? (.+?)( \(this review\))?")
ENDINGS = {"stop price reached": "stop_price"}


def review_step(decided: str, bar: int) -> Step:
    """What one of the page's past reviews decided, as memory stores it."""
    if reduced := REDUCED.fullmatch(decided):
        share, sign, profit = reduced.groups()
        made = float(profit.replace(",", "")) * (-1 if sign == "-" else 1)
        return Step(bar=bar, action="reduce", share=SHARES[share], profit=made)
    if added := ADDED.fullmatch(decided):
        amount = float(added.group(1).replace(",", ""))
        return Step(bar=bar, action="add", amount=amount)
    return Step(bar=bar, action=decided)


def journal(handled: list[str]) -> list[Step]:
    """A past review's whole trade, bar by bar, from the page's runs ("bars 1 to 5 hold")."""
    steps = []
    for run in handled:
        first, last, what, this_review = HANDLED.fullmatch(run).groups()
        for bar in range(int(first), int(last or first) + 1):
            if what in ENDINGS:
                step = Step(bar=bar, action=ENDINGS[what])
            else:
                step = review_step(what, bar)
            steps.append(step.model_copy(update={"this_review": bool(this_review)}))
    return steps


def standing(p: dict) -> dict:
    """A position's standing on the page, as `PositionView.standing` gives it."""
    return {
        "direction": p["direction"],
        "put_in": p["dollars"],
        "bars_open": p["bars"],
        "profit": p["profit"],
        "percent": p["percent"],
        "stop_distance": p["stopPercent"] / 100,
        "best": p["best"],
        "worst": p["worst"],
    }


def past_review(e: dict) -> Episode:
    """One of the page's made-up past position reviews, as memory stores it."""
    part_of_day, trend, volume = e["setting"]
    step = review_step(e["decided"], e["position"]["bars"])
    ended, after = e["ended"], e["after"]
    return Episode(
        id=f"made-up-{e['key']}",
        kind="position_review",
        asset=e["asset"],
        asset_class=e["assetClass"],
        step=NOW - e["stepsAgo"],
        situation=e["situation"],
        patterns=e["patterns"],
        longer_patterns=e.get("patternsOnLongerBars", []),
        part_of_day=part_of_day,
        trend=trend.removeprefix("long-term trend "),
        volume=volume.removeprefix("volume "),
        decided=step.action,
        review=step,
        standing=Standing(**standing(e["position"])),
        prices=Prices(
            after_1_bar=after["oneBar"] / 100,
            after_4_bars=after["fourBars"] / 100,
            end_of_day=after["endOfDay"] / 100,
        ),
        ended=Ended(
            reason=REASONS[ended["reason"]],
            bars_after=max(ended["bars"], 1),
            profit=ended["profit"],
            percent=ended["percent"],
            closed_at_this_review=ended["bars"] == 0,
        ),
        journal=journal(e["handled"]),
    )


def review_situation(story, position: dict, end_of_session: bool) -> Situation:
    current = story["reviewCurrent"]
    return Situation(
        asset=current["asset"],
        asset_class=current["assetClass"],
        step=NOW,
        text=current["situation"],
        patterns=tuple(current["patterns"]),
        playbook={n: (p["lean"], p["shape"]) for n, p in story["playbook"].items()},
        position=ReviewedPosition(
            standing=Standing(**standing(position)), end_of_session=end_of_session
        ),
    )


def review_sent(story, position: dict, end_of_session: bool, shown: int):
    """The page's tab 6 as the selection sends it: the first message, then the answer."""
    clock = FakeClock()
    llm = ScriptedLlm(script=[answers([])], clock=clock)
    selector = LlmSelector(load_llm_settings(), model=llm, clock=clock)
    first_search = SearchResult(
        episodes=[
            Found(
                episode=past_review(story["reviews"][k]),
                vector_rank=rank,
                text_rank=rank,
                merged_rank=rank,
            )
            for rank, k in enumerate(story["reviewFirstSearch"][:shown], start=1)
        ]
    )
    selector.select(
        review_situation(story, position, end_of_session), None, first_search
    )
    return llm.calls


def test_the_second_jobs_instructions_are_the_pages_word_for_word(story):
    assert LlmWording().system_prompt(POSITION_REVIEW) == story["reviewSystemPrompt"]
    [call] = review_sent(story, story["positionNow"], False, 10)
    assert text_of(call.messages[0]) == story["reviewSystemPrompt"]


def test_the_second_jobs_tools_are_described_as_on_the_page(story):
    ours = [
        *definitions(POSITION_REVIEW, list(story["playbook"])),
        LlmWording().answer_tool(),
    ]
    described = {d.name: d.description for d in ours}
    for name, description in story["reviewTools"]:
        assert described[name] == description
    # The other two read the same in both jobs.
    first_job = dict(story["tools"])
    for name in ("read_track_record", ANSWER_TOOL):
        assert described[name] == first_job[name]


def test_a_reviews_first_message_is_the_pages_word_for_word(story):
    [call] = review_sent(story, story["positionNow"], False, 10)
    assert text_of(call.messages[-1]) == story["reviewFirst"]


def test_an_end_of_session_reviews_first_message_is_the_pages_word_for_word(story):
    # Two past reviews found: the heading gives the real count.
    [call] = review_sent(story, story["positionAtClose"], True, 2)
    assert text_of(call.messages[-1]) == story["reviewFirstAtClose"]
