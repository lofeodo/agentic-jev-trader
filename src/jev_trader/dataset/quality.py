"""The cleaning rules a dataset build applies to one asset's bars (spec appendix 2, sections 5 and 6).

What happens to the account: on a day the agent cannot trust a stock's volume (how much was
traded), it does not look at that stock at all, and an open position keeps its last known price.
No bar is ever made up to fill a gap.

- A stock's bars outside its session (its trading hours that day, from the exchange calendar)
  are dropped first. On a day the market closes early, at 13:00 New York time, the provider
  still returns zero-volume bars up to the usual close; once dropped, the day has 14 bars.
- A **partial-volume day** (ADR 0008) is a stock's session in which any bar has zero volume, or
  whose average volume per bar is under a quarter of usual. "Usual" is the median (the middle
  value) of the average volume per bar of the stock's previous 20 sessions, taken as the
  provider supplied them. A session with no bars at all is left out of that median. If Apple's
  last 20 sessions averaged around 40,000 shares a bar, a session averaging 8,000 (a fifth of
  usual) is partial-volume: every bar of that day counts as missing.
- A **missing bar** is a bar the asset should have and does not get: not supplied, supplied with
  zero volume (Bitcoin only: such bars stay missing one at a time), or on a partial-volume day.
"""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from jev_trader.dataset.bars import BAR_LENGTH, STEPS_PER_DAY, Bar
from jev_trader.dataset.measurements import AssetClass, Session


@dataclass(frozen=True)
class UsualVolume:
    """The partial-volume test's two settings, stored with the dataset: a stock's day is
    partial-volume when its average volume per bar is under `share` of the median of its
    previous `sessions` sessions (ADR 0008)."""

    share: float = 0.25
    sessions: int = 20


class MissingReason(StrEnum):
    NOT_SUPPLIED = "not supplied"
    ZERO_VOLUME = "zero volume"
    PARTIAL_VOLUME_DAY = "partial-volume day"


class PartialVolumeTest(StrEnum):
    """Which test caught a partial-volume day."""

    ZERO_VOLUME_BAR = "a zero-volume bar"
    # The share of usual is a dataset setting (a quarter by default), stored with it.
    UNDER_USUAL = "volume under its share of usual"


@dataclass(frozen=True)
class MissingBar:
    start: datetime
    reason: MissingReason


@dataclass(frozen=True)
class PartialVolumeDay:
    """`share_of_usual` is the day's average volume per bar over usual: 0.08 is 8% of usual.

    It is `None` when there is no usual to compare with (every earlier session had no volume).
    """

    day: date
    test: PartialVolumeTest
    share_of_usual: float | None


@dataclass(frozen=True)
class CleanSeries:
    """One asset's bars after cleaning, and its part of the quality report.

    `expected_bars` counts every bar the asset should have in the dataset's range: 96 a day for
    crypto, every 15 minutes of every session for a stock. `days` counts sessions for a stock,
    UTC days for crypto.
    """

    bars: list[Bar]
    missing: list[MissingBar]
    partial_volume_days: list[PartialVolumeDay]
    expected_bars: int
    days: int

    @property
    def other_missing_share(self) -> float:
        """Share of expected bars missing for any reason other than a partial-volume day."""
        other = sum(
            1 for m in self.missing if m.reason is not MissingReason.PARTIAL_VOLUME_DAY
        )
        return other / self.expected_bars if self.expected_bars else 0.0

    @property
    def partial_volume_share(self) -> float:
        """Share of sessions that are partial-volume days (always 0 for crypto)."""
        return len(self.partial_volume_days) / self.days if self.days else 0.0


class NotEnoughHistory(Exception):
    """A stock's history does not reach back far enough to judge usual volume."""


def _slots(sess: Session) -> list[datetime]:
    n = (sess.close - sess.open) // BAR_LENGTH
    return [sess.open + i * BAR_LENGTH for i in range(n)]


def _by_session(
    bars: Iterable[Bar], sessions: Sequence[tuple[date, Session]]
) -> dict[date, list[Bar]]:
    """Each session's bars, keeping only those inside the session (one per 15-minute slot)."""
    slot_day = {slot: day for day, sess in sessions for slot in _slots(sess)}
    kept: dict[date, dict[datetime, Bar]] = defaultdict(dict)
    for bar in bars:
        day = slot_day.get(bar.start)
        if day is not None:
            kept[day][bar.start] = bar
    return {
        day: sorted(by_start.values(), key=lambda b: b.start)
        for day, by_start in kept.items()
    }


def _average_volume(bars: Sequence[Bar]) -> float | None:
    return sum(b.volume for b in bars) / len(bars) if bars else None


def clean_stock(
    bars: Iterable[Bar],
    sessions: Sequence[tuple[date, Session]],
    lead_in: Sequence[tuple[date, Session]],
    usual: UsualVolume | None = None,
) -> CleanSeries:
    """Clean one stock's bars over the dataset's `sessions` (oldest first).

    `bars` are as the provider supplied them, UTC, lead-in sessions included. `lead_in` are the
    sessions just before the dataset's first one: they only supply usual volume and none of
    their bars is kept. Raises `NotEnoughHistory` if there are fewer than `usual.sessions` of
    them or the stock has no bar on or before the earliest.
    """
    usual = usual or UsualVolume()
    bars = list(bars)
    if len(lead_in) < usual.sessions:
        raise NotEnoughHistory(
            f"needs {usual.sessions} sessions before the first day, the calendar gives {len(lead_in)}"
        )
    earliest = lead_in[-usual.sessions][1]
    if not any(b.start < earliest.close for b in bars):
        raise NotEnoughHistory(
            f"the provider has no bar on or before {earliest.open.date()}, {usual.sessions} "
            "sessions before the first day"
        )

    lead_in = list(lead_in[-usual.sessions :])
    all_sessions = lead_in + list(sessions)
    by_day = _by_session(bars, all_sessions)
    averages = [_average_volume(by_day.get(day, [])) for day, _ in all_sessions]

    kept: list[Bar] = []
    missing: list[MissingBar] = []
    partial: list[PartialVolumeDay] = []
    for i, (day, sess) in enumerate(sessions, start=len(lead_in)):
        day_bars = by_day.get(day, [])
        earlier = [a for a in averages[i - usual.sessions : i] if a is not None]
        typical = statistics.median(earlier) if earlier else None
        average = _average_volume(day_bars)
        share = average / typical if average is not None and typical else None

        test = None
        if any(b.volume == 0 for b in day_bars):
            test = PartialVolumeTest.ZERO_VOLUME_BAR
        elif share is not None and share < usual.share:
            test = PartialVolumeTest.UNDER_USUAL

        if test is not None:
            partial.append(PartialVolumeDay(day, test, share))
            missing += [
                MissingBar(slot, MissingReason.PARTIAL_VOLUME_DAY)
                for slot in _slots(sess)
            ]
            continue
        supplied = {b.start for b in day_bars}
        missing += [
            MissingBar(slot, MissingReason.NOT_SUPPLIED)
            for slot in _slots(sess)
            if slot not in supplied
        ]
        kept += day_bars

    expected = sum(len(_slots(sess)) for _, sess in sessions)
    return CleanSeries(kept, missing, partial, expected, len(sessions))


def clean_crypto(bars: Iterable[Bar], first_day: date, last_day: date) -> CleanSeries:
    """Clean a crypto asset's bars over every 15 minutes from `first_day` to `last_day` (UTC).

    A zero-volume bar means the exchange was down: that bar alone is missing.
    """
    begins = datetime.combine(first_day, time(), tzinfo=UTC)
    days = (last_day - first_day).days + 1
    ends = begins + timedelta(days=days)
    by_start = {b.start: b for b in bars if begins <= b.start < ends}

    kept: list[Bar] = []
    missing: list[MissingBar] = []
    slot = begins
    while slot < ends:
        bar = by_start.get(slot)
        if bar is None:
            missing.append(MissingBar(slot, MissingReason.NOT_SUPPLIED))
        elif bar.volume == 0:
            missing.append(MissingBar(slot, MissingReason.ZERO_VOLUME))
        else:
            kept.append(bar)
        slot += BAR_LENGTH
    return CleanSeries(kept, missing, [], days * STEPS_PER_DAY, days)


class QualityLimit(StrEnum):
    """The two limits a build checks."""

    OTHER_MISSING = "bars missing for other reasons"
    PARTIAL_VOLUME_DAYS = "partial-volume days"


@dataclass(frozen=True)
class QualityLimits:
    """The two limits a build checks, as shares: 0.005 is 0.5%. Both are dataset settings.

    `other_missing`: an asset's bars missing because they were not supplied, or (crypto)
    supplied with zero volume. `partial_volume_days`: a stock's sessions that are partial-volume
    days; 3% is about 7 sessions a year.
    """

    other_missing: float = 0.005
    partial_volume_days: float = 0.03


@dataclass(frozen=True)
class AssetCheck:
    """One asset's measured values against the limits. `over` names each limit it passes."""

    asset: str  # masked ID, such as ASSET_01
    other_missing_share: float
    partial_volume_share: float | None  # None for crypto: the rule covers stocks only
    over: list[QualityLimit]


@dataclass(frozen=True)
class CheckResult:
    assets: list[AssetCheck]
    limits: QualityLimits

    @property
    def passed(self) -> bool:
        return not any(a.over for a in self.assets)

    def message(self, names: dict[str, str] | None = None) -> str:
        """Which asset is over which limit, and the ways out. `names` renames assets in it."""
        if self.passed:
            return "Every asset is inside both limits."
        names = names or {}
        lines = ["Over a limit:"]
        for a in self.assets:
            name = names.get(a.asset, a.asset)
            if QualityLimit.OTHER_MISSING in a.over:
                lines.append(
                    f"- {name}: {a.other_missing_share:.1%} of its bars are missing for "
                    f"other reasons (limit {self.limits.other_missing:.1%})"
                )
            if QualityLimit.PARTIAL_VOLUME_DAYS in a.over:
                lines.append(
                    f"- {name}: {a.partial_volume_share:.1%} of its sessions are "
                    f"partial-volume days (limit {self.limits.partial_volume_days:.1%})"
                )
        lines.append(
            "Ways out: pick other first and last days, leave the asset out, raise the limit (on "
            "the Datasets form, or in the settings file), or build with the check off (untick "
            "the check box on the form, or --no-check on the command line), which publishes the "
            'dataset marked "published without the check".'
        )
        return "\n".join(lines)


def check_limits(
    series: dict[str, tuple[AssetClass, CleanSeries]], limits: QualityLimits
) -> CheckResult:
    """Compare each asset's cleaned bars with the two limits, in the order given."""
    checks = []
    for asset, (asset_class, clean) in series.items():
        over = []
        if clean.other_missing_share > limits.other_missing:
            over.append(QualityLimit.OTHER_MISSING)
        partial = None
        if asset_class is AssetClass.STOCK:
            partial = clean.partial_volume_share
            if partial > limits.partial_volume_days:
                over.append(QualityLimit.PARTIAL_VOLUME_DAYS)
        checks.append(AssetCheck(asset, clean.other_missing_share, partial, over))
    return CheckResult(checks, limits)
