"""How code reads Jev's answers in a position review (spec appendix 4, section 7)."""

import pytest

from jev_trader.jev.position_review import read_action, reduce_share


def test_the_action_with_the_highest_probability_wins():
    # The page's example: hold 0.46, close 0.13, reduce 0.33, add 0.08.
    assert read_action({"hold": 0.46, "close": 0.13, "reduce": 0.33, "add": 0.08}) == (
        "hold"
    )
    assert read_action({"hold": 0.2, "close": 0.5, "reduce": 0.3}) == "close"


def test_a_tie_goes_to_the_action_that_changes_least():
    assert read_action({"hold": 0.4, "close": 0.4, "reduce": 0.2}) == "hold"
    assert read_action({"hold": 0.1, "close": 0.1 + 0.2, "reduce": 0.3}) == "close"
    assert read_action({"hold": 0.1, "reduce": 0.3, "add": 0.3, "close": 0.3}) == (
        "close"
    )


def test_the_reduce_share_is_weighted_by_jevs_probabilities():
    # 50% on a quarter and 50% on half closes three eighths.
    half_and_half = {"reduce_25_percent": 0.5, "reduce_50_percent": 0.5}
    assert reduce_share({**half_and_half, "reduce_75_percent": 0.0}) == 0.375
    # Rounded answers that do not add up to 1 still average to a share.
    assert reduce_share(
        {"reduce_25_percent": 0.0, "reduce_50_percent": 0.49, "reduce_75_percent": 0.49}
    ) == pytest.approx(0.625)
