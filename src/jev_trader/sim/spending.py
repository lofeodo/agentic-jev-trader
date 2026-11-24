"""What a sim may spend in real money: its cost estimate and its spending cap (spec appendix 8,
sections 8.3 and 8.5; appendix 9, section 13).

The estimate counts the sim's checks (one screen per asset with a bar at each of its steps), and
the closer looks some of them lead to, at the share the latest practice sim measured (15% until
one exists). Each check is one Jev request; a full evaluation adds two more, and in a sim with
memory one LLM call. The cap is one and a half times the estimate; a practice sim's is 25 cents
unless the developer raises it. The holding sim calls nothing paid: no estimate, no cap.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@dataclass(frozen=True)
class SpendingSettings:
    ceiling_usd: float
    most_sims_in_progress: int
    cap_times_estimate: float
    practice_cap_usd: float
    default_closer_look_share: float
    jev_tokens_per_request: int
    jev_requests_per_full_evaluation: int
    llm_dollars_per_closer_look: float


def load_spending_settings(
    path: Path = CONFIG_DIR / "spending.toml",
) -> SpendingSettings:
    with open(path, "rb") as file:
        return SpendingSettings(**tomllib.load(file))


def estimate_cost(
    variant: str,
    checks: int,
    closer_look_share: float,
    jev_dollars_per_million_tokens: float,
    settings: SpendingSettings,
) -> float:
    """The dollars a sim is expected to spend over `checks` checks."""
    if variant == "buy_hold":
        return 0.0
    jev_request = settings.jev_tokens_per_request * jev_dollars_per_million_tokens / 1e6
    closer_look = settings.jev_requests_per_full_evaluation * jev_request
    if variant == "memory_on":
        closer_look += settings.llm_dollars_per_closer_look
    return checks * (jev_request + closer_look_share * closer_look)


def spending_cap(
    variant: str,
    kind: str,
    estimate: float,
    given: float | None,
    settings: SpendingSettings,
) -> float | None:
    """The sim's cap: the one given by the developer for a practice sim, else 25 cents for a
    practice sim and one and a half times the estimate for the others, up to the next cent."""
    if variant == "buy_hold":
        return None
    if kind == "practice":
        return given if given is not None else settings.practice_cap_usd
    return math.ceil(round(estimate * settings.cap_times_estimate * 100, 6)) / 100
