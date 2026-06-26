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


type _Func[**P, T] = typing.Callable[P, typing.Coroutine[None, None, T]]
type _Decorator[**P, T] = typing.Callable[[_Func[P, T]], _Func[P, T]]


@typing.overload
def postgres_retry[**P, T](func: _Func[P, T], *, retries: int | None = ...) -> _Func[P, T]: ...


@typing.overload
def postgres_retry[**P, T](func: None = ..., *, retries: int | None = ...) -> _Decorator[P, T]: ...


def postgres_retry[**P, T](
    func: _Func[P, T] | None = None,
    *,
    retries: int | None = None,
) -> _Func[P, T] | _Decorator[P, T]:
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
