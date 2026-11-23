"""A dataset build, stage by stage (spec appendix 2, section 8).

1. **Start and check.** Download every asset (each stock with its 20 lead-in sessions), drop a
   stock's bars outside its session, find missing bars and partial-volume days, and compare them
   with the two limits. With the check on, a dataset over a limit fails here, before the slow
   part, and the message says which asset is over which limit.
2. **Lay out the clock and the asset key.** Step numbers, masked IDs, both scales.
3. **Build hourly and daily bars** from the 15-minute bars.
4. **Recognise candle patterns** on all three bar sizes, and store the playbook.
5. **Measure.** The 58 measurements of every snapshot; the warm-up averages and spreads, frozen.
6. **Write the situation text** of every snapshot, with its feature vector, and stage them.
7. **Embed.** Snowflake's model turns each staged text into 768 numbers as the snapshots are
   stored, one asset at a time.
8. **Publish.** Write every other row, then mark the dataset published.

A build that stops for any reason is marked failed, its rows are thrown away, and the next build
of the same settings is a new version. Each stage is timed and the times are printed at the end,
to set its share of the progress bar.
"""

import itertools
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from jev_trader.dataset.candle_patterns import TALIB_VERSION
from jev_trader.dataset.exchange_calendar import sessions_before, stock_sessions
from jev_trader.dataset.layout import (
    CleanedAsset,
    Clock,
    lay_out,
    masked_bars,
    masked_id,
)
from jev_trader.dataset.measurements import (
    MEASUREMENT_NAMES,
    AssetClass,
    measure_asset,
)
from jev_trader.dataset.providers import (
    CryptoProvider,
    ProviderError,
    StockProvider,
    UnknownTicker,
)
from jev_trader.dataset.quality import (
    CheckResult,
    NotEnoughHistory,
    check_limits,
    clean_crypto,
    clean_stock,
)
from jev_trader.dataset.scaling import WarmUpScales
from jev_trader.dataset.settings import DatasetSettings
from jev_trader.dataset.snapshots import (
    EMBEDDING_MODEL,
    MEASUREMENT_SETTINGS,
    AssetBars,
    find_patterns,
    pattern_rows,
    playbook_rows,
    snapshot_rows,
    warm_up_rows,
)
from jev_trader.dataset.store import DatasetStore

# Each stage's place on the progress bar: the share done when it starts. Measured on the first
# dataset's build (1,526 seconds, about 25 minutes, on 2026-11-23).
STAGES = {
    "Start and check": 0.0,
    "Lay out the clock and the asset key": 0.15,
    "Build hourly and daily bars": 0.15,
    "Recognise candle patterns": 0.15,
    "Measure": 0.17,
    "Write the situation text": 0.17,
    "Embed": 0.50,
    "Publish": 0.64,
}
PROVIDERS = {
    AssetClass.STOCK: "Twelve Data (adjust=all)",
    AssetClass.CRYPTO: "Binance public files",
}


class BuildStopped(Exception):
    """The build cannot go on; the message says why and what to change.

    `stored_reason` is the same with masked IDs, for the dataset's row: real tickers live only
    in the asset key.
    """

    def __init__(self, message: str, stored_reason: str | None = None):
        super().__init__(message)
        self.stored_reason = stored_reason or message


@dataclass(frozen=True)
class BuildResult:
    dataset_id: int
    version: int
    published: bool
    check: CheckResult
    message: str
    # Seconds each stage took, in order (empty when the check stopped the build).
    stage_seconds: dict[str, float] = field(default_factory=dict)


def build_dataset(
    settings: DatasetSettings,
    stocks: StockProvider,
    crypto: CryptoProvider,
    store: DatasetStore,
    today: date,
    check: bool = True,
    report: Callable[[str], None] = print,
) -> BuildResult:
    """Build and publish one dataset from `settings`. `today` is the build day.

    Returns a result that is not published if the check is on and an asset is over a limit.
    Raises `BuildStopped` if the settings cannot give a dataset (a ticker the provider does not
    know, too little history, a last day too recent); the dataset is then marked failed.
    """
    if settings.last_day >= today:
        raise BuildStopped(
            f"The last day ({settings.last_day}) must be at least a day before the build day "
            f"({today}): the provider's bars of the current day carry only part of its volume."
        )
    clock = Clock(settings.first_day)
    dataset_id, version = store.begin(
        settings.name,
        {
            "FIRST_STEP": 1,
            "LAST_STEP": clock.last_step_of(settings.last_day),
            "DATA_PROVIDERS": sorted(
                {PROVIDERS[a.asset_class] for a in settings.assets}
            ),
            "PARTIAL_VOLUME_SHARE_OF_USUAL": settings.usual_volume.share,
            "PARTIAL_VOLUME_SESSIONS": settings.usual_volume.sessions,
            "LIMIT_OTHER_MISSING": settings.limits.other_missing,
            "LIMIT_PARTIAL_VOLUME_DAYS": settings.limits.partial_volume_days,
            "PRICE_DECIMALS": settings.price_decimals,
            "TALIB_VERSION": TALIB_VERSION,
            "EMBEDDING_MODEL": EMBEDDING_MODEL,
            "MEASUREMENTS": list(MEASUREMENT_NAMES),
            "MEASUREMENT_SETTINGS": MEASUREMENT_SETTINGS,
        },
    )
    tickers = {masked_id(i): a.ticker for i, a in enumerate(settings.assets)}
    # Seconds each stage took, in order; the current stage is the last.
    seconds: dict[str, float] = {}
    started = [time.monotonic()]

    def stage(name: str) -> None:
        _time_stage(seconds, started)
        seconds[name] = 0.0
        share = STAGES[name]
        store.update(dataset_id, BUILD_STAGE=name, BUILD_PROGRESS=share)
        report(f"[{share:4.0%}] {name}")

    try:
        stage("Start and check")
        cleaned = _download_and_clean(settings, stocks, crypto, report)
        result = check_limits(
            {
                masked_id(i): (a.settings.asset_class, a.clean)
                for i, a in enumerate(cleaned)
            },
            settings.limits,
        )
        store.update(dataset_id, CHECK_RESULT=_check_record(result))
        if check and not result.passed:
            store.fail(dataset_id, result.message())
            message = result.message(names=tickers)
            report(message)
            return BuildResult(dataset_id, version, False, result, message)

        stage("Lay out the clock and the asset key")
        tables = lay_out(
            dataset_id,
            settings,
            cleaned,
            before_bars=lambda: stage("Build hourly and daily bars"),
        )
        assets = [
            _asset_bars(asset, key, settings.price_decimals)
            for asset, key in zip(cleaned, tables["KEYS.ASSET_KEY"], strict=True)
        ]

        stage("Recognise candle patterns")
        store.save_playbook(playbook_rows())
        found = {}
        tables["FEATURES.PATTERNS"] = []
        for asset in assets:
            found[asset.masked_id] = find_patterns(asset, clock)
            tables["FEATURES.PATTERNS"] += pattern_rows(
                dataset_id, asset.masked_id, found[asset.masked_id]
            )

        stage("Measure")
        measured = {
            asset.masked_id: measure_asset(
                asset.bars, asset.asset_class, asset.sessions
            )
            for asset in assets
        }
        scales = WarmUpScales.from_warm_up(
            settings.first_day, itertools.chain.from_iterable(measured.values())
        )
        tables["REF.WARMUP_STATS"] = warm_up_rows(dataset_id, scales)

        stage("Write the situation text")
        for asset in assets:
            store.stage_snapshots(
                dataset_id,
                snapshot_rows(
                    dataset_id,
                    asset,
                    measured.pop(asset.masked_id),
                    scales,
                    found[asset.masked_id],
                    clock,
                ),
            )

        stage("Embed")
        total = sum(len(a.bars) for a in assets)
        done = 0
        for asset in assets:
            done += store.embed_snapshots(dataset_id, asset.masked_id)
            share = STAGES["Embed"] + (STAGES["Publish"] - STAGES["Embed"]) * (
                done / total if total else 1.0
            )
            store.update(dataset_id, BUILD_PROGRESS=share)
            report(f"       embedded {done} of {total} situation texts")

        stage("Publish")
        store.save(dataset_id, tables)
        store.update(dataset_id, BUILD_PROGRESS=1.0)
        store.publish(dataset_id, without_check=not check)
        _time_stage(seconds, started)
    except KeyboardInterrupt:
        store.fail(dataset_id, "stopped by hand")
        raise
    except BuildStopped as stop:
        store.fail(dataset_id, stop.stored_reason)
        raise
    except Exception as error:
        # The error's own text can hold a real ticker, date or URL: it is printed, not stored.
        store.fail(
            dataset_id,
            f"stopped by an unexpected {type(error).__name__}; details in the build's output",
        )
        raise

    if result.passed:
        message = (
            f"Published dataset {settings.name} version {version} (ID {dataset_id})."
        )
    else:
        message = (
            f'Published dataset {settings.name} version {version} (ID {dataset_id}) "published '
            'without the check":\n' + result.message(names=tickers)
        )
    report(message)
    report(_stage_times(seconds))
    return BuildResult(dataset_id, version, True, result, message, seconds)


def _time_stage(seconds: dict[str, float], started: list[float]) -> None:
    """Add the time since `started` to the current (last) stage, and restart the clock."""
    moment = time.monotonic()
    if seconds:
        seconds[next(reversed(seconds))] += moment - started[0]
    started[0] = moment


def _stage_times(seconds: dict[str, float]) -> str:
    """Each stage's seconds and its share of the whole build: what the progress bar should use."""
    total = sum(seconds.values()) or 1.0
    lines = ["Seconds per stage (share of the build):"]
    lines += [
        f"  {name}: {spent:.0f} s ({spent / total:.0%})"
        for name, spent in seconds.items()
    ]
    return "\n".join(lines)


def _asset_bars(asset: CleanedAsset, key: dict, price_decimals: int) -> AssetBars:
    """The asset's bars as stored (masked), for the snapshot stages."""
    stock = asset.settings.asset_class is AssetClass.STOCK
    return AssetBars(
        masked_id=key["MASKED_ID"],
        asset_class=asset.settings.asset_class,
        bars=masked_bars(
            asset.clean.bars, key["PRICE_SCALE"], key["VOLUME_SCALE"], price_decimals
        ),
        missing=[pd.Timestamp(m.start) for m in asset.clean.missing],
        sessions=asset.sessions if stock else None,
    )


def _download_and_clean(
    settings: DatasetSettings,
    stocks: StockProvider,
    crypto: CryptoProvider,
    report: Callable[[str], None],
) -> list[CleanedAsset]:
    sessions = stock_sessions(settings.first_day, settings.last_day)
    lead_in = sessions_before(settings.first_day, settings.usual_volume.sessions)
    cleaned = []
    for i, asset in enumerate(settings.assets):
        masked = masked_id(i)
        report(f"       downloading {asset.ticker}")
        try:
            if asset.asset_class is AssetClass.STOCK:
                first = lead_in[0][0] if lead_in else settings.first_day
                bars = stocks.stock_bars(asset.downloaded_as, first, settings.last_day)
                clean = clean_stock(
                    bars,
                    sessions,
                    lead_in,
                    usual=settings.usual_volume,
                )
            else:
                bars = crypto.crypto_bars(
                    asset.downloaded_as, settings.first_day, settings.last_day
                )
                clean = clean_crypto(bars, settings.first_day, settings.last_day)
        except NotEnoughHistory as short:
            raise BuildStopped(
                f"{asset.ticker}: {short}. Pick a later first day.",
                f"{masked}: its history does not reach {settings.usual_volume.sessions} "
                "sessions before the first day. Pick a later first day.",
            ) from None
        except UnknownTicker as error:
            raise BuildStopped(
                f"{asset.ticker}: {error}",
                f"{masked}: the provider does not know this ticker",
            ) from None
        except ProviderError as error:
            raise BuildStopped(
                f"{asset.ticker}: {error}",
                f"{masked}: the provider refused a download; details in the build's output",
            ) from None
        cleaned.append(CleanedAsset(asset, clean, dict(sessions)))
    return cleaned


def _check_record(result: CheckResult) -> dict:
    """The check's numbers and verdict as stored with the dataset (masked IDs only)."""
    return {
        "passed": result.passed,
        "limits": asdict(result.limits),
        "assets": [
            {
                "asset": a.asset,
                "other_missing_share": a.other_missing_share,
                "partial_volume_share": a.partial_volume_share,
                "over": a.over,
            }
            for a in result.assets
        ],
    }
