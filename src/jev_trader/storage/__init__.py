"""All database access goes through this one module."""


class LoginNotSet(Exception):
    """A database setting is missing from `.env`; the message names it."""


class NotBuiltYet(NotImplementedError):
    """A Postgres store's read or write that a later ticket of the Postgres slice fills in."""

    def __init__(self, ticket: int):
        super().__init__(
            f"Not built yet on Postgres: ticket #{ticket} fills this in. "
            "Set DATABASE_ENGINE=snowflake in .env meanwhile."
        )
