"""The slice's tests: the LLM benchmark command on made-up saved moments with fake answers (spec
appendix 9, section 8). Nothing here reaches a model, Jev, the database or the memory server.

What the tests hand the command (`main(argv, parts_for=...)`):

- Made-up moments of one made-up asset, numbered in their situation text ("Made-up moment 3.").
  Each opens with the same first search: four made-up past episodes A, B, C and D, which the
  model sees as E1 to E4.
- The real runner (`SelectionRunner`) over the real selection step (`LlmSelector`), its chat
  model a fake one per LLM: a plan says what it replies at each attempt at each moment, and
  each reply may take seconds on a fake clock, cost tokens, or be an error to raise.
- A log that only keeps the attempts it is handed, for the tests to read.

What the tests read, and so what the report must hold (spec appendix 9, section 8):

- Models by their names in `config/llm.toml`: "claude-haiku-5-5", "glm-5.3-flash".
- How many attempts went wrong, as "<n> of <attempts>" on a line naming the model.
- A model left out on a line naming it with "left out"; a model kept never shares a line with
  "left out" (unless it reads "not left out"). Both left out: the report says "the developer
  decides".
- Each selection overlap on one line naming the job ("full evaluation" or "position review"),
  the model, and the other model or "itself", its average then its standard deviation as
  percentages ("75%" or "75.0%"). The standard deviation says how far the pairs typically sit
  from the average: pairs of 50% and 100% average 75%, each 25 points away, so it is 25%; it is
  the plain one over every pair (`statistics.pstdev`, not the sample one), and both are
  compared rounded to a whole percent.
- An early stop names the cap, "$1.50", in the report and on the command's output. The meter
  adds whole cents (or allows a hair of rounding): in a computer, fourteen $0.10 attempts add up
  to a hair over $1.40, and the made-up run must still let the fifteenth through to $1.50.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from jev_trader.benchmark import __main__ as command
from jev_trader.benchmark.attempts import Attempt, Outcome
from jev_trader.benchmark.moments import SavedMoment
from jev_trader.benchmark.runner import SelectionRunner
from jev_trader.benchmark.spending import SpendMeter
from jev_trader.jev.client import JevClient
from jev_trader.llm import clients
from jev_trader.llm.selection import LlmSelector, ReviewedPosition, Situation
from jev_trader.llm.wording import ANSWER_TOOL
from jev_trader.memory.episodes import Episode, Standing
from jev_trader.memory.lookups import Episodes, Found, SearchResult
from jev_trader.memory.track_record import TrackRecord

HAIKU, GLM = "claude-haiku-5-5", "glm-5.3-flash"
CAP_USD = 1.50
FULL, REVIEW = "full evaluation", "position review"


# The made-up moments, and the four past episodes their first search shows


def past(n: int) -> Episode:
    return Episode(
        id=f"12-{n}-ASSET_01",
        kind="full_evaluation",
        asset="ASSET_01",
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


PAST = {letter: past(n) for n, letter in enumerate("ABCD", start=1)}
LABELS = {letter: f"E{n}" for n, letter in enumerate("ABCD", start=1)}
FIRST_SEARCH = SearchResult(
    episodes=[
        Found(episode=e, vector_rank=r, text_rank=r, merged_rank=r)
        for r, e in enumerate(PAST.values(), start=1)
    ]
)
OPEN_POSITION = ReviewedPosition(
    Standing(
        direction="long",
        put_in=1000.0,
        bars_open=3,
        profit=4.0,
        percent=0.4,
        stop_distance=0.01,
        best=6.0,
        worst=-2.0,
    )
)


def moment(n: int, review: bool = False) -> SavedMoment:
    return SavedMoment(
        sim=12,
        situation=Situation(
            asset="ASSET_01",
            asset_class="crypto",
            step=1000 + n,
            text=f"Made-up moment {n}.",
            patterns=(),
            playbook={},
            position=OPEN_POSITION if review else None,
        ),
        first_search=FIRST_SEARCH,
    )


def moments(full: int, reviews: int) -> list[SavedMoment]:
    """`full` full evaluations numbered from 1, then `reviews` position reviews."""
    return [moment(n) for n in range(1, full + 1)] + [
        moment(n, review=True) for n in range(full + 1, full + reviews + 1)
    ]


class FakeLookups:
    def search(self, **filters):
        return FIRST_SEARCH

    def read(self, episode_ids):
        by_id = {e.id: e for e in PAST.values()}
        return Episodes(episodes=[by_id[i] for i in episode_ids if i in by_id])

    def track_record(self, pattern, direction):
        return TrackRecord(
            pattern=pattern,
            direction=direction,
            asset_class="crypto",
            minimum_sample=10,
            closed_trades=0,
            groups=[],
        )


# The fake LLMs


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


# A plan: (the moment's number, the attempt at it from 1) to the attempt's replies, in order.
Plan = Callable[[int, int], list]


class FakeModel(BaseChatModel):
    """One LLM, answering from its plan. An attempt starts when the replies of the last one
    are used up; each reply is (seconds it takes on the fake clock, an `AIMessage` or an error
    to raise)."""

    plan: Plan
    clock: FakeClock
    attempts: dict = Field(default_factory=dict)  # attempts so far, by moment
    replies: list = Field(default_factory=list)  # left in the attempt under way

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self.bind(**kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if not self.replies:
            shown = "\n".join(str(m.content) for m in messages)
            number = int(re.search(r"Made-up moment (\d+)\.", shown).group(1))
            self.attempts[number] = self.attempts.get(number, 0) + 1
            self.replies = list(self.plan(number, self.attempts[number]))
        seconds, reply = self.replies.pop(0)
        self.clock.now += seconds
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])


def answers(letters, seconds: float = 2.0, tokens_in: int | None = None):
    """A reply naming the past episodes `letters` ("ABC") by their labels."""
    usage = None
    if tokens_in is not None:
        usage = {
            "input_tokens": tokens_in,
            "output_tokens": 0,
            "total_tokens": tokens_in,
        }
    call = {
        "name": ANSWER_TOOL,
        "args": {"episode_ids": [LABELS[x] for x in letters], "note": "Made-up note."},
        "id": "call_1",
        "type": "tool_call",
    }
    return (seconds, AIMessage(content="", tool_calls=[call], usage_metadata=usage))


def says(sentence: str = "I would pick E1."):
    """A reply code cannot use: a sentence where a tool call was required."""
    return (2.0, AIMessage(content=sentence))


def provider_fails():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return (1.0, anthropic.APIConnectionError(request=request))


def picks(by_moment: dict[int, str]) -> Plan:
    """Every attempt at moment n names the episodes `by_moment[n]`."""
    return lambda number, attempt: [answers(by_moment[number])]


# The benchmark command over them


class KeptLog:
    def __init__(self):
        self.attempts: list[Attempt] = []

    def keep(self, attempt: Attempt) -> None:
        self.attempts.append(attempt)


@dataclass
class Bench:
    """One run of the command on `saved`, each model in `plans` answering from its plan."""

    tmp_path: Path
    saved: list[SavedMoment]
    plans: dict[str, Plan]
    log: KeptLog = field(default_factory=KeptLog)

    def run(self) -> int:
        clock = FakeClock()
        fakes = {name: FakeModel(plan=p, clock=clock) for name, p in self.plans.items()}

        def selector_for(settings):
            return LlmSelector(settings, model=fakes[settings.name], clock=clock)

        runner = SelectionRunner(lambda context: FakeLookups(), selector_for)

        def parts_for(args, held):
            return command.Parts(self.saved, runner, self.log)

        alone = ["--model", *self.plans] if len(self.plans) == 1 else []
        argv = ["--sim", "12", "--report", str(self.report_file), *alone]
        return command.main(argv, parts_for=parts_for)

    @property
    def report_file(self) -> Path:
        return self.tmp_path / "llm-benchmark.md"

    @property
    def page(self) -> str:
        return self.report_file.read_text(encoding="utf-8")

    def outcomes(self, model: str) -> list[Outcome]:
        return [a.outcome for a in self.log.attempts if a.model.endswith(":" + model)]


# Reading the report


def lines(page: str, *words: str) -> list[str]:
    """The report's lines holding every one of `words`, in any capitals."""
    return [
        line
        for line in page.splitlines()
        if all(word.lower() in line.lower() for word in words)
    ]


def overlap(page: str, job: str, model: str, other: str) -> tuple[float, float]:
    """The average and standard deviation of `model`'s selection overlap with `other` (a model,
    or "itself") in `job`, as whole percentages."""
    found = [
        line
        for line in lines(page, job, model, other)
        if "%" in line and (other == "itself" or "itself" not in line.lower())
    ]
    assert found, f"no line on {model} against {other} in a {job}:\n{page}"
    average, deviation = re.findall(r"(\d+(?:\.\d+)?)\s*%", found[0])[:2]
    return round(float(average)), round(float(deviation))


def left_out(page: str, model: str) -> bool:
    return any(
        "not left out" not in line.lower() for line in lines(page, model, "left out")
    )


def went_wrong(page: str, model: str, count: int, attempts: int) -> bool:
    return bool(lines(page, model, f"{count} of {attempts}"))


# A run trades nothing and touches no real model


def test_a_made_up_run_trades_nothing_and_touches_no_real_model(
    tmp_path, capsys, monkeypatch
):
    def refused(*args, **kwargs):
        raise AssertionError("a made-up run reached a real service")

    monkeypatch.setattr(clients, "chat_model", refused)
    monkeypatch.setattr(JevClient, "__init__", refused)
    monkeypatch.setattr(command, "open_database", refused)
    monkeypatch.setattr(command, "Connection", refused)
    monkeypatch.setattr(command, "load_dotenv", refused)
    report_file = tmp_path / "llm-benchmark.md"

    assert command.main(["--made-up", "--report", str(report_file)]) == 0

    # Four made-up moments, two models, three passes: 24 attempts at $0.10 each; the $1.50 cap
    # lets 15 through and stops the run before the 16th.
    out = capsys.readouterr().out
    assert "15 attempts" in out
    assert "Stopped early" in out and "$1.50" in out
    page = report_file.read_text(encoding="utf-8")
    assert HAIKU in page and GLM in page
    assert "$1.50" in page


def test_a_run_hands_every_moment_to_each_model_three_times(tmp_path):
    bench = Bench(
        tmp_path,
        moments(full=2, reviews=2),
        {
            HAIKU: picks(dict.fromkeys(range(1, 5), "AB")),
            GLM: picks(dict.fromkeys(range(1, 5), "AB")),
        },
    )

    assert bench.run() == 0

    for model in (HAIKU, GLM):
        assert bench.outcomes(model) == [Outcome.FINE] * 12
        assert went_wrong(bench.page, model, 0, 12)
        assert not left_out(bench.page, model)
    named = {a.episode_ids for a in bench.log.attempts}
    assert named == {(PAST["A"].id, PAST["B"].id)}


# The three ways of going wrong, and who is left out


WRONG = {
    "a sentence where a tool call was required": (
        [says(), answers("A")],
        Outcome.FAILED_REPLY,
    ),
    "three replies code cannot use": ([says(), says(), says()], Outcome.FAILED_REPLY),
    "the 60-second limit": ([answers("A", seconds=61.0)], Outcome.TIME_LIMIT),
    "a call still failing after 3 retries": (
        [provider_fails()] * 4,
        Outcome.RETRIES_USED_UP,
    ),
}


@pytest.mark.parametrize("kind", list(WRONG))
def test_each_way_of_going_wrong_counts_as_one_failed_attempt(tmp_path, kind):
    replies, outcome = WRONG[kind]

    def plan(number, attempt):
        return list(replies) if attempt == 1 else [answers("A")]

    bench = Bench(tmp_path, [moment(1)], {HAIKU: plan})

    assert bench.run() == 0

    assert bench.outcomes(HAIKU) == [outcome, Outcome.FINE, Outcome.FINE]
    assert went_wrong(bench.page, HAIKU, 1, 3)


def going_wrong_at(wrong: dict[int, str]) -> Plan:
    """The first attempt at each moment in `wrong` goes wrong the way named; every other
    attempt names episode A."""

    def plan(number, attempt):
        if attempt == 1 and number in wrong:
            return list(WRONG[wrong[number]][0])
        return [answers("A")]

    return plan


SENTENCE, THREE_SENTENCES, TIME_LIMIT, RETRIES = WRONG


def test_more_than_10_in_100_attempts_leaves_a_model_out(tmp_path):
    # Five full evaluations (moments 1 to 5) and five position reviews (6 to 10), three passes:
    # 30 attempts each. Haiku goes wrong 3 times, all in full evaluations: 3 of its 15 full
    # evaluations (20%), but the two jobs count together, 3 of 30 (10%), not more than 10 in
    # 100. GLM goes wrong 4 times, each way at least once: 4 of 30 (13%).
    bench = Bench(
        tmp_path,
        moments(full=5, reviews=5),
        {
            HAIKU: going_wrong_at({1: SENTENCE, 2: TIME_LIMIT, 3: RETRIES}),
            GLM: going_wrong_at(
                {1: SENTENCE, 2: THREE_SENTENCES, 6: TIME_LIMIT, 7: RETRIES}
            ),
        },
    )

    assert bench.run() == 0

    assert sum(o is not Outcome.FINE for o in bench.outcomes(HAIKU)) == 3
    assert sum(o is not Outcome.FINE for o in bench.outcomes(GLM)) == 4
    assert went_wrong(bench.page, HAIKU, 3, 30)
    assert went_wrong(bench.page, GLM, 4, 30)
    assert not left_out(bench.page, HAIKU)
    assert left_out(bench.page, GLM)
    assert not lines(bench.page, "the developer decides")


def test_when_both_models_are_left_out_the_developer_decides(tmp_path):
    four_wrong = {1: SENTENCE, 2: THREE_SENTENCES, 6: TIME_LIMIT, 7: RETRIES}
    bench = Bench(
        tmp_path,
        moments(full=5, reviews=5),
        {HAIKU: going_wrong_at(four_wrong), GLM: going_wrong_at(four_wrong)},
    )

    assert bench.run() == 0

    assert left_out(bench.page, HAIKU)
    assert left_out(bench.page, GLM)
    assert lines(bench.page, "the developer decides")


# Selection overlap: the episodes in both divided by the episodes in either


@pytest.mark.parametrize(
    "haiku, glm, expected",
    [
        ("ABC", "BCD", 50),  # B and C in both, A, B, C and D in either: 2 of 4
        ("", "", 100),  # two empty selections count as alike
        ("AB", "AB", 100),
        ("A", "B", 0),
        ("ABCD", "A", 25),
    ],
)
def test_selection_overlap_worked_by_hand(tmp_path, haiku, glm, expected):
    bench = Bench(
        tmp_path, [moment(1)], {HAIKU: picks({1: haiku}), GLM: picks({1: glm})}
    )

    assert bench.run() == 0

    assert overlap(bench.page, FULL, HAIKU, GLM) == (expected, 0)


def test_selection_overlap_between_the_models_for_each_job(tmp_path):
    # Full evaluations: 50% at moment 1, 100% at moment 2 (both name none): average 75%, each
    # pair 25 points from it. Position reviews: 100% at moment 3, 0% at moment 4: average 50%,
    # each pair 50 points from it. Each model names the same at every pass: 100% with itself.
    haiku = {1: "ABC", 2: "", 3: "AB", 4: "A"}
    glm = {1: "BCD", 2: "", 3: "AB", 4: "B"}
    bench = Bench(
        tmp_path, moments(full=2, reviews=2), {HAIKU: picks(haiku), GLM: picks(glm)}
    )

    assert bench.run() == 0

    assert overlap(bench.page, FULL, HAIKU, GLM) == (75, 25)
    assert overlap(bench.page, REVIEW, HAIKU, GLM) == (50, 50)
    for model in (HAIKU, GLM):
        for job in (FULL, REVIEW):
            assert overlap(bench.page, job, model, "itself") == (100, 0)


def test_selection_overlap_of_a_model_with_itself_across_its_passes(tmp_path):
    # GLM alone. Moment 1: B, C, D at every pass, so its three pairs of passes are 100%.
    # Moment 2: A, then A, then A, B, C and D: the pairs are 100%, 25% and 25%. Over the six
    # pairs of the full evaluations: average 75%; the pairs sit 25 or 50 points from it, a standard
    # deviation of about 35%.
    wobble = {1: "A", 2: "A", 3: "ABCD"}

    def plan(number, attempt):
        letters = {1: "BCD", 2: wobble[attempt], 3: "AB", 4: "AB"}[number]
        return [answers(letters)]

    bench = Bench(tmp_path, moments(full=2, reviews=2), {GLM: plan})

    assert bench.run() == 0

    assert overlap(bench.page, FULL, GLM, "itself") == (75, 35)
    assert overlap(bench.page, REVIEW, GLM, "itself") == (100, 0)
    assert HAIKU not in bench.page


# The stop at $1.50


def test_the_spend_meter_adds_up_what_each_attempt_cost():
    meter = SpendMeter(CAP_USD)
    meter.add(0.25)
    meter.add(0.15)

    assert meter.spent_usd == pytest.approx(0.40)
    meter.check()  # $0.40 of $1.50: the run goes on


def test_a_model_whose_cost_climbs_past_the_cap_makes_the_tool_stop_itself(
    tmp_path, capsys
):
    # Haiku alone on four full evaluations, three passes: 12 attempts if nothing stops it. Its
    # k-th attempt reads 500,000 tokens k times over, at $0.10 a million: $0.05 times k. The
    # total climbs $0.05, $0.15, $0.30, $0.50, $0.75, $1.05, $1.40, $1.80, ...
    attempts_so_far = []

    def plan(number, attempt):
        attempts_so_far.append(number)
        return [answers("A", tokens_in=500_000 * len(attempts_so_far))]

    bench = Bench(tmp_path, moments(full=4, reviews=0), {HAIKU: plan})

    assert bench.run() == 0

    spent = sum(a.cost_usd for a in bench.log.attempts)
    assert len(bench.log.attempts) < 12
    assert 1.00 <= spent <= CAP_USD
    out = capsys.readouterr().out
    assert "Stopped early" in out and "$1.50" in out
    assert "$1.50" in bench.page
