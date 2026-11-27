"""Logging in to the database: `postgres.py` connects, `database.py` hands out the stores."""

from collections.abc import Mapping


class LoginNotSet(Exception):
    """A database setting is missing from `.env`, or wrong; the message names it."""


def required_setting(env: Mapping[str, str], name: str) -> str:
    """The setting `name` from `env`, stripped. LoginNotSet if it is empty or missing."""
    value = (env.get(name) or "").strip()
    if not value:
        raise LoginNotSet(f"{name} is not set. Add it to .env (see .env.example).")
    return value
