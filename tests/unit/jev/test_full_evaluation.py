"""How code reads Jev's answers in a full evaluation (spec appendix 4, sections 5.3, 5.4 and 6)."""

import pytest

from jev_trader.broker import load_stop_price_settings
from jev_trader.jev.full_evaluation import (
    NO_TRADE,
    average_copies,
    candidate_trades,
    read_pick,
    shuffled_orders,
)

TRADES = candidate_trades(100.0, 0.6, load_stop_price_settings())
NAMES = [t.name for t in TRADES] + [NO_TRADE]


def pick(long, short, no_trade):
    names = ("tight", "medium", "wide")
    return {
        **{f"long_{w}_stop": p for w, p in zip(names, long, strict=True)},
        **{f"short_{w}_stop": p for w, p in zip(names, short, strict=True)},
        NO_TRADE: no_trade,
    }


def test_the_specs_example_picks_the_long_with_the_tight_stop_price():
    # Long 0.64 (0.34 tight, 0.21 medium, 0.09 wide), no trade 0.29, short 0.07.
    answer = pick((0.34, 0.21, 0.09), (0.03, 0.02, 0.02), 0.29)
    assert read_pick(answer, TRADES) == "long_tight_stop"


def test_a_long_vote_split_three_ways_still_beats_no_trade():
    answer = pick((0.20, 0.25, 0.22), (0.01, 0.01, 0.01), 0.30)
    assert read_pick(answer, TRADES) == "long_medium_stop"


def test_a_short_wins_the_same_way():
    answer = pick((0.05, 0.05, 0.05), (0.1, 0.2, 0.25), 0.30)
    assert read_pick(answer, TRADES) == "short_wide_stop"


def test_no_trade_wins_when_it_is_the_largest_direction():
    answer = pick((0.2, 0.1, 0.0), (0.1, 0.1, 0.0), 0.5)
    assert read_pick(answer, TRADES) == NO_TRADE


@pytest.mark.parametrize(
    "answer",
    [
        pick((0.3, 0.1, 0.1), (0.0, 0.0, 0.0), 0.5),  # long ties no trade
        pick((0.3, 0.1, 0.0), (0.2, 0.2, 0.0), 0.2),  # long ties short
        # 0.1 + 0.2 + 0.1 is 0.4000000000000001 in floating point: still a tie
        pick((0.1, 0.2, 0.1), (0.1, 0.1, 0.0), 0.4),
    ],
)
def test_a_tie_between_directions_goes_to_no_trade(answer):
    assert read_pick(answer, TRADES) == NO_TRADE


def test_a_tie_between_stop_prices_goes_to_the_tighter_one():
    answer = pick((0.1, 0.25, 0.25), (0.0, 0.0, 0.0), 0.4)
    assert read_pick(answer, TRADES) == "long_medium_stop"


def test_copies_are_averaged_option_by_option():
    first = {"a": 0.6, "b": 0.4}
    second = {"b": 0.2, "a": 0.8}
    assert average_copies([first, second]) == pytest.approx({"a": 0.7, "b": 0.3})


def test_each_copy_is_a_shuffled_order_of_all_seven_options():
    orders = shuffled_orders(NAMES, seed=0, step=150, asset="ASSET_01")
    assert len(orders) == 5
    assert all(sorted(order) == sorted(NAMES) for order in orders)
    assert len({tuple(order) for order in orders}) > 1


def test_the_shuffles_come_from_the_seed_the_step_and_the_asset():
    once = shuffled_orders(NAMES, seed=0, step=150, asset="ASSET_01")
    assert shuffled_orders(NAMES, seed=0, step=150, asset="ASSET_01") == once
    assert shuffled_orders(NAMES, seed=1, step=150, asset="ASSET_01") != once
    assert shuffled_orders(NAMES, seed=0, step=151, asset="ASSET_01") != once
    assert shuffled_orders(NAMES, seed=0, step=150, asset="ASSET_02") != once
