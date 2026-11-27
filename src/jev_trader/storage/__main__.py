"""Copies of the database on this computer, and the move of a Snowflake save into Postgres.

    conda run -n agentic-jev-trader python -m jev_trader.storage save
    conda run -n agentic-jev-trader python -m jev_trader.storage load saved-tables/<save>
    conda run -n agentic-jev-trader python -m jev_trader.storage restore saved-tables/<file>.dump

`save` copies the database `.env` points to (`POSTGRES_HOST`) into `saved-tables/` in the repo
(git ignores the folder); `--database TRADING_AGENT_TEST` saves the test database, `--folder`
puts the copy elsewhere. It is Postgres's own `pg_dump`: one file,
`<database>-<date>-<time>.dump`, that `restore` (Postgres's `pg_restore`) loads into any
Postgres with the logins, the database and pgvector but no tables, a new RDS included
(`storage/dump.py`). It logs in as the setup login.

`load` puts a Snowflake save (the Parquet files and `manifest.json` that `storage save` wrote
while the tables were on Snowflake) into the empty Postgres tables, after checking that the
text-to-numbers model on this computer gives Snowflake's numbers, then compares the loaded rows
with the save (`storage/load.py`); `--check-only` compares without loading. It logs in as the
setup login, on the database `.env` points to (`POSTGRES_HOST`).

Output is plain ASCII: `conda run` on Windows fails on other characters.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.storage import LoginNotSet, postgres

REPO_ROOT = Path(__file__).resolve().parents[3]
SAVED_TABLES = REPO_ROOT / "saved-tables"


def say(line: str) -> None:
    print(line, flush=True)


def save(database: str, folder: Path) -> int:
    from jev_trader.storage import dump

    settings = postgres.settings("setup", database)
    file = Path(folder) / f"{settings['dbname']}-{datetime.now(UTC):%Y%m%d-%H%M%S}.dump"
    say(f"Saving {settings['dbname']} on {settings['host']} with pg_dump...")
    dump.dump(settings, file)
    say(f"Saved to {file} ({file.stat().st_size / 1e6:.1f} MB)")
    return 0


def restore(database: str, file: Path) -> int:
    from jev_trader.storage import dump

    settings = postgres.settings("setup", database)
    say(f"Restoring {file} into {settings['dbname']} on {settings['host']}...")
    dump.restore(settings, file)
    say("Restored.")
    return 0


def load(database: str, folder: Path, check_only: bool) -> int:
    import psycopg

    from jev_trader.storage import load as loading

    settings = postgres.settings("setup", database)
    where = f"{settings['dbname']} on {settings['host']}"
    with psycopg.connect(**settings, autocommit=True) as connection:
        if not check_only:
            from jev_trader.dataset import text_to_numbers

            tables = loading.read_manifest(folder)
            try:
                loading.check_ready(connection, tables)
            except loading.LoadRefused as refused:
                say(str(refused))
                return 1
            episodes = loading.model_check_episodes(folder, tables)
            if not episodes:
                say("The save holds no snapshots, so no saved numbers to check.")
            else:
                say(f"Text-to-numbers check on {len(episodes)} saved episodes...")
            similarities = loading.model_check(episodes, text_to_numbers.embed)
            if similarities:
                say("Similarities: " + ", ".join(f"{s:.6f}" for s in similarities))
            if any(s < loading.LEAST_SIMILARITY for s in similarities):
                say(
                    "The local model's numbers differ from Snowflake's (below "
                    f"{loading.LEAST_SIMILARITY}): nothing loaded. Stop and ask the developer."
                )
                return 1
            say(f"Loading {folder} into {where}...")
            loading.load_save(connection, folder, report=say)
        say(f"Comparing {where} with {folder}...")
        problems = loading.check_load(connection, folder, report=say)
    for problem in problems:
        say(f"Differs: {problem}")
    say(
        "Everything matches the save."
        if not problems
        else f"{len(problems)} differences."
    )
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.storage")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "save", help="save a copy of every table on this computer"
    )
    run.add_argument("--database", default=postgres.DATABASE.upper())
    run.add_argument("--folder", type=Path, default=SAVED_TABLES)
    move = commands.add_parser("load", help="load a Snowflake save into Postgres")
    move.add_argument("save", type=Path, help="the save's folder, with manifest.json")
    move.add_argument("--database", default=postgres.DATABASE.upper())
    move.add_argument("--check-only", action="store_true")
    back = commands.add_parser(
        "restore", help="load a pg_dump file into an empty Postgres"
    )
    back.add_argument("file", type=Path)
    back.add_argument("--database", default=postgres.DATABASE.upper())
    args = parser.parse_args(argv)
    load_dotenv(REPO_ROOT / ".env")
    try:
        if args.command == "save":
            return save(args.database, args.folder)
        if args.command == "load":
            return load(args.database, args.save, args.check_only)
        return restore(args.database, args.file)
    except LoginNotSet as missing:
        say(str(missing))
        return 2


if __name__ == "__main__":
    sys.exit(main())
