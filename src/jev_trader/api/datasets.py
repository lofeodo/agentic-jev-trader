"""The Datasets and Dataset screens, and dataset builds through the API (spec appendix 8,
section 8.11; appendix 7, section 9).

- **A build request** (`POST /datasets`) carries typed tickers, the first and last day, the
  test period (optional), the two quality limits and the check switch. It is checked here
  (every refusal at once), its row is added "being built", and its job is started: the same
  `python -m jev_trader.dataset build` the developer types, on a settings file the API writes.
- **Stop** kills the job and marks the dataset failed, "stopped by hand". A build the API did
  not start (from the command line) has no job to kill: it reads its row before each stage and
  ends there. Rows a killed build wrote are thrown away when the next build starts.
- **Reads:** the list, one dataset's page (stage and progress, the check's numbers per asset
  and its verdict, the quality report, the asset key) and one asset's price chart.

Real names lead, as on every screen. A published dataset is named from its asset key. A build
that stopped before writing the key (at the check, say) is named from the settings the API
started it with; one started from the command line keeps its masked IDs.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from jev_trader.api.sim_jobs import Refusal, Refused
from jev_trader.api.sim_page import Price
from jev_trader.api.sims_list import AssetName
from jev_trader.api.store import ApiStore
from jev_trader.dataset.bars import BAR_LENGTH, STEPS_PER_DAY
from jev_trader.dataset.build import STAGES
from jev_trader.dataset.layout import masked_id
from jev_trader.dataset.quality import QualityLimits
from jev_trader.dataset.settings import (
    DatasetSettings,
    Period,
    load_settings_text,
    settings_from_tickers,
    settings_toml,
)
from jev_trader.dataset.store import DatasetStatus
from jev_trader.jobs import Builds, JobNotKilled

STOPPED_BY_HAND = "stopped by hand"
MASKED_ID = re.compile(r"ASSET_\d+")


class DatasetNotFound(Exception):
    pass


class TestPeriodAsked(BaseModel):
    name: str  # "falling market" or "rising market"
    first_day: date
    last_day: date


class DatasetToBuild(BaseModel):
    """A build request, as the Datasets form sends it. Days are real dates (UTC); limits are
    shares (0.03 is 3%)."""

    tickers: list[str]
    first_day: date
    last_day: date
    test_periods: list[TestPeriodAsked] = Field(default_factory=list)
    # A stock's sessions that are partial-volume days.
    limit_partial_volume_days: float = QualityLimits.partial_volume_days
    # An asset's bars missing for any other reason.
    limit_other_missing: float = QualityLimits.other_missing
    check: bool = True  # with it off, the dataset is published whatever the numbers


class DatasetStarted(BaseModel):
    dataset_id: int


class AssetCheck(BaseModel):
    asset: AssetName
    other_missing_share: float  # 0.004 is 0.4% of its bars
    partial_volume_share: float | None  # None for crypto, which has no sessions
    over: list[str]  # the limits it is over


class QualityCheck(BaseModel):
    """The build's first step: each asset's numbers against the two limits, and the verdict."""

    passed: bool
    limit_other_missing: float
    limit_partial_volume_days: float
    assets: list[AssetCheck]


class Stage(BaseModel):
    name: str
    starts_at: float  # the share of the progress bar done when the stage starts


class DatasetLine(BaseModel):
    id: int
    name: str
    version: int
    status: str  # being built, published or failed
    published_without_check: bool
    failure_reason: str | None
    stage: str | None
    progress: float | None  # 0 to 1
    first_day: date | None
    last_day: date | None
    tickers: list[str]
    check: QualityCheck | None  # None until the build's first step is done
    started_at: datetime | None
    published_at: datetime | None


class DatasetsList(BaseModel):
    datasets: list[DatasetLine]


class PeriodLine(BaseModel):
    kind: str  # warm-up or test
    name: str
    first_day: date | None
    last_day: date | None


class KeyLine(BaseModel):
    masked_id: str
    ticker: str
    name: str
    asset_class: str
    provider_symbol: str
    price_scale: float  # a real price is the stored price divided by this


class MissingBar(BaseModel):
    asset: AssetName
    step: int
    ends_at: datetime | None  # real time (UTC) the bar would have ended
    reason: str  # not supplied, zero volume, or partial-volume day


class PartialVolumeDay(BaseModel):
    asset: AssetName
    day: date | None
    test: str  # a zero-volume bar, or volume under its share of usual
    share_of_usual: float | None  # the day's volume per bar against usual: 0.08 is 8%


class DatasetPage(DatasetLine):
    stages: list[Stage]
    periods: list[PeriodLine]
    asset_key: list[KeyLine]
    missing_bars: list[MissingBar]
    partial_volume_days: list[PartialVolumeDay]


class PricePoint(BaseModel):
    day: date | None
    close: Price


class PriceChart(BaseModel):
    asset: AssetName
    points: list[PricePoint]


def _refuse(code: str, message: str) -> Refusal:
    return Refusal(code=code, message=message)


@dataclass(frozen=True)
class Names:
    """What turns one dataset's masked IDs, day numbers and steps into real ones."""

    names: dict[str, AssetName]
    tickers: list[str]
    first_day: date | None
    last_day: date | None
    price_scales: dict[str, float]

    def asset(self, masked: str) -> AssetName:
        return self.names.get(masked, AssetName(name=masked, masked_id=masked))

    def day(self, number: int) -> date | None:
        return (
            None if self.first_day is None else self.first_day + timedelta(number - 1)
        )

    def step_end(self, step: int) -> datetime | None:
        if self.first_day is None:
            return None
        return datetime.combine(self.first_day, datetime.min.time()) + step * BAR_LENGTH

    def text(self, words: str | None) -> str | None:
        """Masked IDs in a stored message, written as real names."""
        if words is None:
            return None
        return MASKED_ID.sub(lambda m: self.asset(m.group()).name, words)


@dataclass(frozen=True)
class DatasetBuilds:
    store: ApiStore
    builds: Builds

    # --- reads ---------------------------------------------------------------------------

    def list(self) -> DatasetsList:
        rows = self.store.datasets()
        return DatasetsList(
            datasets=[self._line(row, self._names(row)) for row in rows]
        )

    def page(self, dataset_id: int) -> DatasetPage:
        row = self._row(dataset_id)
        names = self._names(row)
        classes = {
            r["MASKED_ID"]: r["ASSET_CLASS"]
            for r in self.store.dataset_rows("REF.ASSETS", dataset_id)
        }
        key = sorted(
            self.store.dataset_rows("KEYS.ASSET_KEY", dataset_id),
            key=lambda k: k["MASKED_ID"],
        )
        periods = sorted(
            self.store.dataset_rows("REF.DATASET_PERIODS", dataset_id),
            key=lambda p: p["FIRST_STEP"],
        )
        missing = sorted(
            self.store.dataset_rows("REF.MISSING_BARS", dataset_id),
            key=lambda m: (m["ASSET"], m["STEP"]),
        )
        partial = sorted(
            self.store.dataset_rows("REF.PARTIAL_VOLUME_DAYS", dataset_id),
            key=lambda d: (d["ASSET"], d["DAY"]),
        )
        return DatasetPage(
            **self._line(row, names).model_dump(),
            stages=[Stage(name=n, starts_at=s) for n, s in STAGES.items()],
            periods=[
                PeriodLine(
                    kind=p["KIND"],
                    name=p["NAME"],
                    first_day=names.day((p["FIRST_STEP"] - 1) // STEPS_PER_DAY + 1),
                    last_day=names.day((p["LAST_STEP"] - 1) // STEPS_PER_DAY + 1),
                )
                for p in periods
            ],
            asset_key=[
                KeyLine(
                    masked_id=k["MASKED_ID"],
                    ticker=k["TICKER"],
                    name=k["NAME"],
                    asset_class=classes.get(k["MASKED_ID"], ""),
                    provider_symbol=k["PROVIDER_SYMBOL"],
                    price_scale=k["PRICE_SCALE"],
                )
                for k in key
            ],
            missing_bars=[
                MissingBar(
                    asset=names.asset(m["ASSET"]),
                    step=m["STEP"],
                    ends_at=names.step_end(m["STEP"]),
                    reason=m["REASON"],
                )
                for m in missing
            ],
            partial_volume_days=[
                PartialVolumeDay(
                    asset=names.asset(d["ASSET"]),
                    day=names.day(d["DAY"]),
                    test=d["TEST"],
                    share_of_usual=d["SHARE_OF_USUAL"],
                )
                for d in partial
            ],
        )

    def chart(self, dataset_id: int, asset: str) -> PriceChart:
        names = self._names(self._row(dataset_id))
        bars = self.store.daily_bars(dataset_id, asset)
        if not bars:
            raise DatasetNotFound(f"{dataset_id} with an asset {asset}")
        scale = names.price_scales.get(asset)
        return PriceChart(
            asset=names.asset(asset),
            points=[
                PricePoint(
                    day=names.day(b["DAY"]),
                    close=Price(
                        real=None if scale is None else round(b["CLOSE"] / scale, 6),
                        rescaled=b["CLOSE"],
                    ),
                )
                for b in bars
            ],
        )

    # --- start and stop ------------------------------------------------------------------

    def start(self, wanted: DatasetToBuild, today: date) -> DatasetStarted:
        settings = self._settings(wanted, today)
        dataset_id, _ = self.store.begin_dataset(
            settings.name,
            {
                "FIRST_STEP": 1,
                "LAST_STEP": ((settings.last_day - settings.first_day).days + 1)
                * STEPS_PER_DAY,
                "LIMIT_OTHER_MISSING": settings.limits.other_missing,
                "LIMIT_PARTIAL_VOLUME_DAYS": settings.limits.partial_volume_days,
                "BUILD_STAGE": next(iter(STAGES)),
                "BUILD_PROGRESS": 0.0,
            },
        )
        try:
            self.builds.start(dataset_id, settings_toml(settings), wanted.check)
        except Exception:
            self.store.update_dataset(
                dataset_id,
                STATUS=str(DatasetStatus.FAILED),
                FAILURE_REASON="its job could not start; details in the API's output",
            )
            raise
        return DatasetStarted(dataset_id=dataset_id)

    def _settings(self, wanted: DatasetToBuild, today: date) -> DatasetSettings:
        """The request as settings, or every reason it is refused."""
        refusals = []
        tickers = [t.strip().upper() for t in wanted.tickers if t.strip()]
        if not tickers:
            refusals.append(
                _refuse("no_tickers", "type at least one ticker, such as AAPL")
            )
        doubled = sorted({t for t in tickers if tickers.count(t) > 1})
        if doubled:
            refusals.append(
                _refuse(
                    "ticker_twice", f"{', '.join(doubled)} is typed twice: keep one"
                )
            )
        if wanted.first_day > wanted.last_day:
            refusals.append(
                _refuse(
                    "days_order", "the first day comes after the last day: swap them"
                )
            )
        if wanted.last_day >= today:
            refusals.append(
                _refuse(
                    "last_day_too_recent",
                    f"the last day must be before today ({today}): the provider's bars of "
                    "the current day carry only part of its trading",
                )
            )
        for name, value in (
            ("partial-volume days", wanted.limit_partial_volume_days),
            ("bars missing for other reasons", wanted.limit_other_missing),
        ):
            if not 0 < value < 1:
                refusals.append(
                    _refuse(
                        "limit_out_of_range",
                        f"the {name} limit must be between 0% and 100%, not {value:.1%}",
                    )
                )
        names = [p.name for p in wanted.test_periods]
        for period in wanted.test_periods:
            if not (
                wanted.first_day
                <= period.first_day
                <= period.last_day
                <= wanted.last_day
            ):
                refusals.append(
                    _refuse(
                        "period_outside",
                        f'the "{period.name}" test period must run forwards inside the '
                        "dataset's days",
                    )
                )
            if names.count(period.name) > 1:
                refusals.append(
                    _refuse("period_twice", f'"{period.name}" is given twice: keep one')
                )
        if any(r["STATUS"] == DatasetStatus.BEING_BUILT for r in self.store.datasets()):
            refusals.append(
                _refuse(
                    "build_in_progress",
                    "a dataset is being built: wait for it to end, or stop it (two builds "
                    "would share Twelve Data's 8 requests a minute)",
                )
            )
        if refusals:
            raise Refused(*refusals)
        return settings_from_tickers(
            tickers,
            wanted.first_day,
            wanted.last_day,
            test_periods=[
                Period(p.name, p.first_day, p.last_day) for p in wanted.test_periods
            ],
            limits=QualityLimits(
                other_missing=wanted.limit_other_missing,
                partial_volume_days=wanted.limit_partial_volume_days,
            ),
        )

    def stop(self, dataset_id: int) -> DatasetPage:
        row = self._row(dataset_id)
        if row["STATUS"] != DatasetStatus.BEING_BUILT:
            raise Refused(
                _refuse(
                    "nothing_to_stop",
                    f"dataset {dataset_id} is {row['STATUS']}: nothing to stop",
                )
            )
        try:
            self.builds.stop(dataset_id)
        except JobNotKilled as error:
            raise Refused(
                _refuse(
                    "job_not_killed",
                    f"{error}; the build is left as it was: end that program by hand, "
                    "then try again",
                )
            ) from None
        # The build may have ended by itself meanwhile (published, or failed at the check).
        if self._row(dataset_id)["STATUS"] == DatasetStatus.BEING_BUILT:
            self.store.update_dataset(
                dataset_id,
                STATUS=str(DatasetStatus.FAILED),
                FAILURE_REASON=STOPPED_BY_HAND,
            )
        return self.page(dataset_id)

    # --- shared ----------------------------------------------------------------------------

    def _row(self, dataset_id: int) -> dict:
        for row in self.store.datasets():
            if row["ID"] == dataset_id:
                return row
        raise DatasetNotFound(dataset_id)

    def _asked(self, dataset_id: int) -> DatasetSettings | None:
        text = self.builds.settings_text(dataset_id)
        return None if text is None else load_settings_text(text)

    def _names(self, row: dict) -> Names:
        key = sorted(
            self.store.dataset_rows("KEYS.ASSET_KEY", row["ID"]),
            key=lambda k: k["MASKED_ID"],
        )
        last_step = row.get("LAST_STEP")
        if key:
            first_day = min(k["FIRST_DAY"] for k in key)
            last_day = (
                None
                if last_step is None
                else first_day + timedelta((last_step - 1) // STEPS_PER_DAY)
            )
            return Names(
                names={
                    k["MASKED_ID"]: AssetName(name=k["NAME"], masked_id=k["MASKED_ID"])
                    for k in key
                },
                tickers=[k["TICKER"] for k in key],
                first_day=first_day,
                last_day=last_day,
                price_scales={k["MASKED_ID"]: k["PRICE_SCALE"] for k in key},
            )
        asked = self._asked(row["ID"])
        if asked is None:
            return Names({}, [], None, None, {})
        return Names(
            names={
                masked_id(i): AssetName(name=a.name or a.ticker, masked_id=masked_id(i))
                for i, a in enumerate(asked.assets)
            },
            tickers=[a.ticker for a in asked.assets],
            first_day=asked.first_day,
            last_day=asked.last_day,
            price_scales={},
        )

    @staticmethod
    def _line(row: dict, names: Names) -> DatasetLine:
        check = row.get("CHECK_RESULT")
        return DatasetLine(
            id=row["ID"],
            name=row["NAME"],
            version=row["VERSION"],
            status=row["STATUS"],
            published_without_check=bool(row.get("PUBLISHED_WITHOUT_CHECK")),
            failure_reason=names.text(row.get("FAILURE_REASON")),
            stage=row.get("BUILD_STAGE"),
            progress=row.get("BUILD_PROGRESS"),
            first_day=names.first_day,
            last_day=names.last_day,
            tickers=names.tickers,
            check=None
            if not check
            else QualityCheck(
                passed=check["passed"],
                limit_other_missing=check["limits"]["other_missing"],
                limit_partial_volume_days=check["limits"]["partial_volume_days"],
                assets=[
                    AssetCheck(
                        asset=names.asset(a["asset"]),
                        other_missing_share=a["other_missing_share"],
                        partial_volume_share=a["partial_volume_share"],
                        over=list(a["over"]),
                    )
                    for a in check["assets"]
                ],
            ),
            started_at=row.get("STARTED_AT"),
            published_at=row.get("PUBLISHED_AT"),
        )
