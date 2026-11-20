"""Laying cleaned bars out on the step clock, masked, as the rows a dataset stores.

What the models can never learn from these rows: which asset it is, what it really cost, or on
what date (spec appendix 1, section 2). So:

- **Steps.** The clock ticks every 15 minutes in UTC; step 1 is the first bar's end after the
  dataset's first midnight, and every day has 96 steps (ADR 0002). A bar is stored at the step
  at which it ends: the bar from 13:30 to 13:45 UTC on day 1 ends at step 55.
- **Masked IDs.** Assets are `ASSET_01`, `ASSET_02`, ... in the settings file's order.
- **Price scale.** Each series is multiplied by one number so that its first bar opens at 100,
  then rounded to the dataset's number of decimals. A stock first trading at $50.00 has a price
  scale of 2: a later $50.50 is stored as 101.
- **Volume scale.** Each asset's volume is multiplied by one number so that its average bar
  over its first 5 UTC days with bars is 100.
- The **asset key** (`KEYS.ASSET_KEY`) holds the way back: real ticker and name, both scales, and
  the real date of step 1. It is the only table with any of them.

Hourly and daily bars are built from the 15-minute bars that were kept. An hourly bar covers one
UTC clock hour, so a stock's first hourly bar of a session (13:30 to 14:00 UTC in summer) is
short. A daily bar is one per session for a stock, one per UTC day for crypto.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from jev_trader.dataset.bars import BAR_LENGTH, Bar
from jev_trader.dataset.measurements import AssetClass, Session
from jev_trader.dataset.quality import CleanSeries
from jev_trader.dataset.scaling import first_tradable_day
from jev_trader.dataset.settings import AssetSettings, DatasetSettings

STEPS_PER_DAY = 96
HOUR = timedelta(hours=1)
VOLUME_SCALE_DAYS = 5
VOLUME_DECIMALS = 4
BAR_SIZES = ("15m", "1h", "1d")


def masked_id(index: int) -> str:
    """The masked ID of the asset at `index` (from 0) in the settings file."""
    return f"ASSET_{index + 1:02d}"


@dataclass(frozen=True)
class CleanedAsset:
    """One asset after cleaning. `sessions` is the exchange calendar's, by day, for a stock."""

    settings: AssetSettings
    clean: CleanSeries
    sessions: dict[date, Session]


@dataclass(frozen=True)
class Clock:
    first_day: date

    @property
    def midnight(self) -> datetime:
        return datetime.combine(self.first_day, time(), tzinfo=UTC)

    def step_ending_at(self, moment: datetime) -> int:
        return (moment - self.midnight) // BAR_LENGTH

    def day_number(self, step: int) -> int:
        return (step - 1) // STEPS_PER_DAY + 1

    def first_step_of(self, day: date) -> int:
        return (day - self.first_day).days * STEPS_PER_DAY + 1

    def last_step_of(self, day: date) -> int:
        return ((day - self.first_day).days + 1) * STEPS_PER_DAY


@dataclass(frozen=True)
class _Placed:
    """A bar with where it sits: the moment it ends, its number in the session or day, and
    the bars left after it (None for crypto, which has no session)."""

    bar: Bar
    ends: datetime
    number: int
    left: int | None


def _merge(bars: Sequence[Bar]) -> Bar:
    return Bar(
        start=bars[0].start,
        open=bars[0].open,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        close=bars[-1].close,
        volume=sum(b.volume for b in bars),
    )


def _hour_starts(sess: Session) -> list[datetime]:
    hour = sess.open.replace(minute=0, second=0, microsecond=0)
    starts = []
    while hour < sess.close:
        starts.append(hour)
        hour += HOUR
    return starts


def _place_stock(
    bars: list[Bar], sessions: dict[date, Session]
) -> dict[str, list[_Placed]]:
    placed: dict[str, list[_Placed]] = {size: [] for size in BAR_SIZES}
    by_day: dict[date, list[Bar]] = defaultdict(list)
    for bar in bars:
        by_day[bar.start.date()].append(bar)
    for day, day_bars in sorted(by_day.items()):
        sess = sessions[day]
        in_session = (sess.close - sess.open) // BAR_LENGTH
        for bar in day_bars:
            number = (bar.start - sess.open) // BAR_LENGTH + 1
            placed["15m"].append(_Placed(bar, bar.end, number, in_session - number))
        hours = _hour_starts(sess)
        by_hour: dict[datetime, list[Bar]] = defaultdict(list)
        for bar in day_bars:
            by_hour[bar.start.replace(minute=0)].append(bar)
        for i, hour in enumerate(hours):
            if by_hour.get(hour):
                ends = min(hour + HOUR, sess.close)
                placed["1h"].append(
                    _Placed(_merge(by_hour[hour]), ends, i + 1, len(hours) - i - 1)
                )
        placed["1d"].append(_Placed(_merge(day_bars), sess.close, 1, 0))
    return placed


def _place_crypto(bars: list[Bar]) -> dict[str, list[_Placed]]:
    placed: dict[str, list[_Placed]] = {size: [] for size in BAR_SIZES}
    by_hour: dict[datetime, list[Bar]] = defaultdict(list)
    by_day: dict[date, list[Bar]] = defaultdict(list)
    for bar in bars:
        midnight = bar.start.replace(hour=0, minute=0)
        number = (bar.start - midnight) // BAR_LENGTH + 1
        placed["15m"].append(_Placed(bar, bar.end, number, None))
        by_hour[bar.start.replace(minute=0)].append(bar)
        by_day[bar.start.date()].append(bar)
    for hour, hour_bars in sorted(by_hour.items()):
        placed["1h"].append(
            _Placed(_merge(hour_bars), hour + HOUR, hour.hour + 1, None)
        )
    for day, day_bars in sorted(by_day.items()):
        ends = datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
        placed["1d"].append(_Placed(_merge(day_bars), ends, 1, None))
    return placed


def _volume_scale(bars: list[Bar]) -> float:
    """The factor that makes the average bar over the first 5 UTC days with bars equal 100."""
    days = sorted({b.start.date() for b in bars})[:VOLUME_SCALE_DAYS]
    early = [b.volume for b in bars if b.start.date() in days]
    average = sum(early) / len(early) if early else 0.0
    return 100.0 / average if average > 0 else 1.0


def lay_out(
    dataset_id: int,
    settings: DatasetSettings,
    assets: Sequence[CleanedAsset],
    progress: Callable[[str], None] = lambda stage: None,
) -> dict[str, list[dict]]:
    """Every row the dataset stores apart from its `REF.DATASETS` row, by table name."""
    clock = Clock(settings.first_day)
    tables: dict[str, list[dict]] = defaultdict(list)

    warm_up_ends = min(
        first_tradable_day(settings.first_day) - timedelta(days=1), settings.last_day
    )
    tables["REF.DATASET_PERIODS"].append(
        {
            "DATASET": dataset_id,
            "KIND": "warm-up",
            "NAME": "warm-up",
            "FIRST_STEP": 1,
            "LAST_STEP": clock.last_step_of(warm_up_ends),
        }
    )
    for period in settings.test_periods:
        tables["REF.DATASET_PERIODS"].append(
            {
                "DATASET": dataset_id,
                "KIND": "test",
                "NAME": period.name,
                "FIRST_STEP": clock.first_step_of(period.first_day),
                "LAST_STEP": clock.last_step_of(period.last_day),
            }
        )

    placed_assets = []
    for i, asset in enumerate(assets):
        masked = masked_id(i)
        bars = asset.clean.bars
        price_scale = 100.0 / bars[0].open if bars and bars[0].open else 1.0
        volume_scale = _volume_scale(bars)
        stock = asset.settings.asset_class is AssetClass.STOCK

        tables["REF.ASSETS"].append(
            {
                "DATASET": dataset_id,
                "MASKED_ID": masked,
                "ASSET_CLASS": str(asset.settings.asset_class),
            }
        )
        tables["REF.INSTRUMENTS"].append(
            {
                "DATASET": dataset_id,
                "INSTRUMENT_ID": f"{masked}_SPOT",
                "ASSET": masked,
                "TYPE": "spot",
            }
        )
        tables["KEYS.ASSET_KEY"].append(
            {
                "DATASET": dataset_id,
                "MASKED_ID": masked,
                "TICKER": asset.settings.ticker,
                "PROVIDER_SYMBOL": asset.settings.provider_symbol,
                "NAME": asset.settings.name,
                "PRICE_SCALE": price_scale,
                "VOLUME_SCALE": volume_scale,
                "FIRST_DAY": settings.first_day,
            }
        )
        for m in asset.clean.missing:
            tables["REF.MISSING_BARS"].append(
                {
                    "DATASET": dataset_id,
                    "ASSET": masked,
                    "STEP": clock.step_ending_at(m.start + BAR_LENGTH),
                    "REASON": str(m.reason),
                }
            )
        for p in asset.clean.partial_volume_days:
            tables["REF.PARTIAL_VOLUME_DAYS"].append(
                {
                    "DATASET": dataset_id,
                    "ASSET": masked,
                    "DAY": (p.day - settings.first_day).days + 1,
                    "TEST": str(p.test),
                    "SHARE_OF_USUAL": p.share_of_usual,
                }
            )
        placed_assets.append((masked, price_scale, volume_scale, stock, asset))
    progress("Build hourly and daily bars")

    def price(x: float, scale: float) -> float:
        return round(x * scale, settings.price_decimals)

    for masked, price_scale, volume_scale, stock, asset in placed_assets:
        bars = asset.clean.bars
        placed = _place_stock(bars, asset.sessions) if stock else _place_crypto(bars)
        for size in BAR_SIZES:
            for p in placed[size]:
                step = clock.step_ending_at(p.ends)
                tables["RAW.BARS"].append(
                    {
                        "DATASET": dataset_id,
                        "ASSET": masked,
                        "BAR_SIZE": size,
                        "STEP": step,
                        "DAY": clock.day_number(step),
                        "BAR_NUMBER": p.number,
                        "BARS_LEFT": p.left,
                        "OPEN": price(p.bar.open, price_scale),
                        "HIGH": price(p.bar.high, price_scale),
                        "LOW": price(p.bar.low, price_scale),
                        "CLOSE": price(p.bar.close, price_scale),
                        "VOLUME": round(p.bar.volume * volume_scale, VOLUME_DECIMALS),
                    }
                )
    return dict(tables)
