"""The memory server's three tools, called through the real MCP client and the bridge (spec
appendix 5, sections 3 and 4; appendix 10, section 2).

The server's own code runs over an in-memory stand-in for the database with made-up embeddings
(`conftest.py`). An episode is a stored full evaluation or position review with how it turned out.
"""

import pytest

from jev_trader.memory.bridge import LookupContext, MemoryToolFailed
from jev_trader.memory.lookups import NotAllowed
from jev_trader.memory.render import Reader, full_episode, summary_line, track_record
from tests.unit.memory.conftest import SIM, bridge_to, run, served, vector

NOW = 500
ASSET = "ASSET_01"
OTHER = "ASSET_02"


def current(memory, asset=ASSET, **snapshot):
    memory.snapshot(
        asset, NOW, features=vector(0.0), embedding=(1.0, 0.0, 0.0), **snapshot
    )


def full_evaluation(asset=ASSET):
    return LookupContext(sim=SIM, step=NOW, asset=asset)


def position_review(direction="long"):
    return LookupContext(
        sim=SIM,
        step=NOW,
        asset=ASSET,
        job="position_review",
        position_direction=direction,
    )


def search(memory, context=None, **filters):
    async def body():
        async with bridge_to(memory.store, context or full_evaluation()) as bridge:
            return await bridge.search(**filters)

    return run(body)


def ids(result):
    return [f.episode.id for f in result.episodes]


def test_the_server_answers_its_health_route_and_only_its_own_host_names(memory):
    async def body():
        async with served(memory.store) as http:
            health = await http.get("/health")
            elsewhere = await http.post("http://elsewhere/mcp", json={})
            return health.status_code, health.json(), elsewhere.status_code

    assert run(body) == (200, {"status": "ok"}, 421)


def test_the_closest_both_ways_comes_first_with_both_ranks_kept(memory):
    current(memory)
    near = memory.no_trade(ASSET, 100, features=vector(0.1), embedding=(1, 0.1, 0))
    text_only = memory.no_trade(OTHER, 120, features=vector(4.0), embedding=(1, 0, 0))
    far = memory.no_trade(OTHER, 200, features=vector(3.0), embedding=(0, 1, 0))

    result = search(memory)

    assert ids(result) == [near, text_only, far]
    first = result.episodes[0]
    assert (first.vector_rank, first.text_rank, first.merged_rank) == (1, 2, 1)
    assert result.episodes[1].text_rank == 1


def test_a_full_evaluation_finds_full_evaluations_and_a_review_same_direction_reviews(
    memory,
):
    current(memory)
    evaluation = memory.no_trade(ASSET, 100)
    long_review = memory.review(ASSET, 200, position=1, direction="long")
    memory.review(OTHER, 220, position=2, direction="short")

    assert ids(search(memory)) == [evaluation]
    assert ids(search(memory, position_review("long"))) == [long_review]


def test_the_filters_narrow_the_search(memory):
    current(memory, window=[("doji", 0)])
    same_traded = memory.trade(ASSET, 100, position=1, window=[("hammer", 1)])
    other_stock = memory.no_trade(OTHER, 200, asset_class="stock")
    other_crypto = memory.no_trade("ASSET_03", 300, window=[("hammer", 0)])

    assert ids(search(memory, asset="same_asset")) == [same_traded]
    assert set(ids(search(memory, asset="same_asset_class"))) == {
        same_traded,
        other_crypto,
    }
    assert set(ids(search(memory, pattern="hammer"))) == {same_traded, other_crypto}
    assert ids(search(memory, decided="long")) == [same_traded]
    assert set(ids(search(memory, decided="no_trade"))) == {other_stock, other_crypto}
    assert ids(search(memory, decided="short")) == []


def test_an_entry_never_carried_out_is_filed_and_shown_as_no_trade(memory):
    current(memory)
    cancelled = memory.cancelled(ASSET, 100)

    assert ids(search(memory, decided="long")) == []
    (found,) = search(memory, decided="no_trade").episodes
    assert found.episode.id == cancelled and found.episode.decided == "no_trade"


def test_an_episode_s_volume_word_uses_the_sim_s_own_cut_offs(memory):
    """Volume 1.5 times normal is high by the version 1 cut-offs, average below 2.0."""
    current(memory)
    memory.no_trade(ASSET, 100, volume=1.5)
    assert search(memory).episodes[0].episode.volume == "high"
    memory.store.sims[SIM]["SETTINGS"] = {"track_record": {"volume_high_above": 2.0}}
    assert search(memory).episodes[0].episode.volume == "average"


def test_a_review_search_narrows_by_what_was_decided_and_how_the_position_stood(
    memory,
):
    current(memory)
    held = memory.review(ASSET, 100, position=1, profit=8.0)
    closed = memory.review(OTHER, 200, position=2, action="close", profit=-3.0)
    review = position_review()

    assert ids(search(memory, review, decided="close")) == [closed]
    assert ids(search(memory, review, standing="in_profit")) == [held]
    assert ids(search(memory, review, standing="at_a_loss")) == [closed]


def test_repeats_from_one_asset_keep_only_the_closest_and_10_are_returned(memory):
    current(memory)
    best = memory.no_trade(ASSET, 100, features=vector(0.1))
    memory.no_trade(ASSET, 104, features=vector(0.2))  # 4 bars later: a repeat
    for n in range(12):
        memory.no_trade(OTHER, 200 + 10 * n, features=vector(1.0 + n))

    found = ids(search(memory))
    assert len(found) == 10
    assert found[0] == best and f"{SIM}-104-{ASSET}" not in found


def test_a_search_that_finds_nothing_returns_no_episodes(memory):
    current(memory)
    assert search(memory).episodes == []


def test_a_past_trade_read_in_full_shows_how_it_was_handled(memory):
    current(memory)
    trade = memory.trade(ASSET, 100, position=4, closed_after=3, profit=12.0)

    async def body():
        async with bridge_to(memory.store, full_evaluation()) as bridge:
            return await bridge.read([trade])

    (episode,) = run(body).episodes
    text = full_episode(episode, "E1", Reader(asset=ASSET, now=NOW))
    assert text.splitlines()[0] == "E1: 4 days ago, same asset, crypto"
    assert text.splitlines()[2:] == [
        "Decided: long with a tight stop price (0.6% from the entry price), $1,000.",
        "Handled: bars 0 to 1 hold; bar 2 close.",
        "Ended: closed by choice after 4 bars, +$12 (+1.2%). At best +$20, at worst -$5.",
    ]


def test_a_past_review_read_in_full_marks_the_review_in_its_trade(memory):
    current(memory)
    review = memory.review(ASSET, 100, position=9)
    for bar, step in enumerate((98, 99, 101, 102)):
        memory._decision(ASSET, step, "position_screen", "nothing", None, POSITION=9)

    async def body():
        async with bridge_to(memory.store, position_review()) as bridge:
            return await bridge.read([review])

    (episode,) = run(body).episodes
    text = full_episode(episode, "E1", Reader(asset=ASSET, now=NOW))
    assert (
        "The whole trade: bars 0 to 1 hold; bar 2 hold (this review); bars 3 to 4 hold;"
        " bar 5 stop price reached." in text
    )
    line = summary_line(episode, "E1", Reader(asset=ASSET, now=NOW))
    assert line.endswith("closed at its stop price 5 bars later: -$4 (-0.4%)")


def test_the_track_record_totals_the_pattern_in_the_asset_class(memory):
    current(memory)
    for n in range(10):
        memory.trade(OTHER, 10 + 10 * n, position=n, window=[("hammer", 0)], profit=5.0)
    memory.trade(
        "ASSET_09", 300, position=99, window=[("hammer", 0)], asset_class="stock"
    )

    async def body():
        async with bridge_to(memory.store, full_evaluation()) as bridge:
            return await bridge.track_record("hammer", "long")

    # All ten are with the trend and at high volume; only 4 at this part of the day (Asian
    # hours), too few for a group of their own.
    assert track_record(run(body)).splitlines() == [
        "Track record: hammer, long, crypto",
        (
            "All: 10 closed trades, 10 wins (100%), average win +$5, average loss none,"
            " all together +$50"
        ),
        (
            "With the long-term trend: 10 closed trades, 10 wins (100%),"
            " average win +$5, average loss none, all together +$50"
        ),
        (
            "With the long-term trend, high volume: 10 closed trades, 10 wins (100%),"
            " average win +$5, average loss none, all together +$50"
            "  <- fits the current situation"
        ),
        "Groups with fewer than 10 closed trades are not shown.",
    ]


def test_nothing_from_the_future_is_ever_returned(memory):
    """Episodes and outcomes planted after the current step: no search, read or track record
    may return them (spec appendix 5, section 3, rule 3)."""
    current(memory, window=[("hammer", 0)])
    known = memory.no_trade(ASSET, 100, window=[("hammer", 0)])
    # Decided later than now.
    later = memory.no_trade(ASSET, NOW + 8, window=[("hammer", 0)])
    # Decided before now, but its last outcome is learned after now.
    unfinished = memory.no_trade(OTHER, NOW - 2, window=[("hammer", 0)])
    # A trade decided before now that closes after now.
    still_open = memory.trade(
        OTHER, NOW - 20, position=5, closed_after=30, window=[("hammer", 0)]
    )
    # Complete exactly now: shown.
    just_now = memory.no_trade("ASSET_03", NOW - 6, window=[("hammer", 0)])

    async def body():
        async with bridge_to(memory.store, full_evaluation()) as bridge:
            return (
                await bridge.search(),
                await bridge.search(pattern="hammer"),
                await bridge.read([later, unfinished, still_open, known]),
                await bridge.track_record("hammer", "long"),
            )

    everything, narrowed, read, record = run(body)
    assert set(ids(everything)) == set(ids(narrowed)) == {known, just_now}
    assert [e.id for e in read.episodes] == [known]
    assert record.closed_trades == 0


def test_the_bridge_fills_in_the_sim_and_step_and_the_llm_cannot(memory):
    current(memory)
    memory.no_trade(ASSET, 100)

    attempts = [
        {"step": NOW + 100},
        {"sim": 1},
        {"job": "position_review"},
        {"decided": "hold"},
        {"pattern": "unknown pattern"},
    ]

    async def body():
        refused = []
        async with bridge_to(memory.store, full_evaluation()) as bridge:
            for arguments in attempts:
                with pytest.raises(NotAllowed) as caught:
                    await bridge.call("search_episodes", arguments)
                refused.append(str(caught.value))
        return refused

    refused = run(body)
    assert refused[:3] == [
        "search_episodes has no input step.",
        "search_episodes has no input sim.",
        "search_episodes has no input job.",
    ]
    assert refused[3] == 'decided must be one of "any", "long", "short", "no_trade".'
    assert refused[4].startswith('pattern must be one of "any", "bullish engulfing"')


def test_a_tool_that_fails_on_the_server_comes_back_flagged(memory):
    # No snapshot of the asset at this step: the search cannot start.
    async def body():
        async with bridge_to(memory.store, full_evaluation("ASSET_42")) as bridge:
            with pytest.raises(MemoryToolFailed) as caught:
                await bridge.search()
            return str(caught.value)

    assert run(body) == (
        "search_episodes failed: Error executing tool search_episodes:"
        " ASSET_42 has no snapshot at step 500"
    )
