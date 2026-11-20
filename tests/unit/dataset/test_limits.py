"""The check of the two limits a build applies before its slow part (spec appendix 2, section 7)."""

from datetime import UTC, date, datetime

from jev_trader.dataset.measurements import AssetClass
from jev_trader.dataset.quality import (
    CleanSeries,
    Limits,
    MissingBar,
    MissingReason,
    PartialVolumeDay,
    PartialVolumeTest,
    check_limits,
)

T = datetime(2024, 4, 8, 14, tzinfo=UTC)


def series(
    other_missing: int, partial_days: int, expected: int = 1000, days: int = 100
):
    return CleanSeries(
        bars=[],
        missing=[MissingBar(T, MissingReason.NOT_SUPPLIED)] * other_missing,
        partial_volume_days=[
            PartialVolumeDay(date(2024, 4, 8), PartialVolumeTest.ZERO_VOLUME_BAR, 0.05)
        ]
        * partial_days,
        expected_bars=expected,
        days=days,
    )


def test_assets_inside_both_limits_pass():
    result = check_limits(
        {
            "SPY": (AssetClass.STOCK, series(other_missing=5, partial_days=3)),
            "BTC": (AssetClass.CRYPTO, series(other_missing=5, partial_days=0)),
        },
        Limits(),
    )
    assert result.passed
    assert [a.over for a in result.assets] == [[], []]
    assert result.assets[0].other_missing_share == 0.005
    assert result.assets[0].partial_volume_share == 0.03
    assert result.assets[1].partial_volume_share is None


def test_the_check_names_which_asset_is_over_which_limit():
    result = check_limits(
        {
            "SPY": (AssetClass.STOCK, series(other_missing=0, partial_days=1)),
            "JPM": (AssetClass.STOCK, series(other_missing=0, partial_days=4)),
            "BTC": (AssetClass.CRYPTO, series(other_missing=6, partial_days=0)),
        },
        Limits(),
    )
    assert not result.passed
    assert [(a.asset, a.over) for a in result.assets if a.over] == [
        ("JPM", ["partial-volume days"]),
        ("BTC", ["bars missing for other reasons"]),
    ]
    message = result.message()
    assert "JPM: 4.0% of its sessions are partial-volume days (limit 3.0%)" in message
    assert "BTC: 0.6% of its bars are missing for other reasons (limit 0.5%)" in message
    assert "SPY" not in message
    assert "--no-check" in message


def test_limits_are_settings():
    result = check_limits(
        {"JPM": (AssetClass.STOCK, series(other_missing=0, partial_days=4))},
        Limits(other_missing=0.005, partial_volume_days=0.05),
    )
    assert result.passed
