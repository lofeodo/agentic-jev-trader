"""Build a dataset from its settings file, with no API running (spec appendix 2, section 10).

    conda run -n agentic-jev-trader python -m jev_trader.dataset build datasets/first.toml

Options: `--no-check` publishes even if an asset is over a limit, marking the dataset
"published without the check"; `--database TRADING_AGENT_TEST` builds into the test database.
Needs `TWELVE_DATA_API_KEY` and the Snowflake settings in `.env`. Output is plain ASCII:
`conda run` on Windows fails on other characters.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.dataset.build import BuildStopped, build_dataset
from jev_trader.dataset.providers import BinanceFiles, TwelveData
from jev_trader.dataset.settings import load_settings
from jev_trader.dataset.snowflake_store import SnowflakeStore
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.dataset")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build and publish a dataset")
    build.add_argument(
        "settings", type=Path, help="the dataset's settings file, in datasets/"
    )
    build.add_argument(
        "--no-check",
        action="store_true",
        help='publish even if an asset is over a limit; marked "published without the check"',
    )
    build.add_argument("--database", default=DATABASE)
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")
    api_key = (os.environ.get("TWELVE_DATA_API_KEY") or "").strip()
    if not api_key:
        print("TWELVE_DATA_API_KEY is not set. Add it to .env (see .env.example).")
        return 2
    try:
        connection = connect("builder", database=args.database)
    except LoginNotSet as missing:
        print(missing)
        return 2

    try:
        result = build_dataset(
            load_settings(args.settings),
            stocks=TwelveData(api_key),
            crypto=BinanceFiles(),
            store=SnowflakeStore(connection),
            today=datetime.now(UTC).date(),
            check=not args.no_check,
            report=lambda line: print(line, flush=True),
        )
    except BuildStopped as stop:
        print(f"Build stopped: {stop}")
        return 2
    finally:
        connection.close()
    return 0 if result.published else 1


if __name__ == "__main__":
    sys.exit(main())
