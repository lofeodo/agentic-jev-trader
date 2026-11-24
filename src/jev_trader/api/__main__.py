"""Start the API, or write out its description for the web app's generated data types.

    conda run -n agentic-jev-trader python -m jev_trader.api serve
    conda run -n agentic-jev-trader python -m jev_trader.api describe web/openapi.json

`serve` logs in to Snowflake as the API login (`SNOWFLAKE_ACCOUNT` and
`SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`, the key `api.p8` in `SNOWFLAKE_LOCAL_DIR`) and
listens on this computer only. It starts sims' jobs as `JOB_LAUNCHER` in `.env` says (`local`,
the default: programs on this computer, each printing to `logs/sims/sim-<id>.log`), on the
database it serves. `describe` needs no login. Output is plain ASCII: `conda run` on
Windows fails on other characters.
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
from jev_trader.jobs import launcher_named
from jev_trader.sim.spending import load_spending_settings
from jev_trader.sim.store import InMemorySimStore
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]
JOB_LOGS = REPO_ROOT / "logs" / "sims"


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
    )
    text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def serve(database: str, port: int) -> int:
    import uvicorn

    from jev_trader.api.snowflake_store import SnowflakeApiStore

    load_dotenv(REPO_ROOT / ".env")
    try:
        launcher = launcher_named(
            os.environ.get("JOB_LAUNCHER") or "local", JOB_LOGS, database
        )
    except ValueError as refused:
        print(refused)
        return 2
    try:
        connection = connect("api", database=database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    settings = load_settings()
    app = create_app(
        SnowflakeApiStore(connection),
        spending_ceiling=load_spending_settings().ceiling_usd,
        not_responding_after=timedelta(minutes=settings["not_responding_minutes"]),
        moment_window_steps=settings["moment_window_steps"],
        launcher=launcher,
    )
    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    finally:
        connection.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.api")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("serve", help="start the API on this computer")
    start.add_argument("--database", default=DATABASE)
    start.add_argument("--port", type=int, default=8000)
    write = commands.add_parser("describe", help="write the API's description")
    write.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "describe":
        describe(args.path)
        return 0
    return serve(args.database, args.port)


if __name__ == "__main__":
    sys.exit(main())
