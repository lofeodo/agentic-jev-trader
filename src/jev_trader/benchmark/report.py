"""The benchmark's one-page report, in plain words, made from the attempts' figures (never from
model text) and committed to the repo (spec appendix 9, section 8).

What decides: a model is left out of the measurement sims when more than 10 in 100 of its
attempts went wrong (both jobs counted together); if both are, work stops and the developer
decides. What it shows, deciding nothing: selection overlap per job (the episodes two selections
share divided by the episodes in either: A, B, C against B, C, D is 2 of 4, or 50%), the cost,
and each model's habits (seconds, lookups, replies that were not a tool call, IDs never shown).
"""

from pathlib import Path

from jev_trader.benchmark import NotBuilt
from jev_trader.benchmark.runner import BenchmarkRun

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "llm-benchmark.md"


def report(run: BenchmarkRun) -> str:
    """The report page for every attempt of `run`, and its early stop if it had one."""
    raise NotBuilt("the benchmark's plain-words report")
