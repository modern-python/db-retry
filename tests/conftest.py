import asyncio
import os
import typing

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.ext import asyncio as sa_async


@pytest.fixture
async def async_engine() -> typing.AsyncIterator[sa_async.AsyncEngine]:
    engine: typing.Final = sa_async.create_async_engine(url=os.environ["DB_DSN"], echo=True, echo_pool=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def kill_idle_connection(async_engine: sa_async.AsyncEngine) -> typing.Callable[[], typing.Awaitable[None]]:
    """Return a coroutine function that leaves the pool's idle connection with its backend terminated."""

    async def _kill() -> None:
        async with async_engine.connect() as connection:
            pooled: typing.Final = (await connection.get_raw_connection()).driver_connection
            assert pooled is not None
            pid: typing.Final = await connection.scalar(sqlalchemy.text("SELECT pg_backend_pid()"))
        closed: typing.Final = asyncio.Event()

        def _on_close(_: asyncpg.Connection) -> None:
            closed.set()

        pooled.add_termination_listener(_on_close)
        killer: typing.Final = await asyncpg.connect(
            async_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
        )
        try:
            await killer.execute("SELECT pg_terminate_backend($1)", pid)
        finally:
            await killer.close()
        await asyncio.wait_for(closed.wait(), timeout=5)

    return _kill


@pytest.fixture
async def lost_pooled_connection(kill_idle_connection: typing.Callable[[], typing.Awaitable[None]]) -> None:
    """Leave the engine's pool holding one idle connection whose backend was terminated."""
    await kill_idle_connection()
