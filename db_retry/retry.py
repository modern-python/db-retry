import functools
import logging
import typing

import tenacity

from db_retry import settings
from db_retry.retriable import is_retriable


logger = logging.getLogger(__name__)


def _log_and_decide(exception: BaseException) -> bool:
    if is_retriable(exception):
        logger.debug("postgres_retry, retrying")
        return True
    logger.debug("postgres_retry, giving up on retry")
    return False


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
            retryer = tenacity.AsyncRetrying(
                stop=tenacity.stop_after_attempt(retries if retries is not None else settings.get_retries_number()),
                wait=tenacity.wait_exponential_jitter(),
                retry=tenacity.retry_if_exception(_log_and_decide),
                reraise=True,
                before=tenacity.before_log(logger, logging.DEBUG),
            )
            return await retryer(f, *args, **kwargs)

        return wrapped_method

    if func is not None:
        return decorator(func)
    return decorator
