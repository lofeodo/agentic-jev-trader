"""The free check of the memory's search values (spec appendix 9, section 7), on made-up
memories whose expected figures are worked out by hand in each test."""

import pytest

from jev_trader.memory.__main__ import main
from jev_trader.memory.search import SearchSettings
from jev_trader.memory.search_check import Record, check
from jev_trader.storage.snowflake import DATABASE

UP, DOWN = (1.0, 0.0), (-1.0, 0.0)


def vector(*leading: float) -> list[float]:
    return [*leading, *[0.0] * (58 - len(leading))]


def record(
    id,
    step,
    ended,
    features=None,
    embedding=(1.0, 0.0),
    known_from=None,
    asset="A",
    kind="full_evaluation",
    direction=None,
):
    return Record(
        id=id,
        asset=asset,
        step=step,
        kind=kind,
        direction=direction,
        known_from=step + 4 if known_from is None else known_from,
        features=features or vector(),
        embedding=embedding,
        ended=ended,
    )


def clustered(id, step, ended):
    """A record whose vector and text both sit with the others that ended its way."""
    sign = 1.0 if ended == "up" else -1.0
    return record(id, step, ended, vector(sign), UP if sign > 0 else DOWN)


TWO = SearchSettings(results=2)


def test_similar_records_ending_alike_beat_random_ones():
    """Six records alternating up and down, 10 steps apart, each complete 4 steps later, looked
    up 2 at a time. The first two have fewer than 2 earlier records and are not checked.
    r3: both earlier (r1 up, r2 down) are returned: 1/2 alike; at random 1/2.
    r4: r2 (alike) and one of r1, r3 (not): 1/2; at random 1/3.
    r5: r1 and r3: 2/2; at random 2/4.
    r6: r2 and r4: 2/2; at random 2/5."""
    memory = [
        clustered(f"r{n}", 10 * n, "up" if n % 2 else "down") for n in range(1, 7)
    ]
    found = check(memory, TWO)
    assert found.checked == 4
    assert found.similar_alike == pytest.approx((0.5 + 0.5 + 1 + 1) / 4)
    assert found.random_alike == pytest.approx((1 / 2 + 1 / 3 + 2 / 4 + 2 / 5) / 4)


def test_a_record_whose_ending_is_not_known_yet_is_never_compared():
    """r2's 4-bar price is known only at step 100, after r3 is decided: r3 has one earlier
    record to look at, fewer than the 2 the search returns, so it is not checked."""
    memory = [
        clustered("r1", 10, "up"),
        record("r2", 20, "down", vector(-1.0), DOWN, known_from=100),
        clustered("r3", 30, "up"),
    ]
    assert check(memory, TWO).checked == 0
    assert (
        check(memory[:1] + [clustered("r2", 20, "down")] + memory[2:], TWO).checked == 1
    )


def test_a_review_is_compared_only_with_reviews_of_positions_in_its_direction():
    """A short's review and a full evaluation sit just before f and ended the other way; f's
    pool is the two earlier long reviews, which both ended up. No other record has 2 of its
    own kind before it, so f alone is checked."""

    def review(id, step, ended, direction):
        return record(id, step, ended, kind="position_review", direction=direction)

    memory = [
        review("a", 10, "up", "long"),
        review("b", 20, "up", "long"),
        review("c", 30, "down", "short"),
        record("d", 40, "down"),
        review("f", 60, "up", "long"),
    ]
    found = check(memory, TWO)
    assert found.checked == 1
    assert found.similar_alike == found.random_alike == 1.0


def test_the_two_values_change_which_records_are_called_similar():
    """How each record ended follows its newest bar (the first number), not its context (the
    49th). r3, r4 and r5 are checked, nearest 2 by vector.
    Shapes hold all the say: r3 gets r1, r2 (1/2); r4 gets r2 and r1 (1/2); r5 gets r1, r3 (1).
    Context holds it all: r3 gets r1, r2 (1/2); r4 gets r3 and r1 (0); r5 gets r1, r2 (1/2)."""

    def made(id, step, shape, context):
        ended = "up" if shape > 0 else "down"
        features = vector(shape, *[0.0] * 47, context)
        return record(id, step, ended, features)

    memory = [
        made("r1", 10, 1.0, 1.0),
        made("r2", 20, -1.0, 1.0),
        made("r3", 30, 1.0, -1.0),
        made("r4", 40, -1.0, -1.0),
        made("r5", 50, 1.0, 1.0),
    ]
    by_shape = check(memory, SearchSettings(results=2, shape_share=1.0))
    by_context = check(memory, SearchSettings(results=2, shape_share=0.0))
    assert by_shape.vector_alike == pytest.approx(2 / 3)
    assert by_context.vector_alike == pytest.approx(1 / 3)


def test_a_sample_checks_records_spread_evenly_over_the_memory():
    """3 of 6: the 1st, 3rd and 6th. The 1st has nothing before it; r3 scores 1/2, r6 2/2."""
    memory = [
        clustered(f"r{n}", 10 * n, "up" if n % 2 else "down") for n in range(1, 7)
    ]
    found = check(memory, TWO, sample=3)
    assert found.checked == 2
    assert found.similar_alike == pytest.approx((0.5 + 1) / 2)


def run(capsys, *argv, memory):
    """The command, with the memory handed over in place of reading Snowflake."""
    asked = {}

    def load(sim, after, database):
        asked.update(sim=sim, after=after, database=database)
        return {"memory_search": {"results": 2}}, memory

    code = main(["check-search", *argv], load_memory=load)
    return code, capsys.readouterr().out, asked


ALTERNATING = [
    clustered(f"r{n}", 10 * n, "up" if n % 2 else "down") for n in range(1, 7)
]


def test_the_command_reports_in_plain_words_with_the_sims_own_values(capsys):
    code, out, asked = run(capsys, "--sim", "7", memory=ALTERNATING)
    assert code == 0
    assert asked == {"sim": 7, "after": "4_bars", "database": DATABASE}
    assert "4 of 6 records" in out
    assert "shapes 50% of the say, each older bar 15% less" in out
    assert "ended the same way 75.0% of the time" in out
    assert "picked at random: 43.3%" in out
    assert "ended the same way more often than random ones" in out
    out.encode("ascii")  # conda run on Windows fails on other characters


def test_other_values_are_tried_from_the_command_line(capsys):
    _, out, asked = run(
        capsys,
        "--sim", "7",
        "--shape-share", "0.3", "0.7",
        "--bar-decay", "0.1",
        "--after", "end_of_day",
        "--database", "TRADING_AGENT_TEST",
        memory=ALTERNATING,
    )  # fmt: skip
    assert asked["after"] == "end_of_day"
    assert asked["database"] == "TRADING_AGENT_TEST"
    assert "shapes 30% of the say, each older bar 10% less" in out
    assert "shapes 70% of the say, each older bar 10% less" in out
    assert "15% less" not in out


def test_the_command_says_when_similar_records_did_no_better(capsys):
    """All six records look alike, so the search returns the first two, r1 and r2, which ended
    up; r3 to r6 ended down. Similar: 0 of 2 every time; at random r4 to r6 find some down."""
    memory = [record(f"r{n}", 10 * n, "up" if n <= 2 else "down") for n in range(1, 7)]
    _, out, _ = run(capsys, "--sim", "7", memory=memory)
    assert "ended the same way 0.0% of the time" in out
    assert "did not end the same way more often than random ones" in out
    assert "--shape-share" in out
