import pytest
import sqlalchemy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext import asyncio as sa_async

from db_retry.retry import postgres_retry


@pytest.mark.parametrize(
    ("error_code", "expected_calls"),
    [
        ("08000", 2),  # PostgresConnectionError - backoff triggered, 1 retry
        ("08003", 2),  # subclass of PostgresConnectionError - backoff triggered, 1 retry
        ("40001", 2),  # SerializationError - backoff triggered, 1 retry
        ("40002", 1),  # StatementCompletionUnknownError - backoff not triggered
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
