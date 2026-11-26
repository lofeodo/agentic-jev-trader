"""The made-up data of the recorded-answer scenarios (spec appendix 10, section 7), all generated
by code, so nothing from a data provider lands in the repo.

- **Prices.** Each asset's 15-minute bars run from the made-up calendar's first step to the
  scenario's step, starting at $100, each bar opening at the last close and moving by a drift
  plus a random part drawn from the scenario's seed (`MadeUpPrices`). A stock trades 14:30 to
  21:00 UTC every day (26 bars), crypto all day (96). The real measurements
  (`measure_asset`) and the real situation text are worked out from them, so what Jev and the
  LLM read is shaped as in a real dataset.
- **Search numbers.** A real dataset's snapshot carries two lists of numbers the episode search
  compares: its 58 standard scores (the feature vector: each measurement told as how far it
  sits from its usual value, 0 being usual) and the 768 numbers a Snowflake model turns its
  situation text into (the embedding: texts that say similar things get similar lists).
  Tests have no Snowflake, so code makes both
  up: the feature vector is the measurements themselves (one not available counts as 0, the
  average), and the embedding counts the text's words, each word adding 1 to one of the 768
  places, picked by a hash of the word. Texts sharing words come out alike, as with the real
  model.
- **Memory.** The past episodes a scenario lists (`PastNoTrade`, `PastTrade`, `PastReview`) are
  written as rows of `MEMORY.DECISIONS` and `MEMORY.OUTCOMES` by the memory tests' own
  `MadeUpMemory`, into the in-memory stand-in for the database; each episode's snapshot is the
  one generated for its asset at its step. An episode is visible to a search only once its
  outcomes are all known by the scenario's step (spec appendix 5, section 3): a no-trade or a
  review 6 steps after it, a trade at its closing step.

The calendar's dates exist only to work the measurements out: no model reads a date.
"""

import hashlib
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from jev_trader.broker import Bar
from jev_trader.dataset.bars import BAR_LENGTH, STEPS_PER_DAY
from jev_trader.dataset.bars import Bar as DatasetBar
from jev_trader.dataset.candle_patterns import playbook
from jev_trader.dataset.measurements import (
    AssetClass,
    Measurements,
    Session,
    measure_asset,
)
from jev_trader.dataset.situation_text import (
    PATTERN_WINDOW_STEPS,
    PatternLists,
    situation_text,
)
from jev_trader.memory.store import InMemoryMemoryStore
from jev_trader.sim.market import Playbook, Snapshot
from tests.unit.memory.conftest import MadeUpMemory

SIM, DATASET, ASSET = 1, 1, "ASSET_01"
DAY = 96  # a day's 15-minute steps
STEP = 21 * DAY + 40  # day 22 at 10:00 UTC: every measurement has the 20 days it needs
FIRST_DAY = date(2000, 1, 3)
MIDNIGHT = datetime.combine(FIRST_DAY, time(), tzinfo=UTC)
STOCK_OPENS, STOCK_CLOSES = time(14, 30), time(21, 0)
FIRST_PRICE = 100.0
USUAL_VOLUME = 1000.0
EMBEDDING_SIZE = 768


def the_playbook() -> Playbook:
    """Every candle pattern the dataset build names, with its lean and shape, as a dataset's
    `REF.PLAYBOOK` holds them."""
    return {p.name: (p.lean, p.shape) for p in playbook()}


@dataclass(frozen=True)
class MadeUpPrices:
    """How the made-up bars move. Each bar's close is its open moved by `drift` plus a random
    part about `swing` in size (shares of the price: 0.002 is 0.2%, so a $100 bar closes about
    20 cents up or down), drawn from `seed`.
    `last_moves` replaces the random moves of the scenario's last bars, oldest first (0.01: the
    bar closes 1% above its open), and `last_volume` is the last bar's volume against the usual
    (2.0 is double). Each asset draws its own bars from the seed and its ID."""

    seed: int = 0
    drift: float = 0.0
    swing: float = 0.002
    last_moves: tuple[float, ...] = ()
    last_volume: float = 1.0


def _start(step: int) -> datetime:
    """When the bar of `step` starts: the step comes when the bar ends."""
    return MIDNIGHT + (step - 1) * BAR_LENGTH


def _session(day: date) -> Session:
    return Session(
        datetime.combine(day, STOCK_OPENS, tzinfo=UTC),
        datetime.combine(day, STOCK_CLOSES, tzinfo=UTC),
    )


def trades_at(asset_class: AssetClass, step: int) -> bool:
    """Whether an asset of `asset_class` has a bar at `step`."""
    if asset_class is AssetClass.CRYPTO:
        return True
    return STOCK_OPENS <= _start(step).time() < STOCK_CLOSES


@dataclass(frozen=True)
class Series:
    """One asset's made-up bars up to the last step, with what the dataset measured at each."""

    asset: str
    asset_class: AssetClass
    bars: tuple[DatasetBar, ...]
    steps: tuple[int, ...]
    measured: tuple[Measurements, ...]

    def _index(self, step: int) -> int:
        try:
            return self.steps.index(step)
        except ValueError:
            raise ValueError(
                f"{self.asset} has no made-up bar at step {step}"
            ) from None

    def broker_bars(self) -> list[Bar]:
        return [self.bar(step) for step in self.steps]

    def bar(self, step: int) -> Bar:
        """The bar of `step` as the broker reads it."""
        b = self.bars[self._index(step)]
        return Bar(step, b.open, b.high, b.low, b.close)

    def measurements(self, step: int) -> Measurements:
        return self.measured[self._index(step)]

    def bars_left(self, step: int) -> int | None:
        """A stock's bars left in its session after `step` (0 on its last); None for crypto."""
        if self.asset_class is AssetClass.CRYPTO:
            return None
        ends = self.bars[self._index(step)].end
        return (_session(ends.date()).close - ends) // BAR_LENGTH


def _drawn_bar(
    step: int,
    opened: float,
    move: float,
    draw: random.Random,
    swing: float,
    volume_against_usual: float = 1.0,
) -> DatasetBar:
    close = round(opened * (1 + move), 4)
    above = abs(draw.gauss(0, swing / 2))
    below = abs(draw.gauss(0, swing / 2))
    volume = USUAL_VOLUME * (0.8 + 0.4 * draw.random()) * volume_against_usual
    return DatasetBar(
        start=_start(step),
        open=opened,
        high=round(max(opened, close) * (1 + above), 4),
        low=round(min(opened, close) * (1 - below), 4),
        close=close,
        volume=round(volume, 1),
    )


def made_up_series(
    asset: str,
    asset_class: StrEnum,
    last_step: int,
    prices: MadeUpPrices,
    bars_after: int = 0,
) -> Series:
    """The asset's bars from step 1 to `last_step`, drawn from `prices`, then `bars_after` more
    of its bars. The bars after are drawn apart (same drift and swing, no set moves), so the
    bars up to `last_step` are the same with or without them. `asset_class` may be the broker's
    or the dataset's: the measurements need the dataset's."""
    asset_class = AssetClass(str(asset_class))
    steps = [s for s in range(1, last_step + 1) if trades_at(asset_class, s)]
    draw = random.Random(f"{prices.seed}-{asset}")
    moves = [prices.drift + draw.gauss(0, prices.swing) for _ in steps]
    if prices.last_moves:
        moves[-len(prices.last_moves) :] = prices.last_moves
    bars: list[DatasetBar] = []
    for n, (step, move) in enumerate(zip(steps, moves), start=1):
        opened = bars[-1].close if bars else FIRST_PRICE
        volume = prices.last_volume if n == len(steps) else 1.0
        bars.append(_drawn_bar(step, opened, move, draw, prices.swing, volume))
    draw_after = random.Random(f"{prices.seed}-{asset}-after")
    wanted = len(bars) + bars_after
    step = last_step
    while len(bars) < wanted:
        step += 1
        if trades_at(asset_class, step):
            move = prices.drift + draw_after.gauss(0, prices.swing)
            bars.append(
                _drawn_bar(step, bars[-1].close, move, draw_after, prices.swing)
            )
            steps.append(step)
    days = (steps[-1] - 1) // STEPS_PER_DAY + 1
    sessions = {
        day: _session(day)
        for day in (FIRST_DAY + timedelta(days=d) for d in range(days))
    }
    measured = measure_asset(bars, asset_class, sessions)
    return Series(asset, asset_class, tuple(bars), tuple(steps), tuple(measured))


def _window(patterns: Sequence[tuple[int, str]], step: int) -> list[tuple[str, int]]:
    """The candle patterns of the pattern window at `step`, each with its bars ago."""
    return [
        (name, step - seen)
        for seen, name in patterns
        if step - PATTERN_WINDOW_STEPS < seen <= step
    ]


def made_up_embedding(text: str) -> list[float]:
    """The made-up stand-in for the 768 numbers a Snowflake model turns a text into."""
    numbers = [0.0] * EMBEDDING_SIZE
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(word.encode()).digest()
        numbers[int.from_bytes(digest[:4], "big") % EMBEDDING_SIZE] += 1.0
    return numbers


class MadeUpMarket:
    """The made-up bars of every asset a scenario names, up to its step, then `bars_after` more
    of each asset's bars. `patterns` are the candle patterns recognised on each asset, as
    (step, name) pairs."""

    def __init__(
        self,
        asset_class: StrEnum,
        last_step: int,
        prices: MadeUpPrices,
        patterns: Mapping[str, Sequence[tuple[int, str]]],
        bars_after: int = 0,
    ):
        self.asset_class = AssetClass(str(asset_class))
        self.last_step, self.prices = last_step, prices
        self.patterns, self.bars_after = patterns, bars_after
        self._series: dict[str, Series] = {}

    def series(self, asset: str) -> Series:
        if asset not in self._series:
            self._series[asset] = made_up_series(
                asset, self.asset_class, self.last_step, self.prices, self.bars_after
            )
        return self._series[asset]

    def _text(self, asset: str, step: int) -> tuple[str, list[tuple[str, int]]]:
        window = _window(self.patterns.get(asset, ()), step)
        measured = self.series(asset).measurements(step)
        return situation_text(measured, PatternLists(window, [], [])), window

    def snapshot(self, asset: str, step: int) -> Snapshot:
        """The snapshot the agent reads, as the sim's market builds it from a dataset."""
        text, window = self._text(asset, step)
        series = self.series(asset)
        share = series.measurements(step)["typical_move_share_of_price"]
        newest_first = sorted(window, key=lambda pattern: pattern[1])
        names = tuple(dict.fromkeys(name for name, _ in newest_first))
        return Snapshot(
            situation_text=text,
            typical_move=None if share is None else share * series.bar(step).close,
            bars_left=series.bars_left(step),
            patterns=names,
            window_patterns=names,
        )

    def memory_snapshot(self, asset: str, step: int) -> dict:
        """The snapshot as the memory server reads it, with its made-up search numbers."""
        text, _ = self._text(asset, step)
        values = self.series(asset).measurements(step).values
        return {
            "ASSET_CLASS": str(self.asset_class),
            "MEASUREMENTS": list(values),
            "FEATURE_VECTOR": [0.0 if v is None else float(v) for v in values],
            "EMBEDDING": made_up_embedding(text),
            "SITUATION_TEXT": text,
        }


# The made-up memory


@dataclass(frozen=True)
class PastNoTrade:
    """A past full evaluation that opened no trade; complete 6 steps later."""

    step: int
    asset: str = ASSET


@dataclass(frozen=True)
class PastTrade:
    """A past full evaluation that opened a $1,000 trade as position `position`, closed
    `closed_after` bars after it opened with `profit` dollars, by Jev's choice or as
    `closing_reason` says (stop_price, forced_close, sim_ended)."""

    step: int
    position: int
    direction: str = "long"
    closed_after: int = 3
    profit: float = 12.0
    closing_reason: str = "jev"
    asset: str = ASSET


@dataclass(frozen=True)
class PastReview:
    """A past review of position `position` (open 2 bars, `profit` dollars up then) that decided
    `action` (nothing is a hold, close, reduce, add); complete 6 steps later. A reduce sold half
    the position, an add put in $1,000 more."""

    step: int
    position: int
    direction: str = "long"
    action: str = "nothing"
    profit: float = 8.0
    asset: str = ASSET


PastEpisode = PastNoTrade | PastTrade | PastReview


class _GeneratedMemory(MadeUpMemory):
    """The memory tests' made-up memory, each snapshot the one generated for its step."""

    def __init__(self, market: MadeUpMarket):
        super().__init__(sim=SIM, dataset=DATASET)
        self.market = market

    def snapshot(self, asset: str, step: int) -> None:
        self.store.snapshots[(self.dataset, asset, step)] = self.market.memory_snapshot(
            asset, step
        )
        for seen, name in self.market.patterns.get(asset, ()):
            if seen == step:
                self.store.patterns.append(
                    {
                        "DATASET": self.dataset,
                        "ASSET": asset,
                        "BAR_SIZE": "15m",
                        "STEP": seen,
                        "PATTERN": name,
                    }
                )

    def review(self, asset: str, step: int, position: int, **kwargs) -> str:
        """The memory tests' review, with how much a reduce sold (half) and an add put in
        ($1,000), which an episode of a reduce or an add tells."""
        review = super().review(asset, step, position, **kwargs)
        (row,) = [r for r in self.store.decisions_table if r["ID"] == review]
        action = row["ACTION"]
        row["REDUCE_SHARE"] = 0.5 if action == "reduce" else None
        row["SIZE_AFTER_TRIMMING"] = 1000.0 if action == "add" else None
        return review


def made_up_memory(
    market: MadeUpMarket, now: int, past: Sequence[PastEpisode]
) -> InMemoryMemoryStore:
    """The in-memory stand-in for the database, holding the past episodes and the scenario's
    asset's snapshot at `now`, which a search starts from."""
    memory = _GeneratedMemory(market)
    for episode in past:
        if episode.step >= now:
            raise ValueError(
                f"a past episode at step {episode.step} is not before {now}"
            )
        match episode:
            case PastNoTrade():
                memory.no_trade(episode.asset, episode.step)
            case PastTrade():
                memory.trade(
                    episode.asset,
                    episode.step,
                    episode.position,
                    direction=episode.direction,
                    closed_after=episode.closed_after,
                    profit=episode.profit,
                    closing_reason=episode.closing_reason,
                )
            case PastReview():
                memory.review(
                    episode.asset,
                    episode.step,
                    episode.position,
                    direction=episode.direction,
                    action=episode.action,
                    profit=episode.profit,
                )
    memory.snapshot(ASSET, now)
    return memory.store
