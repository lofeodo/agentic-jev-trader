"""Start the memory MCP server.

    conda run -n agentic-jev-trader python -m jev_trader.memory serve

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
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.broker.config import CONFIG_DIR
from jev_trader.memory.server import build_server, http_app
from jev_trader.storage.snowflake import DATABASE, ConnectionOnFirstUse, LoginNotSet

REPO_ROOT = Path(__file__).resolve().parents[3]
# In its pod: every address of the container, which only the cluster can reach.
EVERY_ADDRESS = "0.0.0.0"


def load_settings(path: Path = CONFIG_DIR / "memory_server.toml") -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def serve(database: str, port: int | None, in_cluster: bool = False) -> int:
    import uvicorn

    from jev_trader.memory.snowflake_store import SnowflakeMemoryStore

    load_dotenv(REPO_ROOT / ".env")
    try:
        connection = ConnectionOnFirstUse("memory", database=database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    settings = load_settings()
    app = http_app(
        build_server(SnowflakeMemoryStore(connection)), settings["allowed_hosts"]
    )
    host = EVERY_ADDRESS if in_cluster else settings["host"]
    try:
        uvicorn.run(app, host=host, port=port or settings["port"])
    finally:
        connection.close()
    return 0


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)
    return serve(args.database, args.port, args.in_cluster)


if __name__ == "__main__":
    sys.exit(main())
