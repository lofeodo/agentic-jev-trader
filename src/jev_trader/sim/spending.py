"""What a sim may spend in real money: its cost estimate and its spending cap (spec appendix 8,
sections 8.3 and 8.5; appendix 9, section 13).

The estimate counts the sim's checks and the Tier 2 work (a full evaluation or a position
review) some of them lead to, at the share the latest practice sim measured, or the default
share in `config/spending.toml` until one exists. Each check is one Jev request; a full
evaluation adds the pick and the size, and in a sim with memory one LLM call. The cap is the
estimate times the setting `cap_times_estimate`; a practice sim's is the setting
`practice_cap_usd` unless the developer raises it. The holding sim calls nothing paid: no
estimate, no cap. Every number is in `config/spending.toml`.

Choices the spec leaves to the build:

- A check is one screen per asset with a bar at each of the sim's steps. A stock's last bars of
  a session and an asset already held are not screened, so the estimate runs a little high.
- A Jev request is priced at a fixed number of tokens read (about the size of one background);
  Jev's price per million tokens is the one in `config/jev.toml`.
- The cap is rounded up to the next cent, so it is never below one and a half times the estimate.
- The LLM's price for Tier 2 is one figure (Claude Haiku's). A price per model comes with the
  agent with memory.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jev_trader.broker.config import CONFIG_DIR


@dataclass(frozen=True)
class SpendingSettings:
    ceiling_usd: float
    most_sims_in_progress: int
    cap_times_estimate: float
    practice_cap_usd: float
    default_tier_2_share: float
    jev_tokens_per_request: int
    jev_requests_per_full_evaluation: int
    llm_dollars_per_tier_2: float
    benchmark_cap_usd: float


def load_spending_settings(
    path: Path = CONFIG_DIR / "spending.toml",
) -> SpendingSettings:
    with open(path, "rb") as file:
        return SpendingSettings(**tomllib.load(file))


def estimate_cost(
    variant: str,
    checks: int,
    tier_2_share: float,
    jev_dollars_per_million_tokens: float,
    settings: SpendingSettings,
) -> float:
    """The dollars a sim is expected to spend over `checks` checks."""
    if variant == "buy_hold":
        return 0.0
    jev_request = settings.jev_tokens_per_request * jev_dollars_per_million_tokens / 1e6
    tier_2 = settings.jev_requests_per_full_evaluation * jev_request
    if variant == "memory_on":
        tier_2 += settings.llm_dollars_per_tier_2
    return checks * (jev_request + tier_2_share * tier_2)


def spending_cap(
    variant: str,
    kind: str,
    estimate: float,
    given: float | None,
    settings: SpendingSettings,
) -> float | None:
    """The sim's cap: for a practice sim the one the developer gave, else the usual practice
    cap; for the others the estimate times `cap_times_estimate`, up to the next cent."""
    if variant == "buy_hold":
        return None
    if kind == "practice":
        return given if given is not None else settings.practice_cap_usd
    return math.ceil(round(estimate * settings.cap_times_estimate * 100, 6)) / 100
