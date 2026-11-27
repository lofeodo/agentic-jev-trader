"""A copy of the Postgres database in one file, with Postgres's own `pg_dump`, and loading it back
with `pg_restore` (spec appendix 11, section 2).

`pg_dump --format=custom` writes every table, its rows, the ID numberings, the logins' grants and
Alembic's record of the applied files into one compressed file. `pg_restore` loads it into any
Postgres 17 that has the five logins, the database and pgvector but no tables yet: the local one
in Docker (its `init.sql` makes them) or a new RDS (Terraform does). pgvector itself is left out
of the file: only an administrator may add it, and those two already have.

Neither tool comes with Windows, so both run from the image the local Postgres runs
(`infra/local-postgres/compose.yaml`), with Docker: the same Postgres version as RDS and the
local one, nothing to install. The file passes through the container's output and input, so no
folder of this computer is shared with it. A database on this computer (`127.0.0.1`) is reached
from inside the container as `host.docker.internal`. The password goes to the container as an
environment variable, never on the command line.

Both log in as the setup login, which owns every table and may read and make them all.
"""

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "infra" / "local-postgres" / "compose.yaml"
THIS_COMPUTER = ("127.0.0.1", "localhost", "::1")


def image() -> str:
    """The Postgres image the local Postgres runs, read from its compose file."""
    found = re.search(
        r"^\s*image:\s*(\S+)", COMPOSE.read_text(encoding="utf-8"), re.MULTILINE
    )
    if not found:
        raise RuntimeError(f"No image named in {COMPOSE}")
    return found.group(1)


def _docker(tool: str, settings: dict, args: list[str], interactive: bool) -> list[str]:
    host = settings["host"]
    if host in THIS_COMPUTER:
        host = "host.docker.internal"
    return [
        "docker",
        "run",
        "--rm",
        *(["--interactive"] if interactive else []),
        "--env",
        "PGPASSWORD",
        "--env",
        "PGSSLMODE",
        image(),
        tool,
        "--host",
        host,
        "--port",
        str(settings["port"]),
        "--username",
        settings["user"],
        "--dbname",
        settings["dbname"],
        *args,
    ]


def _env(settings: dict) -> dict:
    return {
        **os.environ,
        "PGPASSWORD": settings["password"],
        "PGSSLMODE": settings["sslmode"],
    }


def dump(settings: dict, file: Path) -> None:
    """Write the database `settings` reach (the setup login's, `postgres.settings`) to `file`.
    A failed dump leaves no file."""
    command = _docker(
        "pg_dump", settings, ["--format=custom", "--exclude-extension=vector"], False
    )
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file, "wb") as out:
            done = subprocess.run(command, check=False, stdout=out, env=_env(settings))
        if done.returncode != 0:
            raise RuntimeError(
                f"pg_dump failed (exit code {done.returncode}); see above."
            )
    except BaseException:
        file.unlink(missing_ok=True)
        raise


def restore(settings: dict, file: Path) -> None:
    """Load `file` into the empty database `settings` reach, all of it or, on any error, none."""
    command = _docker(
        "pg_restore", settings, ["--exit-on-error", "--single-transaction"], True
    )
    with open(file, "rb") as source:
        done = subprocess.run(command, check=False, stdin=source, env=_env(settings))
    if done.returncode != 0:
        raise RuntimeError(
            f"pg_restore failed (exit code {done.returncode}); see above. "
            "Nothing was loaded."
        )
