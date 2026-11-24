"""Save every table as Parquet files on this machine, before the Snowflake trial ends.

    conda run -n agentic-jev-trader python -m jev_trader.storage save

Writes `saved-tables/TRADING_AGENT-<date>-<time>/` in the repo (git ignores the folder): one
folder per table, and `manifest.json` with each table's rows, files and column types.
`--database TRADING_AGENT_TEST` saves the test database, `--folder` puts the save elsewhere.

Logs in as the API login, the only program login that reads every table, `KEYS` included
(`SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`, the key `api.p8` in
`SNOWFLAKE_LOCAL_DIR`). It cannot read `METADATA`, schemachange's record of applied SQL files,
which applying the files to a new account writes again. It works only while the account is
active. Output is plain ASCII: `conda run` on Windows fails on other characters.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.storage.save import NOT_SAVED, SnowflakeTables, save_tables
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]
SAVED_TABLES = REPO_ROOT / "saved-tables"


def save(database: str, folder: Path) -> int:
    load_dotenv(REPO_ROOT / ".env")
    try:
        connection = connect("api", database=database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    try:
        out = save_tables(
            SnowflakeTables(connection, database),
            folder,
            datetime.now(UTC),
            report=lambda line: print(line, flush=True),
        )
    finally:
        connection.close()
    print(f"Not saved: {NOT_SAVED}")
    print(f"Saved to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.storage")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("save", help="save every table as Parquet files")
    run.add_argument("--database", default=DATABASE)
    run.add_argument("--folder", type=Path, default=SAVED_TABLES)
    args = parser.parse_args(argv)
    return save(args.database, args.folder)


if __name__ == "__main__":
    sys.exit(main())
