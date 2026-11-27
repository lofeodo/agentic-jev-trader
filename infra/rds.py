"""Set up, switch on and off, park and restore the Postgres database on AWS RDS (spec appendix 11,
sections 1 and 7). infra/README.md, section "Postgres on AWS RDS", explains each command.

Run from the repo root (each one but `status` and `plan` costs money or changes the AWS account):

    conda run -n agentic-jev-trader python infra/rds.py status
    conda run -n agentic-jev-trader python infra/rds.py plan
    conda run -n agentic-jev-trader python infra/rds.py apply -auto-approve
    conda run -n agentic-jev-trader python infra/rds.py start
    conda run -n agentic-jev-trader python infra/rds.py stop
    conda run -n agentic-jev-trader python infra/rds.py snapshot-and-delete
    conda run -n agentic-jev-trader python infra/rds.py restore

`plan` and `apply` run Terraform's two RDS roots in turn: `infra/terraform/rds` (the database, its
network rule, the budget alarm) and `infra/terraform/rds/postgres` (the five logins, the two
databases, pgvector). The passwords go to Terraform as `TF_VAR_*` environment variables from
`.env`, never on a command line or in a file, and Terraform sends them write-only, so its state
never holds them. The state is kept outside the repo, in `~/.agentic-jev-trader/rds`.

AWS is reached with the AWS CLI's login on this computer (the `default` profile; when it has run
out, `aws sso login` renews it). Output is plain ASCII: `conda run` on Windows fails on other
characters.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AWS_DIR = REPO_ROOT / "infra" / "terraform" / "rds"
POSTGRES_DIR = AWS_DIR / "postgres"
STATE_DIR = Path.home() / ".agentic-jev-trader" / "rds"

# These must match infra/terraform/rds/main.tf and jev_trader.storage.postgres.LOGINS.
REGION = "ca-central-1"
IDENTIFIER = "trading-agent"
PARKED_PREFIX = f"{IDENTIFIER}-parked-"
LOGINS = ("builder", "sim", "memory", "api", "setup")
# Shown to `plan` before the database exists: the logins' part is planned, not run.
NOT_MADE_YET = "not-made-yet.invalid"


class SetupError(Exception):
    """A setting is missing or the database is not in the state a command needs."""


def read_env() -> dict[str, str]:
    """`.env`'s values, with a variable set in the shell winning over its line in `.env`."""
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v is not None}
    env.update(os.environ)
    return env


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise SetupError(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def aws_secrets(env: Mapping[str, str]) -> dict[str, str]:
    """What the AWS root reads from `.env`, as `TF_VAR_*` variables."""
    return {
        "TF_VAR_admin_password": _required(env, "POSTGRES_ADMIN_PASSWORD"),
        "TF_VAR_budget_email": _required(env, "AWS_BUDGET_EMAIL"),
    }


def postgres_secrets(env: Mapping[str, str]) -> dict[str, str]:
    """What the logins' root reads from `.env`, as `TF_VAR_*` variables."""
    passwords = {
        login: _required(env, f"POSTGRES_{login.upper()}_PASSWORD") for login in LOGINS
    }
    return {
        "TF_VAR_admin_password": _required(env, "POSTGRES_ADMIN_PASSWORD"),
        "TF_VAR_passwords": json.dumps(passwords),
    }


# --- AWS -------------------------------------------------------------------------------------


def rds_client():
    import boto3

    return boto3.client("rds", region_name=REGION)


def find_instance(rds) -> dict | None:
    """The database as AWS describes it, or None when there is none."""
    try:
        found = rds.describe_db_instances(DBInstanceIdentifier=IDENTIFIER)
    except rds.exceptions.DBInstanceNotFoundFault:
        return None
    return found["DBInstances"][0]


def parked_snapshots(rds) -> list[dict]:
    """The snapshots `snapshot-and-delete` made, newest first."""
    found = rds.describe_db_snapshots(
        DBInstanceIdentifier=IDENTIFIER, SnapshotType="manual"
    )["DBSnapshots"]
    parked = [
        s
        for s in found
        if s["DBSnapshotIdentifier"].startswith(PARKED_PREFIX)
        and s["Status"] == "available"
    ]
    return sorted(parked, key=lambda s: s["SnapshotCreateTime"], reverse=True)


def is_parked(rds) -> bool:
    """No database, but a snapshot to restore it from."""
    return find_instance(rds) is None and bool(parked_snapshots(rds))


def wait_for_status(rds, wanted: str, minutes: int = 30) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        instance = find_instance(rds)
        status = instance["DBInstanceStatus"] if instance else "deleted"
        if status == wanted:
            return
        if time.monotonic() > deadline:
            raise SetupError(f"Still {status} after {minutes} minutes, not {wanted}.")
        print(f"  ... {status}")
        time.sleep(30)


# --- Terraform ------------------------------------------------------------------------------


def terraform(folder: Path, args: list[str], env: Mapping[str, str]) -> int:
    """Run Terraform in `folder`. Only the arguments are shown, never `env`."""
    return subprocess.run(
        ["terraform", f"-chdir={folder}", *args], env=dict(env), check=False
    ).returncode


def init(folder: Path, state: str, env: Mapping[str, str]) -> int:
    """`terraform init`, its output shown only when it fails."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [
            "terraform",
            f"-chdir={folder}",
            "init",
            "-input=false",
            "-no-color",
            "-reconfigure",
            f"-backend-config=path={(STATE_DIR / state).as_posix()}",
        ],
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        print(done.stdout + done.stderr, file=sys.stderr)
    return done.returncode


def aws_output(env: Mapping[str, str], name: str) -> str | None:
    done = subprocess.run(
        ["terraform", f"-chdir={AWS_DIR}", "output", "-raw", name],
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    value = done.stdout.strip()
    return value if done.returncode == 0 and value else None


def run_aws_root(
    command: str,
    extra: list[str],
    env: Mapping[str, str],
    parked: bool,
    restore_from=None,
) -> int:
    done = init(AWS_DIR, "rds.tfstate", env)
    if done != 0:
        return done
    variables = [f"-var=parked={'true' if parked else 'false'}"]
    if restore_from:
        variables.append(f"-var=restore_from={restore_from}")
    return terraform(
        AWS_DIR, [command, "-input=false", "-no-color", *variables, *extra], env
    )


def run_postgres_root(
    command: str, extra: list[str], env: Mapping[str, str], host: str
) -> int:
    done = init(POSTGRES_DIR, "postgres.tfstate", env)
    if done != 0:
        return done
    admin = aws_output(env, "admin_user") or "trading_agent_admin"
    variables = [f"-var=host={host}", f"-var=admin_user={admin}"]
    return terraform(
        POSTGRES_DIR, [command, "-input=false", "-no-color", *variables, *extra], env
    )


# --- Commands -------------------------------------------------------------------------------


def cmd_status(rds) -> int:
    instance = find_instance(rds)
    if instance:
        print(f"Database {IDENTIFIER}: {instance['DBInstanceStatus']}")
        endpoint = instance.get("Endpoint") or {}
        if endpoint.get("Address"):
            print(f"POSTGRES_HOST={endpoint['Address']}")
        return 0
    snapshots = parked_snapshots(rds)
    if snapshots:
        print(
            f"Database {IDENTIFIER}: parked, as the snapshot "
            f"{snapshots[0]['DBSnapshotIdentifier']}. `restore` brings it back."
        )
    else:
        print(f"Database {IDENTIFIER}: not made yet. `apply` makes it.")
    return 0


def cmd_terraform(rds, command: str, extra: list[str], env: dict) -> int:
    """`plan` or `apply`, on the AWS root, then on the logins' root when it can be reached."""
    parked = is_parked(rds)
    run_env = {**os.environ, **aws_secrets(env), **postgres_secrets(env)}
    done = run_aws_root(command, extra, run_env, parked)
    if done != 0 or parked:
        if parked:
            print(
                "The database is parked: the logins' part is inside the snapshot. "
                "`restore` brings it back."
            )
        return done
    instance = find_instance(rds)
    if instance is None:
        if command == "apply":
            return done
        # Before the database exists, plan the logins' part against a made-up address: Terraform
        # plans new logins without connecting.
        print("\nThe logins' part, once the database exists:")
        return run_postgres_root("plan", [], run_env, NOT_MADE_YET)
    if instance["DBInstanceStatus"] != "available":
        print(
            f"The database is {instance['DBInstanceStatus']}: the logins' part needs it "
            "switched on (`start`)."
        )
        return done
    host = instance["Endpoint"]["Address"]
    print("\nThe logins, the two databases and pgvector, inside the database:")
    done = run_postgres_root(command, extra, run_env, host)
    if done == 0 and command == "apply":
        print(f"\nPut this line in .env: POSTGRES_HOST={host}")
    return done


def cmd_start(rds) -> int:
    instance = find_instance(rds)
    if instance is None:
        raise SetupError("There is no database to start. `status` says why.")
    if instance["DBInstanceStatus"] != "available":
        if instance["DBInstanceStatus"] == "stopped":
            rds.start_db_instance(DBInstanceIdentifier=IDENTIFIER)
        print("Starting the database (a few minutes)...")
        wait_for_status(rds, "available")
    print("The database is on: about 1.8 cents an hour until `stop`.")
    return 0


def cmd_stop(rds) -> int:
    instance = find_instance(rds)
    if instance is None:
        raise SetupError("There is no database to stop. `status` says why.")
    if instance["DBInstanceStatus"] != "stopped":
        if instance["DBInstanceStatus"] == "available":
            rds.stop_db_instance(DBInstanceIdentifier=IDENTIFIER)
        print("Stopping the database (a few minutes)...")
        wait_for_status(rds, "stopped")
    print(
        "The database is stopped: only its disk is billed (about $2.50 a month).\n"
        "AWS starts it again by itself after 7 days. For a longer pause, run "
        "`snapshot-and-delete`."
    )
    return 0


def cmd_snapshot_and_delete(rds) -> int:
    instance = find_instance(rds)
    if instance is None:
        raise SetupError("There is no database to delete. `status` says why.")
    older = parked_snapshots(rds)
    name = PARKED_PREFIX + datetime.now(UTC).strftime("%Y%m%d-%H%M")
    print(f"Saving the database as the snapshot {name}, then deleting it...")
    rds.delete_db_instance(
        DBInstanceIdentifier=IDENTIFIER,
        SkipFinalSnapshot=False,
        FinalDBSnapshotIdentifier=name,
        DeleteAutomatedBackups=True,
    )
    wait_for_status(rds, "deleted", minutes=45)
    rds.get_waiter("db_snapshot_available").wait(DBSnapshotIdentifier=name)
    # Only the newest copy is kept: each costs cents a month.
    for snapshot in older:
        rds.delete_db_snapshot(DBSnapshotIdentifier=snapshot["DBSnapshotIdentifier"])
        print(f"Deleted the older snapshot {snapshot['DBSnapshotIdentifier']}.")
    print(
        f"Parked: the database is deleted and kept as the snapshot {name} "
        "(cents a month). `restore` brings it back in 10 to 15 minutes."
    )
    return 0


def cmd_restore(rds, env: dict) -> int:
    if find_instance(rds) is not None:
        raise SetupError("The database exists already: nothing to restore.")
    snapshots = parked_snapshots(rds)
    if not snapshots:
        raise SetupError("No snapshot to restore from. `status` says why.")
    name = snapshots[0]["DBSnapshotIdentifier"]
    print(
        f"Making the database again from the snapshot {name} (10 to 15 minutes)...",
    )
    run_env = {**os.environ, **aws_secrets(env)}
    done = run_aws_root("apply", ["-auto-approve"], run_env, False, restore_from=name)
    if done == 0:
        instance = find_instance(rds)
        print(
            "Restored and on: about 1.8 cents an hour until `stop`.\n"
            f"POSTGRES_HOST={instance['Endpoint']['Address']}"
        )
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/rds.py")
    parser.add_argument(
        "command",
        choices=(
            "status",
            "plan",
            "apply",
            "start",
            "stop",
            "snapshot-and-delete",
            "restore",
        ),
    )
    parser.add_argument("terraform_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    # Each line shows at once, in order with Terraform's own output.
    sys.stdout.reconfigure(line_buffering=True)
    try:
        env = read_env()
        rds = rds_client()
        if args.command == "status":
            return cmd_status(rds)
        if args.command in ("plan", "apply"):
            return cmd_terraform(rds, args.command, args.terraform_args, env)
        if args.command == "start":
            return cmd_start(rds)
        if args.command == "stop":
            return cmd_stop(rds)
        if args.command == "snapshot-and-delete":
            return cmd_snapshot_and_delete(rds)
        return cmd_restore(rds, env)
    except SetupError as problem:
        print(f"Setup problem: {problem}", file=sys.stderr)
        return 2
    except Exception as problem:
        from botocore.exceptions import (
            NoCredentialsError,
            SSOError,
            TokenRetrievalError,
        )

        if isinstance(problem, NoCredentialsError | SSOError | TokenRetrievalError):
            print(
                "The AWS login has run out or is missing: run `aws sso login`, then again.",
                file=sys.stderr,
            )
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
