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
# Its own folder, not SNOWFLAKE_LOCAL_DIR: that one goes with Snowflake at the end of the move.
STATE_DIR = Path.home() / ".agentic-jev-trader" / "rds"

# These three must match infra/terraform/rds/main.tf.
REGION = "ca-central-1"
IDENTIFIER = "trading-agent"
ADMIN_USER = "trading_agent_admin"
PARKED_PREFIX = f"{IDENTIFIER}-parked-"
# Shown to `plan` before the database exists: Terraform plans new logins without connecting.
NOT_MADE_YET = "not-made-yet.invalid"
# AWS passes through other statuses on its own (a backup, a change, starting, stopping); a
# command waits them out before acting.
SETTLED = ("available", "stopped")
ON = "about 2.3 cents an hour (1.8 for the database, 0.5 for its internet address)"


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
    # This checkout's own code, whichever copy the conda env has installed.
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from jev_trader.storage import postgres

    passwords = {
        login: _required(env, postgres.password_variable(login))
        for login in postgres.LOGINS
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


def status_of(rds) -> str:
    """The database's status, `deleted` when there is none."""
    instance = find_instance(rds)
    return instance["DBInstanceStatus"] if instance else "deleted"


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


def wait_for(rds, wanted: tuple[str, ...], minutes: int = 30) -> str:
    """Wait until the database's status is one of `wanted`, and return it."""
    deadline = time.monotonic() + minutes * 60
    while True:
        status = status_of(rds)
        if status in wanted:
            return status
        if time.monotonic() > deadline:
            raise SetupError(f"Still {status} after {minutes} minutes.")
        print(f"  ... {status}")
        time.sleep(30)


# --- Terraform ------------------------------------------------------------------------------


def terraform(folder: Path, args: list[str], env: Mapping[str, str]) -> int:
    """Run Terraform in `folder`, after `init` (whose output shows only when it fails).
    Only the arguments are shown, never `env`."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = STATE_DIR / (
        "postgres.tfstate" if folder == POSTGRES_DIR else "rds.tfstate"
    )
    common = ["terraform", f"-chdir={folder}"]
    init = subprocess.run(
        [
            *common,
            "init",
            "-input=false",
            "-no-color",
            "-reconfigure",
            f"-backend-config=path={state.as_posix()}",
        ],
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        print(init.stdout + init.stderr, file=sys.stderr)
        return init.returncode
    command, *rest = args
    return subprocess.run(
        [*common, command, "-input=false", "-no-color", *rest],
        env=dict(env),
        check=False,
    ).returncode


def run_aws_root(
    command: str,
    extra: list[str],
    env: Mapping[str, str],
    parked: bool,
    restore_from: str | None = None,
) -> int:
    variables = [f"-var=parked={'true' if parked else 'false'}"]
    if restore_from:
        variables.append(f"-var=restore_from={restore_from}")
    return terraform(AWS_DIR, [command, *variables, *extra], env)


def run_postgres_root(
    command: str, extra: list[str], env: Mapping[str, str], host: str
) -> int:
    variables = [f"-var=host={host}", f"-var=admin_user={ADMIN_USER}"]
    return terraform(POSTGRES_DIR, [command, *variables, *extra], env)


# --- Commands -------------------------------------------------------------------------------
# Each takes the RDS client, the arguments after the command (for Terraform) and the settings.


def cmd_status(rds, extra: list[str], env: Mapping[str, str]) -> int:
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


def terraform_command(command: str):
    """`plan` or `apply`: the AWS root, then the logins' root when it can be reached."""

    def run(rds, extra: list[str], env: Mapping[str, str]) -> int:
        instance = find_instance(rds)
        status = instance["DBInstanceStatus"] if instance else None
        parked = instance is None and bool(parked_snapshots(rds))
        if status == "deleting":
            raise SetupError("The database is being deleted: wait, then `status`.")
        if command == "apply" and status not in (None, "available"):
            raise SetupError(f"The database is {status}: `start` it before `apply`.")
        run_env = {**os.environ, **aws_secrets(env)}
        done = run_aws_root(command, extra, run_env, parked)
        if done != 0:
            return done
        if parked:
            print(
                "The database is parked: the logins' part is inside the snapshot. "
                "`restore` brings it back."
            )
            return done
        run_env.update(postgres_secrets(env))
        instance = find_instance(rds)
        if instance is None:
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
            print(f"The database is on: {ON}, until `stop`.")
        return done

    return run


def cmd_start(rds, extra: list[str], env: Mapping[str, str]) -> int:
    if find_instance(rds) is None:
        raise SetupError("There is no database to start. `status` says why.")
    print("Starting the database (a few minutes)...")
    if wait_for(rds, SETTLED) == "stopped":
        rds.start_db_instance(DBInstanceIdentifier=IDENTIFIER)
        wait_for(rds, ("available",))
    print(f"The database is on: {ON}, until `stop`.")
    return 0


def cmd_stop(rds, extra: list[str], env: Mapping[str, str]) -> int:
    if find_instance(rds) is None:
        raise SetupError("There is no database to stop. `status` says why.")
    print("Stopping the database (a few minutes)...")
    if wait_for(rds, SETTLED) == "available":
        rds.stop_db_instance(DBInstanceIdentifier=IDENTIFIER)
        wait_for(rds, ("stopped",))
    print(
        "The database is stopped: only its disk is billed (about $2.50 a month).\n"
        "AWS starts it again by itself after 7 days. For a longer pause, run "
        "`snapshot-and-delete`."
    )
    return 0


def cmd_snapshot_and_delete(rds, extra: list[str], env: Mapping[str, str]) -> int:
    if find_instance(rds) is None:
        raise SetupError("There is no database to delete. `status` says why.")
    wait_for(rds, SETTLED)
    name = PARKED_PREFIX + datetime.now(UTC).strftime("%Y%m%d-%H%M")
    print(f"Saving the database as the snapshot {name}, then deleting it...")
    rds.delete_db_instance(
        DBInstanceIdentifier=IDENTIFIER,
        SkipFinalSnapshot=False,
        FinalDBSnapshotIdentifier=name,
        DeleteAutomatedBackups=True,
    )
    wait_for(rds, ("deleted",), minutes=45)
    rds.get_waiter("db_snapshot_available").wait(DBSnapshotIdentifier=name)
    print(
        f"Parked: the database is deleted and kept as the snapshot {name} "
        "(cents a month). `restore` brings it back in 10 to 15 minutes."
    )
    return 0


def cmd_restore(rds, extra: list[str], env: Mapping[str, str]) -> int:
    if find_instance(rds) is not None:
        raise SetupError("The database exists already: nothing to restore.")
    snapshots = parked_snapshots(rds)
    if not snapshots:
        raise SetupError("No snapshot to restore from. `status` says why.")
    name = snapshots[0]["DBSnapshotIdentifier"]
    print(f"Making the database again from the snapshot {name} (10 to 15 minutes)...")
    run_env = {**os.environ, **aws_secrets(env)}
    done = run_aws_root("apply", ["-auto-approve"], run_env, False, restore_from=name)
    if done == 0:
        print(f"Restored. The database is on: {ON}, until `stop`.")
        print(f"POSTGRES_HOST={find_instance(rds)['Endpoint']['Address']}")
    return done


COMMANDS = {
    "status": cmd_status,
    "plan": terraform_command("plan"),
    "apply": terraform_command("apply"),
    "start": cmd_start,
    "stop": cmd_stop,
    "snapshot-and-delete": cmd_snapshot_and_delete,
    "restore": cmd_restore,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/rds.py")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("terraform_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    # Each line shows at once, in order with Terraform's own output.
    sys.stdout.reconfigure(line_buffering=True)
    try:
        return COMMANDS[args.command](rds_client(), args.terraform_args, read_env())
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
