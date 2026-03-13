import functools
import logging
import typing

import asyncpg
import tenacity
from sqlalchemy.exc import DBAPIError

from db_retry import settings


logger = logging.getLogger(__name__)


def _retry_handler(exception: BaseException) -> bool:
    if (
        isinstance(exception, DBAPIError)
        and hasattr(exception, "orig")
        and isinstance(exception.orig.__cause__, (asyncpg.SerializationError, asyncpg.PostgresConnectionError))  # type: ignore[union-attr]
    ):
        logger.debug("postgres_retry, retrying")
        return True

    logger.debug("postgres_retry, giving up on retry")
    return False


def postgres_retry[**P, T](
    func: typing.Callable[P, typing.Coroutine[None, None, T]],
) -> typing.Callable[P, typing.Coroutine[None, None, T]]:
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(settings.DB_RETRY_RETRIES_NUMBER),
        wait=tenacity.wait_exponential_jitter(),
        retry=tenacity.retry_if_exception(_retry_handler),
        reraise=True,
        before=tenacity.before_log(logger, logging.DEBUG),  # ty: ignore[invalid-argument-type]
    )
    @functools.wraps(func)
    async def wrapped_method(*args: P.args, **kwargs: P.kwargs) -> T:
        return await func(*args, **kwargs)

    return wrapped_method
