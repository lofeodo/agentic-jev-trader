"""The benchmark's spend meter: a running dollar total that stops the run at its cap
(`benchmark_cap_usd` in `config/spending.toml`, $1.50).

The total is a plain sum of each call's cost: after attempts costing $0.25 and $0.15, $0.40 is
spent of the $1.50 allowed. The run asks the meter before each attempt; once another attempt
could take the total past the cap, the run stops itself and the report says so.
"""

from jev_trader.benchmark import NotBuilt
from jev_trader.sim.spending import load_spending_settings


class CapReached(Exception):
    """The benchmark stopped itself: another attempt could pass its cap. The message says, in
    plain words, how much was spent of how much."""


def load_cap_usd() -> float:
    """The benchmark's cap in US dollars."""
    return load_spending_settings().benchmark_cap_usd


class SpendMeter:
    """The dollars spent so far in one run of the benchmark, against `cap_usd`."""

    def __init__(self, cap_usd: float):
        self.cap_usd = cap_usd

    @property
    def spent_usd(self) -> float:
        """The dollars spent so far."""
        raise NotBuilt("the spend meter's total")

    def check(self) -> None:
        """Before an attempt: raises `CapReached` if it could take the total past the cap."""
        raise NotBuilt("the spend meter's check before an attempt")

    def add(self, cost_usd: float) -> None:
        """After an attempt: adds what its calls cost."""
        raise NotBuilt("the spend meter's running total")
