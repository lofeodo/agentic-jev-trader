"""Where each benchmark attempt is kept (spec appendix 9, section 8): no new table.

- Each call to a model goes in `SIM.CALLS` with the purpose "benchmark" and no sim, so the
  project's spending total includes it.
- Each attempt's result and its word-for-word exchange go to a file on this computer, in a folder
  git ignores (`DETAIL_DIR`): one folder per run, one file per attempt.

A run is named by the time it started (`run_name`), so a re-run of one model never meets the
rows or files of an earlier run.
"""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from jev_trader.benchmark.attempts import Attempt
from jev_trader.sim.records import llm_call_row

PURPOSE = "benchmark"
DETAIL_DIR = Path(__file__).resolve().parents[3] / "logs" / "benchmark"


def run_name() -> str:
    """The name of a run starting now: "20261126T101500Z"."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def attempt_name(attempt: Attempt) -> str:
    """The same for one model's attempt at one moment in one pass:
    "claude-haiku-5-5-pass-1-12-4410-ASSET_03-full_evaluation"."""
    model = attempt.model.partition(":")[2]
    return f"{model}-pass-{attempt.pass_number}-{attempt.moment.id}"


def call_rows(attempt: Attempt, run: str) -> list[dict]:
    """The attempt's rows in `SIM.CALLS`: one per call, the purpose "benchmark", no sim. STEP,
    ASSET and DECISION name the build-up sim's moment the attempt was made at."""
    moment = attempt.moment
    return [
        {
            **llm_call_row(moment.sim, moment.now, moment.asset, call, number),
            "ID": f"{PURPOSE}-{run}-{attempt_name(attempt)}-{number}",
            "SIM": None,
            "PURPOSE": PURPOSE,
        }
        for number, call in enumerate(attempt.calls, start=1)
    ]


def detail_file(attempt: Attempt) -> dict:
    """Everything kept about the attempt in its file: the moment, the result, each call, and the
    exchange word for word (the whole selection when the model answered; otherwise why it did
    not, its failed replies and the exchange up to the failure)."""
    moment = attempt.moment
    kept = {
        "moment": moment.id,
        "sim": moment.sim,
        "step": moment.now,
        "asset": moment.asset,
        "job": str(moment.job),
        "model": attempt.model,
        "pass": attempt.pass_number,
        "outcome": str(attempt.outcome),
        "episode_ids": list(attempt.episode_ids),
        "cost_usd": attempt.cost_usd,
        "calls": [asdict(call) for call in attempt.calls],
    }
    if attempt.selection is not None:
        kept["selection"] = asdict(attempt.selection)
    if attempt.failure is not None:
        kept["failure"] = {
            "error": str(attempt.failure),
            "failed_replies": list(attempt.failure.failed_replies),
            "exchange": list(attempt.failure.exchange),
        }
    return kept


class DatabaseAttemptLog:
    """Keeps attempts in the database, through `connection` (`postgres.OneConnection`, as the
    sim login), and in files under
    `detail_dir`, in a folder of their own for the run `run` (by default named now)."""

    def __init__(
        self, connection, detail_dir: Path = DETAIL_DIR, run: str | None = None
    ):
        self.connection = connection
        self.run = run or run_name()
        self.detail_dir = detail_dir / self.run

    def keep(self, attempt: Attempt) -> None:
        self.detail_dir.mkdir(parents=True, exist_ok=True)
        path = self.detail_dir / f"{attempt_name(attempt)}.json"
        path.write_text(
            json.dumps(detail_file(attempt), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        rows = call_rows(attempt, self.run)
        if not rows:
            return
        columns = list(rows[0])
        with self.connection.cursor() as cur:
            cur.executemany(
                f"INSERT INTO SIM.CALLS ({', '.join(columns)}) "
                f"VALUES ({', '.join('%s' for _ in columns)})",
                [[row[c] for c in columns] for row in rows],
            )


class NoAttemptLog:
    """Keeps nothing: for a run on made-up moments, which writes no table and no file."""

    def keep(self, attempt: Attempt) -> None:
        pass
