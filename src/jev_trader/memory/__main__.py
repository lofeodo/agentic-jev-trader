"""Start the memory MCP server, or check the episode search's values.

    conda run -n agentic-jev-trader python -m jev_trader.memory serve
    conda run -n agentic-jev-trader python -m jev_trader.memory check-search --sim 12

`check-search` (spec appendix 9, section 7; `search_check.py`) reads a sim's memory once as the
memory login and reports whether the records the search calls most similar ended the same way
more often than random ones did. It calls no model. `--shape-share` and `--bar-decay` each take
several values to try instead of the sim's own; `--after` picks when the price is read (`1_bar`,
`4_bars`, `end_of_day`); `--sample 2000` checks only that many records, for a quicker answer.

It logs in to Snowflake as the memory login (`SNOWFLAKE_ACCOUNT` and
`SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`, the key `memory.p8` in `SNOWFLAKE_LOCAL_DIR`), whose
role can only read, and serves its three tools at `/mcp` and its health at `/health`, on the
host, port and host names in `config/memory_server.toml`. `--database TRADING_AGENT_TEST` serves
the test database. `--in-cluster` is for its pod in the kind cluster: it listens on every
address of its container, so the cluster's other pods reach it as `memory`. It logs in to
Snowflake on the first lookup, not at start. Output is plain ASCII: `conda run` on Windows fails
on other characters.
"""

import argparse
import sys
import tomllib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.broker.config import CONFIG_DIR
from jev_trader.memory.search import SearchSettings
from jev_trader.memory.search_check import AFTER, load_memory, report
from jev_trader.memory.server import build_server, http_app
from jev_trader.memory.store import UnknownSim
from jev_trader.storage import LoginNotSet, NotBuiltYet
from jev_trader.storage.database import open_database, refuse_postgres_until
from jev_trader.storage.snowflake import DATABASE, connect

REPO_ROOT = Path(__file__).resolve().parents[3]
# In its pod: every address of the container, which only the cluster can reach.
EVERY_ADDRESS = "0.0.0.0"


def load_settings(path: Path = CONFIG_DIR / "memory_server.toml") -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def serve(database: str, port: int | None, in_cluster: bool = False) -> int:
    import uvicorn

    load_dotenv(REPO_ROOT / ".env")
    try:
        opened = open_database("memory", database, on_first_use=True)
    except LoginNotSet as missing:
        print(missing)
        return 2
    settings = load_settings()
    app = http_app(build_server(opened.memory_store()), settings["allowed_hosts"])
    host = EVERY_ADDRESS if in_cluster else settings["host"]
    try:
        uvicorn.run(app, host=host, port=port or settings["port"])
    finally:
        opened.close()
    return 0


def load_from_snowflake(sim: int, after: str, database: str) -> tuple[dict, list]:
    """The sim's settings and memory, read as the memory login. LoginNotSet if it is not set."""
    load_dotenv(REPO_ROOT / ".env")
    # The search check reads Snowflake alone until then.
    refuse_postgres_until(279)
    connection = connect("memory", database=database)
    try:
        return load_memory(connection, sim, after)
    finally:
        connection.close()


def check_search(args: argparse.Namespace, read_memory: Callable) -> int:
    try:
        settings, records = read_memory(args.sim, args.after, args.database)
    except (LoginNotSet, UnknownSim, NotBuiltYet) as problem:
        print(f"Cannot read sim {args.sim}'s memory: {problem}")
        return 2
    base = SearchSettings.of_sim(settings)
    tried = [
        replace(base, shape_share=shape, bar_decay=decay)
        for shape in args.shape_share or [base.shape_share]
        for decay in args.bar_decay or [base.bar_decay]
    ]
    print(report(args.sim, records, tried, args.after, args.sample))
    return 0


def main(
    argv: list[str] | None = None, read_memory: Callable = load_from_snowflake
) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.memory")
    commands = parser.add_subparsers(dest="command", required=True)
    serving = commands.add_parser("serve", help="start the memory MCP server")
    serving.add_argument("--database", default=DATABASE)
    serving.add_argument("--port", type=int, default=None)
    serving.add_argument(
        "--in-cluster",
        action="store_true",
        help="serve the rest of the kind cluster (in its pod there)",
    )
    checking = commands.add_parser(
        "check-search",
        help="check whether the search's similar records ended alike more often than random",
    )
    checking.add_argument("--sim", type=int, required=True, help="whose memory")
    checking.add_argument("--after", choices=list(AFTER), default="4_bars")
    checking.add_argument(
        "--shape-share", type=float, nargs="+", help="shapes' share of the say, 0 to 1"
    )
    checking.add_argument(
        "--bar-decay", type=float, nargs="+", help="how much less each older bar counts"
    )
    checking.add_argument(
        "--sample", type=int, default=None, help="check only this many records"
    )
    checking.add_argument("--database", default=DATABASE)
    args = parser.parse_args(argv)
    if args.command == "check-search":
        return check_search(args, read_memory)
    return serve(args.database, args.port, args.in_cluster)


if __name__ == "__main__":
    sys.exit(main())
