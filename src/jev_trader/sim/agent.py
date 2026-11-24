"""The agent without memory, part one: the screen (spec appendix 4, sections 3.1 and 4).

At each step, for each asset with a bar and no position, either code already knows no trade could
open (the daily loss limit, a stock's last two bars) and nothing is asked, or Jev is asked whether
a full evaluation is worth running. The number is stored whatever it is. The full evaluation
itself comes with the next ticket, so for now no decision places an order.
"""

from jev_trader.broker import Bar, Broker
from jev_trader.jev.client import JevClient
from jev_trader.jev.reading import AccountView, AssetView, Reading
from jev_trader.sim import records
from jev_trader.sim.market import Market, Snapshot

_STEPS_LOADED_AT_ONCE = 96  # a day


class ScreeningAgent:
    def __init__(
        self,
        sim_id: int,
        dataset: int,
        last_step: int,
        market: Market,
        jev: JevClient,
        reading: Reading,
    ):
        self.sim_id = sim_id
        self.dataset = dataset
        self.last_step = last_step
        self.market = market
        self.jev = jev
        self.reading = reading
        self._playbook = market.playbook(dataset)
        self._snapshots: dict[int, dict[str, Snapshot]] = {}
        self._loaded_through = -1

    def on_step(
        self, step: int, broker: Broker, bars: dict[str, Bar]
    ) -> dict[str, list[dict]]:
        """Look at each asset once. Returns the rows this step stores, by table."""
        if broker.positions:
            raise RuntimeError("open positions are not handled yet: see ticket #99")
        rows: dict[str, list[dict]] = {
            "MEMORY.DECISIONS": [],
            "SIM.JEV_REQUESTS": [],
            "SIM.CALLS": [],
        }
        if not bars:
            return rows
        snapshots = self._snapshots_at(step)
        for asset in sorted(bars):
            snapshot = snapshots[asset]
            blocked_by = broker.entry_blocked_by(asset, snapshot.bars_left)
            if blocked_by is not None:
                rows["MEMORY.DECISIONS"].append(
                    records.decision_row(
                        self.sim_id, self.dataset, step, asset, str(blocked_by)
                    )
                )
                continue
            request = self.reading.screen_request(
                self._asset_view(asset, broker, bars[asset], snapshot),
                self._account_view(broker),
                self._playbook,
            )
            reply = self.jev.ask(request)
            rows["MEMORY.DECISIONS"].append(
                records.decision_row(
                    self.sim_id, self.dataset, step, asset, None, reply
                )
            )
            rows["SIM.JEV_REQUESTS"].append(
                records.jev_request_row(
                    self.sim_id, step, asset, self.reading, request, reply
                )
            )
            rows["SIM.CALLS"].append(
                records.jev_call_row(self.sim_id, step, asset, reply)
            )
        return rows

    def _snapshots_at(self, step: int) -> dict[str, Snapshot]:
        if step > self._loaded_through:
            self._loaded_through = min(step + _STEPS_LOADED_AT_ONCE - 1, self.last_step)
            self._snapshots = self.market.snapshots(
                self.dataset, step, self._loaded_through
            )
        return self._snapshots.get(step, {})

    @staticmethod
    def _asset_view(
        asset: str, broker: Broker, bar: Bar, snapshot: Snapshot
    ) -> AssetView:
        return AssetView(
            asset_id=asset,
            asset_class=str(broker.asset_classes[asset]),
            price=bar.close,
            typical_move=snapshot.typical_move,
            situation=snapshot.situation_text,
            patterns=snapshot.patterns,
        )

    @staticmethod
    def _account_view(broker: Broker) -> AccountView:
        return AccountView(
            value=broker.account_value(),
            cash=broker.cash,
            loan=broker.loan(),
            exposure=broker.exposure(),
        )
