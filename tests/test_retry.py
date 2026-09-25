import asyncio
import typing

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext import asyncio as sa_async

from db_retry.retry import postgres_retry


def _retriable_error() -> DBAPIError:
    orig = Exception("connection lost")
    orig.__cause__ = asyncpg.PostgresConnectionError()
    return DBAPIError("SELECT 1", None, orig)


def _record_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retryer's sleep with a recorder, so attempt counts cost no wall time."""
    waits: list[float] = []

    async def _record(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _record)
    return waits


@pytest.mark.parametrize(
    ("error_code", "expected_calls"),
    [
        ("40001", 2),  # SerializationError - backoff triggered, 1 retry
        ("40002", 1),  # TransactionIntegrityConstraintViolationError - backoff not triggered
    ],
)
async def test_postgres_retry(async_engine: sa_async.AsyncEngine, error_code: str, expected_calls: int) -> None:
    async with async_engine.connect() as connection:
        await connection.execute(
            sqlalchemy.text(
                f"""
        CREATE OR REPLACE FUNCTION raise_error()
        RETURNS VOID AS $$
        BEGIN
            RAISE SQLSTATE '{error_code}';
        END;
        $$ LANGUAGE plpgsql;
        """,
            ),
        )

        call_count = 0

        @postgres_retry
        async def raise_error() -> None:
            nonlocal call_count
            call_count += 1
            await connection.execute(sqlalchemy.text("SELECT raise_error()"))

        with pytest.raises(DBAPIError):
            await raise_error()

        assert call_count == expected_calls


async def test_postgres_retry_with_retries(async_engine: sa_async.AsyncEngine) -> None:
    async with async_engine.connect() as connection:
        await connection.execute(
            sqlalchemy.text("""
        CREATE OR REPLACE FUNCTION raise_error()
        RETURNS VOID AS $$
        BEGIN
            RAISE SQLSTATE '40001';
        END;
        $$ LANGUAGE plpgsql;
        """),
        )

        call_count = 0

        @postgres_retry(retries=1)
        async def raise_error() -> None:
            nonlocal call_count
            call_count += 1
            await connection.execute(sqlalchemy.text("SELECT raise_error()"))

        with pytest.raises(DBAPIError):
            await raise_error()

        assert call_count == 1


async def test_the_default_attempt_count_is_re_read_on_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: a bare ``@postgres_retry`` resolves its attempt count per call, not at decoration.

    Broken by hoisting ``settings.get_retries_number()`` anywhere outside ``wrapped_method`` -- into
    the ``decorator`` body, into a default argument, or into a module-level constant. Each of those
    reads the environment correctly exactly once and then freezes, which no test that sets the
    variable before importing can see. `DB_RETRY_RETRIES_NUMBER` is this package's whole
    configuration surface (`docs/adr/0001-retry-default-stays-env-configured.md` declined an
    injectable resolver precisely because the env read already gives callers control), so a process
    that retunes it expects the running decorator to follow without a reimport, and a deployment
    lowering it during an incident expects the retry storm to stop now rather than after a restart.
    """
    waits: typing.Final = _record_backoff(monkeypatch)
    attempts = 0

    @postgres_retry
    async def _always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise _retriable_error()

    for configured in ("1", "4", "2"):
        monkeypatch.setenv("DB_RETRY_RETRIES_NUMBER", configured)
        attempts = 0
        with pytest.raises(DBAPIError):
            await _always_fails()
        assert attempts == int(configured)

    assert waits, "asyncio.sleep is no longer the retryer's sleep; this test would wait out real backoff"


async def test_a_retry_never_re_runs_the_body_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: every retry is separated from the attempt before it by a non-zero wait.

    Broken by dropping ``wait=tenacity.wait_exponential_jitter()`` from the retryer, or swapping it
    for ``wait_none()`` -- a change that keeps every attempt-count assertion in this file green,
    because the counts do not depend on the delay. Waiting is the reason to reach for tenacity at
    all rather than a bare loop: both retriable classes are failures of an overloaded or unreachable
    server, and re-running instantly turns one serialization conflict into a spin against the same
    row and one refused connection into a flood at a node that is already down. Tuning the curve --
    the initial delay, the base, how much jitter -- stays within the invariant; removing the wait
    does not.
    """
    waits: typing.Final = _record_backoff(monkeypatch)

    @postgres_retry(retries=4)
    async def _always_fails() -> None:
        raise _retriable_error()

    with pytest.raises(DBAPIError):
        await _always_fails()

    assert len(waits) == 3  # noqa: PLR2004  # four attempts, one wait between each pair
    assert all(wait > 0 for wait in waits)


async def test_a_connect_time_connection_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    _record_backoff(monkeypatch)
    attempts = 0

    async def _refusing_creator() -> asyncpg.Connection:
        nonlocal attempts
        attempts += 1
        msg = "connection refused"
        raise asyncpg.PostgresConnectionError(msg)

    engine: typing.Final = sa_async.create_async_engine("postgresql+asyncpg://", async_creator=_refusing_creator)
    expected_attempts: typing.Final = 2

    @postgres_retry(retries=expected_attempts)
    async def connect() -> None:
        await engine.connect().__aenter__()

    try:
        with pytest.raises((asyncpg.PostgresConnectionError, DBAPIError)):
            await connect()
    finally:
        await engine.dispose()
    assert attempts == expected_attempts
