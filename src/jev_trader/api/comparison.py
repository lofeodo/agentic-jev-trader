"""The Comparison screen's read: the project's answer (spec appendix 9 sections 6 and 8, appendix
7 section 10, appendix 8 section 8.4; `GET /comparison`).

For each test period ("market") on its own, and each LLM on its own, the verdict compares the
average ending account value of the model's sims with memory against the sims without memory.
The threshold is one standard deviation of the repeats, pooled across the two groups: the square
root of the average of the two groups' squared standard deviations, each worked out dividing by
one less than the count. Memory helped if the difference is above the threshold, hurt if it is
below minus the threshold, and otherwise can't tell. The two markets are never merged.

Beside the verdicts, per market: the performance winner (the model whose sims with memory ended
higher on average, by the same test), the price winner (fewer real LLM dollars per full
evaluation or position review, no margin), each repeat, and the gap over time.

Worked out from stored records when asked for; nothing is stored.

Choices the spec leaves to the build:

- A market is the measurement sims of one dataset sharing a test period's name.
- Only finished sims count. A sim still running or stopped is listed in its repeat but stays
  out of every average, price and speed. A group needs two finished sims for a standard
  deviation, so until both groups have two the verdict is "waiting".
- The price counts the LLM's calls only: Jev's calls are asked the same way for both models.
- The gap over time is, at the end of each UTC day, the average account value of the model's
  finished sims with memory minus that of the finished sims without.
- The Jev versions are those that answered any sim of the market, finished or not.
"""

import math
import statistics
from datetime import date, timedelta

from pydantic import BaseModel

from jev_trader.api.llm_names import llm_model, model_label
from jev_trader.api.store import ApiStore
from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.sim.clock import day_of
from jev_trader.sim.store import SimStatus

MEASUREMENT = "measurement"
MEMORY_ON, MEMORY_OFF = "memory_on", "memory_off"
HELPED, HURT, CANT_TELL, WAITING = "helped", "hurt", "can't tell", "waiting"


class Group(BaseModel):
    """The finished sims of one side: their ending account values, average and spread."""

    ending_values_usd: list[float]
    average_usd: float | None
    standard_deviation_usd: float | None  # None with fewer than two sims


class ModelResult(BaseModel):
    model: str  # "claude-haiku-5-5"
    label: str  # "Claude Haiku"
    with_memory: Group
    difference_usd: float | None  # with memory's average minus without memory's
    threshold_usd: float | None  # one standard deviation, pooled across the two groups
    verdict: str  # helped, hurt, can't tell, or waiting
    says: str
    # Real LLM dollars per full evaluation or position review, thinking included; None
    # before any.
    usd_per_evaluation_or_review: float | None
    # Every call of a full evaluation (Jev's and the LLM's) added up, averaged.
    seconds_per_full_evaluation: float | None
    # How many times the LLM searched memory per full evaluation. Not recorded yet: the agent
    # with memory will store its lookups.
    lookups_per_full_evaluation: float | None
    models_returned: list[str]  # the model names the LLM's provider returned


class PerformanceWinner(BaseModel):
    """Which model's sims with memory ended higher, by the verdict's own test."""

    winner: str | None  # the model; None when the gap is within the spread, or waiting
    gap_usd: float | None  # the higher average minus the lower
    threshold_usd: float | None
    says: str


class PriceWinner(BaseModel):
    """Which model cost fewer real dollars per full evaluation or position review, dollar for dollar, no margin."""

    winner: str | None  # None until both have a price, or if they cost exactly the same
    says: str


class RepeatSim(BaseModel):
    sim_id: int
    label: str  # "With memory / Claude Haiku", "Without memory"
    model: str | None  # the LLM, for a sim with memory
    status: str
    ending_value_usd: float | None  # once finished


class Repeat(BaseModel):
    number: int | None
    sims: list[RepeatSim]


class GapPoint(BaseModel):
    day: date | None  # the real UTC day; None if the dataset has no asset key
    gap_usd: (
        float  # with memory's average account value minus without's, at the day's end
    )


class GapLine(BaseModel):
    model: str
    label: str
    points: list[GapPoint]


class MarketComparison(BaseModel):
    dataset: int
    market: str  # "falling market"
    first_day: date | None
    last_day: date | None
    starting_value_usd: float
    without_memory: Group
    models: list[ModelResult]
    performance: PerformanceWinner | None  # None unless two models played this market
    price: PriceWinner | None  # None unless two models played this market
    repeats: list[Repeat]
    gap_over_time: list[GapLine]
    jev_versions: list[str]  # every Jev version that answered
    notes: list[str]  # what changed between the sims compared, in plain words


class Comparison(BaseModel):
    markets: list[MarketComparison]


def _usd(value: float) -> str:
    return f"${value:,.0f}"


def _ratio(top: float, bottom: float) -> float | None:
    return top / bottom if bottom else None


def _group(values: list[float]) -> Group:
    return Group(
        ending_values_usd=values,
        average_usd=statistics.mean(values) if values else None,
        standard_deviation_usd=statistics.stdev(values) if len(values) > 1 else None,
    )


def pooled(a: Group, b: Group) -> float | None:
    """One standard deviation across two groups: the root of the average of their squares."""
    if a.standard_deviation_usd is None or b.standard_deviation_usd is None:
        return None
    return math.sqrt((a.standard_deviation_usd**2 + b.standard_deviation_usd**2) / 2)


def verdict(memory: Group, without: Group) -> tuple[str, float | None, float | None]:
    """(verdict, difference, threshold) for one model's sims with memory against without."""
    threshold = pooled(memory, without)
    if threshold is None or memory.average_usd is None or without.average_usd is None:
        return WAITING, None, None
    difference = memory.average_usd - without.average_usd
    if difference > threshold:
        return HELPED, difference, threshold
    if difference < -threshold:
        return HURT, difference, threshold
    return CANT_TELL, difference, threshold


def _verdict_says(label: str, found: str, difference, threshold) -> str:
    if found == WAITING:
        return (
            "Waiting: each side needs at least two finished repeats to say whether memory "
            f"helped {label}."
        )
    gap = (
        f"With memory ({label}) the account ended {_usd(abs(difference))} "
        f"{'higher' if difference >= 0 else 'lower'} on average than without, and the "
        f"repeats themselves typically land {_usd(threshold)} apart."
    )
    return {
        HELPED: f"{gap} The gap is larger than that spread: memory helped.",
        HURT: f"{gap} The gap is larger than that spread: memory hurt.",
        CANT_TELL: f"{gap} The gap is within that spread: can't tell.",
    }[found]


def _performance(results: list[ModelResult]) -> PerformanceWinner | None:
    if len(results) != 2:
        return None
    first, second = results
    a, b = first.with_memory, second.with_memory
    threshold = pooled(a, b)
    if threshold is None or a.average_usd is None or b.average_usd is None:
        return PerformanceWinner(
            winner=None,
            gap_usd=None,
            threshold_usd=None,
            says="Waiting: each model needs at least two finished repeats with memory.",
        )
    higher, lower = (
        (first, second) if a.average_usd >= b.average_usd else (second, first)
    )
    gap = abs(a.average_usd - b.average_usd)
    ahead = (
        f"With memory, {higher.label}'s sims ended {_usd(gap)} higher on average than "
        f"{lower.label}'s, and the repeats typically land {_usd(threshold)} apart."
    )
    if gap > threshold:
        return PerformanceWinner(
            winner=higher.model,
            gap_usd=gap,
            threshold_usd=threshold,
            says=f"{ahead} {higher.label} is the performance winner.",
        )
    return PerformanceWinner(
        winner=None,
        gap_usd=gap,
        threshold_usd=threshold,
        says=f"{ahead} The gap is within that spread: no performance winner.",
    )


def _price(results: list[ModelResult]) -> PriceWinner | None:
    if len(results) != 2:
        return None
    first, second = results
    a, b = first.usd_per_evaluation_or_review, second.usd_per_evaluation_or_review
    if a is None or b is None:
        return PriceWinner(
            winner=None,
            says="Waiting: each model needs a finished sim with memory that made a full "
            "evaluation or position review.",
        )
    if a == b:
        return PriceWinner(
            winner=None,
            says=f"Both cost ${a:.4f} per full evaluation or position review: no price "
            "winner.",
        )
    cheaper, dearer = (first, second) if a < b else (second, first)
    return PriceWinner(
        winner=cheaper.model,
        says=f"{cheaper.label} cost ${cheaper.usd_per_evaluation_or_review:.4f} per full evaluation "
        f"or position review, {dearer.label} ${dearer.usd_per_evaluation_or_review:.4f}: "
        f"{cheaper.label} is the price winner.",
    )


def _label(sim: dict) -> str:
    if sim["VARIANT"] == MEMORY_ON:
        return f"With memory / {model_label(llm_model(sim))}"
    return "Without memory"


class _Market:
    """One market's sims and what the store holds about them."""

    def __init__(
        self,
        sims: list[dict],
        endings: dict[int, float],
        day_ends: dict[tuple[int, int], float],
        figures: dict[int, dict],
        first_day: date | None,
    ):
        self.sims = sorted(sims, key=lambda s: s["ID"])
        self.endings = endings
        self.day_ends = day_ends
        self.figures = figures
        self.first_day = first_day
        self.first_step = min(s["FIRST_STEP"] for s in sims)
        self.last_step = max(s["LAST_STEP"] for s in sims)
        self.without = [s for s in self.counted() if s["VARIANT"] == MEMORY_OFF]

    def counted(self) -> list[dict]:
        return [s for s in self.sims if s["ID"] in self.endings]

    def models(self) -> list[str | None]:
        found = {llm_model(s) for s in self.sims if s["VARIANT"] == MEMORY_ON}
        return sorted(found, key=lambda m: (m is None, m or ""))

    def with_memory(self, model: str | None) -> list[dict]:
        return [
            s
            for s in self.counted()
            if s["VARIANT"] == MEMORY_ON and llm_model(s) == model
        ]

    def group(self, sims: list[dict]) -> Group:
        return _group([self.endings[s["ID"]] for s in sims])

    def real_day(self, day: int) -> date | None:
        return self.first_day and self.first_day + timedelta(day - 1)

    def result(self, model: str | None) -> ModelResult:
        label = model_label(model)
        mine = self.with_memory(model)
        memory, without = self.group(mine), self.group(self.without)
        found, difference, threshold = verdict(memory, without)
        figures = [self.figures[s["ID"]] for s in mine]
        evaluations = sum(f["FULL_EVALUATIONS"] for f in figures)
        everyone = [
            s for s in self.sims if s["VARIANT"] == MEMORY_ON and llm_model(s) == model
        ]
        return ModelResult(
            model=model or "",
            label=label,
            with_memory=memory,
            difference_usd=difference,
            threshold_usd=threshold,
            verdict=found,
            says=_verdict_says(label, found, difference, threshold),
            usd_per_evaluation_or_review=_ratio(
                sum(f["LLM_USD"] for f in figures),
                evaluations + sum(f["POSITION_REVIEWS"] for f in figures),
            ),
            seconds_per_full_evaluation=_ratio(
                sum(f["FULL_EVALUATION_SECONDS"] for f in figures), evaluations
            ),
            lookups_per_full_evaluation=None,
            models_returned=sorted(
                {n for s in everyone for n in self.figures[s["ID"]]["LLM_MODELS"]}
            ),
        )

    def repeats(self) -> list[Repeat]:
        numbers = sorted(
            {s["REPEAT_NUMBER"] for s in self.sims},
            key=lambda n: (n is None, n or 0),
        )
        order = {MEMORY_ON: 0, MEMORY_OFF: 1}
        return [
            Repeat(
                number=number,
                sims=[
                    RepeatSim(
                        sim_id=s["ID"],
                        label=_label(s),
                        model=llm_model(s) if s["VARIANT"] == MEMORY_ON else None,
                        status=s["STATUS"],
                        ending_value_usd=self.endings.get(s["ID"]),
                    )
                    for s in sorted(
                        (s for s in self.sims if s["REPEAT_NUMBER"] == number),
                        key=lambda s: (
                            order.get(s["VARIANT"], 2),
                            llm_model(s) or "",
                            s["ID"],
                        ),
                    )
                ],
            )
            for number in numbers
        ]

    def day_end_steps(self) -> list[int]:
        return [
            day * STEPS_PER_DAY
            for day in range(day_of(self.first_step), day_of(self.last_step) + 1)
        ]

    def gap_line(self, model: str | None) -> GapLine:
        mine = self.with_memory(model)
        points = []
        for step in self.day_end_steps():
            memory = [
                self.day_ends[(s["ID"], step)]
                for s in mine
                if (s["ID"], step) in self.day_ends
            ]
            without = [
                self.day_ends[(s["ID"], step)]
                for s in self.without
                if (s["ID"], step) in self.day_ends
            ]
            if memory and without:
                points.append(
                    GapPoint(
                        day=self.real_day(day_of(step)),
                        gap_usd=statistics.mean(memory) - statistics.mean(without),
                    )
                )
        return GapLine(model=model or "", label=model_label(model), points=points)

    def notes(self, results: list[ModelResult], jev_versions: list[str]) -> list[str]:
        notes = []
        if len(jev_versions) > 1:
            notes.append(
                f"The Jev version changed between the sims compared: "
                f"{', '.join(jev_versions)} answered. Part of any gap may be Jev itself."
            )
        for result in results:
            if len(result.models_returned) > 1:
                notes.append(
                    f"{result.label}: the provider returned more than one model name "
                    f"({', '.join(result.models_returned)}), so the model may have changed "
                    "between sims."
                )
        return notes

    def comparison(self, dataset: int, market: str) -> MarketComparison:
        results = [self.result(model) for model in self.models()]
        jev_versions = sorted(
            {v for s in self.sims for v in self.figures[s["ID"]]["JEV_VERSIONS"]}
        )
        return MarketComparison(
            dataset=dataset,
            market=market,
            first_day=self.real_day(day_of(self.first_step)),
            last_day=self.real_day(day_of(self.last_step)),
            starting_value_usd=self.sims[0]["STARTING_VALUE"],
            without_memory=self.group(self.without),
            models=results,
            performance=_performance(results),
            price=_price(results),
            repeats=self.repeats(),
            gap_over_time=[self.gap_line(model) for model in self.models()],
            jev_versions=jev_versions,
            notes=self.notes(results, jev_versions),
        )


def comparison(store: ApiStore) -> Comparison:
    sims = [s for s in store.sims() if s["KIND"] == MEASUREMENT and s.get("MARKET")]
    if not sims:
        return Comparison(markets=[])

    finished = [s for s in sims if s["STATUS"] == SimStatus.FINISHED]
    wanted = [(s["ID"], s["LAST_STEP"]) for s in finished]
    for sim in finished:
        wanted += [
            (sim["ID"], day * STEPS_PER_DAY)
            for day in range(day_of(sim["FIRST_STEP"]), day_of(sim["LAST_STEP"]) + 1)
        ]
    values = store.account_values_at(wanted)
    endings = {
        s["ID"]: values[(s["ID"], s["LAST_STEP"])]
        for s in finished
        if (s["ID"], s["LAST_STEP"]) in values
    }
    figures = store.comparison_figures([s["ID"] for s in sims])
    first_days: dict[int, date] = {}
    for key in store.asset_key():
        day = first_days.get(key["DATASET"])
        first_days[key["DATASET"]] = (
            min(day, key["FIRST_DAY"]) if day else key["FIRST_DAY"]
        )

    markets: dict[tuple[int, str], list[dict]] = {}
    for sim in sims:
        markets.setdefault((sim["DATASET"], sim["MARKET"]), []).append(sim)
    found = [
        _Market(group, endings, values, figures, first_days.get(dataset)).comparison(
            dataset, market
        )
        for (dataset, market), group in markets.items()
    ]
    found.sort(key=lambda m: (m.dataset, m.first_day or date.min, m.market))
    return Comparison(markets=found)
