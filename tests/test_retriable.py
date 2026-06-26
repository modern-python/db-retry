import asyncpg
import pytest
from sqlalchemy.exc import DBAPIError

from db_retry.retriable import RETRIABLE_ASYNCPG_ERRORS, is_retriable


def _make_dbapi_error(cause: BaseException) -> DBAPIError:
    orig = Exception("db error")
    orig.__cause__ = cause
    return DBAPIError("SELECT 1", None, orig)


def test_retriable_asyncpg_errors_contains_expected_classes() -> None:
    assert asyncpg.SerializationError in RETRIABLE_ASYNCPG_ERRORS
    assert asyncpg.PostgresConnectionError in RETRIABLE_ASYNCPG_ERRORS


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        pytest.param(_make_dbapi_error(asyncpg.SerializationError()), True, id="serialization_error_40001"),
        pytest.param(_make_dbapi_error(asyncpg.PostgresConnectionError()), True, id="postgres_connection_error_08000"),
        pytest.param(
            _make_dbapi_error(asyncpg.ConnectionDoesNotExistError()), True, id="connection_does_not_exist_08003"
        ),
        pytest.param(_make_dbapi_error(asyncpg.PostgresError()), False, id="non_retriable_postgres_error"),
        pytest.param(ValueError("not a db error"), False, id="bare_non_dbapi_exception"),
    ],
)
def test_is_retriable(exception: BaseException, expected: bool) -> None:
    assert is_retriable(exception) == expected


def test_is_retriable_rewrapped_cause() -> None:
    class RepositoryError(Exception):
        pass

    dbapi_err = _make_dbapi_error(asyncpg.SerializationError())
    repo_err = RepositoryError("wrapped")
    repo_err.__cause__ = dbapi_err
    assert is_retriable(repo_err) is True


def test_is_retriable_context_only() -> None:
    dbapi_err = _make_dbapi_error(asyncpg.SerializationError())
    wrapper = ValueError("wrapper")
    wrapper.__context__ = dbapi_err
    assert is_retriable(wrapper) is True


def test_is_retriable_cause_cycle_terminates() -> None:
    a = ValueError("a")
    b = ValueError("b")
    a.__cause__ = b
    b.__cause__ = a
    assert is_retriable(a) is False
