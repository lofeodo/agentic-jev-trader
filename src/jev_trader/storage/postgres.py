"""Logging in to Postgres as one of the project's programs (spec appendix 11, sections 1 and 4).

Each program logs in as its own Postgres role, with the least it needs: `trading_agent_builder`
(the dataset builder), `trading_agent_sim`, `trading_agent_memory` (can only read: ADR 0006),
`trading_agent_api` and `trading_agent_setup` (makes the tables). Each role's password lives in
`.env` as `POSTGRES_<LOGIN>_PASSWORD`, beside the database's address (`POSTGRES_HOST`,
`POSTGRES_PORT`). Connections are encrypted (`POSTGRES_SSL_MODE`, `require` unless set; the local
Postgres in Docker that the database tests use has no encryption, so it sets `disable`).

**One connection per process.** Opening a new encrypted connection to Montreal takes about 0.2
seconds, so a program opens one per login and database and reuses it: `connection` hands back
the same `OneConnection` each time it is asked with the same settings. A `OneConnection` logs in
when first used, not when made, so a server starts and answers its health address before the
database is reached, and a missing setting still fails at once.

Statements use `%s` placeholders. Each statement commits on its own (autocommit, as Snowflake's
connector does); a store that writes several statements all or nothing opens a transaction
itself (`with connection.transaction(): ...`), which waits for the database's answer to its
start, each statement and its end. To send them all in one round trip, a store writes them in
`with connection.transaction_in_one_trip() as cursor: ...`: `BEGIN`, the statements and
`COMMIT` go together in psycopg's pipeline mode (statements sent together, answered together).
psycopg's own `transaction()` inside `pipeline()` would wait for its start and end: 3 or 4
trips. Since no answer comes back before the end, a check that must stop the write goes inside
the SQL (a statement that fails), not in Python between statements.

**Threads.** The API and the memory server answer requests on several threads, all through the
one connection. psycopg runs one statement at a time on it, but a transaction is the
connection's, not the thread's: while one thread is inside `transaction()`, another thread's
statements would land in it. So `transaction()` holds the connection for its whole block, and
a thread outside one waits for the block to end before its own statement runs.

The database names are the Snowflake ones in lower case (`trading_agent`,
`trading_agent_test`), so `--database TRADING_AGENT_TEST` names the test database on either.
"""

import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from jev_trader.storage import required_setting

DATABASE = "trading_agent"
TEST_DATABASE = "trading_agent_test"
LOGINS = ("builder", "sim", "memory", "api", "setup")
DEFAULT_PORT = 5432
DEFAULT_SSL_MODE = "require"


def as_param(value):
    """`value` as psycopg sends it: lists and dictionaries as `jsonb` (Postgres's JSON column
    type), the rest as they are."""
    if isinstance(value, dict | list):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def set_clause(columns: dict) -> tuple[str, list]:
    """An UPDATE's `SET ...` text for `columns`, and the values it sends."""
    return (
        ", ".join(f"{name} = %s" for name in columns),
        [as_param(v) for v in columns.values()],
    )


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
        "host": required_setting(env, "POSTGRES_HOST"),
        "port": int((env.get("POSTGRES_PORT") or "").strip() or DEFAULT_PORT),
        "dbname": database.lower(),
        "user": role(login),
        "password": required_setting(env, password_variable(login)),
        "sslmode": (env.get("POSTGRES_SSL_MODE") or "").strip() or DEFAULT_SSL_MODE,
    }


class OneConnection:
    """One connection with `settings`, opened on first use and kept open for the rest of the
    process. A connection the database closed (a restart, a dropped line) is opened again on
    the next use; a statement under way when it dropped fails as usual."""

    def __init__(self, settings: dict):
        self._settings = settings
        self._connection = None
        # Held to open the connection, and for the whole of a transaction (see Threads above).
        self._lock = threading.RLock()

    def _open(self):
        import psycopg

        if self._connection is None or self._connection.closed:
            self._connection = psycopg.connect(**self._settings, autocommit=True)
        return self._connection

    @contextmanager
    def cursor(self) -> Iterator:
        with self._lock, self._open().cursor() as cursor:
            yield cursor

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """All the statements inside commit together, or none of them does."""
        with self._lock, self._open().transaction():
            yield

    @contextmanager
    def pipeline(self) -> Iterator[None]:
        """The statements inside go to the database together, in one round trip."""
        with self._lock, self._open().pipeline():
            yield

    @contextmanager
    def transaction_in_one_trip(self) -> Iterator:
        """A cursor whose statements commit together or not at all, sent with `BEGIN` and
        `COMMIT` in one round trip. No statement's answer can be read inside: a statement that
        fails raises its error as the block ends, and nothing of the block is kept."""
        import psycopg

        with self._lock:
            connection = self._open()
            try:
                with connection.pipeline(), connection.cursor() as cursor:
                    cursor.execute("BEGIN")
                    yield cursor
                    cursor.execute("COMMIT")
            except BaseException:
                # A failed statement leaves the transaction open and refusing: end it.
                idle = psycopg.pq.TransactionStatus.IDLE
                if not connection.closed and connection.info.transaction_status != idle:
                    connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


_opened: dict[tuple, OneConnection] = {}
_opened_lock = threading.Lock()


def connection(
    login: str, database: str = DATABASE, env: Mapping[str, str] = os.environ
) -> OneConnection:
    """This process's one connection as `login` to `database`: the same object each time it is
    asked with the same settings. LoginNotSet names a missing setting."""
    wanted = settings(login, database, env)
    key = tuple(sorted(wanted.items()))
    with _opened_lock:
        if key not in _opened:
            _opened[key] = OneConnection(wanted)
        return _opened[key]
