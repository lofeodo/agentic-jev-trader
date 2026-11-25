"""Deploy the memory server, the API and the web app into the local kind cluster with the real
secrets from `.env` (spec appendix 10, section 3): Terraform's Kubernetes part, run from here.

Run from the repo root, after `python infra/images.py build` (both images of this commit loaded
into the cluster `jev-trader`):

    conda run -n agentic-jev-trader python infra/deploy.py plan
    conda run -n agentic-jev-trader python infra/deploy.py apply -auto-approve

`plan` shows what would change; `apply` asks nothing, so it takes `-auto-approve`.
Each secret goes to Terraform as an environment variable `TF_VAR_<name>`, never on a command line
or in a file, and Terraform sends it to the cluster write-only, so its state never holds it. The
images' tag is this checkout's commit (`images.py tag`); the private keys come from the keys
folder in `SNOWFLAKE_LOCAL_DIR`, where the state is kept too (`kubernetes.tfstate`, beside the
Snowflake part's). `--database TRADING_AGENT_TEST`, given before the command, serves the test
database; anything after the command goes to Terraform as it is (`apply -var=secrets_revision=2`
after changing a secret). Output is plain ASCII: `conda run` on Windows fails on other
characters.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

if __package__ in (
    None,
    "",
):  # run as a script: import its neighbours from the repo root
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra import images
from infra.snowflake_admin import DATABASES, REPO_ROOT, Settings, SetupError

KUBERNETES_DIR = REPO_ROOT / "infra" / "terraform" / "kubernetes"

# Terraform's secret variables (terraform/kubernetes/variables.tf), each from its line in .env.
SECRETS = {
    "snowflake_account": "SNOWFLAKE_ACCOUNT",
    "snowflake_private_key_passphrase": "SNOWFLAKE_PRIVATE_KEY_FILE_PWD",
    "twelve_data_api_key": "TWELVE_DATA_API_KEY",
    "typesafe_api_key": "TYPESAFE_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def secrets_env(env: Mapping[str, str]) -> dict[str, str]:
    """The secrets as Terraform reads them, `TF_VAR_<name>`. SetupError names any missing."""
    missing = [name for name in SECRETS.values() if not (env.get(name) or "").strip()]
    if missing:
        raise SetupError(
            ", ".join(missing) + " not set. Add them to .env (see .env.example)."
        )
    return {f"TF_VAR_{var}": env[name].strip() for var, name in SECRETS.items()}


def state_path(settings: Settings) -> Path:
    return settings.local_dir / "kubernetes.tfstate"


def terraform_variables(settings: Settings, tag: str, database: str) -> list[str]:
    """The variables that are not secret, for `plan` and `apply`."""
    return [
        f"-var=image_tag={tag}",
        f"-var=snowflake_keys_dir={settings.keys_dir.as_posix()}",
        f"-var=database={database}",
    ]


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
        env = read_env()
        settings = Settings.from_env(env)
        secrets = secrets_env(env)
    except SetupError as problem:
        print(f"Setup problem: {problem}", file=sys.stderr)
        return 2
    settings.local_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **secrets}
    init = [
        "init",
        "-input=false",
        "-no-color",
        "-reconfigure",
        f"-backend-config=path={state_path(settings).as_posix()}",
    ]
    done = terraform(init, env)
    if done != 0:
        return done
    tag = images.commit_tag()
    variables = terraform_variables(settings, tag, args.database)
    return terraform(
        [args.command, "-input=false", "-no-color", *variables, *args.terraform_args],
        env,
    )


if __name__ == "__main__":
    sys.exit(main())
