import asyncio
import functools
import logging
import random
import typing

from db_retry import settings
from db_retry.retriable import is_retriable


logger = logging.getLogger(__name__)


def _log_and_decide(exception: BaseException) -> bool:
    if is_retriable(exception):
        logger.debug("postgres_retry, retrying")
        return True
    logger.debug("postgres_retry, giving up on retry")
    return False


def _backoff(attempt: int) -> float:
    return 2 ** (attempt - 1) + random.uniform(0, 1)  # noqa: S311


P = typing.ParamSpec("P")
T = typing.TypeVar("T")

_Func: typing.TypeAlias = typing.Callable[P, typing.Coroutine[None, None, T]]
_Decorator: typing.TypeAlias = typing.Callable[[_Func], _Func]


@typing.overload
def postgres_retry(func: _Func, *, retries: int | None = ...) -> _Func: ...


@typing.overload
def postgres_retry(func: None = ..., *, retries: int | None = ...) -> _Decorator: ...


def postgres_retry(
    func: _Func | None = None,
    *,
    retries: int | None = None,
) -> _Func | _Decorator:
    def decorator(f: _Func[P, T]) -> _Func[P, T]:
        @functools.wraps(f)
        async def wrapped_method(*args: P.args, **kwargs: P.kwargs) -> T:
            attempt = 1
            while True:
                try:
                    return await f(*args, **kwargs)
                except Exception as exception:
                    attempts = retries if retries is not None else settings.get_retries_number()
                    if not _log_and_decide(exception) or attempt >= attempts:
                        raise
                await asyncio.sleep(_backoff(attempt))
                attempt += 1

        return wrapped_method

    if func is not None:
        return decorator(func)
    return decorator
