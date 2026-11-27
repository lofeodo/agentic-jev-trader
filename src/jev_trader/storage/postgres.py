"""Logging in to Postgres as one of the project's programs (spec appendix 11, sections 1 and 4).

Each program logs in as its own Postgres role, with the least it needs: `trading_agent_builder`
(the dataset builder), `trading_agent_sim`, `trading_agent_memory` (can only read: ADR 0006),
`trading_agent_api` and `trading_agent_setup` (makes the tables). Each role's password lives in
`.env` as `POSTGRES_<LOGIN>_PASSWORD`, beside the database's address (`POSTGRES_HOST`,
`POSTGRES_PORT`). Connections are encrypted (`POSTGRES_SSL_MODE`, `require` unless set; the local
Postgres in Docker that the database tests use has no encryption, so it sets `disable`).

**One connection per process.** Opening a new encrypted connection to Montreal takes about 0.2
seconds, so a program opens one per login and database and reuses it: `connection` hands back
the same `OneConnection` each time it is asked. A `OneConnection` logs in when first used, not
when made, so a server starts and answers its health address before the database is reached,
and a missing setting still fails at once.

Statements use `%s` placeholders. Each statement commits on its own (autocommit, as Snowflake's
connector does); a store that writes several statements all or nothing opens a transaction
itself (`with connection.transaction(): ...`).

The database names are the Snowflake ones in lower case (`trading_agent`,
`trading_agent_test`), so `--database TRADING_AGENT_TEST` names the test database on either.
"""

import os
import threading
from collections.abc import Mapping

from jev_trader.storage import LoginNotSet

DATABASE = "trading_agent"
TEST_DATABASE = "trading_agent_test"
LOGINS = ("builder", "sim", "memory", "api", "setup")
DEFAULT_PORT = 5432
DEFAULT_SSL_MODE = "require"


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise LoginNotSet(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def role(login: str) -> str:
    """The Postgres role `login` (`builder`, `sim`, ...) logs in as."""
    if login not in LOGINS:
        raise ValueError(f"No login named {login!r}; the logins are {LOGINS}.")
    return f"trading_agent_{login}"


def password_variable(login: str) -> str:
    """The `.env` variable holding `login`'s password."""
    role(login)
    return f"POSTGRES_{login.upper()}_PASSWORD"


def settings(
    login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ
) -> dict:
    """What `login` connects with, read from `env`. LoginNotSet names a missing setting."""
    return {
        "host": _required(env, "POSTGRES_HOST"),
        "port": int((env.get("POSTGRES_PORT") or "").strip() or DEFAULT_PORT),
        "dbname": database.lower(),
        "user": role(login),
        "password": _required(env, password_variable(login)),
        "sslmode": (env.get("POSTGRES_SSL_MODE") or "").strip() or DEFAULT_SSL_MODE,
    }


def connect(login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ):
    """A new connection as `login`. Programs use `connection` instead, which reuses one."""
    import psycopg

    return psycopg.connect(**settings(login, database, env), autocommit=True)


class OneConnection:
    """One connection as `login` to `database`, opened on first use and kept open for the rest
    of the process. A connection the database closed (a restart, a dropped line) is opened again
    on the next use; a statement under way when it dropped fails as usual."""

    def __init__(
        self, login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ
    ):
        self._settings = settings(login, database, env)
        self._connection = None
        self._lock = threading.Lock()

    def _open(self):
        import psycopg

        with self._lock:
            if self._connection is None or self._connection.closed:
                self._connection = psycopg.connect(**self._settings, autocommit=True)
            return self._connection

    def cursor(self):
        return self._open().cursor()

    def transaction(self):
        """All the statements inside commit together, or none of them does."""
        return self._open().transaction()

    def pipeline(self):
        """The statements inside go to the database together, in one round trip."""
        return self._open().pipeline()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


_opened: dict[tuple[str, str], OneConnection] = {}
_opened_lock = threading.Lock()


def connection(
    login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ
) -> OneConnection:
    """This process's one connection as `login` to `database`: the same object each time."""
    key = (login, database.lower())
    with _opened_lock:
        if key not in _opened:
            _opened[key] = OneConnection(login, database, env)
        return _opened[key]
