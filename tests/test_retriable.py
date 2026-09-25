import asyncpg
import pytest
from sqlalchemy.exc import DBAPIError

from db_retry.retriable import RETRIABLE_ASYNCPG_ERRORS, is_retriable


def _make_dbapi_error(cause: BaseException) -> DBAPIError:
    orig = Exception("db error")
    orig.__cause__ = cause
    err = DBAPIError("SELECT 1", None, orig)
    assert err.orig is not None  # the predicate hinges on .orig being set; make the invariant explicit
    return err


def test_retriable_asyncpg_errors_contains_expected_classes() -> None:
    assert asyncpg.SerializationError in RETRIABLE_ASYNCPG_ERRORS
    assert asyncpg.PostgresConnectionError in RETRIABLE_ASYNCPG_ERRORS


def test_a_statement_of_unknown_outcome_is_never_retriable() -> None:
    """INVARIANT: ``asyncpg.StatementCompletionUnknownError`` never classifies as retriable.

    Broken by widening the taxonomy to a base class that swallows it -- and the tempting
    base is ``asyncpg.TransactionRollbackError``, because the retriable
    ``SerializationError`` is a sibling underneath it. The two are not interchangeable. A
    serialization failure definitely rolled back, so repeating the operation is free;
    ``40003`` means the server lost track of whether the statement committed, so repeating
    it can apply a write twice. Everything above this predicate treats a retry as a repeat
    of something that did not happen, and only this boundary makes that true.
    """
    assert is_retriable(_make_dbapi_error(asyncpg.StatementCompletionUnknownError())) is False


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
        pytest.param(asyncpg.SerializationError(), True, id="raw_serialization_error_40001"),
        pytest.param(asyncpg.PostgresConnectionError(), True, id="raw_postgres_connection_error_08000"),
        pytest.param(asyncpg.StatementCompletionUnknownError(), False, id="raw_statement_completion_unknown_40003"),
        pytest.param(asyncpg.PostgresError(), False, id="raw_non_retriable_postgres_error"),
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


def test_is_retriable_cycle_containing_retriable_link() -> None:
    # A cyclic chain that *contains* a retriable DBAPIError still returns True:
    # the walk finds the retriable link before the cycle guard would re-visit a node.
    outer = ValueError("outer")
    dbapi_err = _make_dbapi_error(asyncpg.SerializationError())
    outer.__cause__ = dbapi_err
    dbapi_err.__cause__ = outer
    assert is_retriable(outer) is True
