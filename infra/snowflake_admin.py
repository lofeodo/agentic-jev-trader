"""Set up and check the project's Snowflake account.

Run from the repo root, in this order the first time (infra/README.md explains each):

    conda run -n agentic-jev-trader python infra/snowflake_admin.py keys
    conda run -n agentic-jev-trader python infra/snowflake_admin.py terraform plan
    conda run -n agentic-jev-trader python infra/snowflake_admin.py terraform apply
    conda run -n agentic-jev-trader python infra/snowflake_admin.py migrate
    conda run -n agentic-jev-trader python infra/snowflake_admin.py check

Settings come from `.env` at the repo root (see `.env.example`). Output is plain ASCII on
purpose: `conda run` on Windows fails on other characters.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from snowflake.connector.errors import Error as SnowflakeError

REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"

# These names must match infra/terraform/main.tf.
DATABASES = (
    "TRADING_AGENT_TEST",
    "TRADING_AGENT",
)  # test first, so a bad file stops there
WAREHOUSE = "TRADING_AGENT_WH"
SERVICE_LOGINS = ("builder", "sim", "memory", "api", "migrations")
TERRAFORM_LOGIN = "terraform"  # made by hand once (infra/README.md), holds ACCOUNTADMIN
EMBEDDING_MODEL = "snowflake-arctic-embed-m-v1.5"
EMBEDDING_SIZE = 768
SCHEMAS = ("REF", "KEYS", "RAW", "FEATURES", "SIM", "MEMORY", "METADATA")


def role_name(login: str) -> str:
    return f"TRADING_AGENT_{login.upper()}"


def user_name(login: str) -> str:
    return f"TRADING_AGENT_{login.upper()}_SVC"


class SetupError(Exception):
    """A setting is missing or wrong; the message says what to fix."""


_ACCOUNT_RE = re.compile(r"^([A-Za-z0-9_]+)-([A-Za-z0-9_]+)$")


def split_account(identifier: str) -> tuple[str, str]:
    """Split an account identifier "ORGNAME-ACCOUNTNAME" into its two names."""
    match = _ACCOUNT_RE.match(identifier.strip())
    if not match:
        raise SetupError(
            f"SNOWFLAKE_ACCOUNT must look like ORGNAME-ACCOUNTNAME, got {identifier!r}. "
            "Snowsight shows it under your name (bottom left) > Account > View account details."
        )
    return match.group(1), match.group(2)


@dataclass(frozen=True)
class Settings:
    account: str
    passphrase: str
    local_dir: Path

    @property
    def keys_dir(self) -> Path:
        return self.local_dir / "keys"

    @property
    def state_path(self) -> Path:
        return self.local_dir / "terraform.tfstate"

    def private_key_path(self, login: str) -> Path:
        return self.keys_dir / f"{login}.p8"

    @classmethod
    def from_env(cls, env: Mapping[str, str], home: Path | None = None) -> Settings:
        def required(name: str) -> str:
            value = (env.get(name) or "").strip()
            if not value:
                raise SetupError(
                    f"{name} is not set. Add it to .env (see .env.example)."
                )
            return value

        account = required("SNOWFLAKE_ACCOUNT")
        split_account(account)
        passphrase = required("SNOWFLAKE_PRIVATE_KEY_FILE_PWD")
        local = (env.get("SNOWFLAKE_LOCAL_DIR") or "").strip()
        if local:
            local_dir = Path(local).expanduser()
        else:
            local_dir = (home or Path.home()) / ".agentic-jev-trader" / "snowflake"
        return cls(account=account, passphrase=passphrase, local_dir=local_dir)


def public_key_body(public_pem: str) -> str:
    """The public key as Snowflake wants it: one line, no BEGIN/END lines."""
    lines = [ln.strip() for ln in public_pem.splitlines()]
    return "".join(ln for ln in lines if ln and not ln.startswith("-----"))


def write_key_pair(folder: Path, login: str, passphrase: str) -> str:
    """Make `<login>.p8` (encrypted private key) and `<login>.pub` in `folder`.

    An existing pair is kept as it is, so a key already registered on a Snowflake
    user is never replaced by accident. Returns the one-line public key.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    folder = Path(folder)
    private_path = folder / f"{login}.p8"
    public_path = folder / f"{login}.pub"
    if private_path.exists() and public_path.exists():
        return public_key_body(public_path.read_text())
    if private_path.exists() or public_path.exists():
        raise SetupError(
            f"Only half of the key pair for {login!r} exists in {folder}; remove it and run again."
        )

    folder.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(
                passphrase.encode()
            ),
        )
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public_pem)
    return public_key_body(public_pem.decode())


def terraform_env(settings: Settings) -> dict[str, str]:
    """Terraform's input variables, passed as TF_VAR_* so no secret is on a command line."""
    organization, account = split_account(settings.account)
    return {
        "TF_VAR_organization_name": organization,
        "TF_VAR_account_name": account,
        "TF_VAR_admin_user": user_name(TERRAFORM_LOGIN),
        "TF_VAR_admin_private_key_path": str(
            settings.private_key_path(TERRAFORM_LOGIN)
        ),
        "TF_VAR_private_key_passphrase": settings.passphrase,
        "TF_VAR_public_keys_dir": str(settings.keys_dir),
    }


def schemachange_command(settings: Settings, database: str) -> list[str]:
    """schemachange's arguments for one database. The passphrase goes in the environment."""
    return [
        sys.executable,
        "-m",
        "schemachange.cli",
        "deploy",
        "--schemachange-root-folder",
        str(MIGRATIONS_DIR),
        "--snowflake-account",
        settings.account,
        "--snowflake-user",
        user_name("migrations"),
        "--snowflake-role",
        role_name("migrations"),
        "--snowflake-warehouse",
        WAREHOUSE,
        "--snowflake-database",
        database,
        "--snowflake-authenticator",
        "snowflake_jwt",
        "--snowflake-private-key-file",
        str(settings.private_key_path("migrations")),
        "--schemachange-change-history-table",
        f"{database}.METADATA.CHANGE_HISTORY",
        # Only creates the table when it is missing, so it is safe on every run.
        "--schemachange-create-change-history-table",
    ]


# ---------------------------------------------------------------------------
# Commands (they touch the disk, Terraform or Snowflake; not unit-tested)
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v is not None}
    env.update(os.environ)  # a variable set in the shell wins over .env
    return Settings.from_env(env)


def cmd_keys(settings: Settings) -> int:
    for login in (TERRAFORM_LOGIN, *SERVICE_LOGINS):
        write_key_pair(settings.keys_dir, login, settings.passphrase)
    print(
        f"Key pairs are in {settings.keys_dir} (private keys encrypted with SNOWFLAKE_PRIVATE_KEY_FILE_PWD)."
    )
    body = public_key_body((settings.keys_dir / f"{TERRAFORM_LOGIN}.pub").read_text())
    sql = (
        "USE ROLE ACCOUNTADMIN;\n"
        f"CREATE USER IF NOT EXISTS {user_name(TERRAFORM_LOGIN)}\n"
        "  TYPE = SERVICE\n"
        f"  RSA_PUBLIC_KEY = '{body}'\n"
        "  DEFAULT_ROLE = ACCOUNTADMIN\n"
        "  COMMENT = 'Terraform for agentic-jev-trader (infra/terraform)';\n"
        f"GRANT ROLE ACCOUNTADMIN TO USER {user_name(TERRAFORM_LOGIN)};\n"
    )
    sql_path = settings.local_dir / "create_terraform_user.sql"
    sql_path.write_text(sql)
    print(
        "\nOnce only: run this in a Snowsight SQL worksheet as ACCOUNTADMIN (also saved to"
    )
    print(f"{sql_path}):\n")
    print(sql)
    return 0


def cmd_terraform(settings: Settings, args: list[str]) -> int:
    settings.local_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **terraform_env(settings)}
    init = [
        "terraform",
        f"-chdir={TERRAFORM_DIR}",
        "init",
        "-input=false",
        "-reconfigure",
        f"-backend-config=path={settings.state_path}",
    ]
    done = subprocess.run(init, env=env, check=False)
    if done.returncode != 0:
        return done.returncode
    return subprocess.run(
        ["terraform", f"-chdir={TERRAFORM_DIR}", *args], env=env, check=False
    ).returncode


def cmd_migrate(settings: Settings) -> int:
    env = {**os.environ, "SNOWFLAKE_PRIVATE_KEY_FILE_PWD": settings.passphrase}
    for database in DATABASES:
        print(f"--- schemachange on {database}")
        done = subprocess.run(
            schemachange_command(settings, database), env=env, check=False
        )
        if done.returncode != 0:
            return done.returncode
    return 0


def connect(settings: Settings, login: str, role: str | None = None):
    import snowflake.connector

    return snowflake.connector.connect(
        account=settings.account,
        user=user_name(login),
        role=role or role_name(login),
        warehouse=WAREHOUSE,
        authenticator="SNOWFLAKE_JWT",
        private_key_file=str(settings.private_key_path(login)),
        private_key_file_pwd=settings.passphrase,
    )


def first_line(exc: Exception) -> str:
    return (str(exc).splitlines() or [""])[0]


def fetch_dicts(cur) -> list[dict]:
    """Rows of the last query as dicts keyed by lower-case column name."""
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def try_embed(settings: Settings, login: str) -> tuple[bool, str]:
    """Embed one sentence as `login`'s role alone. Returns (worked, detail)."""
    con = connect(settings, login)
    try:
        cur = con.cursor()
        cur.execute("USE SECONDARY ROLES NONE")
        cur.execute(
            f"SELECT ARRAY_SIZE(AI_EMBED('{EMBEDDING_MODEL}', 'A quiet morning, prices drifting up.')::ARRAY)"
        )
        size = cur.fetchone()[0]
        if size != EMBEDDING_SIZE:
            return False, f"vector of {size} numbers, expected {EMBEDDING_SIZE}"
        return True, f"vector of {size} numbers"
    except SnowflakeError as exc:  # the error text is the finding
        return False, f"{type(exc).__name__}: {first_line(exc)}"
    finally:
        con.close()


def cmd_check(settings: Settings) -> int:
    """The live checks of ticket #85. Prints a report that can be pasted on the ticket."""
    failures: list[str] = []
    warnings: list[str] = []
    builder_role = role_name("builder")

    admin = connect(settings, TERRAFORM_LOGIN, role="ACCOUNTADMIN")
    cur = admin.cursor()

    print("== 1. Grants to the dataset builder's role")
    cur.execute(f"SHOW GRANTS TO ROLE {builder_role}")
    grants = fetch_dicts(cur)
    embed_grants = [g for g in grants if "CORTEX" in str(g.get("name", "")).upper()]
    for g in embed_grants:
        print(f"   {g['privilege']} on {g['granted_on']} {g['name']}")
    if not any(g["granted_on"] == "APPLICATION_ROLE" for g in embed_grants):
        failures.append("builder role holds no Cortex model application role")
    if not any(g["granted_on"] == "DATABASE_ROLE" for g in embed_grants):
        failures.append("builder role does not hold SNOWFLAKE.CORTEX_EMBED_USER")

    print(
        "== 2. What every role gets anyway (new accounts may open every model to every role)"
    )
    for query in (
        "SHOW GRANTS TO ROLE PUBLIC",
        "SHOW GRANTS TO APPLICATION ROLE SNOWFLAKE.PUBLIC",
        "SHOW PARAMETERS LIKE 'CORTEX_MODELS_ALLOWLIST' IN ACCOUNT",
    ):
        try:
            cur.execute(query)
            rows = fetch_dicts(cur)
            if query.startswith("SHOW PARAMETERS"):
                print(
                    f"   CORTEX_MODELS_ALLOWLIST = {rows[0]['value'] if rows else '(not shown)'}"
                )
                continue
            cortex = [r for r in rows if "CORTEX" in str(r.get("name", "")).upper()]
            print(
                f"   {query}: {len(rows)} grants, Cortex ones: "
                + (
                    ", ".join(f"{r['granted_on']} {r['name']}" for r in cortex)
                    or "none"
                )
            )
        except SnowflakeError as exc:
            print(f"   {query}: could not run ({first_line(exc)})")

    print("== 3. Embedding as the real roles, secondary roles off")
    worked, detail = try_embed(settings, "builder")
    print(f"   builder: {'WORKS' if worked else 'FAILS'} ({detail})")
    if not worked:
        failures.append(f"builder cannot embed: {detail}")
    worked, detail = try_embed(settings, "sim")
    print(f"   sim (should fail): {'WORKS' if worked else 'FAILS'} ({detail})")
    if worked:
        # Not this ticket's grant failing: an account-wide default (section 2 above) opens
        # the model to every role, so the builder's success alone does not prove our grant.
        warnings.append(
            "the sim role can embed too: an account-wide default opens the model to every role"
        )

    print("== 4. The memory server's role can only read")
    memory_role = role_name("memory")
    cur.execute(f"SHOW GRANTS TO ROLE {memory_role}")
    privileges = {r["privilege"] for r in fetch_dicts(cur)}
    future: set[str] = set()
    for database in DATABASES:
        for schema in SCHEMAS:
            cur.execute(f"SHOW FUTURE GRANTS IN SCHEMA {database}.{schema}")
            future |= {
                r["privilege"]
                for r in fetch_dicts(cur)
                if r.get("grantee_name") == memory_role
            }
    print(
        f"   current privileges: {sorted(privileges)}; future-table privileges: {sorted(future)}"
    )
    extra = (privileges | future) - {"USAGE", "SELECT"}
    if extra:
        failures.append(
            f"memory role holds more than USAGE and SELECT: {sorted(extra)}"
        )
    memory = connect(settings, "memory")
    try:
        mcur = memory.cursor()
        mcur.execute("USE SECONDARY ROLES NONE")
        try:
            mcur.execute(f"CREATE TABLE {DATABASES[0]}.MEMORY.WRITE_PROBE (X INT)")
        except SnowflakeError as exc:
            print(f"   CREATE TABLE as memory: refused ({first_line(exc)})")
        else:
            failures.append("memory role could create a table")
            print("   CREATE TABLE as memory: WORKED (bad)")
            mcur.execute(f"DROP TABLE {DATABASES[0]}.MEMORY.WRITE_PROBE")
    finally:
        memory.close()

    print("== 5. schemachange's history on both databases")
    for database in DATABASES:
        try:
            cur.execute(
                f"SELECT VERSION, SCRIPT, STATUS FROM {database}.METADATA.CHANGE_HISTORY ORDER BY INSTALLED_ON"
            )
            rows = cur.fetchall()
            print(
                f"   {database}: "
                + ("; ".join(f"{v} {s} {st}" for v, s, st in rows) or "empty")
            )
            if not rows:
                failures.append(f"no migration recorded in {database}")
        except SnowflakeError as exc:
            failures.append(f"no change history in {database}")
            print(f"   {database}: {first_line(exc)}")
    admin.close()

    print()
    for w in warnings:
        print(f"WARNING: {w}")
    if failures:
        print("FAILED:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("All checks passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "keys",
        help="make the key pairs and print the one-time SQL for Terraform's login",
    )
    tf = sub.add_parser(
        "terraform", help="run terraform in infra/terraform with the settings from .env"
    )
    tf.add_argument("args", nargs=argparse.REMAINDER, help="for example: plan, apply")
    sub.add_parser("migrate", help="apply the numbered SQL files to both databases")
    sub.add_parser(
        "check", help="try the embedding grant and the read-only memory role live"
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "keys":
            return cmd_keys(settings)
        if args.command == "terraform":
            return cmd_terraform(settings, args.args)
        if args.command == "migrate":
            return cmd_migrate(settings)
        return cmd_check(settings)
    except SetupError as exc:
        print(f"Setup problem: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
