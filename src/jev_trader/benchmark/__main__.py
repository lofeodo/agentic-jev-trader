"""Run the LLM benchmark from the command line; the web app never starts it.

    conda run -n agentic-jev-trader python -m jev_trader.benchmark --sim 12
    conda run -n agentic-jev-trader python -m jev_trader.benchmark --sim 12 --model glm-5.3-flash

Hands each model the 50 moments the build-up sim `--sim` saved, three times each, with nothing
traded, and writes the plain-words report to `--report` (by default `docs/llm-benchmark.md`, to
commit). `--model` runs that one model alone, for re-running a changed model on the same moments
(about 20 cents); without it both models in `config/llm.toml` run. It stops itself at
`benchmark_cap_usd` in `config/spending.toml` ($1.50).

It calls the LLMs, which costs money: run it only with the developer's go-ahead. Their keys are
read from `.env`. It reads memory through the memory server, which must be running on the same
database first, in its own terminal (`python -m jev_trader.memory serve`), and logs in to
Snowflake as the sim login to write its calls to `SIM.CALLS` (the purpose "benchmark", no sim).
`--database TRADING_AGENT_TEST` uses the test database. Output is plain ASCII: `conda run` on
Windows fails on other characters.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.benchmark import NotBuilt
from jev_trader.benchmark.moments import SavedMoment, saved_moments
from jev_trader.benchmark.records import AttemptLog, SnowflakeAttemptLog
from jev_trader.benchmark.report import REPORT_PATH, report
from jev_trader.benchmark.runner import ModelRunner, SelectionRunner, run_benchmark
from jev_trader.benchmark.spending import SpendMeter, load_cap_usd
from jev_trader.llm.models import load_model_settings
from jev_trader.llm.settings import LlmSettings
from jev_trader.memory.bridge import Connection, local_url
from jev_trader.storage.snowflake import DATABASE, connect

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Parts:
    """What one run needs from outside: the saved moments, the runner and where attempts are
    kept. Tests hand in made-up ones."""

    moments: Sequence[SavedMoment]
    runner: ModelRunner
    log: AttemptLog


def open_parts(args: argparse.Namespace, held: ExitStack) -> Parts:
    """The real parts: the build-up sim's moments, the memory server's lookups, and Snowflake,
    each connection kept open in `held` for the whole run."""
    load_dotenv(REPO_ROOT / ".env")
    moments = saved_moments(args.sim, args.database)
    patterns = list(moments[0].situation.playbook) if moments else []
    memory = held.enter_context(Connection(local_url(), patterns))
    snowflake = connect("sim", database=args.database)
    held.callback(snowflake.close)
    return Parts(
        moments, SelectionRunner(memory.lookups_at), SnowflakeAttemptLog(snowflake)
    )


def parser(models: Sequence[str]) -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="python -m jev_trader.benchmark",
        description="Hand the LLMs the build-up sim's saved moments and report how they did.",
    )
    command.add_argument(
        "--sim", type=int, required=True, help="the build-up sim whose moments are used"
    )
    command.add_argument(
        "--model", choices=models, help="run this model alone (default: every model)"
    )
    command.add_argument("--database", default=DATABASE)
    command.add_argument("--report", type=Path, default=REPORT_PATH)
    return command


def main(
    argv: list[str] | None = None,
    parts_for: Callable[[argparse.Namespace, ExitStack], Parts] = open_parts,
) -> int:
    settings = load_model_settings()
    args = parser(settings.models).parse_args(argv)
    names = [args.model] if args.model else list(settings.models)
    models = [LlmSettings(model=settings.setting(name)) for name in names]
    try:
        with ExitStack() as held:
            parts = parts_for(args, held)
            run = run_benchmark(
                parts.moments,
                models,
                parts.runner,
                SpendMeter(load_cap_usd()),
                parts.log,
            )
        page = report(run)
    except NotBuilt as missing:
        print(f"The benchmark cannot run: {missing}.")
        return 2
    args.report.write_text(page, encoding="utf-8")
    if run.stopped:
        print(f"Stopped early: {run.stopped}")
    print(f"{len(run.attempts)} attempts. Report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
