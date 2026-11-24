"""How a past episode and the track record are written (spec appendix 5, sections 4 and 5).

One renderer writes a past episode for both the LLM's tools and Jev's background. The expected
texts are the walkthrough pages' (`docs/llm-prompt-walkthrough.html`, `docs/jev-reading-walkthrough
.html`), worked out by hand from their made-up episodes a, c, r1, r2 and r3 and the track record.
"""

from jev_trader.memory.episodes import (
    Ended,
    Episode,
    Prices,
    Standing,
    Step,
    Trade,
)
from jev_trader.memory.render import (
    Reader,
    full_episode,
    summary_line,
    track_record,
)
from jev_trader.memory.track_record import Group, TrackRecord

DAY = 96
NOW = 1000 * DAY
SITUATION = "Stock, first hour (bar 4 of 26). Patterns in the last 4 bars: ..."

LLM = Reader(asset="ASSET_03", now=NOW)


def episode(**fields) -> Episode:
    base = {
        "id": "x",
        "kind": "full_evaluation",
        "asset": "ASSET_03",
        "asset_class": "stock",
        "situation": SITUATION,
        "longer_patterns": [],
        "trend": "up",
    }
    return Episode(**{**base, **fields})


A = episode(
    step=NOW - (3 * DAY + 8),
    patterns=["bullish engulfing", "hammer"],
    part_of_day="first hour",
    volume="high",
    decided="long",
    trade=Trade(direction="long", stop="tight", stop_distance=0.006, dollars=6000),
    ended=Ended(reason="jev", bars_after=6, profit=21, percent=0.4, best=33, worst=-8),
    journal=[
        Step(bar=1, action="hold"),
        Step(bar=2, action="hold"),
        Step(bar=3, action="reduce", share=0.5, profit=14),
        Step(bar=4, action="hold"),
        Step(bar=5, action="hold"),
        Step(bar=6, action="close"),
    ],
)
C = episode(
    step=NOW - (12 * DAY + 2),
    asset="ASSET_01",
    patterns=["bullish engulfing", "belt-hold"],
    part_of_day="first hour",
    volume="average",
    decided="no_trade",
    prices=Prices(after_1_bar=0.001, after_4_bars=0.006, end_of_day=0.011),
)


def review(**fields) -> Episode:
    return episode(kind="position_review", part_of_day="middle", **fields)


R1 = review(
    step=NOW - (12 * DAY + 20),
    patterns=["spinning top"],
    volume="average",
    decided="hold",
    review=Step(bar=6, action="hold"),
    standing=Standing(
        direction="long",
        put_in=5000,
        bars_open=6,
        profit=18,
        percent=0.4,
        stop_distance=0.009,
        best=25,
        worst=-6,
    ),
    prices=Prices(after_1_bar=-0.002, after_4_bars=-0.005, end_of_day=-0.009),
    ended=Ended(reason="stop_price", bars_after=9, profit=-31, percent=-0.6),
    journal=[Step(bar=b, action="hold") for b in range(1, 6)]
    + [Step(bar=6, action="hold", this_review=True)]
    + [Step(bar=b, action="hold") for b in range(7, 15)]
    + [Step(bar=15, action="stop_price")],
)
R1_STANDING = "long, $5,000, open 6 bars, +$18 (+0.4%), stop price 0.9% away"
R1_AFTER = (
    "price went -0.2% after 1 bar, -0.5% after 4 bars, -0.9% by the end of the day"
)


def test_a_past_trade_in_one_line():
    assert summary_line(A, "E1", LLM) == (
        "E1 | 3 days ago | same asset, stock | first hour, long-term trend up, volume high"
        " | bullish engulfing, hammer | long, tight stop, $6,000"
        " | closed by choice after 6 bars: +$21 (+0.4%)"
    )


def test_a_past_no_trade_in_one_line_names_the_other_asset():
    assert summary_line(C, "E3", LLM) == (
        "E3 | 12 days ago | ASSET_01, stock"
        " | first hour, long-term trend up, volume average"
        " | bullish engulfing, belt-hold | no trade | price went +0.1% after 1 bar,"
        " +0.6% after 4 bars, +1.1% by the end of the day"
    )


def test_a_past_trade_in_full_for_the_llm_and_for_jev():
    decided = (
        "Decided: long with a tight stop price (0.6% from the entry price), $6,000.\n"
    )
    ended = "Ended: closed by choice after 6 bars, +$21 (+0.4%). At best +$33, at worst -$8."
    assert full_episode(A, "E1", LLM) == (
        f"E1: 3 days ago, same asset, stock\nSituation then: {SITUATION}\n"
        + decided
        + "Handled: bars 1 to 2 hold; bar 3 reduce by half (that part: +$14);"
        " bars 4 to 5 hold; bar 6 close.\n" + ended
    )
    # Jev's block: numbered, the asset unnamed, and no bar-by-bar line.
    jev = Reader(asset="ASSET_05", now=NOW, for_jev=True)
    assert full_episode(A, "Episode 2", jev) == (
        f"Episode 2: 3 days ago, another asset, stock\nSituation then: {SITUATION}\n"
        + decided
        + ended
    )


def test_a_past_no_trade_in_full():
    assert full_episode(C, "E3", LLM) == (
        f"E3: 12 days ago, ASSET_01, stock\nSituation then: {SITUATION}\n"
        "Decided: no trade.\nAfterwards: price went +0.1% after 1 bar, +0.6% after 4 bars,"
        " +1.1% by the end of the day."
    )


def test_a_past_review_in_one_line():
    assert summary_line(R1, "E1", LLM) == (
        "E1 | 12 days ago | same asset, stock | middle, long-term trend up, volume average"
        f" | spinning top | {R1_STANDING} | hold"
        f" | {R1_AFTER}; closed at its stop price 9 bars later: -$31 (-0.6%)"
    )


def test_a_past_review_in_full_is_the_same_for_jev():
    record = (
        f"The position then: {R1_STANDING}. At best it had been +$25, at worst -$6.\n"
        "Decided: hold.\n"
        f"Afterwards: {R1_AFTER}.\n"
        "The whole trade: bars 1 to 5 hold; bar 6 hold (this review); bars 7 to 14 hold;"
        " bar 15 stop price reached.\n"
        "Ended: closed at its stop price 9 bars later, -$31 (-0.6%)."
    )
    assert full_episode(R1, "E1", LLM) == (
        f"E1: 12 days ago, same asset, stock\nSituation then: {SITUATION}\n{record}"
    )
    jev = Reader(asset="ASSET_03", now=NOW, for_jev=True)
    assert full_episode(R1, "Episode 1", jev) == (
        f"Episode 1: 12 days ago, same asset, stock\nSituation then: {SITUATION}\n{record}"
    )


def test_a_review_that_reduced_or_closed_the_position():
    reduced = R1.model_copy(
        update={
            "decided": "reduce",
            "review": Step(bar=4, action="reduce", share=0.5, profit=13),
        }
    )
    assert " | reduce by half (that part: +$13) | " in summary_line(reduced, "E2", LLM)
    closed = R1.model_copy(
        update={
            "decided": "close",
            "review": Step(bar=5, action="close"),
            "ended": Ended(
                reason="jev",
                bars_after=1,
                profit=12,
                percent=0.3,
                closed_at_this_review=True,
            ),
        }
    )
    assert summary_line(closed, "E4", LLM).endswith(
        f"{R1_AFTER}; closed at this review: +$12 (+0.3%)"
    )


def test_a_recent_episode_counts_hours():
    recent = A.model_copy(update={"step": NOW - 9})
    assert summary_line(recent, "E1", LLM).startswith("E1 | 2 hours ago | ")
    assert summary_line(A.model_copy(update={"step": NOW - 1}), "E1", LLM).startswith(
        "E1 | 1 hour ago | "
    )


def group(trades, wins, gain, loss, total, **split):
    return Group(
        trades=trades,
        made_money=wins,
        average_gain=gain,
        average_loss=loss,
        total_profit=total,
        **split,
    )


def test_the_track_record_marks_the_group_that_fits():
    record = TrackRecord(
        pattern="bullish engulfing",
        direction="long",
        asset_class="stock",
        minimum_sample=10,
        closed_trades=42,
        groups=[
            group(42, 17, 31, -18, 77),
            group(30, 14, 33, -17, 190, trend="with the trend"),
            group(18, 10, 36, -19, 208, trend="with the trend", volume_level="high"),
            group(
                11,
                7,
                38,
                -21,
                182,
                trend="with the trend",
                volume_level="high",
                part_of_day="first hour",
                fits=True,
            ),
        ],
    )
    assert track_record(record) == (
        "Track record: bullish engulfing, long, stocks\n"
        "All: 42 closed trades, 17 wins (40%), average win +$31, average loss -$18,"
        " all together +$77\n"
        "With the long-term trend: 30 closed trades, 14 wins (47%), average win +$33,"
        " average loss -$17, all together +$190\n"
        "With the long-term trend, high volume: 18 closed trades, 10 wins (56%),"
        " average win +$36, average loss -$19, all together +$208\n"
        "With the long-term trend, high volume, first hour: 11 closed trades, 7 wins (64%),"
        " average win +$38, average loss -$21, all together +$182"
        "  <- fits the current situation\n"
        "Groups with fewer than 10 closed trades are not shown."
    )


def test_a_track_record_under_the_minimum_shows_only_the_count():
    record = TrackRecord(
        pattern="hammer",
        direction="short",
        asset_class="crypto",
        minimum_sample=10,
        closed_trades=6,
        groups=[],
    )
    assert track_record(record) == (
        "Track record: hammer, short, crypto\n6 closed trades, too few to show totals."
    )
