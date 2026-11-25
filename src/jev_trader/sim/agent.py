"""The agent without memory: the screen and the full evaluation for an asset with no position, the
position screen and the position review for an open one (spec appendix 4, sections 3 to 7).

At each step, for each asset with a bar and no position:

1. If code already knows no trade could open (the daily loss limit, a stock's last two bars, no
   typical move to set stop prices from), nothing is asked: tier 0.
2. The screen: is a full evaluation worth running? Below the cut-off (0.5), nothing more: tier 1.
3. The full evaluation (tier 2). Request 1: the pick among the six candidate trades and no
   trade, asked as five copies in orders shuffled from the sim's random seed, the step and the
   asset. Code adds the probabilities by direction first. No trade ends it here.
4. Request 2: the size, asked smallest first and largest first, and the rating. The size is the
   five sizes averaged with Jev's probabilities; the broker trims it to the limits and places the
   order, carried out at the asset's next bar's open.

For each asset with an open position:

1. At a stock's last bar of the session nothing is asked (an order decided there would only be
   carried out the next morning): tier 0, and the position is held.
2. At a stock's second-to-last bar, the end-of-session review runs with no position screen first,
   so holding a stock overnight is always decided.
3. Otherwise the position screen: is a review worth running? Below the cut-off the position is
   held: tier 1.
4. The position review (tier 2). Request 1: hold, close, reduce or add, asked as five shuffled
   copies (add left out when nothing can be added), and whether the reason for opening it still
   holds (recorded only). The likeliest action wins. Close places the order; reduce and add ask
   how much in request 2, smallest first and largest first.

Every full evaluation and every position review is stored as an episode on its decision record.
In the agent without memory the background holds no scorecard lines and no past episodes, and
says nothing about their absence.

What the agent keeps between steps, saved with the account so a resumed sim carries on the same:
for each open position, the situation it was opened in and its journal (what was done at each
of its bars). A position's bars are counted from the one it was opened in, bar 0.

Choices the spec leaves to the build (appendix 4, "Not decided by any ticket"):

- An asset with no typical move is not screened, since no candidate trade can be built for it.
- A position is looked at from the bar it was opened in (bar 0) on, like any open position.
- A stock whose second-to-last bar is missing gets no end-of-session review that day.
- The journal's reduce says what that part would have made at the last price when it was
  decided, as the reduce option said it; an add says what was placed after the limits. An add
  the limits left nothing of reads "hold", since nothing changed.

The choices about the pick and the action themselves are in `jev_trader.jev.full_evaluation`
and `jev_trader.jev.position_review`.

The agent with memory (`AgentWithMemory`, at the end) takes the same steps; before a full
evaluation's request 1 it runs memory's first search and the LLM's selection
(`jev_trader.llm.selection`), and the background gains the track record and the episodes
selected. Its choices the spec leaves to the build:

- Memory "holds none yet" when code's first search finds nothing; the LLM is then not asked.
- The track record is read for each candle pattern the situation text names now (the
  snapshot's patterns) and each direction.
"""

import copy
from collections.abc import Callable
from typing import NamedTuple

from jev_trader.broker import Bar, Broker, Direction, Position, StopPriceSettings
from jev_trader.jev.client import JevClient, JevReply
from jev_trader.jev.full_evaluation import (
    NO_TRADE,
    Evaluation,
    average_copies,
    candidate_trades,
    read_pick,
    shuffled_orders,
)
from jev_trader.jev.position_review import (
    ADD,
    CLOSE,
    HOLD,
    REDUCE,
    REDUCE_SHARES,
    Review,
    read_action,
    reduce_option_name,
    reduce_share,
)
from jev_trader.jev.reading import (
    AccountView,
    AssetView,
    JevRequest,
    MemorySections,
    PastEpisodes,
    PositionLine,
    PositionView,
    Reading,
    size_option_name,
)
from jev_trader.llm.selection import MemoryLookups, Selection, Selector
from jev_trader.memory.bridge import LookupContext
from jev_trader.memory.outcomes import Outcomes, is_last_bar_of_day
from jev_trader.memory.search import DIRECTIONS
from jev_trader.risk import RiskLimit
from jev_trader.sim import records
from jev_trader.sim.market import Market, Snapshot
from jev_trader.sim.store import (
    ACTION_ADD,
    ACTION_CLOSE,
    ACTION_ENTRY,
    ACTION_NOTHING,
    ACTION_REDUCE,
)

_STEPS_LOADED_AT_ONCE = 96  # a day
NO_TYPICAL_MOVE = "no_typical_move"


class _Told(NamedTuple):
    """How much of the broker's history the episodes waiting for outcomes have been told."""

    fills: int = 0
    cancelled_orders: int = 0
    closed_trades: int = 0


class AgentWithoutMemory:
    def __init__(
        self,
        sim_id: int,
        dataset: int,
        last_step: int,
        market: Market,
        jev: JevClient,
        reading: Reading,
        stop_settings: StopPriceSettings,
        random_seed: int,
    ):
        self.sim_id = sim_id
        self.dataset = dataset
        self.last_step = last_step
        self.market = market
        self.jev = jev
        self.reading = reading
        self.stop_settings = stop_settings
        self.random_seed = random_seed
        self.playbook = market.playbook(dataset)
        self._snapshots: dict[int, dict[str, Snapshot]] = {}
        self._loaded_through = -1
        self._bar_steps: dict[str, list[int]] | None = None  # for "opened N bars ago"
        # The situation an entry was decided in, by asset, until its position opens.
        self._entries: dict[str, dict] = {}
        # Each open position's situation at entry and its journal, by position ID (as text).
        self._positions: dict[str, dict] = {}
        # The episodes waiting for their outcomes, and how much of the broker's history
        # (fills, cancelled orders, closed trades) they have been told about.
        self.outcomes = Outcomes(sim_id)
        self._told = _Told()

    def on_step(
        self, step: int, broker: Broker, bars: dict[str, Bar]
    ) -> dict[str, list[dict]]:
        """Look at each asset once. Returns the rows this step stores, by table."""
        rows: dict[str, list[dict]] = {
            "MEMORY.DECISIONS": [],
            "MEMORY.OUTCOMES": [],
            "SIM.JEV_REQUESTS": [],
            "SIM.CALLS": [],
        }
        self._note_bars(step, broker, bars)
        open_ids = {str(p.position_id) for p in broker.positions.values()}
        self._positions = {k: v for k, v in self._positions.items() if k in open_ids}
        if not bars:
            return rows
        snapshots = self._snapshots_at(step)
        for asset in sorted(bars):
            looked_at = (
                _PositionAtStep if asset in broker.positions else self._decision_at_step
            )
            looked_at(
                self, step, broker, asset, bars[asset], snapshots[asset], rows
            ).run()
        return rows

    @property
    def _decision_at_step(self) -> type["_DecisionAtStep"]:
        """How an asset with no position is looked at."""
        return _DecisionAtStep

    def after_step(
        self, step: int, broker: Broker, bars: dict[str, Bar]
    ) -> tuple[list[dict], dict[str, int]]:
        """Once the step's orders are carried out (the sim's end closes included): the episodes'
        outcomes it taught, and the decisions it made complete, each with its step."""
        told = self._told
        self._told = _Told(
            len(broker.fills), len(broker.cancelled_orders), len(broker.closed_trades)
        )
        snapshots = self._snapshots_at(step) if bars else {}
        return self.outcomes.on_step(
            step,
            {asset: bar.close for asset, bar in bars.items()},
            {
                asset
                for asset in bars
                if asset in snapshots
                and is_last_bar_of_day(step, snapshots[asset].bars_left)
            },
            broker.fills[told.fills :],
            broker.cancelled_orders[told.cancelled_orders :],
            broker.closed_trades[told.closed_trades :],
        )

    # What the agent keeps between steps

    def state(self) -> dict:
        """What a resumed sim needs to carry on as if it had never stopped, as plain data: a
        copy, so later steps do not change what was saved."""
        return copy.deepcopy(
            {
                "entries": self._entries,
                "positions": self._positions,
                "outcomes": self.outcomes.state(),
            }
        )

    def restore(self, state: dict | None) -> None:
        if state:
            self._entries = copy.deepcopy(state["entries"])
            self._positions = copy.deepcopy(state["positions"])
            self.outcomes = Outcomes(self.sim_id, state.get("outcomes"))

    def entry_decided(self, asset: str, snapshot: Snapshot) -> None:
        self._entries[asset] = {
            "situation": snapshot.situation_text,
            "patterns": list(snapshot.patterns),
        }

    def position_record(self, position: Position) -> dict:
        """The position's situation at entry and journal, begun when it is first looked at."""
        key = str(position.position_id)
        if key not in self._positions:
            self._positions[key] = {**self._entries.pop(position.asset), "journal": []}
        return self._positions[key]

    def _snapshots_at(self, step: int) -> dict[str, Snapshot]:
        if step > self._loaded_through:
            self._loaded_through = min(step + _STEPS_LOADED_AT_ONCE - 1, self.last_step)
            self._snapshots = self.market.snapshots(
                self.dataset, step, self._loaded_through
            )
        return self._snapshots.get(step, {})

    def _note_bars(self, step: int, broker: Broker, bars: dict[str, Bar]) -> None:
        """Remember each asset's bar steps. A resumed sim first fetches its open positions' bars."""
        if self._bar_steps is None:
            self._bar_steps = {}
            opened = [p.step_opened for p in broker.positions.values()]
            if opened and min(opened) < step:
                earlier = self.market.bars(self.dataset, min(opened), step - 1)
                for bar_step in sorted(earlier):
                    for asset in earlier[bar_step]:
                        self._bar_steps.setdefault(asset, []).append(bar_step)
        for asset in bars:
            self._bar_steps.setdefault(asset, []).append(step)

    def bars_since(self, asset: str, step_opened: int) -> int:
        return sum(1 for s in self._bar_steps.get(asset, []) if s > step_opened)

    # What Jev is shown

    def account_view(self, broker: Broker) -> AccountView:
        lines = []
        shorts = 0.0
        for asset, position in sorted(broker.positions.items()):
            worth = position.units * broker.last_prices[asset]
            put_in = position.units * position.average_price
            profit = broker.profit_if_closed(asset)
            if position.direction is Direction.SHORT:
                shorts += worth
            lines.append(
                PositionLine(
                    asset=asset,
                    asset_class=str(broker.asset_classes[asset]),
                    direction=str(position.direction),
                    worth=worth,
                    bars_ago=self.bars_since(asset, position.step_opened),
                    profit=profit,
                    percent=100 * profit / put_in if put_in else 0.0,
                )
            )
        return AccountView(
            value=broker.account_value(),
            cash=broker.cash,
            loan=broker.loan(),
            exposure=broker.exposure(),
            positions=tuple(lines),
            shorts=shorts,
        )


class _AssetAtStep:
    """One asset looked at, at one step: what is asked of Jev and stored for it."""

    def __init__(
        self,
        agent: AgentWithoutMemory,
        step: int,
        broker: Broker,
        asset: str,
        bar: Bar,
        snapshot: Snapshot,
        rows: dict[str, list[dict]],
    ):
        self.agent, self.step, self.broker, self.asset = agent, step, broker, asset
        self.snapshot, self.rows = snapshot, rows
        self.reading = agent.reading
        self.view = AssetView(
            asset_id=asset,
            asset_class=str(broker.asset_classes[asset]),
            price=bar.close,
            typical_move=snapshot.typical_move,
            situation=snapshot.situation_text,
            patterns=snapshot.patterns,
        )

    def _ask(self, request: JevRequest, purpose: str) -> JevReply:
        sim_id = self.agent.sim_id
        reply = self.agent.jev.ask(request)
        self.rows["SIM.JEV_REQUESTS"].append(
            records.jev_request_row(
                sim_id, self.step, self.asset, self.reading, request, reply, purpose
            )
        )
        self.rows["SIM.CALLS"].append(
            records.jev_call_row(sim_id, self.step, self.asset, reply, purpose)
        )
        return reply

    def _store(self, decision: dict) -> None:
        """Store the decision; an episode starts waiting for its outcomes."""
        self.rows["MEMORY.DECISIONS"].append(decision)
        self.rows["MEMORY.OUTCOMES"] += self.agent.outcomes.watch(
            decision,
            self.view.price,
            is_last_bar_of_day(self.step, self.snapshot.bars_left),
        )

    def _shuffled(self, names: list[str]) -> list[list[str]]:
        return shuffled_orders(names, self.agent.random_seed, self.step, self.asset)

    def _placed(self, order_id: int) -> tuple[float, str | None]:
        """An entry or add just placed: what the limits left of it, and the limit that trimmed it.

        Nothing left means the broker cancelled it; it then says which limit did.
        """
        waiting = {o.order_id: o for o in self.broker.waiting_orders}
        if order_id in waiting:
            order = waiting[order_id]
            return order.amount, order.limited_by and str(order.limited_by)
        return 0.0, str(self.broker.blocked_orders[order_id])

    def _chosen_size(self, reply: JevReply, question: str, account: AccountView):
        """The size Jev chose, from the two mirrored copies of `question`, and its answers."""
        risk = self.reading.risk
        names = [size_option_name(share) for share in risk.size_buckets]
        copies = {
            f"{question}_{order}": reply.choice(f"{question}_{order}", names)
            for order in ("small_first", "large_first")
        }
        averaged = average_copies(list(copies.values()))
        size = risk.chosen_size([averaged[name] for name in names], account.value)
        return size, copies


class _DecisionAtStep(_AssetAtStep):
    """An asset with no position: the screen, then the full evaluation."""

    # The full evaluation's memory sections, and how the LLM chose its past episodes: both
    # None without memory.
    memory: MemorySections | None = None
    selection: Selection | None = None

    def _recall(self) -> MemorySections | None:
        """What memory adds to the full evaluation's background: nothing, without memory."""
        return None

    def run(self) -> None:
        blocked_by = self.broker.entry_blocked_by(self.asset, self.snapshot.bars_left)
        if blocked_by is None and not (self.snapshot.typical_move or 0) > 0:
            blocked_by = NO_TYPICAL_MOVE
        if blocked_by is not None:
            self._store_decision(str(blocked_by))
            return
        account = self.agent.account_view(self.broker)
        playbook = self.agent.playbook
        screen = self._ask(
            self.reading.screen_request(self.view, account, playbook), "screen"
        )
        if screen.noul("screen") < self.reading.risk.screen_cut_off:
            self._store_decision(None, screen)
            return
        evaluation = self._pick(account)
        action = ACTION_NOTHING
        if evaluation.pick != NO_TRADE:
            action = self._size_and_order(account, evaluation)
        self._store_decision(None, screen, evaluation, action)

    def _pick(self, account: AccountView) -> Evaluation:
        self.memory = self._recall()
        trades = candidate_trades(
            self.view.price, self.snapshot.typical_move, self.agent.stop_settings
        )
        names = [t.name for t in trades] + [NO_TRADE]
        request = self.reading.pick_request(
            self.view,
            account,
            self.agent.playbook,
            trades,
            self._shuffled(names),
            self.memory,
        )
        reply = self._ask(request, "pick")
        answers = {q: reply.choice(q, names) for q in request.questions}
        pick = read_pick(average_copies(list(answers.values())), trades)
        return Evaluation(candidates=trades, answers=answers, pick=pick)

    def _size_and_order(self, account: AccountView, evaluation: Evaluation) -> str:
        """Ask the size, place the order, and say what was done: an entry, or nothing."""
        trade = next(t for t in evaluation.candidates if t.name == evaluation.pick)
        request = self.reading.size_request(
            self.view, account, self.agent.playbook, trade, self.memory
        )
        reply = self._ask(request, "size")
        evaluation.size_chosen, copies = self._chosen_size(reply, "size", account)
        score, levels = reply.score("rating")
        evaluation.answers.update(
            copies, rating={"score": score, "probabilities": levels}
        )
        evaluation.rating = score
        order_id = self.broker.enter(
            self.asset,
            trade.direction,
            evaluation.size_chosen,
            trade.stop_price,
            self.step,
            self.snapshot.bars_left,
        )
        evaluation.size_after_trimming, evaluation.limited_by = self._placed(order_id)
        if evaluation.size_after_trimming > 0:
            self.agent.entry_decided(self.asset, self.snapshot)
            return ACTION_ENTRY
        return ACTION_NOTHING

    def _store_decision(
        self,
        skipped_because: str | None,
        screen: JevReply | None = None,
        evaluation: Evaluation | None = None,
        action: str = ACTION_NOTHING,
    ) -> None:
        row = records.decision_row(
            self.agent.sim_id,
            self.agent.dataset,
            self.step,
            self.asset,
            skipped_because,
            screen,
            evaluation,
            action,
        )
        self._store({**row, **records.selection_columns(self.selection)})


class _PositionAtStep(_AssetAtStep):
    """An open position: the position screen, then the position review."""

    def run(self) -> None:
        self.position = self.broker.positions[self.asset]
        self.record = self.agent.position_record(self.position)
        self.bar_number = self.agent.bars_since(self.asset, self.position.step_opened)
        bars_left = self.snapshot.bars_left
        if bars_left == 0:  # a stock's last bar: only code acts on it
            self._store_decision(str(RiskLimit.SESSION_END))
            return
        end_of_session = bars_left == 1
        account = self.agent.account_view(self.broker)
        position = self._position_view(end_of_session)
        screen = None
        if not end_of_session:
            screen = self._ask(
                self.reading.position_screen_request(
                    self.view, account, self.agent.playbook, position
                ),
                "position_screen",
            )
            if screen.noul("position_screen") < self.reading.risk.screen_cut_off:
                self._store_decision(None, screen)
                return
        review, action = self._review(account, position)
        self._store_decision(None, screen, review, action)

    def _position_view(self, end_of_session: bool) -> PositionView:
        p, broker = self.position, self.broker
        put_in = p.units * p.average_price
        profit = broker.profit_if_closed(self.asset)
        return PositionView(
            direction=p.direction,
            put_in=put_in,
            bars_ago=self.bar_number,
            entry_price=p.entry_price,
            stop_price=p.stop_price,
            worth=p.units * broker.last_prices[self.asset],
            profit=profit,
            percent=100 * profit / put_in,
            best=profit if p.best is None else p.best,
            worst=profit if p.worst is None else p.worst,
            situation_at_entry=self.record["situation"],
            patterns_at_entry=tuple(self.record["patterns"]),
            since=self.reading.since(self.record["journal"]),
            end_of_session=end_of_session,
        )

    def _review(
        self, account: AccountView, position: PositionView
    ) -> tuple[Review, str]:
        """Ask the action, then how much if it is a reduce or an add, and place the order."""
        playbook = self.agent.playbook
        add_allowed = (
            self.broker.add_blocked_by(self.asset, self.snapshot.bars_left) is None
        )
        names = list(
            self.reading.action_options(self.view, account, position, add_allowed)
        )
        request = self.reading.action_request(
            self.view, account, playbook, position, self._shuffled(names), add_allowed
        )
        reply = self._ask(request, "action")
        copies = [q for q in request.questions if q.startswith("action_")]
        answers = {q: reply.choice(q, names) for q in copies}
        thesis_intact = reply.noul("thesis_intact")
        review = Review(
            standing=position.standing(self.view.price),
            end_of_session=position.end_of_session,
            answers={**answers, "thesis_intact": thesis_intact},
            action=read_action(average_copies(list(answers.values()))),
            thesis_intact=thesis_intact,
        )
        if review.action == CLOSE:
            self.broker.close(self.asset, self.step)
            return review, ACTION_CLOSE
        if review.action == REDUCE:
            return review, self._reduce(account, position, review)
        if review.action == ADD:
            return review, self._add(account, position, review)
        return review, ACTION_NOTHING

    def _reduce(self, account: AccountView, position: PositionView, review: Review):
        request = self.reading.reduce_request(
            self.view, account, self.agent.playbook, position
        )
        reply = self._ask(request, "reduce")
        names = [reduce_option_name(share) for share in REDUCE_SHARES]
        copies = {q: reply.choice(q, names) for q in request.questions}
        review.answers.update(copies)
        review.reduce_share = reduce_share(average_copies(list(copies.values())))
        self.broker.reduce(
            self.asset, review.reduce_share * self.position.units, self.step
        )
        self._journal(
            REDUCE,
            share=review.reduce_share,
            profit=review.reduce_share * position.profit,
        )
        return ACTION_REDUCE

    def _add(self, account: AccountView, position: PositionView, review: Review):
        request = self.reading.add_request(
            self.view, account, self.agent.playbook, position
        )
        reply = self._ask(request, "add")
        review.size_chosen, copies = self._chosen_size(reply, "add", account)
        review.answers.update(copies)
        order_id = self.broker.add(
            self.asset, review.size_chosen, self.step, self.snapshot.bars_left
        )
        review.size_after_trimming, review.limited_by = self._placed(order_id)
        if review.size_after_trimming > 0:
            self._journal(ADD, amount=review.size_after_trimming)
            return ACTION_ADD
        return ACTION_NOTHING

    def _journal(self, action: str, **details) -> None:
        self.record["journal"].append(
            {"bar": self.bar_number, "action": action, **details}
        )

    def _store_decision(
        self,
        skipped_because: str | None,
        screen: JevReply | None = None,
        review: Review | None = None,
        action: str = ACTION_NOTHING,
    ) -> None:
        if action == ACTION_NOTHING:
            self._journal(HOLD)
        self._store(
            records.position_decision_row(
                self.agent.sim_id,
                self.agent.dataset,
                self.step,
                self.asset,
                self.position.position_id,
                skipped_because,
                screen,
                review,
                action,
            )
        )


# The agent with memory


class AgentWithMemory(AgentWithoutMemory):
    """The agent with memory (spec appendix 5): the same steps, but before a full evaluation's
    request 1 the LLM selects which past episodes Jev reads, and the background gains the track
    record and those episodes. An open position is looked at as without memory.

    `lookups_at` gives memory's lookups for one moment; `selector` is the LLM's selection step.
    """

    def __init__(
        self,
        *args,
        lookups_at: Callable[[LookupContext], MemoryLookups],
        selector: Selector,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.lookups_at = lookups_at
        self.selector = selector

    @property
    def _decision_at_step(self) -> type[_DecisionAtStep]:
        return _DecisionWithMemory


class _DecisionWithMemory(_DecisionAtStep):
    """An asset with no position, in the agent with memory."""

    agent: AgentWithMemory

    def _recall(self) -> MemorySections:
        """Code's first search, then the LLM's selection, and the track record for each candle
        pattern showing now and each direction. Memory holding nothing yet asks no LLM."""
        lookups = self.agent.lookups_at(
            LookupContext(self.agent.sim_id, self.step, self.asset)
        )
        track_records = tuple(
            lookups.track_record(pattern, direction)
            for pattern in self.snapshot.patterns
            for direction in DIRECTIONS
        )
        first_search = lookups.search()
        if not first_search.episodes:
            return MemorySections(track_records, PastEpisodes.NONE_YET)
        self.selection = self.agent.selector.select(lookups, first_search)
        self.rows["SIM.CALLS"] += [
            records.llm_call_row(self.agent.sim_id, self.step, self.asset, call, n)
            for n, call in enumerate(self.selection.calls, start=1)
        ]
        if not self.selection.episode_ids:
            return MemorySections(track_records, PastEpisodes.NONE_SELECTED)
        chosen = lookups.read(list(self.selection.episode_ids)).episodes
        return MemorySections(track_records, PastEpisodes.SELECTED, tuple(chosen))
