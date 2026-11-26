"""The benchmark's spend meter: a running dollar total that stops the run at its cap
(`benchmark_cap_usd` in `config/spending.toml`, $1.50).

The total is a plain sum of each call's cost: after attempts costing $0.25 and $0.15, $0.40 is
spent of the $1.50 allowed. The run asks the meter before each attempt; once another attempt
could take the total past the cap, the run stops itself and the report says so.

What the next attempt could cost is not known before it runs, so the meter takes the dearest
attempt so far as its guess: at $1.40 spent, with no attempt so far over $0.10, one more is let
through (to $1.50 at most); had one cost $0.35, the run stops at $1.40. The sum is compared
rounded to a millionth of a dollar, so the small error of adding cents in a computer (fourteen
$0.10 attempts add to a hair over $1.40) never stops a run that is exactly at the cap.
"""

from jev_trader.sim.spending import load_spending_settings

# Dollars are compared rounded to this many decimals: far below a cent, far above the error of
# adding.
_DECIMALS = 6


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
        self._spent_usd = 0.0
        self._dearest_usd = (
            0.0  # the dearest attempt so far: the guess for the next one
        )

    @property
    def spent_usd(self) -> float:
        """The dollars spent so far."""
        return self._spent_usd

    def check(self) -> None:
        """Before an attempt: raises `CapReached` if it could take the total past the cap."""
        after = round(self._spent_usd + self._dearest_usd, _DECIMALS)
        if after > round(self.cap_usd, _DECIMALS):
            raise CapReached(
                f"the benchmark stopped itself at ${self._spent_usd:.2f} spent of the "
                f"${self.cap_usd:.2f} allowed: the next attempt could cost "
                f"${self._dearest_usd:.2f} (as much as the dearest so far), which would "
                f"pass ${self.cap_usd:.2f}."
            )

    def add(self, cost_usd: float) -> None:
        """After an attempt: adds what its calls cost."""
        self._spent_usd += cost_usd
        self._dearest_usd = max(self._dearest_usd, cost_usd)
