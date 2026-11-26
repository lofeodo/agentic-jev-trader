"""The benchmark's one-page report, in plain words, made from the attempts' figures (never from
model text) and committed to the repo (spec appendix 9, section 8).

What decides: a model is left out of the measurement sims when more than 10 in 100 of its
attempts went wrong (both jobs counted together); if both are, work stops and the developer
decides. What it shows, deciding nothing: selection overlap per job (the episodes two selections
share divided by the episodes in either: A, B, C against B, C, D is 2 of 4, or 50%), the cost,
and each model's habits (seconds, lookups, replies that were not a tool call, IDs never shown).

The page is built in two steps: the figures first (`figures`, plain data), then the words
(`render`), so no sentence comes from a model.

Choices the spec leaves to the build:

- The failure rate is out of the attempts actually made (150 in a whole run; fewer when the
  cap stops it early), and "more than 10 in 100" is checked in whole numbers: 16 of 150 is out,
  15 of 150 is not. The "both left out" line needs two models: one model run alone
  (`--model`) and left out gets only its own verdict.
- Selection overlap compares only attempts that ended with a selection (an attempt stopped
  before the model named anything has none). A model against itself compares every pair of its
  passes at the same moment (three passes make three pairs); against the other model, every
  pass of one with every pass of the other at the same moment (nine pairs). The standard
  deviation is the plain one over every pair (`statistics.pstdev`).
- An evaluation's seconds are the time its calls and lookups took, added up.
- A failed reply that stopped its attempt (the third) left no selection, so an attempt that
  went wrong by failed replies and holds no selection counts as stopped by three, its three
  replies counted.
- An episode ID named but never shown is counted from the selection's "unknown episode ID"
  events.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path

from jev_trader.benchmark.attempts import Attempt, Outcome
from jev_trader.benchmark.runner import BenchmarkRun
from jev_trader.llm.selection import UNKNOWN_ID_EVENT, LimitHit, SelectionLimits
from jev_trader.memory.search import FULL_EVALUATION, POSITION_REVIEW, Job

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "llm-benchmark.md"

JOBS: tuple[Job, ...] = (FULL_EVALUATION, POSITION_REVIEW)
JOB_WORDS = {FULL_EVALUATION: "full evaluation", POSITION_REVIEW: "position review"}

# Left out when more than LEFT_OUT_PER_100 attempts in 100 went wrong.
LEFT_OUT_PER_100 = 10
LIMITS = SelectionLimits()


# The figures


@dataclass(frozen=True)
class ModelFigures:
    """One model's figures over all its attempts, both jobs together."""

    name: str  # "claude-haiku-5-5"
    attempts: int
    went_wrong: dict[Outcome, int]  # by way of going wrong, zero counts left out
    cost_usd: float
    price_usd: dict[Job, float | None]  # average cost of one attempt, per job
    tokens_in: int
    cached_tokens: int
    tokens_out: int
    thinking_tokens: int
    seconds: float | None  # average per attempt
    lookups: float | None  # average per attempt that ended with a selection
    lookup_limit_reached: int
    failed_replies: int
    stopped_by_failed_replies: int
    unknown_ids: int

    @property
    def wrong(self) -> int:
        return sum(self.went_wrong.values())

    @property
    def left_out(self) -> bool:
        return self.wrong * 100 > LEFT_OUT_PER_100 * self.attempts


@dataclass(frozen=True)
class Overlap:
    """The selection overlap of `model` with `other` (another model, or None for itself) in one
    job, over `pairs` pairs of selections; the average and standard deviation as fractions."""

    job: Job
    model: str
    other: str | None
    pairs: int
    average: float | None
    deviation: float | None


@dataclass(frozen=True)
class Figures:
    models: tuple[ModelFigures, ...]
    overlaps: tuple[Overlap, ...]
    stopped: str | None

    @property
    def all_left_out(self) -> bool:
        return len(self.models) > 1 and all(m.left_out for m in self.models)


def name_of(attempt: Attempt) -> str:
    """The model's name in `config/llm.toml`: "claude-haiku-5-5"."""
    return attempt.model.partition(":")[2] or attempt.model


def selected(attempt: Attempt) -> bool:
    """Whether the attempt ended with episodes named (none is a valid answer)."""
    return attempt.selection is not None or attempt.outcome is Outcome.FINE


def overlap_of(first: tuple[str, ...], second: tuple[str, ...]) -> float:
    """The episodes in both divided by the episodes in either; two empty count as alike."""
    either = set(first) | set(second)
    if not either:
        return 1.0
    return len(set(first) & set(second)) / len(either)


def model_figures(name: str, attempts: list[Attempt]) -> ModelFigures:
    went_wrong: dict[Outcome, int] = {}
    for attempt in attempts:
        if attempt.went_wrong:
            went_wrong[attempt.outcome] = went_wrong.get(attempt.outcome, 0) + 1
    price: dict[Job, float | None] = {}
    for job in JOBS:
        costs = [a.cost_usd for a in attempts if a.moment.job == job]
        price[job] = sum(costs) / len(costs) if costs else None
    calls = [call for a in attempts for call in a.calls]
    selections = [a.selection for a in attempts if a.selection is not None]
    seconds = [
        sum(call.latency_seconds for call in a.calls)
        + sum(
            lookup.latency_seconds
            for lookup in (a.selection.lookups if a.selection else ())
        )
        for a in attempts
    ]
    stopped_by_three = sum(
        a.outcome is Outcome.FAILED_REPLY and a.selection is None for a in attempts
    )
    return ModelFigures(
        name=name,
        attempts=len(attempts),
        went_wrong=went_wrong,
        cost_usd=sum(a.cost_usd for a in attempts),
        price_usd=price,
        tokens_in=sum(a.tokens_in for a in attempts),
        cached_tokens=sum(call.cached_tokens or 0 for call in calls),
        tokens_out=sum(a.tokens_out for a in attempts),
        thinking_tokens=sum(call.thinking_tokens or 0 for call in calls),
        seconds=statistics.fmean(seconds) if seconds else None,
        lookups=(
            statistics.fmean(len(s.lookups) for s in selections) if selections else None
        ),
        lookup_limit_reached=sum(s.limit_hit is LimitHit.LOOKUPS for s in selections),
        failed_replies=sum(len(s.failed_replies) for s in selections)
        + stopped_by_three * LIMITS.failed_replies_to_stop,
        stopped_by_failed_replies=stopped_by_three,
        unknown_ids=sum(
            event.kind == UNKNOWN_ID_EVENT for s in selections for event in s.events
        ),
    )


def overlap(
    job: Job, model: str, other: str | None, pairs: list[tuple[Attempt, Attempt]]
) -> Overlap:
    values = [overlap_of(a.episode_ids, b.episode_ids) for a, b in pairs]
    return Overlap(
        job=job,
        model=model,
        other=other,
        pairs=len(values),
        average=statistics.fmean(values) if values else None,
        deviation=statistics.pstdev(values) if values else None,
    )


def figures(run: BenchmarkRun) -> Figures:
    by_model: dict[str, list[Attempt]] = defaultdict(list)
    for attempt in run.attempts:
        by_model[name_of(attempt)].append(attempt)
    names = list(by_model)
    # (job, model) to each moment's attempts that ended with a selection, in pass order.
    at_moment: dict[tuple[Job, str], dict[str, list[Attempt]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for attempt in run.attempts:
        if selected(attempt):
            key = (attempt.moment.job, name_of(attempt))
            at_moment[key][attempt.moment.id].append(attempt)
    overlaps = []
    for job in JOBS:
        for name in names:
            mine = at_moment[(job, name)]
            pairs = [pair for tried in mine.values() for pair in combinations(tried, 2)]
            overlaps.append(overlap(job, name, None, pairs))
        for name, other in combinations(names, 2):
            mine, theirs = at_moment[(job, name)], at_moment[(job, other)]
            pairs = [
                pair
                for moment_id, tried in mine.items()
                for pair in product(tried, theirs.get(moment_id, []))
            ]
            overlaps.append(overlap(job, name, other, pairs))
    return Figures(
        models=tuple(model_figures(n, by_model[n]) for n in names),
        overlaps=tuple(overlaps),
        stopped=run.stopped,
    )


# The words


OUTCOME_WORDS = {
    Outcome.FAILED_REPLY: "failed replies",
    Outcome.TIME_LIMIT: f"{LIMITS.seconds:.0f}-second limit reached",
    Outcome.RETRIES_USED_UP: "calls still failing after 3 retries",
}


def percent(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def dollars(amount: float | None) -> str:
    return "no attempts" if amount is None else f"${amount:.4f}"


def verdict_line(model: ModelFigures) -> str:
    if model.attempts == 0:
        return f"- **{model.name}**: no attempts made, so not left out."
    ways = ", ".join(
        f"{OUTCOME_WORDS[outcome]} {count}"
        for outcome, count in model.went_wrong.items()
    )
    share = percent(model.wrong / model.attempts)
    verdict = (
        "**Left out** of the measurement sims"
        if model.left_out
        else "Kept: not left out"
    )
    detail = f" ({ways})" if ways else ""
    return (
        f"- **{model.name}**: {model.wrong} of {model.attempts} attempts went wrong, "
        f"{share}{detail}. {verdict}."
    )


def overlap_line(item: Overlap) -> str:
    job = JOB_WORDS[item.job].capitalize()
    against = "itself" if item.other is None else item.other
    if item.average is None or item.deviation is None:
        return f"- {job}, {item.model} against {against}: no pairs to compare."
    return (
        f"- {job}, {item.model} against {against}: {percent(item.average)} on average, "
        f"standard deviation {percent(item.deviation)}, over {item.pairs} pair{'' if item.pairs == 1 else 's'}."
    )


def render(shown: Figures) -> str:
    out = [
        "# LLM benchmark",
        "",
        (
            "Each LLM was handed the same saved moments from the build-up sim, three times each, "
            "and asked to pick the past episodes worth showing Jev. Nothing was traded and Jev was "
            "not asked. This page is written by code from the attempts' figures "
            "(`python -m jev_trader.benchmark`, spec appendix 9, section 8)."
        ),
        "",
    ]
    if shown.stopped:
        out += [f"**The run stopped itself early:** {shown.stopped}", ""]
    out += [
        "## Who is left out",
        "",
        (
            "An attempt goes wrong in one of three ways: a failed reply (an answer code cannot "
            "use, such as a sentence where a tool call was required), the "
            f"{LIMITS.seconds:.0f}-second limit reached, "
            "or a call still failing after 3 retries. A model whose attempts go wrong more than "
            f"{LEFT_OUT_PER_100} "
            "times in 100 (more than 15 of its 150, both jobs together) sits out the measurement "
            "sims."
        ),
        "",
    ]
    out += [verdict_line(model) for model in shown.models] or ["- No attempts made."]
    out.append("")
    if shown.all_left_out:
        out += [
            "**Both models are left out: work stops and the developer decides.**",
            "",
        ]
    out += [
        "## Selection overlap",
        "",
        (
            "How alike two sets of picked episodes are: the episodes in both divided by the "
            "episodes in either. A, B, C against B, C, D is 2 of 4, or 50%; two empty sets count "
            "as 100%. The standard deviation says how far the pairs typically sit from the "
            "average: pairs of 50% and 100% average 75%, each 25 points away, so it is 25%. If a "
            "model agrees with itself 70% of the time and with the other model 65%, the two choose "
            "about alike. This decides nothing."
        ),
        "",
    ]
    out += [overlap_line(item) for item in shown.overlaps] or ["- No attempts made."]
    out += [
        "",
        "## Cost",
        "",
        (
            "What the attempts cost, thinking (the model's private reasoning, billed like written "
            "text) and the saving from prompt caching (text the provider has seen before, read at "
            "a lower price) included. The price per job is the average attempt: an early guess at "
            "what one full evaluation or one position review costs in a sim, before Jev's own "
            "price. Example: at $0.0040 a full evaluation, 250 of them cost $1.00."
        ),
        "",
    ]
    for model in shown.models:
        out.append(
            f"- **{model.name}**: ${model.cost_usd:.2f} in all; "
            f"{dollars(model.price_usd[FULL_EVALUATION])} per full evaluation, "
            f"{dollars(model.price_usd[POSITION_REVIEW])} per position review. Tokens "
            f"(pieces of words) read {model.tokens_in:,}, of them from the cache "
            f"{model.cached_tokens:,}; written {model.tokens_out:,}, of them thinking "
            f"{model.thinking_tokens:,}."
        )
    out += [
        "",
        "## Habits",
        "",
        (
            "Per model, over every attempt, both jobs together. A model that often fails to call "
            "a tool is a poor fit however cheap it is, but these figures decide nothing."
        ),
        "",
    ]
    for model in shown.models:
        seconds = "-" if model.seconds is None else f"{model.seconds:.1f}"
        lookups = "-" if model.lookups is None else f"{model.lookups:.1f}"
        out += [
            f"- **{model.name}**",
            f"  - Seconds per evaluation, on average: {seconds}",
            (
                f"  - Lookups per evaluation, on average (the limit is "
                f"{LIMITS.most_lookups}): {lookups}"
            ),
            (
                f"  - Evaluations that reached the limit of {LIMITS.most_lookups} lookups: "
                f"{model.lookup_limit_reached}"
            ),
            f"  - Replies that were not a usable tool call: {model.failed_replies}",
            (
                f"  - Evaluations stopped by three such replies: "
                f"{model.stopped_by_failed_replies}"
            ),
            f"  - Episode IDs named that were never shown: {model.unknown_ids}",
        ]
    out.append("")
    return "\n".join(out)


def report(run: BenchmarkRun) -> str:
    """The report page for every attempt of `run`, and its early stop if it had one."""
    return render(figures(run))
