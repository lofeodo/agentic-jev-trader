"""The scenarios for an asset with no position (spec appendix 10, section 8, "No position on the
asset"): each runs from Jev's screen through the full evaluation to the order and the stored
records, or ends early where the screen or a risk limit says no.

Jev's and the LLM's answers cannot be dictated: a scenario's made-up market and memory are drawn
to make its path likely (a quiet market for the screen's no, a sharp fall for a short), and
more scenarios were recorded than kept. Once the real answers were saved, the scenarios that
took their path were kept, renamed after it where they took another, and the rest dropped.

Every scenario looks at the same crypto asset at the same step, day 22 at 10:00 UTC, when every
measurement has the 20 days it needs. A **short** is a bet that the price falls (sell $2,000 of
borrowed coins, the price falls 1%, the account is up $20). The **daily loss limit** blocks new
trades for the rest of the UTC day once the account is down 5% since midnight ($500 of $10,000).
"""

from tests.recorded.made_up import (
    STEP,
    MadeUpPrices,
    PastEpisode,
    PastNoTrade,
    PastTrade,
)
from tests.recorded.scenarios import MadeUpInputs, Scenario

OTHER_ASSETS = ("ASSET_02", "ASSET_03", "ASSET_04", "ASSET_05")

# A rise after a hammer (a candle pattern read as a hint the price will rise), on two and a half
# times the usual trading (volume): worth a closer look.
RISING = MadeUpPrices(seed=4, last_moves=(0.004, 0.006), last_volume=2.5)
RISING_PATTERNS = ((STEP - 1, "hammer"),)

# A few past episodes on the asset: little to look further into.
SMALL_MEMORY = (
    PastNoTrade(STEP - 300),
    PastTrade(STEP - 200, position=1, profit=-6.0, closing_reason="stop_price"),
    PastNoTrade(STEP - 100),
    PastNoTrade(STEP - 50, asset="ASSET_02"),
)


def _busy_memory(count: int, every: int) -> tuple[PastEpisode, ...]:
    """`count` past episodes, one every `every` steps back from the scenario's step: trades
    long and short that made or lost money, closed by Jev or at their stop price, and
    no-trades, spread over the five assets. Enough to tempt the LLM into more lookups."""
    episodes = []
    for n in range(count):
        step = STEP - every * (n + 2)
        asset = ("ASSET_01", *OTHER_ASSETS)[n % 5]
        if n % 3 == 0:
            episodes.append(PastNoTrade(step, asset=asset))
            continue
        episodes.append(
            PastTrade(
                step,
                position=n + 1,
                direction="short" if n % 4 == 1 else "long",
                closed_after=1 + n % 5,
                profit=(15.0, -9.0, 4.0, -22.0)[n % 4],
                closing_reason="stop_price" if n % 7 == 2 else "jev",
                asset=asset,
            )
        )
    return tuple(episodes)


BUSY_MEMORY = _busy_memory(count=14, every=40)
LARGE_MEMORY = _busy_memory(count=40, every=24)

# Past trades on the asset after the same hammer, each shown in the first search with how it
# ended: the summaries alone may be enough to answer.
HAMMER_MEMORY = tuple(
    PastTrade(STEP - 96 * n, position=n, profit=(14.0, 9.0, -5.0)[n - 1])
    for n in (1, 2, 3)
)
HAMMER_PATTERNS = (
    *RISING_PATTERNS,
    *((STEP - 96 * n - 1, "hammer") for n in (1, 2, 3)),
)

# Shorts that made money after a fall.
SHORTS_THAT_WORKED = (
    PastTrade(STEP - 400, position=1, direction="short", profit=18.0),
    PastTrade(STEP - 250, position=2, direction="short", profit=11.0),
    PastNoTrade(STEP - 120),
    PastTrade(STEP - 60, position=3, direction="long", profit=-14.0),
)

SCENARIOS = [
    Scenario(
        name="screen_says_no_on_a_quiet_market",
        path="the screen says no",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=1, swing=0.0005, last_moves=(0.0, 0.0001), last_volume=0.4
            ),
            memory=SMALL_MEMORY,
        ),
    ),
    Scenario(
        name="answers_at_once_after_hammers_seen_before",
        path="the LLM answers at once",
        inputs=MadeUpInputs(
            step=STEP, prices=RISING, patterns=HAMMER_PATTERNS, memory=HAMMER_MEMORY
        ),
    ),
    Scenario(
        name="looks_further_in_a_busy_memory",
        path="the LLM looks further first",
        inputs=MadeUpInputs(
            step=STEP,
            prices=RISING,
            patterns=(*RISING_PATTERNS, (STEP, "bullish engulfing")),
            memory=BUSY_MEMORY,
        ),
    ),
    Scenario(
        name="memory_holds_none_yet",
        path="nothing to show: memory holds none yet",
        inputs=MadeUpInputs(step=STEP, prices=RISING, patterns=RISING_PATTERNS),
    ),
    # Written for the lookup limit, recorded as Jev picking no trade.
    Scenario(
        name="no_trade_on_opposite_hints",
        path="Jev picks no trade",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=14, last_moves=(0.006, -0.005), last_volume=2.6),
            patterns=(
                (STEP - 2, "morning star"),
                (STEP - 1, "hanging man"),
                (STEP, "doji"),
            ),
            memory=LARGE_MEMORY,
        ),
    ),
    # The single likeliest option is no trade, but the three long options together outweigh
    # it, so a long is picked.
    Scenario(
        name="direction_totals_after_opposite_patterns",
        path="a pick where adding the probabilities by direction changes the winner",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=5, last_moves=(-0.004, 0.005), last_volume=2.2),
            patterns=((STEP - 1, "bearish engulfing"), (STEP, "piercing")),
            memory=BUSY_MEMORY,
        ),
    ),
    Scenario(
        name="short_after_a_sharp_fall",
        path="a short is picked",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=10, drift=-0.001, last_moves=(-0.008, -0.012), last_volume=3.0
            ),
            patterns=((STEP - 1, "bearish engulfing"), (STEP, "three black crows")),
            memory=SHORTS_THAT_WORKED,
        ),
    ),
    # A stop price is the price at which code closes a trade by itself to cap its loss. Bars
    # that swing about 3% each put even the tightest stop price about 3% away, so the
    # trade risk limit (lose at most 1% of the account, $100, at the stop price) allows about
    # $3,300: a size Jev picks above that is cut down.
    Scenario(
        name="size_cut_by_the_trade_risk_limit",
        path="a size above what a limit allows",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=12, swing=0.03, last_moves=(0.03, 0.04), last_volume=3.0
            ),
            patterns=((STEP, "bullish marubozu"),),
            memory=SMALL_MEMORY,
        ),
    ),
    # Worth $10,000 now and $10,600 at midnight: down $600, past the $530 the limit allows, so
    # nothing is asked.
    Scenario(
        name="daily_loss_limit_blocks_a_new_trade",
        path="a new trade blocked by the daily loss limit",
        inputs=MadeUpInputs(
            step=STEP,
            prices=RISING,
            patterns=RISING_PATTERNS,
            memory=SMALL_MEMORY,
            start_of_day_value=10_600.0,
        ),
    ),
    Scenario(
        name="full_evaluation_without_memory",
        path="a full evaluation in the agent without memory",
        inputs=MadeUpInputs(
            step=STEP, prices=RISING, patterns=RISING_PATTERNS, with_memory=False
        ),
    ),
]
