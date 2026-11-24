"""The agent without memory: the screen, then the full evaluation (spec appendix 4, sections 3.1,
4, 5 and 6).

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

Every full evaluation is stored as an episode on its decision record, the ones ending in no
trade included. In the agent without memory the background holds no scorecard lines and no past
episodes, and says nothing about their absence.

An open position is left to code (its stop price, a forced close, the sim's last step) until the
position screen and review arrive (ticket #100): its asset gets no decision record meanwhile.

Choice the spec leaves to the build (appendix 4, "Not decided by any ticket"): an asset with no
typical move is not screened, since no candidate trade can be built for it. The choices about the
pick itself are in `jev_trader.jev.full_evaluation`.
"""

from jev_trader.broker import Bar, Broker, Direction, StopPriceSettings
from jev_trader.jev.client import JevClient, JevReply
from jev_trader.jev.full_evaluation import (
    NO_TRADE,
    Evaluation,
    average_copies,
    candidate_trades,
    read_pick,
    shuffled_orders,
)
from jev_trader.jev.reading import (
    AccountView,
    AssetView,
    JevRequest,
    PositionLine,
    Reading,
    size_option_name,
)
from jev_trader.sim import records
from jev_trader.sim.market import Market, Snapshot
from jev_trader.sim.store import ACTION_ENTRY, ACTION_NOTHING

_STEPS_LOADED_AT_ONCE = 96  # a day
NO_TYPICAL_MOVE = "no_typical_move"


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

    def on_step(
        self, step: int, broker: Broker, bars: dict[str, Bar]
    ) -> dict[str, list[dict]]:
        """Look at each asset once. Returns the rows this step stores, by table."""
        rows: dict[str, list[dict]] = {
            "MEMORY.DECISIONS": [],
            "SIM.JEV_REQUESTS": [],
            "SIM.CALLS": [],
        }
        self._note_bars(step, broker, bars)
        if not bars:
            return rows
        snapshots = self._snapshots_at(step)
        for asset in sorted(bars):
            if asset in broker.positions:
                continue  # left to code until ticket #100
            _DecisionAtStep(
                self, step, broker, asset, bars[asset], snapshots[asset], rows
            ).run()
        return rows

    # What the agent keeps between steps

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


class _DecisionAtStep:
    """One asset looked at, at one step: what is asked, decided and stored for it."""

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
        trades = candidate_trades(
            self.view.price, self.snapshot.typical_move, self.agent.stop_settings
        )
        names = [t.name for t in trades] + [NO_TRADE]
        orders = shuffled_orders(names, self.agent.random_seed, self.step, self.asset)
        request = self.reading.pick_request(
            self.view, account, self.agent.playbook, trades, orders
        )
        reply = self._ask(request, "pick")
        answers = {q: reply.choice(q, names) for q in request.questions}
        pick = read_pick(average_copies(list(answers.values())), trades)
        return Evaluation(candidates=trades, answers=answers, pick=pick)

    def _size_and_order(self, account: AccountView, evaluation: Evaluation) -> str:
        """Ask the size, place the order, and say what was done: an entry, or nothing."""
        risk = self.reading.risk
        trade = next(t for t in evaluation.candidates if t.name == evaluation.pick)
        request = self.reading.size_request(
            self.view, account, self.agent.playbook, trade
        )
        reply = self._ask(request, "size")
        names = [size_option_name(share) for share in risk.size_buckets]
        copies = [
            reply.choice(q, names) for q in ("size_small_first", "size_large_first")
        ]
        score, levels = reply.score("rating")
        evaluation.answers.update(
            size_small_first=copies[0],
            size_large_first=copies[1],
            rating={"score": score, "probabilities": levels},
        )
        evaluation.rating = score
        averaged = average_copies(copies)
        evaluation.size_chosen = risk.chosen_size(
            [averaged[name] for name in names], account.value
        )
        order_id = self.broker.enter(
            self.asset,
            trade.direction,
            evaluation.size_chosen,
            trade.stop_price,
            self.step,
            self.snapshot.bars_left,
        )
        waiting = {o.order_id: o for o in self.broker.waiting_orders}
        if order_id in waiting:
            order = waiting[order_id]
            evaluation.size_after_trimming = order.amount
            evaluation.limited_by = order.limited_by and str(order.limited_by)
            return ACTION_ENTRY
        # The limits left nothing of it: the broker cancelled it and says which limit.
        evaluation.size_after_trimming = 0.0
        evaluation.limited_by = str(self.broker.blocked_orders[order_id])
        return ACTION_NOTHING

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

    def _store_decision(
        self,
        skipped_because: str | None,
        screen: JevReply | None = None,
        evaluation: Evaluation | None = None,
        action: str = ACTION_NOTHING,
    ) -> None:
        self.rows["MEMORY.DECISIONS"].append(
            records.decision_row(
                self.agent.sim_id,
                self.agent.dataset,
                self.step,
                self.asset,
                skipped_because,
                screen,
                evaluation,
                action,
            )
        )
