"""What Jev reads: the background and the questions, written by code (spec appendix 4, section 8).

The words live in `prompts/jev_reading.toml`. The same data always gives the same text: nothing
here reads a clock, a random number, a step number or a sim number.

The **reading version** is a fingerprint worked out from the wording, the opening as this sim's
settings fill it in, and the layout of a request, so a changed word, setting or section order
gives a new version and nobody has to bump a number.

Choices the spec leaves to the build:

- An asset with no typical move (its price did not move for 14 bars) has that sentence left out,
  as the situation text leaves out a number that is not available.
- Room to hold more never reads below $0, and a negative amount reads "-$5".
"""

import hashlib
import json
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from jev_trader.broker import TradingCosts
from jev_trader.risk import RiskProfile

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


def _bars(n: int) -> str:
    return f"{n} bar" if n == 1 else f"{n} bars"


def load_wording(path: Path = WORDING_PATH) -> dict[str, str]:
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


class Reading:
    """The text of one sim's requests to Jev, given the settings it runs with."""

    def __init__(
        self,
        costs: TradingCosts,
        risk: RiskProfile,
        wording: Mapping[str, str] | None = None,
    ):
        self.risk = risk
        self.wording = dict(load_wording() if wording is None else wording)
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
        sample = self.screen_request(_LAYOUT_ASSET, _LAYOUT_ACCOUNT, _LAYOUT_PLAYBOOK)
        fingerprinted = json.dumps(
            {
                "wording": self.wording,
                "opening": self.opening,
                "layout": [sample.background, sample.questions],
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
        sections = [
            self.opening,
            self._account(account),
            self._open_positions(account.positions),
            self._asset(asset),
            self._pattern_notes(asset.patterns, playbook),
        ]
        question = self.wording["screen_question"].format(asset=asset.asset_id)
        return JevRequest(
            background="\n\n".join(s for s in sections if s),
            questions={"screen": {"type": "noul", "instructions": question}},
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

    def _open_positions(self, positions: tuple[PositionLine, ...]) -> str:
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
        return f"{w['open_positions_heading']}\n{body}"

    def _asset(self, asset: AssetView) -> str:
        w = self.wording
        prices = w["last_price"].format(price=f"${asset.price:.2f}")
        if asset.typical_move is not None:
            prices += w["typical_move"].format(move=f"${asset.typical_move:.2f}")
        heading = w["asset_heading"].format(
            asset=asset.asset_id, asset_class=asset.asset_class
        )
        return "\n".join(
            [heading, w["holds_no_position"], prices, asset.situation],
        )

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
