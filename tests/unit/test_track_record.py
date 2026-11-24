"""The track record's ladder of groups and its fallback (spec appendix 3, section 5.2).

A group names a candle pattern, a direction and an asset class, and may narrow by trend, then
volume level, then part of the day. The narrowest group that fits the moment and holds at least
10 closed trades is the one used; below 10 at every level only the count is shown.
"""

from jev_trader.memory.track_record import FiledTrade, Moment, ladder

NOW = Moment(
    pattern="hammer",
    direction="long",
    asset_class="stock",
    trend="with the trend",
    volume_level="high",
    part_of_day="first hour",
)


def trade(
    patterns=("hammer",),
    direction="long",
    asset_class="stock",
    trend="with the trend",
    volume_level="high",
    part_of_day="first hour",
    profit=10.0,
    closed_step=100,
):
    return FiledTrade(
        patterns=patterns,
        direction=direction,
        asset_class=asset_class,
        trend=trend,
        volume_level=volume_level,
        part_of_day=part_of_day,
        profit=profit,
        closed_step=closed_step,
    )


def test_the_narrowest_group_holding_ten_closed_trades_is_used():
    trades = (
        [trade() for _ in range(4)]  # the whole of the narrowest group
        + [trade(part_of_day="middle") for _ in range(6)]  # with the trend, high volume
        + [trade(volume_level="low")]  # with the trend
        + [trade(trend="against the trend")]
    )

    found = ladder(trades, NOW)

    # Broadest first: pattern, direction and asset class; then trend; volume; part of day.
    assert [r.trades for r in found.rungs] == [12, 11, 10, 4]
    assert found.used.details == ("trend", "volume")
    assert [r.trades for r in found.shown] == [12, 11, 10]


def test_with_fewer_than_ten_at_every_level_only_the_count_is_shown():
    found = ladder([trade() for _ in range(6)], NOW)

    assert found.used is None
    assert found.shown == ()
    assert found.count == 6


def test_stocks_and_crypto_and_the_two_directions_are_never_counted_together():
    trades = [trade() for _ in range(9)] + [
        trade(asset_class="crypto"),
        trade(direction="short"),
        trade(patterns=("doji",)),
    ]

    assert ladder(trades, NOW).count == 9


def test_a_trade_counts_once_for_each_of_its_patterns():
    trades = [trade(patterns=("hammer", "doji")) for _ in range(10)]

    assert ladder(trades, NOW).count == 10
    doji = Moment(**{**NOW.__dict__, "pattern": "doji"})
    assert ladder(trades, doji).count == 10
    none = Moment(**{**NOW.__dict__, "pattern": "none"})
    assert ladder([trade(patterns=()) for _ in range(3)], none).count == 3


def test_a_trade_counts_only_from_the_step_it_closed():
    trades = [trade(closed_step=100 + n) for n in range(12)]

    assert ladder(trades, NOW, step=105).count == 6
    assert ladder(trades, NOW).count == 12


def test_a_rungs_totals():
    trades = [trade(profit=p) for p in (30.0, -10.0, -20.0, 0.0)]

    [rung, *_] = ladder(trades, NOW).rungs

    assert (rung.made_money, rung.average_gain, rung.average_loss) == (1, 30.0, -15.0)
    assert rung.total_profit == 0.0
