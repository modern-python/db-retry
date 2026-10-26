import asyncio
import typing

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext import asyncio as sa_async

from db_retry import Transaction
from db_retry.retry import postgres_retry


def _retriable_error() -> DBAPIError:
    orig = Exception("connection lost")
    orig.__cause__ = asyncpg.PostgresConnectionError()
    return DBAPIError("SELECT 1", None, orig)


def _record_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retry loop's sleep with a recorder, so attempt counts cost no wall time."""
    waits: list[float] = []

    async def _record(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _record)
    return waits


@pytest.mark.parametrize(
    ("error_code", "expected_calls"),
    [
        ("40001", 2),  # SerializationError - backoff triggered, 1 retry
        ("40P01", 2),  # DeadlockDetectedError - backoff triggered, 1 retry
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

    assert waits, "asyncio.sleep is no longer the retry loop's sleep; this test would wait out real backoff"


async def test_a_retry_never_re_runs_the_body_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: every retry is separated from the attempt before it by a non-zero wait.

    Broken by dropping the ``asyncio.sleep`` from the retry loop, or making ``_backoff`` return
    ``0`` -- a change that keeps every attempt-count assertion in this file green, because the
    counts do not depend on the delay. Every retriable class is lock contention or an unreachable server,
    and re-running instantly turns one serialization conflict or deadlock into a spin against the same
    rows and one refused connection into a flood at a node that is already down. Tuning the curve --
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


@pytest.mark.usefixtures("lost_pooled_connection")
async def test_a_connection_closed_while_pooled_is_retried_through_a_transaction(
    async_engine: sa_async.AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_backoff(monkeypatch)
    attempts = 0

    async with sa_async.AsyncSession(async_engine) as session:
        transaction: typing.Final = Transaction(session=session)

        @postgres_retry(retries=2)
        async def select_one() -> int | None:
            nonlocal attempts
            attempts += 1
            async with transaction:
                return await session.scalar(sqlalchemy.text("SELECT 1"))

        assert await select_one() == 1
    assert attempts == 2  # noqa: PLR2004  # the closed connection, then a fresh one


async def test_a_connection_lost_after_the_transaction_is_retried(
    async_engine: sa_async.AsyncEngine,
    kill_idle_connection: typing.Callable[[], typing.Awaitable[None]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_backoff(monkeypatch)
    attempts = 0

    async with sa_async.AsyncSession(async_engine) as session:
        transaction: typing.Final = Transaction(session=session)

        @postgres_retry(retries=2)
        async def read_after_the_block() -> int | None:
            nonlocal attempts
            attempts += 1
            async with transaction:
                await session.scalar(sqlalchemy.text("SELECT 1"))
                await transaction.commit()
            if attempts == 1:
                await kill_idle_connection()
            return await session.scalar(sqlalchemy.text("SELECT 2"))

        assert await read_after_the_block() == 2  # noqa: PLR2004
    assert attempts == 2  # noqa: PLR2004


async def test_a_retriable_first_failure_waits_once_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: typing.Final = _record_backoff(monkeypatch)
    attempts = 0

    @postgres_retry(retries=3)
    async def _fails_once() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _retriable_error()
        return attempts

    assert await _fails_once() == 2  # noqa: PLR2004  # the failed attempt, then the one that succeeds
    assert len(waits) == 1
    assert waits[0] > 0


async def test_a_deadlock_victim_is_rolled_back_and_re_run_through_a_transaction(
    async_engine: sa_async.AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_backoff(monkeypatch)
    async with async_engine.begin() as connection:
        await connection.execute(sqlalchemy.text("CREATE TABLE deadlock_victim_writes (attempt INT NOT NULL)"))
    attempts = 0

    try:
        async with sa_async.AsyncSession(async_engine) as session:
            transaction: typing.Final = Transaction(session=session)

            @postgres_retry(retries=2)
            async def write_then_deadlock_once() -> None:
                nonlocal attempts
                attempts += 1
                async with transaction:
                    await session.execute(
                        sqlalchemy.text("INSERT INTO deadlock_victim_writes VALUES (:attempt)"), {"attempt": attempts}
                    )
                    if attempts == 1:
                        await session.execute(sqlalchemy.text("DO $$ BEGIN RAISE SQLSTATE '40P01'; END $$"))
                    await transaction.commit()

            await write_then_deadlock_once()

        async with async_engine.connect() as connection:
            written: typing.Final = (
                await connection.scalars(sqlalchemy.text("SELECT attempt FROM deadlock_victim_writes"))
            ).all()
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(sqlalchemy.text("DROP TABLE deadlock_victim_writes"))

    assert attempts == 2  # noqa: PLR2004
    assert written == [2]
