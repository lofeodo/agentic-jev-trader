"""All database access goes through this one module."""

from collections.abc import Mapping


class LoginNotSet(Exception):
    """A database setting is missing from `.env`, or wrong; the message names it."""


def required_setting(env: Mapping[str, str], name: str) -> str:
    """The setting `name` from `env`, stripped. LoginNotSet if it is empty or missing."""
    value = (env.get(name) or "").strip()
    if not value:
        raise LoginNotSet(f"{name} is not set. Add it to .env (see .env.example).")
    return value


class NotBuiltYet(NotImplementedError):
    """A Postgres store's read or write that a later ticket of the Postgres slice fills in."""

    def __init__(self, ticket: int):
        super().__init__(
            f"Not built yet on Postgres: ticket #{ticket} fills this in. "
            "Set DATABASE_ENGINE=snowflake in .env meanwhile."
        )
