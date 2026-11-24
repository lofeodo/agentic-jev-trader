"""Start the memory MCP server.

    conda run -n agentic-jev-trader python -m jev_trader.memory serve

It logs in to Snowflake as the memory login (`SNOWFLAKE_ACCOUNT` and
`SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`, the key `memory.p8` in `SNOWFLAKE_LOCAL_DIR`), whose
role can only read, and serves its three tools at `/mcp` and its health at `/health`, on the
host, port and host names in `config/memory_server.toml`. `--database TRADING_AGENT_TEST` serves
the test database. Output is plain ASCII: `conda run` on Windows fails on other characters.
"""

import argparse
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.broker.config import CONFIG_DIR
from jev_trader.memory.server import build_server, http_app
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_settings(path: Path = CONFIG_DIR / "memory_server.toml") -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


def serve(database: str, port: int | None) -> int:
    import uvicorn

    from jev_trader.memory.snowflake_store import SnowflakeMemoryStore

    load_dotenv(REPO_ROOT / ".env")
    try:
        connection = connect("memory", database=database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    settings = load_settings()
    app = http_app(
        build_server(SnowflakeMemoryStore(connection)), settings["allowed_hosts"]
    )
    uvicorn.run(app, host=settings["host"], port=port or settings["port"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.memory")
    commands = parser.add_subparsers(dest="command", required=True)
    serving = commands.add_parser("serve", help="start the memory MCP server")
    serving.add_argument("--database", default=DATABASE)
    serving.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    return serve(args.database, args.port)


if __name__ == "__main__":
    sys.exit(main())
