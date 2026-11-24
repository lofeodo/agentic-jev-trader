"""The medium risk profile and the sizing arithmetic (spec appendix 1, section 5).

Dollar figures are the spec's own examples, on a $10,000 account.
"""

import dataclasses

import pytest

from jev_trader.risk import RISK_PROFILE_PATH, RiskLimit, RiskProfile, load_risk_profile

MEDIUM = RiskProfile(
    name="medium",
    trade_risk_limit=0.01,
    size_buckets=(0.2, 0.4, 0.8, 1.2, 2.0),
    position_limit=2.0,
    exposure_limit=2.0,
    daily_loss_limit=0.05,
    forced_close_share=0.25,
    no_new_stock_trade_bars=2,
    screen_cut_off=0.5,
)


def test_the_medium_profile_comes_from_config():
    assert load_risk_profile() == MEDIUM


def test_the_profile_is_stored_as_plain_settings_under_its_name():
    stored = dataclasses.asdict(load_risk_profile())
    assert stored["name"] == "medium"
    assert stored["trade_risk_limit"] == 0.01


def test_a_setting_changed_in_the_file_changes_the_profile(tmp_path):
    text = RISK_PROFILE_PATH.read_text(encoding="utf-8")
    changed = tmp_path / "risk_profile.toml"
    changed.write_text(
        text.replace("trade_risk_limit = 0.01", "trade_risk_limit = 0.02"),
        encoding="utf-8",
    )
    assert load_risk_profile(changed).trade_risk_limit == 0.02
    # The limit it changes works with no code change: a stop price 1.5% away allows $6,667
    # at 1% ($100 of loss), and twice that at 2%.
    assert MEDIUM.largest_size(
        account_value=10_000.0, price=100.0, stop_price=98.5
    ) == (pytest.approx(6_666.67, abs=0.01), RiskLimit.TRADE_RISK)
    assert load_risk_profile(changed).largest_size(
        account_value=10_000.0, price=100.0, stop_price=98.5
    ) == (pytest.approx(13_333.33, abs=0.01), RiskLimit.TRADE_RISK)


# How a trade's size is set


def test_jevs_size_is_the_buckets_weighted_by_its_probabilities():
    # 50% on $4,000 and 50% on $8,000 gives $6,000.
    assert MEDIUM.chosen_size([0, 0.5, 0.5, 0, 0], 10_000.0) == pytest.approx(6_000.0)


def test_probabilities_that_do_not_add_up_to_one_still_give_an_average():
    assert MEDIUM.chosen_size([0, 0.49, 0.49, 0, 0], 10_000.0) == pytest.approx(6_000.0)


def test_a_size_under_every_limit_is_left_alone():
    assert MEDIUM.fit(
        6_000.0, account_value=10_000.0, price=100.0, stop_price=99.0
    ) == (6_000.0, None)


@pytest.mark.parametrize(
    ("stop_price", "allowed"),
    [
        # A stop price 0.95% away: $20,000 would lose $190, so about $10,500 loses $100.
        (99.05, 10_526.32),
        # 0.6% away allows about $16,700.
        (99.4, 16_666.67),
    ],
)
def test_the_trade_risk_limit_cuts_the_size_to_lose_one_percent_at_the_stop_price(
    stop_price, allowed
):
    amount, limit = MEDIUM.fit(
        20_000.0, account_value=10_000.0, price=100.0, stop_price=stop_price
    )
    assert amount == pytest.approx(allowed, abs=0.01)
    assert limit is RiskLimit.TRADE_RISK
    # What it would lose at its stop price is exactly 1% of account value.
    assert amount * (100.0 - stop_price) / 100.0 == pytest.approx(100.0)


def test_a_shorts_stop_price_sits_above_and_counts_the_same():
    amount, limit = MEDIUM.fit(
        20_000.0, account_value=10_000.0, price=100.0, stop_price=100.6
    )
    assert amount == pytest.approx(16_666.67, abs=0.01)
    assert limit is RiskLimit.TRADE_RISK


def test_the_exposure_limit_counts_what_is_already_held():
    # $15,000 already held: $5,000 of room is left under $20,000.
    assert MEDIUM.fit(
        8_000.0,
        account_value=10_000.0,
        price=100.0,
        stop_price=99.5,
        exposure=15_000.0,
    ) == (pytest.approx(5_000.0), RiskLimit.EXPOSURE)


def test_an_add_shares_the_trade_risk_room_with_the_position_already_held():
    # $5,000 held with a stop price 1% away already risks $50: an add may risk $50 more.
    assert MEDIUM.fit(
        8_000.0,
        account_value=10_000.0,
        price=100.0,
        stop_price=99.0,
        position_value=5_000.0,
        exposure=5_000.0,
    ) == (pytest.approx(5_000.0), RiskLimit.TRADE_RISK)


def test_an_add_stops_at_the_position_limit():
    # $18,000 held: $2,000 more reaches twice account value.
    assert MEDIUM.fit(
        8_000.0,
        account_value=10_000.0,
        price=100.0,
        stop_price=99.75,
        position_value=18_000.0,
        exposure=18_000.0,
    ) == (pytest.approx(2_000.0), RiskLimit.POSITION)


def test_no_room_left_gives_nothing():
    assert MEDIUM.fit(
        2_000.0,
        account_value=10_000.0,
        price=100.0,
        stop_price=99.0,
        exposure=20_000.0,
    ) == (0.0, RiskLimit.EXPOSURE)


# The account-wide rules


def test_forced_close_below_a_quarter_of_what_is_held():
    # $3,000 holding $13,000: a quarter is $3,250.
    assert MEDIUM.forced_close_due(account_value=3_000.0, exposure=13_000.0)
    assert not MEDIUM.forced_close_due(account_value=3_300.0, exposure=13_000.0)
    assert not MEDIUM.forced_close_due(account_value=10_000.0, exposure=0.0)


def test_the_daily_loss_limit_is_reached_at_five_percent_down():
    assert MEDIUM.daily_loss_reached(account_value=9_500.0, start_of_day=10_000.0)
    assert not MEDIUM.daily_loss_reached(account_value=9_501.0, start_of_day=10_000.0)


def test_no_new_stock_trade_in_the_sessions_last_two_bars():
    assert MEDIUM.stock_entry_allowed(bars_left=2)
    assert not MEDIUM.stock_entry_allowed(bars_left=1)
    assert not MEDIUM.stock_entry_allowed(bars_left=0)
    # An add is still allowed at the second-to-last bar, never at the last.
    assert MEDIUM.stock_add_allowed(bars_left=1)
    assert not MEDIUM.stock_add_allowed(bars_left=0)
