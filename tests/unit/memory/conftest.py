"""A made-up memory, served by the real memory server over an in-memory connection.

The store is `InMemoryMemoryStore`; the snapshots' situation texts are written by the real
`situation_text`, and their embeddings are made up (a few numbers, not 768). The server runs as
its web app, reached through `httpx2.ASGITransport`: nothing leaves the process.
"""

from contextlib import asynccontextmanager
from datetime import date

import anyio
import httpx2
import pytest

from jev_trader.dataset.measurements import MEASUREMENT_NAMES, AssetClass, Measurements
from jev_trader.dataset.situation_text import PatternLists, situation_text
from jev_trader.memory.bridge import MemoryBridge, Moment, connect
from jev_trader.memory.server import build_server, http_app
from jev_trader.memory.store import InMemoryMemoryStore
from jev_trader.sim.records import decision_id

SIM = 7
DATASET = 3
HOST = "memory"
PATTERNS = ("bullish engulfing", "doji", "hammer", "spinning top")


def vector(*leading: float) -> list[float]:
    """A feature vector: the leading numbers given, the rest 0 (average)."""
    return [*leading, *[0.0] * (58 - len(leading))]


class MadeUpMemory:
    def __init__(self, sim: int = SIM, dataset: int = DATASET):
        self.sim, self.dataset = sim, dataset
        self.store = InMemoryMemoryStore()
        self.store.sims[sim] = {"DATASET": dataset, "SETTINGS": {}}

    def snapshot(
        self,
        asset: str,
        step: int,
        features=None,
        embedding=(1.0, 0.0, 0.0),
        window=(),
        asset_class="crypto",
        long_term_trend=1.0,
        volume=1.5,
    ):
        """A snapshot; `window` is (pattern, bars ago) pairs, also stored as FEATURES.PATTERNS."""
        readings = {
            "long_term_trend": long_term_trend,
            "volume_against_normal": volume,
            **{f"bar_{k}_direction": 1 for k in range(8)},
            "bar_0_body": 0.6,
            "bar_0_upper_wick": 0.2,
            "bar_0_lower_wick": 0.2,
            "bar_0_range": 1.0,
        }
        values = tuple(readings.get(n) for n in MEASUREMENT_NAMES)
        klass = AssetClass(asset_class)
        bars_in_day = 96 if klass is AssetClass.CRYPTO else 26
        bar_number = (step - 1) % bars_in_day + 1
        measured = Measurements(
            klass, date(2024, 1, 2), bar_number, bars_in_day, values
        )
        self.store.snapshots[(self.dataset, asset, step)] = {
            "ASSET_CLASS": asset_class,
            "MEASUREMENTS": list(values),
            "FEATURE_VECTOR": features or vector(),
            "EMBEDDING": list(embedding),
            "SITUATION_TEXT": situation_text(measured, PatternLists(window, [], [])),
        }
        for name, ago in window:
            self.store.patterns.append(
                {
                    "DATASET": self.dataset,
                    "ASSET": asset,
                    "BAR_SIZE": "15m",
                    "STEP": step - ago,
                    "PATTERN": name,
                }
            )

    def _decision(self, asset, step, kind, action, complete_at, **columns):
        row = {
            "ID": decision_id(self.sim, step, asset),
            "SIM": self.sim,
            "FIRST_WRITTEN_BY": self.sim,
            "DATASET": self.dataset,
            "ASSET": asset,
            "STEP": step,
            "KIND": kind,
            "TIER": 2 if kind in ("full_evaluation", "position_review") else 1,
            "ACTION": action,
            "OUTCOMES_KNOWN_FROM": complete_at,
            **columns,
        }
        self.store.decisions_table.append(row)
        return row["ID"]

    def outcome(self, decision, kind, value, known_from):
        self.store.outcomes_table.append(
            {
                "ID": f"{decision}-{kind}",
                "SIM": self.sim,
                "FIRST_WRITTEN_BY": self.sim,
                "DECISION": decision,
                "KIND": kind,
                "VALUE": value,
                "KNOWN_FROM": known_from,
            }
        )

    def prices(self, decision, step, changes=(0.001, 0.004, 0.01)):
        for kind, after, change in zip(
            ("price_after_1_bar", "price_after_4_bars", "price_at_end_of_day"),
            (1, 4, 6),
            changes,
        ):
            self.outcome(
                decision,
                kind,
                {"price": 100 * (1 + change), "change": change},
                step + after,
            )

    def no_trade(self, asset, step, **snapshot):
        self.snapshot(asset, step, **snapshot)
        decision = self._decision(
            asset, step, "full_evaluation", "nothing", step + 6, PICK="no_trade"
        )
        self.prices(decision, step)
        return decision

    def trade(
        self,
        asset,
        step,
        position,
        direction="long",
        closed_after=3,
        profit=12.0,
        closing_reason="jev",
        **snapshot,
    ):
        """A full evaluation that opened a $1,000 trade, held it, then closed it."""
        self.snapshot(asset, step, **snapshot)
        closed_step = step + 1 + closed_after
        pick = f"{direction}_tight_stop"
        decision = self._decision(
            asset,
            step,
            "full_evaluation",
            "entry",
            closed_step,
            PICK=pick,
            CANDIDATE_TRADES=[
                {
                    "name": pick,
                    "direction": direction,
                    "stop_price": 99.4,
                    "stop_share": 0.006,
                }
            ],
        )
        self.outcome(
            decision,
            "order_carried_out",
            {
                "carried_out": True,
                "price": 100.0,
                "value": 1000.0,
                "position": position,
            },
            step + 1,
        )
        for bar in range(closed_after):
            closing = closing_reason == "jev" and bar == closed_after - 1
            self._decision(
                asset,
                step + 1 + bar,
                "position_screen",
                "close" if closing else "nothing",
                None,
                POSITION=position,
            )
        self.outcome(
            decision,
            "position_closed",
            {
                "closing_reason": closing_reason,
                "step_closed": closed_step,
                "bars_after": closed_after + 1,
                "profit": profit,
                "trading_costs": 2.0,
                "amount_entered": 1000.0,
                "best": max(profit, 20.0),
                "worst": min(profit, -5.0),
            },
            closed_step,
        )
        return decision

    def review(
        self,
        asset,
        step,
        position,
        direction="long",
        action="nothing",
        profit=8.0,
        complete_at=None,
        **snapshot,
    ):
        """A review of an open position at its bar 2, closed 5 bars later."""
        self.snapshot(asset, step, **snapshot)
        standing = {
            "direction": direction,
            "put_in": 1000.0,
            "bars_open": 2,
            "profit": profit,
            "percent": profit / 10,
            "stop_distance": 0.005,
            "best": 10.0,
            "worst": -3.0,
        }
        decision = self._decision(
            asset,
            step,
            "position_review",
            action,
            complete_at or step + 6,
            POSITION=position,
            STANDING=standing,
            END_OF_SESSION=False,
        )
        self.prices(decision, step)
        self.outcome(
            decision,
            "position_closed",
            {
                "closing_reason": "stop_price",
                "step_closed": step + 5,
                "bars_after": 5,
                "profit": -4.0,
                "trading_costs": 2.0,
                "amount_entered": 1000.0,
                "best": 10.0,
                "worst": -6.0,
                "closed_at_this_review": False,
            },
            step + 5,
        )
        return decision


@pytest.fixture
def memory():
    return MadeUpMemory()


@asynccontextmanager
async def served(store, allowed_hosts=(f"{HOST}:*", HOST)):
    """The real memory server over `store`, and an HTTP client that reaches it in memory."""
    server = build_server(store)
    app = http_app(server, list(allowed_hosts))
    async with (
        server.session_manager.run(),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=f"http://{HOST}"
        ) as http,
    ):
        yield http


@asynccontextmanager
async def bridge_to(store, moment: Moment):
    async with (
        served(store) as http,
        connect(f"http://{HOST}", http_client=http) as session,
    ):
        yield MemoryBridge(session, moment, PATTERNS)


def run(async_fn):
    """Run one async test body."""
    return anyio.run(async_fn)
