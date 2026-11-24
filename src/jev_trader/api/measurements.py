"""The measurements of the Trading sim page (spec appendix 7 section 5.6, appendix 9 section 10;
`GET /sims/{id}/measurements`).

Six groups: money, how wild the ride is, what kind of trader it is, trades, Jev's confidence, and
memory. Each figure has the trader's term (`name`), the sim's number, the same number for
holding the five assets over the same days where it means something, and a plain sentence saying
what happened to the account. All are worked out from stored records when asked for and never
stored.

Choices the spec leaves to the build:

- A day is a UTC day (ADR 0002). A day's change runs from the account value at the end of the
  day before (the starting amount on the first day) to the last stored value of the day.
- The typical daily swing is the standard deviation of the daily changes (with fewer than two
  days there is none). The Sharpe ratio is the average daily change in percent over that
  swing, times the square root of 365 (a year of UTC days), with no risk-free rate.
- Days to climb back count from the day of the high before the biggest drop to the day the
  account was first back at that high; None while it has not.
- "How often the largest size was picked": of the full evaluations Jev sized, the share where
  the largest size had the most probability, its two copies averaged.
- "How often a limit held it back": looks a risk limit ruled out before anything was asked,
  and trades a limit trimmed.
- Jev's confidence in a trade is the probability its pick copies, averaged, gave the trade's
  direction (every stop price added). Trades are put in tens of percent by it, and each band
  says the share that made money.
- The speed and price figures of appendix 9 sit in the money group.
- Holding is measured only up to the step the sim has reached.
- The memory group's figures on the LLM's picks wait for the agent with memory; until then a
  sim's own profit per day is the one figure it has.
"""

import math
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from jev_trader.api.sim_page import Sim, holding_of
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import NO_TRADE, trades_of
from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.jev.reading import size_option_name
from jev_trader.sim.clock import day_of
from jev_trader.sim.store import ACTION_ENTRY, KIND_FULL_EVALUATION

HOURS_PER_STEP = 0.25
DAYS_PER_YEAR = 365
# Reasons a look was ruled out that are not risk limits.
NOT_A_LIMIT = frozenset({"no_typical_move"})
ENDINGS = {
    "jev": "Jev chose to close it",
    "stop_price": "Its stop price was reached",
    "forced_close": "A forced close",
    "sim_ended": "Closed because the sim ended",
}


class Figure(BaseModel):
    key: str
    name: str  # the trader's term, shown in small type
    unit: str  # usd, signed_usd, cents, share (0 to 1), count, number, hours or days
    sim: float | None  # None: not available
    holding: float | None  # None: not available, or meaningless for holding
    says: str  # what happened to the account, in plain words


class BreakdownRow(BaseModel):
    label: str
    trades: int
    value: float | None  # in the breakdown's unit; None when the count says it all


class Breakdown(BaseModel):
    key: str
    name: str
    unit: str
    says: str
    rows: list[BreakdownRow]


class MeasurementGroup(BaseModel):
    key: str
    title: str
    says: str
    figures: list[Figure]
    breakdowns: list[Breakdown]


class Measurements(BaseModel):
    through_step: int | None  # the last step measured
    holding_sim_id: int | None
    groups: list[MeasurementGroup]


# How numbers read in sentences. A gain or a loss is told by its sign.


def _usd(value: float) -> str:
    return f"${abs(value):,.0f}" if value >= 0 else f"-${abs(value):,.0f}"


def _signed(value: float) -> str:
    rounded = round(value)
    if rounded == 0:
        return "$0"
    return f"{'+' if rounded > 0 else '-'}${abs(rounded):,}"


def _cents(value: float) -> str:
    return f"${value:,.2f}"


def _share(value: float) -> str:
    return f"{100 * value:.0f}%"


def _signed_share(value: float) -> str:
    return f"{100 * value:+.1f}%"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ratio(top: float, bottom: float) -> float | None:
    return top / bottom if bottom else None


@dataclass
class _Day:
    day: int
    start: float
    end: float

    @property
    def change(self) -> float:
        return self.end - self.start

    @property
    def percent(self) -> float:
        return self.change / self.start if self.start else 0.0


class _Book:
    """One sim's records up to a step, and the numbers worked out from them."""

    def __init__(
        self,
        store: ApiStore,
        row: dict,
        through: int | None,
        with_decisions: bool = True,
    ):
        sim_id = row["ID"]
        self.row = row
        self.start = row["STARTING_VALUE"]
        self.rows = [
            r
            for r in store.account_steps([sim_id])[sim_id]
            if through is None or r["STEP"] <= through
        ]
        orders = [
            o
            for o in store.orders(sim_id)
            if through is None
            or (
                o.get("STEP_CARRIED_OUT") is not None
                and o["STEP_CARRIED_OUT"] <= through
            )
        ]
        self.trades = trades_of(orders, store.charges(sim_id))
        self.closed = [t for t in self.trades if t.closed]
        self.decisions = store.decisions(sim_id) if with_decisions else []
        self.calls = store.calls(sim_id) if with_decisions else []
        self.days = self._days()

    def _days(self) -> list[_Day]:
        ends: dict[int, float] = {}
        for r in self.rows:
            ends[day_of(r["STEP"])] = r["ACCOUNT_VALUE"]
        days, before = [], self.start
        for day in sorted(ends):
            days.append(_Day(day, before, ends[day]))
            before = ends[day]
        return days

    # Money

    @property
    def value(self) -> float:
        return self.rows[-1]["ACCOUNT_VALUE"] if self.rows else self.start

    @property
    def profit(self) -> float:
        return self.value - self.start

    # The ride

    def swing(self) -> float | None:
        changes = [d.change for d in self.days]
        return statistics.stdev(changes) if len(changes) > 1 else None

    def swing_percent(self) -> float | None:
        changes = [d.percent for d in self.days]
        return statistics.stdev(changes) if len(changes) > 1 else None

    def sharpe(self) -> float | None:
        swing = self.swing_percent()
        if not swing:
            return None
        return (
            statistics.mean(d.percent for d in self.days)
            / swing
            * math.sqrt(DAYS_PER_YEAR)
        )

    def best_day(self) -> float | None:
        return max((d.change for d in self.days), default=None)

    def worst_day(self) -> float | None:
        return min((d.change for d in self.days), default=None)

    def highest(self) -> float | None:
        return max((r["ACCOUNT_VALUE"] for r in self.rows), default=None)

    def lowest(self) -> float | None:
        return min((r["ACCOUNT_VALUE"] for r in self.rows), default=None)

    def biggest_drop(self) -> tuple[float, float, int | None]:
        """The biggest fall from a high, as dollars and a share of the high, and the days
        taken to be back at that high (None while it is not)."""
        if not self.rows:
            return 0.0, 0.0, 0
        peak, peak_step = self.start, self.rows[0]["STEP"]
        drop, high, high_step, bottom_step = 0.0, peak, peak_step, peak_step
        for r in self.rows:
            value = r["ACCOUNT_VALUE"]
            if value > peak:
                peak, peak_step = value, r["STEP"]
            elif value - peak < drop:
                drop, high, high_step, bottom_step = (
                    value - peak,
                    peak,
                    peak_step,
                    r["STEP"],
                )
        if drop == 0:
            return 0.0, 0.0, 0
        back = next(
            (
                r["STEP"]
                for r in self.rows
                if r["STEP"] > bottom_step and r["ACCOUNT_VALUE"] >= high
            ),
            None,
        )
        days = None if back is None else day_of(back) - day_of(high_step)
        return drop, drop / high, days

    def share_of_days_up(self) -> float | None:
        if not self.days:
            return None
        return sum(1 for d in self.days if d.change > 0) / len(self.days)

    # The trader

    def time_invested(self) -> float | None:
        if not self.rows:
            return None
        return sum(1 for r in self.rows if r["EXPOSURE"] > 0) / len(self.rows)

    def average_invested(self) -> float | None:
        return _mean(
            [
                r["EXPOSURE"] / r["ACCOUNT_VALUE"]
                for r in self.rows
                if r["ACCOUNT_VALUE"] > 0
            ]
        )

    def full_evaluations(self) -> list[dict]:
        return [d for d in self.decisions if d["KIND"] == KIND_FULL_EVALUATION]

    def screens_answered(self) -> list[dict]:
        return [d for d in self.decisions if d.get("SCREEN_ANSWER") is not None]

    def trades_by_day(self) -> Counter:
        return Counter(day_of(t.opened_step) for t in self.trades)


def _figure(
    key: str,
    name: str,
    unit: str,
    sim: float | None,
    holding: float | None,
    says: str,
) -> Figure:
    return Figure(key=key, name=name, unit=unit, sim=sim, holding=holding, says=says)


def _or(value, sentence: Callable[[float], str], missing: str) -> str:
    return missing if value is None else sentence(value)


# The six groups


def _money(book: _Book, holding: _Book | None) -> MeasurementGroup:
    spent = sum(c.get("COST_USD") or 0.0 for c in book.calls)
    evaluations = {d["ID"] for d in book.full_evaluations()}
    evaluation_calls = [c for c in book.calls if c.get("DECISION") in evaluations]
    per_evaluation = _ratio(
        sum(c.get("COST_USD") or 0.0 for c in evaluation_calls), len(evaluations)
    )
    seconds = _ratio(
        sum(c.get("LATENCY_SECONDS") or 0.0 for c in evaluation_calls),
        len(evaluations),
    )
    return MeasurementGroup(
        key="money",
        title="Money",
        says="Where the account ended, and what the models cost in real dollars",
        figures=[
            _figure(
                "ending_value",
                "Account value",
                "usd",
                book.value,
                holding and holding.value,
                f"The account is worth {_usd(book.value)}"
                + (
                    f"; holding the five assets would be worth {_usd(holding.value)}."
                    if holding
                    else "."
                ),
            ),
            _figure(
                "profit",
                "Profit",
                "signed_usd",
                book.profit,
                holding and holding.profit,
                f"Since the start the account is {_signed(book.profit)}: "
                f"from {_usd(book.start)} to {_usd(book.value)}.",
            ),
            _figure(
                "beat_holding",
                "Excess return over the benchmark",
                "signed_usd",
                None if holding is None else book.value - holding.value,
                None,
                "No holding sim to compare with."
                if holding is None
                else f"It ended {_signed(book.value - holding.value)} against holding "
                "the five assets: only what it ends above holding is the agent's doing.",
            ),
            _figure(
                "spent",
                "Model spending",
                "cents",
                spent,
                None,
                f"Real money paid to Jev and the LLM for this sim: {_cents(spent)}.",
            ),
            _figure(
                "cost_per_full_evaluation",
                "Cost per full evaluation",
                "cents",
                per_evaluation,
                None,
                _or(
                    per_evaluation,
                    lambda v: (
                        f"Each full evaluation cost {_cents(v)} in real money, "
                        "from the screen to the size."
                    ),
                    "No full evaluations yet.",
                ),
            ),
            _figure(
                "seconds_per_full_evaluation",
                "Latency per full evaluation",
                "number",
                seconds,
                None,
                _or(
                    seconds,
                    lambda v: (
                        f"Jev took {v:.1f} seconds per full evaluation, "
                        "its calls added up."
                    ),
                    "No full evaluations yet.",
                ),
            ),
            _figure(
                "cost_per_position_review",
                "Cost per position review",
                "cents",
                None,
                None,
                "No position reviews yet: the agent leaves open trades to code for now.",
            ),
        ],
        breakdowns=[],
    )


def _ride(book: _Book, holding: _Book | None) -> MeasurementGroup:
    drop, drop_share, back_days = book.biggest_drop()
    held_drop = holding.biggest_drop() if holding else None
    swing, swing_share = book.swing(), book.swing_percent()
    held_swing_share = holding.swing_percent() if holding else None
    relative = (
        None
        if swing_share is None or not held_swing_share
        else swing_share / held_swing_share
    )
    best, worst = book.best_day(), book.worst_day()
    high, low = book.highest(), book.lowest()
    up = book.share_of_days_up()
    sharpe = book.sharpe()

    def h(work: Callable[[_Book], float | None]) -> float | None:
        return None if holding is None else work(holding)

    return MeasurementGroup(
        key="ride",
        title="How wild the ride is",
        says="How much the account swung from day to day (a day is a UTC day)",
        figures=[
            _figure(
                "daily_swing",
                "Volatility (standard deviation of daily change)",
                "usd",
                swing,
                h(_Book.swing),
                _or(
                    swing,
                    lambda v: (
                        f"On a typical day the account moved about {_usd(v)} "
                        "up or down."
                    ),
                    "Needs two days to work out.",
                ),
            ),
            _figure(
                "daily_swing_percent",
                "Daily volatility",
                "share",
                swing_share,
                held_swing_share,
                _or(
                    swing_share,
                    lambda v: f"That is about {100 * v:.2f}% of the account a day.",
                    "Needs two days to work out.",
                ),
            ),
            _figure(
                "best_day",
                "Best day",
                "signed_usd",
                best,
                h(_Book.best_day),
                _or(
                    best,
                    lambda v: f"Its best day: {_signed(v)}.",
                    "No full day yet.",
                ),
            ),
            _figure(
                "worst_day",
                "Worst day",
                "signed_usd",
                worst,
                h(_Book.worst_day),
                _or(
                    worst,
                    lambda v: f"Its worst day: {_signed(v)}.",
                    "No full day yet.",
                ),
            ),
            _figure(
                "highest",
                "High-water mark",
                "usd",
                high,
                h(_Book.highest),
                _or(
                    high,
                    lambda v: f"The account was never worth more than {_usd(v)}.",
                    "Nothing stored yet.",
                ),
            ),
            _figure(
                "lowest",
                "Low point",
                "usd",
                low,
                h(_Book.lowest),
                _or(
                    low,
                    lambda v: f"Nor less than {_usd(v)}.",
                    "Nothing stored yet.",
                ),
            ),
            _figure(
                "biggest_drop",
                "Maximum drawdown",
                "signed_usd",
                drop,
                held_drop and held_drop[0],
                "It never fell below a high it had reached."
                if drop == 0
                else f"Its biggest fall from a high was {_signed(drop)} "
                f"({_signed_share(drop_share)} of that high).",
            ),
            _figure(
                "days_to_climb_back",
                "Recovery time",
                "days",
                back_days,
                held_drop and held_drop[2],
                "It has not climbed back to that high yet."
                if back_days is None
                else f"It took {back_days} day(s) to climb back to that high.",
            ),
            _figure(
                "share_of_days_up",
                "Share of up days",
                "share",
                up,
                h(_Book.share_of_days_up),
                _or(
                    up,
                    lambda v: f"{_share(v)} of days ended with the account up.",
                    "No full day yet.",
                ),
            ),
            _figure(
                "swing_against_holding",
                "Relative volatility",
                "number",
                relative,
                None,
                _or(
                    relative,
                    lambda v: (
                        f"It swung {v:.1f} times as much as holding the five assets."
                    ),
                    "Needs two days of both this sim and holding.",
                ),
            ),
            _figure(
                "sharpe",
                "Sharpe ratio",
                "number",
                sharpe,
                h(_Book.sharpe),
                _or(
                    sharpe,
                    lambda v: (
                        f"Profit per unit of swing, over a year: {v:.2f}. Above "
                        "1 is good; below 0 it lost money."
                    ),
                    "Needs two days with some swing.",
                ),
            ),
        ],
        breakdowns=[],
    )


def _largest_size_share(book: _Book) -> float | None:
    buckets = ((book.row.get("SETTINGS") or {}).get("risk_profile") or {}).get(
        "size_buckets"
    )
    if not buckets:
        return None
    largest = size_option_name(max(buckets))
    picked = []
    for d in book.full_evaluations():
        answers = d.get("ANSWERS") or {}
        copies = [
            answers[q] for q in ("size_small_first", "size_large_first") if q in answers
        ]
        if not copies:
            continue
        averaged = {
            n: sum(c.get(n, 0.0) for c in copies) / len(copies) for n in copies[0]
        }
        picked.append(max(averaged, key=lambda n: averaged[n]) == largest)
    return _ratio(sum(picked), len(picked))


def _trader(book: _Book, sim: Sim) -> MeasurementGroup:
    trades, closed = book.trades, book.closed
    days = len(book.days)
    per_day = _ratio(len(trades), days)
    longs = sum(1 for t in trades if t.direction == "long")
    hold_hours = _mean(
        [(t.closed_step - t.opened_step) * HOURS_PER_STEP for t in closed]
    )
    same_day = _ratio(
        sum(1 for t in closed if day_of(t.closed_step) == day_of(t.opened_step)),
        len(closed),
    )
    screens = book.screens_answered()
    evaluations = book.full_evaluations()
    entries = sum(1 for d in evaluations if d["ACTION"] == ACTION_ENTRY)
    to_evaluation = _ratio(len(evaluations), len(screens))
    to_trade = _ratio(entries, len(evaluations))
    ruled_out = sum(
        1
        for d in book.decisions
        if d.get("SKIPPED_BECAUSE") and d["SKIPPED_BECAUSE"] not in NOT_A_LIMIT
    ) + sum(
        1
        for d in evaluations
        if d["ACTION"] != ACTION_ENTRY and d.get("PICK") not in (None, NO_TRADE)
    )
    trimmed = sum(1 for t in trades if t.limited_by is not None)
    invested, average_invested = book.time_invested(), book.average_invested()
    size = _mean([t.put_in for t in trades])
    largest = _largest_size_share(book)

    by_day = book.trades_by_day()
    after_loss, after_other = [], []
    for before, day in zip(book.days, book.days[1:], strict=False):
        (after_loss if before.change < 0 else after_other).append(by_day[day.day])
    after_loss_avg, after_other_avg = _mean(after_loss), _mean(after_other)

    per_asset = Counter(sim.asset(t.asset).name for t in trades)
    endings = Counter(t.closing_reason for t in closed)
    hours = Counter((t.opened_step % STEPS_PER_DAY) * 15 // 60 for t in trades)
    return MeasurementGroup(
        key="trader",
        title="What kind of trader it is",
        says="How often it trades, how big, how long it holds, and what holds it back",
        figures=[
            _figure(
                "trades_per_day",
                "Trade frequency",
                "number",
                per_day,
                None,
                _or(
                    per_day,
                    lambda v: (
                        f"It opened {v:.1f} trades a day ({len(trades)} in "
                        f"{days} days)."
                    ),
                    "No days stored yet.",
                ),
            ),
            _figure(
                "share_of_time_invested",
                "Time in the market",
                "share",
                invested,
                None,
                _or(
                    invested,
                    lambda v: f"It held at least one position {_share(v)} of the time.",
                    "Nothing stored yet.",
                ),
            ),
            _figure(
                "average_invested",
                "Average exposure",
                "share",
                average_invested,
                None,
                _or(
                    average_invested,
                    lambda v: (
                        f"On average {_share(v)} of the account was in positions "
                        "(above 100% means borrowed money)."
                    ),
                    "Nothing stored yet.",
                ),
            ),
            _figure(
                "average_trade_size",
                "Average position size",
                "usd",
                size,
                None,
                _or(
                    size,
                    lambda v: f"A typical trade put {_usd(v)} in.",
                    "No trades yet.",
                ),
            ),
            _figure(
                "largest_size_share",
                "Maximum size frequency",
                "share",
                largest,
                None,
                _or(
                    largest,
                    lambda v: (
                        f"Jev leaned most to the largest size in {_share(v)} of "
                        "the trades it sized."
                    ),
                    "No trades sized yet.",
                ),
            ),
            _figure(
                "share_long",
                "Long / short mix",
                "share",
                _ratio(longs, len(trades)),
                None,
                f"{longs} bets on a rise (long), {len(trades) - longs} on a fall "
                "(short).",
            ),
            _figure(
                "average_hold_hours",
                "Average holding period",
                "hours",
                hold_hours,
                None,
                _or(
                    hold_hours,
                    lambda v: f"A trade stayed open {v:.1f} hours on average.",
                    "No closed trades yet.",
                ),
            ),
            _figure(
                "share_closed_same_day",
                "Intraday trades",
                "share",
                same_day,
                None,
                _or(
                    same_day,
                    lambda v: f"{_share(v)} of trades closed on the day they opened.",
                    "No closed trades yet.",
                ),
            ),
            _figure(
                "screens_to_full_evaluation",
                "Screen pass rate",
                "share",
                to_evaluation,
                None,
                _or(
                    to_evaluation,
                    lambda v: (
                        f"{_share(v)} of Jev's quick checks led to a full "
                        f"evaluation ({len(evaluations)} of {len(screens)})."
                    ),
                    "No screens yet.",
                ),
            ),
            _figure(
                "full_evaluations_to_trade",
                "Conversion rate",
                "share",
                to_trade,
                None,
                _or(
                    to_trade,
                    lambda v: (
                        f"{_share(v)} of full evaluations placed a trade "
                        f"({entries} of {len(evaluations)})."
                    ),
                    "No full evaluations yet.",
                ),
            ),
            _figure(
                "limits_ruled_out",
                "Risk limit blocks",
                "count",
                ruled_out,
                None,
                f"A risk limit stopped a trade from opening {ruled_out} time(s).",
            ),
            _figure(
                "trades_trimmed",
                "Trades cut by risk limits",
                "count",
                trimmed,
                None,
                f"Code made {trimmed} trade(s) smaller to fit a risk limit.",
            ),
            _figure(
                "trades_after_losing_day",
                "Activity after a losing day",
                "number",
                after_loss_avg,
                None,
                "No losing day yet."
                if after_loss_avg is None
                else f"After a losing day it opened {after_loss_avg:.1f} trades a day"
                + (
                    f", against {after_other_avg:.1f} after other days."
                    if after_other_avg is not None
                    else "."
                ),
            ),
        ],
        breakdowns=[
            Breakdown(
                key="trades_per_asset",
                name="Trades per asset",
                unit="count",
                says="How many trades it opened in each asset.",
                rows=[
                    BreakdownRow(label=name, trades=n, value=None)
                    for name, n in sorted(per_asset.items())
                ],
            ),
            Breakdown(
                key="how_trades_end",
                name="Exit reasons",
                unit="count",
                says="How each closed trade ended.",
                rows=[
                    BreakdownRow(
                        label=ENDINGS.get(reason, reason), trades=n, value=None
                    )
                    for reason, n in sorted(endings.items())
                ],
            ),
            Breakdown(
                key="time_of_day",
                name="Entry time",
                unit="count",
                says="The hour (UTC) each trade opened in.",
                rows=[
                    BreakdownRow(label=f"{hour:02d}:00 UTC", trades=n, value=None)
                    for hour, n in sorted(hours.items())
                ],
            ),
        ],
    )


def _profit_split(name: str, key: str, groups: dict[str, list[float]]) -> Breakdown:
    return Breakdown(
        key=key,
        name=name,
        unit="signed_usd",
        says="Trades and the profit they added up to.",
        rows=[
            BreakdownRow(label=label, trades=len(profits), value=sum(profits))
            for label, profits in sorted(groups.items())
        ],
    )


def _trades(
    book: _Book, holding: _Book | None, sim: Sim, patterns: dict[tuple, list[str]]
) -> MeasurementGroup:
    def numbers(b: _Book):
        profits = [t.profit for t in b.closed]
        gains = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        return (
            len(b.trades),
            _ratio(len(gains), len(profits)),
            _mean(gains),
            _mean(losses),
            None if not losses else sum(gains) / -sum(losses),
        )

    count, share, gain, loss, factor = numbers(book)
    held = numbers(holding) if holding else (None,) * 5

    splits: dict[str, dict[str, list[float]]] = {
        "asset": {},
        "direction": {},
        "pattern": {},
        "ending": {},
    }
    for t in book.closed:
        splits["asset"].setdefault(sim.asset(t.asset).name, []).append(t.profit)
        splits["direction"].setdefault(t.direction, []).append(t.profit)
        splits["ending"].setdefault(
            ENDINGS.get(t.closing_reason, t.closing_reason), []
        ).append(t.profit)
        for pattern in patterns.get((t.asset, t.decided_step), []):
            splits["pattern"].setdefault(pattern, []).append(t.profit)

    return MeasurementGroup(
        key="trades",
        title="Trades",
        says="How the trades themselves did, after every trading cost",
        figures=[
            _figure(
                "trades",
                "Number of trades",
                "count",
                count,
                held[0],
                f"{count} trades opened, {len(book.closed)} of them closed.",
            ),
            _figure(
                "share_made_money",
                "Win rate",
                "share",
                share,
                held[1],
                _or(
                    share,
                    lambda v: f"{_share(v)} of closed trades made money.",
                    "No closed trades yet.",
                ),
            ),
            _figure(
                "average_gain",
                "Average win",
                "signed_usd",
                gain,
                held[2],
                _or(
                    gain,
                    lambda v: f"A trade that made money made {_signed(v)} on average.",
                    "No trade has made money yet.",
                ),
            ),
            _figure(
                "average_loss",
                "Average loss",
                "signed_usd",
                loss,
                held[3],
                _or(
                    loss,
                    lambda v: f"A trade that lost money lost {_signed(v)} on average.",
                    "No trade has lost money yet.",
                ),
            ),
            _figure(
                "gains_over_losses",
                "Profit factor",
                "number",
                factor,
                held[4],
                _or(
                    factor,
                    lambda v: (
                        f"For every $1 lost, trades made ${v:.2f}. Above 1 the "
                        "trades made money overall."
                    ),
                    "No losing trade yet to compare with.",
                ),
            ),
        ],
        breakdowns=[
            _profit_split("Profit by asset", "by_asset", splits["asset"]),
            _profit_split("Profit by direction", "by_direction", splits["direction"]),
            _profit_split("Profit by candle pattern", "by_pattern", splits["pattern"]),
            _profit_split("Profit by exit reason", "by_ending", splits["ending"]),
        ],
    )


def _direction_probability(answers: dict, direction: str) -> float | None:
    copies = [v for q, v in answers.items() if q.startswith("pick_")]
    if not copies:
        return None
    return sum(
        sum(p for name, p in copy.items() if name.startswith(f"{direction}_"))
        for copy in copies
    ) / len(copies)


def _confidence(book: _Book) -> MeasurementGroup:
    answers = {d["ID"]: d.get("ANSWERS") or {} for d in book.full_evaluations()}
    sure: list[tuple[float, bool]] = []
    for t in book.closed:
        said = _direction_probability(answers.get(t.decision) or {}, t.direction)
        if said is not None:
            sure.append((said, t.profit > 0))
    bands: dict[int, list[bool]] = {}
    for said, won in sure:
        bands.setdefault(min(int(said * 10 + 1e-9), 9), []).append(won)
    average = _mean([s for s, _ in sure])
    right = _ratio(sum(1 for _, w in sure if w), len(sure))
    return MeasurementGroup(
        key="confidence",
        title="Jev's confidence",
        says="When Jev says 70% sure, is it right about 70% of the time?",
        figures=[
            _figure(
                "average_confidence",
                "Average stated probability",
                "share",
                average,
                None,
                _or(
                    average,
                    lambda v: (
                        f"Jev gave the direction it traded {_share(v)} on average."
                    ),
                    "No closed trades from a full evaluation yet.",
                ),
            ),
            _figure(
                "share_right",
                "Hit rate",
                "share",
                right,
                None,
                _or(
                    right,
                    lambda v: f"Those trades made money {_share(v)} of the time.",
                    "No closed trades from a full evaluation yet.",
                ),
            ),
        ],
        breakdowns=[
            Breakdown(
                key="calibration",
                name="Calibration",
                unit="share",
                says="Trades by how sure Jev was of their direction, and the share "
                "that made money. A well-calibrated Jev makes money about as often as "
                "it says.",
                rows=[
                    BreakdownRow(
                        label=f"{10 * band}-{10 * band + 10}%",
                        trades=len(won),
                        value=sum(won) / len(won),
                    )
                    for band, won in sorted(bands.items())
                ],
            )
        ],
    )


def _memory(book: _Book, holding: _Book | None) -> MeasurementGroup:
    variant = book.row["VARIANT"]
    waiting = (
        "Recorded once the agent with memory is built."
        if variant == "memory_on"
        else "This sim has no memory, so there is nothing to measure here."
    )
    days = len(book.days)
    per_day = _ratio(book.profit, days)
    held_per_day = (
        None if holding is None else _ratio(holding.profit, len(holding.days))
    )
    return MeasurementGroup(
        key="memory",
        title="Memory",
        says="Whether looking back at past trades helped",
        figures=[
            _figure(
                "took_top_results", "Top-k acceptance", "share", None, None, waiting
            ),
            _figure("more_one_sided", "Selection bias", "share", None, None, waiting),
            _figure(
                "ranking_helped", "Text ranking lift", "share", None, None, waiting
            ),
            _figure(
                "profit_per_day",
                "Profit per day",
                "signed_usd",
                per_day,
                held_per_day,
                _or(
                    per_day,
                    lambda v: (
                        f"It made {_signed(v)} a day on average. With memory "
                        "against without is on the Comparison screen."
                    ),
                    "No days stored yet.",
                ),
            ),
        ],
        breakdowns=[],
    )


def measurements(store: ApiStore, sim_id: int) -> Measurements:
    sim = Sim(store, sim_id)
    row = sim.row
    reached = row.get("LAST_COMPLETED_STEP")
    book = _Book(store, row, reached)
    holding_row = holding_of(store.sims(), row)
    holding = (
        None
        if holding_row is None
        else _Book(store, holding_row, reached, with_decisions=False)
    )
    found = store.entry_details(
        row["DATASET"], sorted({(t.asset, t.decided_step) for t in book.closed})
    )
    patterns = {pair: (d["PATTERNS"] or ["none"]) for pair, d in found.items()}
    return Measurements(
        through_step=reached,
        holding_sim_id=None if holding_row is None else holding_row["ID"],
        groups=[
            _money(book, holding),
            _ride(book, holding),
            _trader(book, sim),
            _trades(book, holding, sim, patterns),
            _confidence(book),
            _memory(book, holding),
        ],
    )
