import asyncpg
from sqlalchemy.exc import DBAPIError


RETRIABLE_ASYNCPG_ERRORS = (asyncpg.SerializationError, asyncpg.PostgresConnectionError)


def _is_retriable_link(exception: BaseException) -> bool:
    candidate = (
        exception.orig.__cause__ if isinstance(exception, DBAPIError) and exception.orig is not None else exception
    )
    return isinstance(candidate, RETRIABLE_ASYNCPG_ERRORS)


def is_retriable(exception: BaseException) -> bool:
    """Walk __cause__/__context__; True if any link is a retriable asyncpg error, raw or wrapped in a DBAPIError."""
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _is_retriable_link(current):
            return True
        current = current.__cause__ or current.__context__
    return False
