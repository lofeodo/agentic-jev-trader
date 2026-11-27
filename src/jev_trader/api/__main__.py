"""Start the API, or write out its description for the web app's generated data types.

    conda run -n agentic-jev-trader python -m jev_trader.api serve
    conda run -n agentic-jev-trader python -m jev_trader.api describe web/openapi.json

`serve` logs in to Postgres as the API login (`POSTGRES_HOST` and `POSTGRES_API_PASSWORD` in
`.env`) and listens on this computer only. It starts sims' jobs as `JOB_LAUNCHER` in `.env` says (`local`,
the default: programs on this computer, each printing to `logs/sims/sim-<id>.log`), on the
database it serves, and dataset builds the same way (`logs/datasets/dataset-<id>.log`, beside
the build's settings file). `kubernetes` starts each as a Job in the kind cluster instead
(`jev_trader.jobs`). A build logs in as the builder and needs
`TWELVE_DATA_API_KEY`. `--in-cluster` is for its pod in the kind cluster: it listens on every
address of its container and answers the cluster's callers too (`jev_trader.api.app`). It logs
in on the first request that reads, not at start. `describe` needs no login.
Output is plain ASCII: `conda run` on Windows fails on other characters.
"""

import argparse
import json
import os
import sys
import tomllib
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.broker.config import CONFIG_DIR
from jev_trader.jobs import builds_named, launcher_named
from jev_trader.sim.spending import load_spending_settings
from jev_trader.sim.store import InMemorySimStore
from jev_trader.storage import LoginNotSet
from jev_trader.storage.database import DATABASE, open_database

REPO_ROOT = Path(__file__).resolve().parents[3]
JOB_LOGS = REPO_ROOT / "logs" / "sims"
# Each dataset build the API starts: its settings file, where its job runs, what it prints.
BUILD_FILES = REPO_ROOT / "logs" / "datasets"
# Where it listens: this computer only, or in its pod every address of the container.
THIS_COMPUTER = "127.0.0.1"
EVERY_ADDRESS = "0.0.0.0"


def load_settings(path: Path = CONFIG_DIR / "api.toml") -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def describe(path: Path) -> None:
    """Write the API's description. It depends on the code alone, so any store will do."""
    app = create_app(
        InMemoryApiStore(InMemorySimStore(), []),
        spending_ceiling=0.0,
        not_responding_after=timedelta(0),
        launcher=launcher_named("local", JOB_LOGS, DATABASE),
        builds=builds_named("local", BUILD_FILES, DATABASE),
    )
    text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def serve(database: str, port: int, in_cluster: bool = False) -> int:
    import uvicorn

    load_dotenv(REPO_ROOT / ".env")
    try:
        name = os.environ.get("JOB_LAUNCHER") or "local"
        launcher = launcher_named(name, JOB_LOGS, database)
        builds = builds_named(name, BUILD_FILES, database)
    except ValueError as refused:
        print(refused)
        return 2
    try:
        opened = open_database("api", database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    settings = load_settings()
    app = create_app(
        opened.api_store(),
        spending_ceiling=load_spending_settings().ceiling_usd,
        not_responding_after=timedelta(minutes=settings["not_responding_minutes"]),
        moment_window_steps=settings["moment_window_steps"],
        launcher=launcher,
        builds=builds,
        in_cluster=in_cluster,
    )
    try:
        uvicorn.run(app, host=EVERY_ADDRESS if in_cluster else THIS_COMPUTER, port=port)
    finally:
        opened.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.api")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("serve", help="start the API on this computer")
    start.add_argument("--database", default=DATABASE)
    start.add_argument("--port", type=int, default=8000)
    start.add_argument(
        "--in-cluster",
        action="store_true",
        help="serve the rest of the kind cluster (in its pod there)",
    )
    write = commands.add_parser("describe", help="write the API's description")
    write.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "describe":
        describe(args.path)
        return 0
    return serve(args.database, args.port, args.in_cluster)


if __name__ == "__main__":
    sys.exit(main())
