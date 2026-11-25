"""The search's arithmetic (spec appendix 5, section 3): the weights of the feature vector, the
merge of the two rankings, and repeats removed. Expected figures are the spec's own."""

import pytest

from jev_trader.memory.search import (
    Candidate,
    SearchSettings,
    feature_weights,
    merge,
)


def share_of(weights, positions):
    """The share of the say held by some numbers of the vector: their squared weights."""
    return sum(weights[i] ** 2 for i in positions)


def test_shapes_and_context_each_hold_half_the_say():
    w = feature_weights(SearchSettings())
    assert len(w) == 58
    assert share_of(w, range(48)) == pytest.approx(0.5)
    assert share_of(w, range(48, 58)) == pytest.approx(0.5)


def test_each_older_bar_counts_15_percent_less():
    w = feature_weights(SearchSettings())
    newest, oldest = range(6), range(42, 48)
    assert share_of(w, newest) == pytest.approx(0.103, abs=0.0005)
    assert share_of(w, oldest) == pytest.approx(0.033, abs=0.0005)
    assert share_of(w, range(6, 12)) == pytest.approx(0.85 * share_of(w, newest))
    assert share_of(w, [50]) == pytest.approx(0.05)


def test_close_both_ways_beats_close_one_way():
    merged = merge(["a", "b"] + [f"x{i}" for i in range(38)] + ["c"], ["c", "x0", "a"])
    scores = {m.id: m.score for m in merged}
    assert scores["a"] == pytest.approx(0.032, abs=0.0005)  # 1st and 3rd
    assert scores["x0"] > scores["b"]  # ranked both ways beats 2nd one way
    assert merged[0].id == "a"
    a = merged[0]
    assert (a.vector_rank, a.text_rank, a.merged_rank) == (1, 3, 1)


def test_second_and_fortieth_score_about_0_026():
    by_vector = ["z", "a"]
    by_text = [f"y{i}" for i in range(39)] + ["a"]
    scores = {m.id: m.score for m in merge(by_vector, by_text)}
    assert scores["a"] == pytest.approx(0.026, abs=0.0005)


def test_equal_scores_are_ordered_the_same_way_every_time():
    """Ranked only one way each, 1st by vector and 1st by text tie: the vector's comes first,
    whichever order the rankings arrive in."""
    first = [m.id for m in merge(["v"], ["t"])]
    assert first == [m.id for m in merge(["v"], ["t"])] == ["v", "t"]


def candidate(id, asset, step):
    return Candidate(id=id, asset=asset, step=step)


def test_repeats_from_one_asset_under_8_bars_apart_keep_the_closest_match():
    from jev_trader.memory.search import best_without_repeats

    ranked = [
        candidate("a", "ASSET_01", 100),
        candidate("b", "ASSET_01", 107),  # 7 bars after a: a repeat
        candidate("c", "ASSET_02", 101),  # another asset
        candidate("d", "ASSET_01", 108),  # 8 bars after a: kept
    ]
    assert [c.id for c in best_without_repeats(ranked, 10)] == ["a", "c", "d"]
    assert [c.id for c in best_without_repeats(ranked, 2)] == ["a", "c"]
