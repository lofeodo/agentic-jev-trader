"""Deploy the memory server, the API and the web app into the local kind cluster with the real
secrets from `.env` (spec appendix 10, section 3; appendix 11, section 1): Terraform's Kubernetes
part, run from here.

Run from the repo root, after `python infra/images.py build` (both images of this commit loaded
into the cluster `jev-trader`):

    conda run -n agentic-jev-trader python infra/deploy.py plan
    conda run -n agentic-jev-trader python infra/deploy.py apply -auto-approve

`plan` shows what would change; `apply` asks nothing, so it takes `-auto-approve`.
The programs in the cluster reach the same Postgres as the programs on this computer: the
address, port and encryption from `.env` (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_SSL_MODE`)
and the password of each login that runs there (api, memory, sim, builder). Those and the model
and price-data keys go to Terraform as environment variables `TF_VAR_<name>`, never on a command
line or in a file, and Terraform sends the passwords and keys to the cluster write-only, so its
state never holds them. The images' tag is this checkout's commit (`images.py tag`); the state is
kept outside the repo, in `~/.agentic-jev-trader/kubernetes`. `--database TRADING_AGENT_TEST`,
given before the command, serves the test database; anything after the command goes to
Terraform as it is (`apply -var=secrets_revision=2` after changing a secret). Output is plain
ASCII: `conda run` on Windows fails on other characters.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if (
    __package__
    in (
        None,
        "",
    )
):  # run as a script: import its neighbours from the repo root, and this checkout's code
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "src"))

from infra import images
from jev_trader.storage import postgres

KUBERNETES_DIR = REPO_ROOT / "infra" / "terraform" / "kubernetes"
# Its own folder, beside infra/rds.py's: nothing here depends on Snowflake any more.
STATE_DIR = Path.home() / ".agentic-jev-trader" / "kubernetes"
DATABASES = ("TRADING_AGENT", "TRADING_AGENT_TEST")

# Terraform's key variables (terraform/kubernetes/variables.tf), each from its line in .env.
KEYS = {
    "twelve_data_api_key": "TWELVE_DATA_API_KEY",
    "typesafe_api_key": "TYPESAFE_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}
# The logins that run in the cluster; the setup login stays on this computer.
CLUSTER_LOGINS = ("api", "memory", "sim", "builder")
# Addresses that, inside a pod, name the pod itself rather than this computer.
NOT_FROM_A_POD = ("127.0.0.1", "localhost", "::1")


class SetupError(Exception):
    """A setting in `.env` is missing or cannot work in the cluster."""


def _missing(env: Mapping[str, str], names: list[str]) -> list[str]:
    return [name for name in names if not (env.get(name) or "").strip()]


def secrets_env(env: Mapping[str, str]) -> dict[str, str]:
    """What Terraform reads, as `TF_VAR_<name>`: the keys, the cluster logins' passwords (one
    JSON map) and where the database is. SetupError names anything missing, never a value."""
    passwords = {login: postgres.password_variable(login) for login in CLUSTER_LOGINS}
    missing = _missing(env, [*KEYS.values(), "POSTGRES_HOST", *passwords.values()])
    if missing:
        raise SetupError(
            ", ".join(missing) + " not set. Add them to .env (see .env.example)."
        )
    host = env["POSTGRES_HOST"].strip()
    if host.lower() in NOT_FROM_A_POD:
        raise SetupError(
            f"POSTGRES_HOST is {host}: inside the cluster that names the pod itself. Set it "
            "to the RDS address (infra/rds.py status) to deploy."
        )
    found = {f"TF_VAR_{var}": env[name].strip() for var, name in KEYS.items()}
    found["TF_VAR_postgres_passwords"] = json.dumps(
        {login: env[name].strip() for login, name in passwords.items()}
    )
    found["TF_VAR_postgres_host"] = host
    for var, name in (
        ("postgres_port", "POSTGRES_PORT"),
        ("postgres_ssl_mode", "POSTGRES_SSL_MODE"),
    ):
        if value := (env.get(name) or "").strip():
            found[f"TF_VAR_{var}"] = value
    return found


def state_path() -> Path:
    return STATE_DIR / "kubernetes.tfstate"


def terraform_variables(tag: str, database: str) -> list[str]:
    """The variables that are not secret, for `plan` and `apply`."""
    return [f"-var=image_tag={tag}", f"-var=database={database}"]


def read_env() -> dict[str, str]:
    """`.env`'s values, with a variable set in the shell winning over its line in `.env`."""
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v is not None}
    env.update(os.environ)
    return env


def terraform(args: list[str], env: dict[str, str]) -> int:
    """Run Terraform on the Kubernetes part. Only the arguments are shown, never `env`."""
    return 0 if images.run(["terraform", f"-chdir={KUBERNETES_DIR}", *args], env) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/deploy.py")
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--database", choices=DATABASES, default="TRADING_AGENT")
    parser.add_argument("terraform_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        secrets = secrets_env(read_env())
    except SetupError as problem:
        print(f"Setup problem: {problem}", file=sys.stderr)
        return 2
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **secrets}
    init = [
        "init",
        "-input=false",
        "-no-color",
        "-reconfigure",
        f"-backend-config=path={state_path().as_posix()}",
    ]
    done = terraform(init, env)
    if done != 0:
        return done
    variables = terraform_variables(images.commit_tag(), args.database)
    return terraform(
        [args.command, "-input=false", "-no-color", *variables, *args.terraform_args],
        env,
    )


if __name__ == "__main__":
    sys.exit(main())
