"""The scenarios with an open position on the asset, and the sim's last step (spec appendix 10,
section 8: "Open position on the asset" and "The sim's last step").

Each starts from an account already holding a position (`MadeUpPosition`) and runs from the
position screen through the position review to the order and the stored records. Jev's and the
LLM's answers cannot be dictated, so each scenario's made-up market leans towards its path: a
calm market for a screen that says no, a sharp fall for a close, a fast rise for a reduce, and
so on. Which path a scenario really took shows only once its answers are recorded; one that took
another is renamed to the path it took, and another is written for the path left uncovered.

Two need no saved answer, since code alone acts: the sim's last step at a stock's last bar of
the session (where nothing is asked of a position), and the holding sim. At the stop price,
code closes the position before the agent looks; the asset, now with no position, then goes
through the screen as usual.

Terms: a **long** is a bet that the price rises ($2,000 bought, the price rises 1%, the account
is up $20). A **stop price** is the price at which code closes a trade by itself to cap its
loss. A **forced close** is code closing every position when the account's value falls below a
quarter of what it holds. A **review** decides to hold, close, reduce (sell part) or add (buy
more).

Every position fits the risk limits a real entry is held to (at most $100 lost at its stop
price, at most twice the account in one position), but one: the forced close. With a stop
price on every position, a real account reaches a forced close only when prices jump past
many stops at once; one asset at one step cannot show that, so its scenario holds $38,000 on a
$10,000 account, beyond the limits, and a 3% fall brings the close on.
"""

from jev_trader.broker import AssetClass, Direction
from jev_trader.sim.clock import STEPS_PER_DAY as DAY
from tests.recorded.made_up import MadeUpPrices, PastNoTrade, PastReview, PastTrade
from tests.recorded.scenarios import MadeUpInputs, MadeUpPosition, Scenario

# Day 22: every measurement has the 20 days it needs.
DAY_22 = 21 * DAY
STEP = DAY_22 + 40  # 10:00 UTC
# A stock's session runs 14:30 to 21:00 UTC: its second-to-last bar ends at step 83 of the day
# (20:45), its last at step 84 (21:00).
STOCK_SECOND_TO_LAST, STOCK_LAST = DAY_22 + 83, DAY_22 + 84
# Two bars before midnight: the hold scenario's outcomes test lets the day end soon after.
BEFORE_MIDNIGHT = 22 * DAY - 2

# Past position reviews of longs, with the trades around them, for the LLM to select from.
PAST_REVIEWS = (
    PastTrade(STEP - 600, position=1, profit=18.0),
    PastReview(STEP - 500, position=2, action="nothing", profit=6.0),
    PastReview(STEP - 420, position=3, action="close", profit=-4.0),
    PastNoTrade(STEP - 350),
    PastReview(STEP - 300, position=4, action="reduce", profit=25.0),
    PastReview(STEP - 220, position=5, action="add", profit=9.0),
    PastTrade(STEP - 150, position=6, profit=-7.0, closing_reason="stop_price"),
    PastReview(STEP - 80, position=7, action="nothing", profit=-2.0),
)
# A stock has bars only in its session: its past reviews are at 17:15 UTC on earlier days.
PAST_STOCK_REVIEWS = (
    PastReview(DAY_22 - 4 * DAY + 70, position=1, action="nothing", profit=5.0),
    PastReview(DAY_22 - 3 * DAY + 70, position=2, action="close", profit=-6.0),
    PastReview(DAY_22 - 2 * DAY + 70, position=3, action="reduce", profit=14.0),
    PastReview(DAY_22 - DAY + 70, position=4, action="nothing", profit=3.0),
)
# Just inside the 5% the broker allows between a stop price and the price: wide enough that
# the made-up bars do not reach it.
WIDE_STOP = 0.045


def _long(amount=2_000.0, steps_ago=4, stop_distance=0.03) -> MadeUpPosition:
    return MadeUpPosition(Direction.LONG, amount, steps_ago, stop_distance)


HOLD = Scenario(
    name="review-ends-in-hold",
    path="a position review ending in hold",
    inputs=MadeUpInputs(
        step=BEFORE_MIDNIGHT,
        prices=MadeUpPrices(seed=11, last_moves=(0.002, 0.003, 0.002), last_volume=1.8),
        memory=PAST_REVIEWS,
        position=_long(steps_ago=3, stop_distance=WIDE_STOP),
    ),
)

OPEN_POSITION_SCENARIOS = [
    Scenario(
        name="position-screen-says-no",
        path="a position screen that says no",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=10, swing=0.0008),
            memory=PAST_REVIEWS,
            position=_long(steps_ago=6),
        ),
    ),
    HOLD,
    Scenario(
        name="review-ends-in-close",
        path="a position review ending in close",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=12, last_moves=(-0.004, -0.006, -0.009), last_volume=2.5
            ),
            patterns=((STEP - 1, "bearish engulfing"), (STEP, "three black crows")),
            memory=PAST_REVIEWS,
            position=_long(steps_ago=8, stop_distance=WIDE_STOP),
        ),
    ),
    Scenario(
        name="review-ends-in-reduce",
        path="a position review ending in reduce",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=13, drift=0.0005, last_moves=(0.01, 0.012), last_volume=3.0
            ),
            patterns=((STEP, "shooting star"),),
            memory=PAST_REVIEWS,
            position=_long(amount=3_000.0, steps_ago=12),
        ),
    ),
    Scenario(
        name="review-ends-in-add",
        path="a position review ending in add",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(
                seed=14,
                drift=0.0008,
                last_moves=(0.002, 0.003, 0.004),
                last_volume=2.0,
            ),
            patterns=((STEP - 1, "three advancing white soldiers"),),
            memory=PAST_REVIEWS,
            position=_long(amount=1_000.0, steps_ago=4),
        ),
    ),
    Scenario(
        name="end-of-session-review",
        path="an end-of-session review",
        inputs=MadeUpInputs(
            step=STOCK_SECOND_TO_LAST,
            asset_class=AssetClass.STOCK,
            prices=MadeUpPrices(seed=15, last_moves=(0.003,)),
            memory=PAST_STOCK_REVIEWS,
            position=_long(steps_ago=6),
        ),
    ),
    Scenario(
        name="review-llm-selects-none",
        path="a review where the LLM selects none",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=16, last_moves=(0.006,), last_volume=2.0),
            # Past reviews of another asset only, in other markets: none much like this one.
            memory=tuple(
                PastReview(STEP - 500 + 60 * n, position=n, asset="ASSET_02")
                for n in range(1, 4)
            ),
            position=_long(steps_ago=5),
        ),
    ),
    Scenario(
        name="review-without-memory",
        path="a review in the agent without memory",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=17, last_moves=(0.004, 0.006), last_volume=2.2),
            with_memory=False,
            position=_long(steps_ago=5),
        ),
    ),
    Scenario(
        name="closed-at-stop-price",
        path="a position closed at its stop price",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=18, last_moves=(-0.02,)),
            memory=PAST_REVIEWS,
            position=_long(steps_ago=4, stop_distance=0.01),
        ),
    ),
    Scenario(
        name="forced-close",
        path="a forced close",
        inputs=MadeUpInputs(
            step=STEP,
            # $38,000 held on a $10,000 account: a 3% fall leaves it worth less than a quarter
            # of what it holds.
            prices=MadeUpPrices(seed=19, swing=0.0005, last_moves=(-0.03,)),
            memory=PAST_REVIEWS,
            position=_long(amount=38_000.0, steps_ago=2, stop_distance=WIDE_STOP),
        ),
    ),
    Scenario(
        name="sim-ends-everything-sold",
        path="everything is sold at the sim's last step",
        # A stock at its session's last bar: nothing is asked, then the sim's end sells it.
        inputs=MadeUpInputs(
            step=STOCK_LAST,
            asset_class=AssetClass.STOCK,
            prices=MadeUpPrices(seed=20),
            position=_long(steps_ago=10),
            sim_ends_here=True,
        ),
        asks_a_model=False,
    ),
    Scenario(
        name="holding-sim-sells-five",
        path="the holding sim sells the five assets at its last step",
        inputs=MadeUpInputs(
            step=STEP,
            prices=MadeUpPrices(seed=21),
            holding_sim=True,
            sim_ends_here=True,
        ),
        asks_a_model=False,
    ),
]
