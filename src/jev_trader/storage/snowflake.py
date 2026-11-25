"""Logging in to Snowflake as one of the project's programs.

Each program has its own service user and role (infra/README.md): the dataset builder logs in
as `TRADING_AGENT_BUILDER_SVC` with the private key `builder.p8` kept in `SNOWFLAKE_LOCAL_DIR`
(default `.agentic-jev-trader/snowflake` in the home folder), unlocked by
`SNOWFLAKE_PRIVATE_KEY_FILE_PWD`.
"""

import os
import threading
from collections.abc import Mapping
from pathlib import Path

DATABASE = "TRADING_AGENT"
TEST_DATABASE = "TRADING_AGENT_TEST"
WAREHOUSE = "TRADING_AGENT_WH"


class LoginNotSet(Exception):
    """A Snowflake setting is missing from `.env`; the message names it."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise LoginNotSet(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def key_file(login: str, env: Mapping[str, str] = os.environ) -> Path:
    local = (env.get("SNOWFLAKE_LOCAL_DIR") or "").strip()
    folder = (
        Path(local).expanduser()
        if local
        else Path.home() / ".agentic-jev-trader" / "snowflake"
    )
    return folder / "keys" / f"{login}.p8"


def connect(
    login: str,
    database: str = DATABASE,
    env: Mapping[str, str] = os.environ,
    user: str | None = None,
    private_key_file: str | Path | None = None,
):
    """A connection as `login` (`builder`, `sim`, ...), with `?` placeholders in statements.

    `user` and `private_key_file` override the login's own, as the hand-run tests do.
    """
    import snowflake.connector

    return snowflake.connector.connect(
        account=_required(env, "SNOWFLAKE_ACCOUNT"),
        user=user or f"TRADING_AGENT_{login.upper()}_SVC",
        role=f"TRADING_AGENT_{login.upper()}",
        warehouse=WAREHOUSE,
        database=database,
        authenticator="SNOWFLAKE_JWT",
        private_key_file=str(private_key_file or key_file(login, env)),
        private_key_file_pwd=_required(env, "SNOWFLAKE_PRIVATE_KEY_FILE_PWD"),
        paramstyle="qmark",
    )


class ConnectionOnFirstUse:
    """A connection as `login` that logs in when first used, not when made, for the two
    servers. A server then starts and answers its health address before Snowflake is
    reached: in the kind cluster's deployment check, whose logins are dummies, never. A
    setting missing from the environment still fails at once, as `connect` does."""

    def __init__(
        self, login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ
    ):
        _required(env, "SNOWFLAKE_ACCOUNT")
        _required(env, "SNOWFLAKE_PRIVATE_KEY_FILE_PWD")
        self._login = login
        self._database = database
        self._env = env
        self._connection = None
        self._lock = threading.Lock()

    def cursor(self):
        with self._lock:
            if self._connection is None:
                self._connection = connect(
                    self._login, database=self._database, env=self._env
                )
        return self._connection.cursor()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
