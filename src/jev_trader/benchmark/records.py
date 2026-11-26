"""Where each benchmark attempt is kept (spec appendix 9, section 8): no new table.

- Each call to a model goes in `SIM.CALLS` with the purpose "benchmark" and no sim, so the
  project's spending total includes it.
- Each attempt's result and its word-for-word exchange go to a file on this computer, in a folder
  git ignores (`DETAIL_DIR`).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from jev_trader.benchmark import NotBuilt

if TYPE_CHECKING:
    from jev_trader.benchmark.runner import Attempt

PURPOSE = "benchmark"
DETAIL_DIR = Path(__file__).resolve().parents[3] / "logs" / "benchmark"


class AttemptLog(Protocol):
    def keep(self, attempt: "Attempt") -> None:
        """Write the attempt's calls to `SIM.CALLS` and its detail to a file."""
        ...


def call_rows(attempt: "Attempt") -> list[dict]:
    """The attempt's rows in `SIM.CALLS`: one per call, the purpose "benchmark", no sim."""
    raise NotBuilt("the benchmark's rows in SIM.CALLS")


class SnowflakeAttemptLog:
    """Keeps attempts in Snowflake, through `connection` (as the sim login), and in files under
    `detail_dir`."""

    def __init__(self, connection, detail_dir: Path = DETAIL_DIR):
        self.connection, self.detail_dir = connection, detail_dir

    def keep(self, attempt: "Attempt") -> None:
        raise NotBuilt("keeping a benchmark attempt (SIM.CALLS and its detail file)")
