"""What Jev reads: the background and the questions, written by code (spec appendix 4, section 8).

The words live in `prompts/jev_reading.toml`; a past episode and a track record line are written
with the words in `prompts/episodes.toml`, by the renderer the LLM's lookups use
(`jev_trader.memory.render`). The same data always gives the same text: nothing here reads a
clock, a random number or a sim number, and the step only counts how long ago an episode was.

The **reading version** is a fingerprint worked out from both wording files, the opening as this
sim's settings fill it in, and the layout of a request (with and without memory), so a changed
word, setting or section order gives a new version and nobody has to bump a number.

Choices the spec leaves to the build:

- An asset with no typical move (its price did not move for 14 bars) has that sentence left out,
  as the situation text leaves out a number that is not available.
- Room to hold more never reads below $0, and a negative amount reads "-$5".
- With no candle pattern showing, the track record section says so in one line.
- The candle pattern notes take the episodes' patterns (15-minute, then hourly and daily) in the
  order the episodes are shown, newest first.
"""

import hashlib
import json
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from jev_trader.broker import Direction, TradingCosts
from jev_trader.jev.full_evaluation import NO_TRADE, SHUFFLED_COPIES, CandidateTrade
from jev_trader.jev.position_review import (
    ACTIONS,
    ADD,
    CLOSE,
    HOLD,
    REDUCE,
    REDUCE_SHARES,
    reduce_option_name,
)
from jev_trader.risk import RiskLimit, RiskProfile

if TYPE_CHECKING:  # memory's episodes reach back here through the sim's records
    from jev_trader.memory.episodes import Episode
    from jev_trader.memory.track_record import TrackRecord

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "jev_reading.toml"
VERSION_LENGTH = 12


@dataclass(frozen=True)
class PositionLine:
    """One open position, as the account's list shows it."""

    asset: str
    asset_class: str
    direction: str
    worth: float
    bars_ago: int
    profit: float  # after trading costs, in dollars
    percent: float  # the same, as a percentage: 0.3 is 0.3%


@dataclass(frozen=True)
class AccountView:
    value: float
    cash: float
    loan: float
    exposure: float
    positions: tuple[PositionLine, ...] = ()
    shorts: float = (
        0.0  # the open shorts' worth: their sale money in cash is not the account's
    )


@dataclass(frozen=True)
class AssetView:
    """The asset at this step. Prices are masked: rescaled so the series started at 100."""

    asset_id: str
    asset_class: str
    price: float
    typical_move: float | None
    situation: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class PositionView:
    """The open position under a position screen or review: its journal, as Jev reads it."""

    direction: Direction
    put_in: float  # dollars put into what is held now
    bars_ago: int  # bars since the one it was opened in
    entry_price: float
    stop_price: float
    worth: float  # at the last price
    profit: float  # what closing now would leave, after trading costs
    percent: float  # the same, as a percentage of what was put in: 0.4 is 0.4%
    best: float  # its best and worst profit so far, after trading costs
    worst: float
    situation_at_entry: str
    patterns_at_entry: tuple[str, ...]
    since: tuple[str, ...]  # "since then", runs already merged: ("bars 1 to 4 hold",)
    end_of_session: bool = False  # a stock's end-of-session review

    @property
    def is_long(self) -> bool:
        return self.direction is Direction.LONG

    def stop_share(self, price: float) -> float:
        """How far the stop price is from `price`, as a share of it."""
        return abs(price - self.stop_price) / price

    def risk_used(self, price: float) -> float:
        """What the whole position loses if the price goes from `price` to the stop price."""
        return self.worth * self.stop_share(price)

    def standing(self, price: float) -> dict:
        """How the position stands at `price`, as a review's episode stores it: "open 6 bars,
        +$18, stop price 0.9% away"."""
        return {
            "direction": str(self.direction),
            "put_in": self.put_in,
            "bars_open": self.bars_ago,
            "profit": self.profit,
            "percent": self.percent,
            "stop_distance": self.stop_share(price),
            "best": self.best,
            "worst": self.worst,
        }


class PastEpisodes(StrEnum):
    """What the past-episodes section has to show. Each "nothing to show" case is its own
    state, worded apart, so Jev can tell them apart; the agent without memory passes no memory
    at all, and its background has neither memory section."""

    SELECTED = "selected"
    NONE_SELECTED = "none_selected"  # the LLM chose none: memory has earlier decisions
    NONE_YET = "none_yet"  # memory holds none yet, so the LLM was not asked


# The recorded-only question of request 1 when past episodes are shown (spec appendix 4,
# section 10).
MEMORIES_RELEVANT = "memories_relevant"


@dataclass(frozen=True)
class MemorySections:
    """The agent with memory's two sections of a full evaluation's or position review's
    background: the track record, then the past episodes the LLM selected (spec appendix 4,
    sections 7 and 8).

    `step` is the step the evaluation or review runs at, for how long ago each episode was.
    """

    step: int
    track_records: tuple["TrackRecord", ...]  # one per candle pattern and direction
    past_episodes: PastEpisodes
    episodes: tuple["Episode", ...] = ()  # the selected ones, in any order

    @property
    def newest_first(self) -> tuple["Episode", ...]:
        """The episodes as Jev reads them: newest first, so the LLM's order of preference does
        not reach Jev."""
        return tuple(sorted(self.episodes, key=lambda e: (-e.step, e.id)))

    def __post_init__(self):
        if bool(self.episodes) != (self.past_episodes is PastEpisodes.SELECTED):
            raise ValueError(
                f"{len(self.episodes)} episodes do not fit {self.past_episodes}"
            )


@dataclass(frozen=True)
class JevRequest:
    """One call to Jev: a background, and its questions as they go on the wire."""

    background: str
    questions: dict[str, dict]


def _round(n: float) -> int:
    return math.floor(n + 0.5)


def dollars(n: float) -> str:
    rounded = _round(n)
    return f"{'-' if rounded < 0 else ''}${abs(rounded):,}"


def _signed_dollars(n: float) -> str:
    rounded = _round(n)
    return f"{'-' if rounded < 0 else '+'}${abs(rounded):,}"


def _signed_percent(n: float) -> str:
    return f"{'-' if n < 0 else '+'}{abs(n):.1f}%"


def _whole_percent(share: float) -> str:
    return f"{_round(100 * share)}%"


def _price(n: float) -> str:
    return f"${n:.2f}"


def _percent(share: float) -> str:
    return f"{100 * share:.1f}%"


def size_option_name(share: float) -> str:
    """A size bucket's option name: 0.2 gives "size_20_percent"."""
    return f"size_{_round(100 * share)}_percent"


def _bars(n: int) -> str:
    return f"{n} bar" if n == 1 else f"{n} bars"


def load_wording(path: Path = WORDING_PATH) -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


_LAYOUT_ASSET = AssetView("ASSET", "stock", 100.0, 1.0, "Situation.", ("pattern",))
_LAYOUT_ACCOUNT = AccountView(
    value=100.0,
    cash=50.0,
    loan=1.0,
    exposure=50.0,
    positions=(PositionLine("OTHER", "crypto", "long", 50.0, 1, 1.0, 1.0),),
)
_LAYOUT_PLAYBOOK = {"pattern": ("lean", "Shape.")}
_LAYOUT_TRADES = (
    CandidateTrade("long_tight_stop", Direction.LONG, "tight", 99.0, 0.01),
    CandidateTrade("short_tight_stop", Direction.SHORT, "tight", 101.0, 0.01),
)
_LAYOUT_ORDERS = [[t.name for t in _LAYOUT_TRADES] + [NO_TRADE]] * SHUFFLED_COPIES
# An end-of-session long, so the layout carries every line a position's record can have.
_LAYOUT_POSITION = PositionView(
    direction=Direction.LONG,
    put_in=10.0,
    bars_ago=2,
    entry_price=99.0,
    stop_price=98.0,
    worth=10.0,
    profit=1.0,
    percent=1.0,
    best=1.0,
    worst=-1.0,
    situation_at_entry="Situation.",
    patterns_at_entry=("pattern",),
    since=("bars 0 to 1 hold",),
    end_of_session=True,
)


def _patterns_named_in(memory: MemorySections | None) -> tuple[str, ...]:
    """Every candle pattern the episodes shown name, for the pattern notes."""
    if memory is None:
        return ()
    return tuple(
        name for e in memory.newest_first for name in (*e.patterns, *e.longer_patterns)
    )


def _layout_memories() -> list[MemorySections]:
    """Memory in each of its states, on fixed data, so the reading version carries the memory
    sections' layout: a pattern with a group that fits and one with too few trades (or no
    pattern at all), and a past trade, a past no trade and a past position review."""
    from jev_trader.memory.episodes import (
        Ended,
        Episode,
        Prices,
        Standing,
        Step,
        Trade,
    )
    from jev_trader.memory.track_record import Group, TrackRecord

    fits = Group(
        trend="with the trend",
        volume_level="high",
        part_of_day="first hour",
        trades=10,
        made_money=5,
        average_gain=1.0,
        average_loss=-1.0,
        total_profit=0.0,
        fits=True,
    )
    records = (
        TrackRecord(
            pattern="pattern",
            direction="long",
            asset_class="stock",
            minimum_sample=10,
            closed_trades=10,
            groups=[fits],
        ),
        TrackRecord(
            pattern="pattern",
            direction="short",
            asset_class="stock",
            minimum_sample=10,
            closed_trades=1,
            groups=[],
        ),
    )
    trade = Episode(
        id="1-1-OTHER",
        kind="full_evaluation",
        asset="OTHER",
        asset_class="crypto",
        step=1,
        situation="Situation.",
        patterns=["pattern"],
        longer_patterns=["pattern"],
        part_of_day="morning",
        trend="up",
        volume="high",
        decided="long",
        trade=Trade(direction="long", stop="tight", stop_distance=0.01, dollars=10.0),
        prices=Prices(after_1_bar=0.01, after_4_bars=0.01, end_of_day=0.01),
        ended=Ended(
            reason="jev", bars_after=1, profit=1.0, percent=1.0, best=1.0, worst=-1.0
        ),
    )
    no_trade = trade.model_copy(
        update={
            "id": "1-2-ASSET",
            "asset": "ASSET",
            "step": 2,
            "decided": "no_trade",
            "trade": None,
            "ended": None,
        }
    )
    review = trade.model_copy(
        update={
            "id": "1-3-ASSET",
            "kind": "position_review",
            "asset": "ASSET",
            "step": 3,
            "decided": "hold",
            "trade": None,
            "review": Step(bar=1, action="hold", this_review=True),
            "standing": Standing(
                direction="long",
                put_in=10.0,
                bars_open=1,
                profit=1.0,
                percent=1.0,
                stop_distance=0.01,
                best=1.0,
                worst=-1.0,
            ),
            "ended": Ended(reason="jev", bars_after=1, profit=1.0, percent=1.0),
            "journal": [Step(bar=1, action="hold", this_review=True)],
        }
    )
    episodes = (trade, no_trade, review)
    return [
        MemorySections(200, records, PastEpisodes.SELECTED, episodes),
        MemorySections(200, records, PastEpisodes.NONE_SELECTED),
        MemorySections(200, records, PastEpisodes.NONE_YET),
        MemorySections(200, (), PastEpisodes.NONE_YET),
    ]


class Reading:
    """The text of one sim's requests to Jev, given the settings it runs with."""

    def __init__(
        self,
        costs: TradingCosts,
        risk: RiskProfile,
        wording: Mapping | None = None,
        episode_wording: Mapping | None = None,
    ):
        # Imported here: memory reaches back to this module through the sim's records.
        from jev_trader.memory import render

        self._render = render  # the episode renderer the LLM's lookups share
        self.risk = risk
        self.wording = dict(load_wording() if wording is None else wording)
        self.episode_wording = dict(
            render.load_wording() if episode_wording is None else episode_wording
        )
        self.opening = self.wording["opening"].format(
            stock_commission=dollars(costs.stock_commission),
            crypto_fee=f"{100 * costs.crypto_trading_fee:.1f}%",
            slippage=f"{100 * costs.slippage:.2f}%",
            stock_borrow_fee=f"{100 * costs.stock_borrow_fee_yearly:.2f}%",
            crypto_borrow_fee=_whole_percent(costs.crypto_borrow_fee_yearly),
            loan_rate=_whole_percent(costs.loan_interest_yearly),
            trade_risk_limit=_whole_percent(risk.trade_risk_limit),
            position_limit=f"{risk.position_limit:g}",
            exposure_limit=f"{risk.exposure_limit:g}",
            daily_loss_limit=_whole_percent(risk.daily_loss_limit),
            forced_close_share=_whole_percent(risk.forced_close_share),
        )
        # A request written from fixed data carries the layout: the sections' order and joins.
        views = (_LAYOUT_ASSET, _LAYOUT_ACCOUNT, _LAYOUT_PLAYBOOK)
        held = (*views, _LAYOUT_POSITION)
        samples = [
            self.screen_request(*views),
            self.pick_request(*views, _LAYOUT_TRADES, _LAYOUT_ORDERS),
            *(self.size_request(*views, trade) for trade in _LAYOUT_TRADES),
            self.position_screen_request(*held),
            self.action_request(*held, [list(ACTIONS)] * SHUFFLED_COPIES),
            self.reduce_request(*held),
            self.add_request(*held),
        ]
        memory_layouts = [self._background(*views, m) for m in _layout_memories()]
        memory_layouts += [
            self._position_background(*held, m) for m in _layout_memories()
        ]
        fingerprinted = json.dumps(
            {
                "wording": self.wording,
                "episode_wording": self.episode_wording,
                "memory_layout": memory_layouts,
                "opening": self.opening,
                "layout": [[s.background, s.questions] for s in samples],
            },
            sort_keys=True,
        )
        self.version = hashlib.sha256(fingerprinted.encode("utf-8")).hexdigest()[
            :VERSION_LENGTH
        ]

    def screen_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
    ) -> JevRequest:
        """The screen: is a full evaluation of this asset worth running now?"""
        question = self.wording["screen_question"].format(asset=asset.asset_id)
        return JevRequest(
            background=self._background(asset, account, playbook),
            questions={"screen": {"type": "noul", "instructions": question}},
        )

    def pick_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        trades: tuple[CandidateTrade, ...],
        orders: list[list[str]],
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 1 of a full evaluation: which of the seven options, asked once per order,
        and, when at least one past episode is shown, whether they fit (recorded only).

        `orders` lists the option names in the order each copy sends them. Without memory the
        background is the screen's: the memory sections are absent, with nothing said about it.
        """
        options = self.pick_options(asset, account, trades)
        instructions = self.wording["pick_question"].format(asset=asset.asset_id)
        questions = {
            f"pick_{n}": {
                "type": "choice",
                "instructions": instructions,
                "criteria": {name: options[name] for name in order},
            }
            for n, order in enumerate(orders, start=1)
        }
        questions.update(self._memories_relevant(memory))
        return JevRequest(
            background=self._background(asset, account, playbook, memory),
            questions=questions,
        )

    def _memories_relevant(self, memory: MemorySections | None) -> dict[str, dict]:
        """The recorded-only question whether the past episodes shown fit: asked only when at
        least one is shown."""
        if memory is None or not memory.episodes:
            return {}
        return {
            MEMORIES_RELEVANT: {
                "type": "noul",
                "instructions": self.wording["memories_relevant_question"],
            }
        }

    def size_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        trade: CandidateTrade,
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 2: how much money, asked smallest first and largest first, and the rating."""
        w = self.wording
        picked = f"{w['trade_picked_heading']}\n{self._trade_text(trade, asset.price)}"
        options = self.size_options(asset, account, trade)
        size = {"type": "choice", "instructions": w["size_question"]}
        background = self._background(asset, account, playbook, memory)
        return JevRequest(
            background=background + "\n\n" + picked,
            questions={
                "size_small_first": {**size, "criteria": options},
                "size_large_first": {
                    **size,
                    "criteria": dict(reversed(list(options.items()))),
                },
                "rating": {
                    "type": "score",
                    "instructions": w["rating_question"],
                    "criteria": list(w["rating_levels"]),
                },
            },
        )

    def position_screen_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
    ) -> JevRequest:
        """The position screen: is a review of this open position worth running now?"""
        question = self.wording["position_screen_question"].format(asset=asset.asset_id)
        return JevRequest(
            background=self._position_background(asset, account, playbook, position),
            questions={"position_screen": {"type": "noul", "instructions": question}},
        )

    def action_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
        orders: list[list[str]],
        add_allowed: bool = True,
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 1 of a position review: hold, close, reduce or add, asked once per order,
        whether the reason for opening it still holds, and, when at least one past episode is
        shown, whether they fit (both recorded only).

        `orders` lists the option names in the order each copy sends them. Without memory the
        background is the position screen's; with it, the memory sections follow the asset.
        """
        w = self.wording
        options = self.action_options(asset, account, position, add_allowed)
        instructions = w["action_question"].format(asset=asset.asset_id)
        questions = {
            f"action_{n}": {
                "type": "choice",
                "instructions": instructions,
                "criteria": {name: options[name] for name in order},
            }
            for n, order in enumerate(orders, start=1)
        }
        questions["thesis_intact"] = {
            "type": "noul",
            "instructions": w["thesis_intact_question"],
        }
        questions.update(self._memories_relevant(memory))
        return JevRequest(
            background=self._position_background(
                asset, account, playbook, position, memory
            ),
            questions=questions,
        )

    def action_options(
        self,
        asset: AssetView,
        account: AccountView,
        position: PositionView,
        add_allowed: bool = True,
    ) -> dict[str, str]:
        """The actions by name, in code's own order. Add only if allowed and the limits leave room."""
        w = self.wording
        options = {
            HOLD: w["action_hold"],
            CLOSE: w["action_close"].format(
                closes=w["close_verb"][str(position.direction)],
                profit=_signed_dollars(position.profit),
            ),
            REDUCE: w["action_reduce"],
        }
        room, _ = self.add_room(asset, account, position)
        if add_allowed and room > 0:
            options[ADD] = w["action_add"].format(amount=dollars(room))
        return options

    def add_room(
        self, asset: AssetView, account: AccountView, position: PositionView
    ) -> tuple[float, RiskLimit]:
        """The most code adds to the position at the last price, and the limit that sets it."""
        return self.risk.largest_size(
            account_value=account.value,
            price=asset.price,
            stop_price=position.stop_price,
            position_value=position.worth,
            exposure=account.exposure,
        )

    def reduce_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 2 after a reduce: how much, asked smallest first and largest first."""
        w = self.wording
        options = {}
        for rank, share in zip(w["reduce_ranks"], REDUCE_SHARES, strict=True):
            options[reduce_option_name(share)] = w["reduce_option"].format(
                rank=rank,
                amount=dollars(share * position.worth),
                profit=_signed_dollars(share * position.profit),
                left=dollars((1 - share) * position.worth),
            )
        return self._decided_request(
            asset, account, playbook, position, "reduce", options, memory
        )

    def add_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 2 after an add: how much more, in the five sizes of a new trade."""
        w = self.wording
        largest, limit = self.add_room(asset, account, position)
        why = self._limit_words(limit)
        stop_share = position.stop_share(asset.price)
        options = {}
        for rank, share in zip(w["size_ranks"], self.risk.size_buckets, strict=True):
            asked = share * account.value
            actual = min(asked, largest)
            text = w["add_option"].format(
                rank=rank, asked=dollars(asked), share=_whole_percent(share)
            )
            if actual < asked:
                text += w["add_cut"].format(actual=dollars(actual), why=why)
            text += self._borrowing(account, actual, position.is_long)
            loss = position.risk_used(asset.price) + actual * stop_share
            text += w["add_loss"].format(loss=dollars(loss))
            options[size_option_name(share)] = text
        return self._decided_request(
            asset, account, playbook, position, "add", options, memory
        )

    def since(self, journal: list[dict]) -> tuple[str, ...]:
        """A position's "since then", from its journal: one entry a bar, runs of the same merged.

        An entry is {"bar": 3, "action": "hold"}, {"bar": 4, "action": "reduce", "share": 0.25,
        "profit": 7.0} or {"bar": 5, "action": "add", "amount": 2000.0}. A share that is not a
        quarter, half or three quarters reads as a whole percentage ("38%").
        """
        w = self.wording
        runs: list[list] = []  # [first bar, last bar, text]
        for entry in journal:
            if entry["action"] == REDUCE:
                words = dict(zip(REDUCE_SHARES, w["reduce_share_words"], strict=True))
                text = w["journal_reduce"].format(
                    share=words.get(entry["share"], _whole_percent(entry["share"])),
                    profit=_signed_dollars(entry["profit"]),
                )
            elif entry["action"] == ADD:
                text = w["journal_add"].format(amount=dollars(entry["amount"]))
            else:
                text = w["journal_hold"]
            if runs and runs[-1][2] == text:
                runs[-1][1] = entry["bar"]
            else:
                runs.append([entry["bar"], entry["bar"], text])
        return tuple(
            w["journal_bar"].format(bar=first, entry=text)
            if first == last
            else w["journal_bars"].format(first=first, last=last, entry=text)
            for first, last, text in runs
        )

    def _decided_request(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
        decided: str,
        options: dict[str, str],
        memory: MemorySections | None = None,
    ) -> JevRequest:
        """Request 2: the background ending with what was decided ("reduce" or "add"), and how
        much, asked smallest first and largest first."""
        w = self.wording
        background = self._position_background(
            asset, account, playbook, position, memory
        )
        background += f"\n\n{w['decided_heading']}\n{w['decided_' + decided]}"
        question = {"type": "choice", "instructions": w[f"{decided}_question"]}
        return JevRequest(
            background=background,
            questions={
                f"{decided}_small_first": {**question, "criteria": options},
                f"{decided}_large_first": {
                    **question,
                    "criteria": dict(reversed(list(options.items()))),
                },
            },
        )

    def pick_options(
        self,
        asset: AssetView,
        account: AccountView,
        trades: tuple[CandidateTrade, ...],
    ) -> dict[str, str]:
        """The seven options by name, in code's own order: the six trades, then no trade."""
        options = {}
        for trade in trades:
            largest, _ = self.largest_size(asset, account, trade)
            options[trade.name] = self._trade_text(trade, asset.price) + self.wording[
                "largest_size"
            ].format(amount=dollars(largest))
        options[NO_TRADE] = self.wording["no_trade"]
        return options

    def size_options(
        self, asset: AssetView, account: AccountView, trade: CandidateTrade
    ) -> dict[str, str]:
        """The five sizes by name, smallest first, each with what it borrows and loses."""
        w = self.wording
        largest, limit = self.largest_size(asset, account, trade)
        why = self._limit_words(limit)
        options = {}
        for rank, share in zip(w["size_ranks"], self.risk.size_buckets, strict=True):
            asked = share * account.value
            actual = min(asked, largest)
            text = w["size_option"].format(
                rank=rank, asked=dollars(asked), share=_whole_percent(share)
            )
            if actual < asked:
                text += w["size_cut"].format(actual=dollars(actual), why=why)
            text += self._borrowing(account, actual, trade.direction is Direction.LONG)
            text += w["size_loss"].format(loss=dollars(actual * trade.stop_share))
            options[size_option_name(share)] = text
        return options

    def _limit_words(self, limit: RiskLimit) -> str:
        w = self.wording
        return {
            RiskLimit.TRADE_RISK: w["limit_trade_risk"],
            RiskLimit.POSITION: w["limit_position"],
            RiskLimit.EXPOSURE: w["limit_exposure"],
        }[limit]

    def _borrowing(self, account: AccountView, amount: float, long: bool) -> str:
        """How much of `amount` is borrowed: for a long, what the loan grows by."""
        w = self.wording
        if not long:
            return w["size_short"]
        # Cash beyond the shorts' sale money pays first.
        borrowed = max(0.0, account.shorts - account.cash + amount) - account.loan
        if borrowed > 0:
            return w["size_borrowed"].format(borrowed=dollars(borrowed))
        return w["size_from_cash"]

    def largest_size(
        self, asset: AssetView, account: AccountView, trade: CandidateTrade
    ) -> tuple[float, RiskLimit]:
        """The most code opens with `trade` at the last price, and the limit that sets it."""
        return self.risk.largest_size(
            account_value=account.value,
            price=asset.price,
            stop_price=trade.stop_price,
            exposure=account.exposure,
        )

    def _background(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        memory: MemorySections | None = None,
    ) -> str:
        """The screen's background, which is also a full evaluation's without memory. With
        memory, the track record and the past episodes follow the asset."""
        sections = [
            self.opening,
            self._account(account),
            self._open_positions(account.positions),
            self._asset(asset),
            *self._memory(asset, memory),
            self._pattern_notes(asset.patterns + _patterns_named_in(memory), playbook),
        ]
        return "\n\n".join(s for s in sections if s)

    def _memory(
        self, asset: AssetView, memory: MemorySections | None
    ) -> tuple[str, str]:
        """The track record and past-episodes sections; both absent without memory."""
        if memory is None:
            return ("", "")
        return (self._track_record(memory), self._past_episodes(asset, memory))

    def _track_record(self, memory: MemorySections) -> str:
        w = self.wording
        if not memory.track_records:
            return f"{w['track_record_heading']}\n{w['track_record_no_pattern']}"
        lines = [
            self._render.track_record_line(r, self.episode_wording)
            for r in memory.track_records
        ]
        footer = w["track_record_footer"].format(
            minimum=memory.track_records[0].minimum_sample
        )
        return "\n".join([w["track_record_heading"], *lines, footer])

    def _past_episodes(self, asset: AssetView, memory: MemorySections) -> str:
        render = self._render
        w = self.wording
        if memory.past_episodes is PastEpisodes.NONE_YET:
            return f"{w['past_episodes_none_heading']}\n{w['past_episodes_none_yet']}"
        if memory.past_episodes is PastEpisodes.NONE_SELECTED:
            return (
                f"{w['past_episodes_none_heading']}\n{w['past_episodes_none_selected']}"
            )
        reader = render.Reader(
            asset=asset.asset_id,
            now=memory.step,
            for_jev=True,
            wording=self.episode_wording,
        )
        blocks = [
            render.full_episode(e, w["episode_label"].format(number=n), reader)
            for n, e in enumerate(memory.newest_first, start=1)
        ]
        heading = w["past_episodes_heading"].format(count=len(blocks))
        return "\n".join([heading, "\n\n".join(blocks)])

    def _trade_text(self, trade: CandidateTrade, price: float) -> str:
        template = (
            self.wording["trade_long"]
            if trade.direction is Direction.LONG
            else self.wording["trade_short"]
        )
        return template.format(
            width=trade.width,
            price=_price(price),
            stop=_price(trade.stop_price),
            distance=_percent(trade.stop_share),
        )

    def after_opening(self, background: str) -> str:
        """The background without the opening, which is stored once per reading version."""
        return background.removeprefix(self.opening + "\n\n")

    def _account(self, account: AccountView) -> str:
        w = self.wording
        count = len(account.positions)
        if count == 0:
            positions = w["no_positions"]
        else:
            template = w["one_position"] if count == 1 else w["several_positions"]
            positions = template.format(count=count, worth=dollars(account.exposure))
        most = self.risk.exposure_limit * account.value
        return w["account"].format(
            value=dollars(account.value),
            cash=dollars(account.cash),
            loan=dollars(account.loan) if account.loan else w["no_loan"],
            positions=positions,
            most=dollars(most),
            multiple=f"{self.risk.exposure_limit:g}",
            room=dollars(max(0.0, most - account.exposure)),
        )

    def _open_positions(
        self, positions: tuple[PositionLine, ...], heading: str | None = None
    ) -> str:
        w = self.wording
        lines = [
            w["position_line"].format(
                asset=p.asset,
                asset_class=p.asset_class,
                direction=p.direction,
                worth=dollars(p.worth),
                bars=_bars(p.bars_ago),
                profit=_signed_dollars(p.profit),
                percent=_signed_percent(p.percent),
            )
            for p in positions
        ]
        body = "\n".join(lines) if lines else w["no_open_positions"]
        return f"{heading or w['open_positions_heading']}\n{body}"

    def _asset(self, asset: AssetView, held: bool = False) -> str:
        """The asset: for a position screen or review, "the asset now", after the position."""
        w = self.wording
        prices = w["last_price"].format(price=f"${asset.price:.2f}")
        if asset.typical_move is not None:
            prices += w["typical_move"].format(move=f"${asset.typical_move:.2f}")
        heading = w["asset_now_heading" if held else "asset_heading"].format(
            asset=asset.asset_id, asset_class=asset.asset_class
        )
        holding = [] if held else [w["holds_no_position"]]
        return "\n".join([heading, *holding, prices, asset.situation])

    def _position(self, asset: AssetView, position: PositionView) -> str:
        w = self.wording
        direction = str(position.direction)
        lines = [
            w["position_heading"].format(
                asset=asset.asset_id, asset_class=asset.asset_class
            ),
            w["position_opened"].format(
                direction=w["position_direction"][direction],
                put_in=dollars(position.put_in),
                bars=_bars(position.bars_ago),
                entry=_price(position.entry_price),
            ),
            w["position_stop"].format(
                stop=_price(position.stop_price),
                closes=w["stop_closes"][direction],
                distance=_percent(position.stop_share(asset.price)),
                side=w["stop_side"][direction],
            ),
            w["position_now"].format(
                worth=dollars(position.worth),
                profit=_signed_dollars(position.profit),
                percent=_signed_percent(position.percent),
                best=_signed_dollars(position.best),
                worst=_signed_dollars(position.worst),
            ),
            w["position_entry_situation"].format(situation=position.situation_at_entry),
            w["position_since"].format(
                since="; ".join(position.since) or w["position_since_nothing"]
            ),
        ]
        if position.end_of_session:
            lines.append(w["end_of_session"])
        return "\n".join(lines)

    def _position_background(
        self,
        asset: AssetView,
        account: AccountView,
        playbook: Mapping[str, tuple[str, str]],
        position: PositionView,
        memory: MemorySections | None = None,
    ) -> str:
        """A position screen's background, which is also a position review's without memory.
        With memory, the track record and the past episodes follow the asset."""
        w = self.wording
        others = tuple(p for p in account.positions if p.asset != asset.asset_id)
        named = asset.patterns + position.patterns_at_entry + _patterns_named_in(memory)
        sections = [
            self.opening,
            self._account(account),
            self._open_positions(others, w["other_positions_heading"]),
            self._position(asset, position),
            self._asset(asset, held=True),
            *self._memory(asset, memory),
            self._pattern_notes(named, playbook),
        ]
        return "\n\n".join(s for s in sections if s)

    def _pattern_notes(
        self, names: tuple[str, ...], playbook: Mapping[str, tuple[str, str]]
    ) -> str:
        once = list(dict.fromkeys(names))
        if not once:
            return ""
        notes = [
            self.wording["pattern_note"].format(
                name=name, lean=playbook[name][0], shape=playbook[name][1]
            )
            for name in once
        ]
        return "\n".join([self.wording["pattern_notes_heading"], *notes])
