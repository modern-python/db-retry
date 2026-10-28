import asyncio
import contextlib
import os
import typing
from unittest import mock

import pytest
import sqlalchemy
from sqlalchemy.ext import asyncio as sa_async

from db_retry.connections import build_connection_factory


COMMAND_TIMEOUT_SECONDS: typing.Final = 0.5
HANG_BUDGET_SECONDS: typing.Final = 5.0


class FreezingProxy:
    """TCP proxy whose freeze() silences the connections open so far while still forwarding new ones."""

    def __init__(self, upstream_host: str, upstream_port: int) -> None:
        self._upstream: typing.Final = (upstream_host, upstream_port)
        self._pumps: list[asyncio.Task[None]] = []
        self._writers: list[asyncio.StreamWriter] = []
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return int(self._server.sockets[0].getsockname()[1])

    def freeze(self) -> None:
        for pump in self._pumps:
            pump.cancel()
        self._pumps.clear()

    async def close(self) -> None:
        self.freeze()
        for writer in self._writers:
            writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        upstream_reader, upstream_writer = await asyncio.open_connection(*self._upstream)
        self._writers += [client_writer, upstream_writer]
        self._pumps += [
            asyncio.create_task(self._pump(client_reader, upstream_writer)),
            asyncio.create_task(self._pump(upstream_reader, client_writer)),
        ]

    @staticmethod
    async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(ConnectionError):
            while chunk := await reader.read(65536):
                writer.write(chunk)
                await writer.drain()


@pytest.fixture
async def proxied_url() -> typing.AsyncIterator[tuple[sqlalchemy.URL, FreezingProxy]]:
    url: typing.Final = sqlalchemy.make_url(os.environ["DB_DSN"])
    proxy: typing.Final = FreezingProxy(url.host or "localhost", url.port or 5432)
    port: typing.Final = await proxy.start()
    try:
        yield url.set(host="127.0.0.1", port=port), proxy
    finally:
        await proxy.close()


async def test_statement_on_frozen_connection_times_out(
    proxied_url: tuple[sqlalchemy.URL, FreezingProxy],
) -> None:
    url, proxy = proxied_url
    engine: typing.Final = sa_async.create_async_engine(
        url=url,
        async_creator=build_connection_factory(url=url, timeout=1.0, command_timeout=COMMAND_TIMEOUT_SECONDS),
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(sqlalchemy.text("SELECT 1"))
        proxy.freeze()

        async with asyncio.timeout(HANG_BUDGET_SECONDS):
            with pytest.raises(TimeoutError):
                async with engine.connect() as connection:
                    await connection.execute(sqlalchemy.text("SELECT 1"))
            async with engine.connect() as connection:
                assert await connection.scalar(sqlalchemy.text("SELECT 1")) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://user:password@host/database",
        "postgresql+asyncpg://user:password@/database?host=host1:5432&host=host2:5432",
    ],
)
@pytest.mark.parametrize(
    ("dsn_command_timeout", "keyword_command_timeout", "expected"),
    [
        (None, None, None),
        (None, 2.0, 2.0),
        ("7", 2.0, "7"),
        ("7", None, "7"),
    ],
)
async def test_command_timeout_reaches_asyncpg(
    monkeypatch: pytest.MonkeyPatch,
    dsn: str,
    dsn_command_timeout: str | None,
    keyword_command_timeout: float | None,
    expected: str | float | None,
) -> None:
    connect: typing.Final = mock.AsyncMock()
    monkeypatch.setattr("asyncpg.connect", connect)
    url: typing.Final = sqlalchemy.make_url(dsn)
    factory: typing.Final = build_connection_factory(
        url=url.update_query_dict({"command_timeout": dsn_command_timeout}) if dsn_command_timeout else url,
        timeout=1.0,
        command_timeout=keyword_command_timeout,
    )

    await factory()

    assert connect.call_args.kwargs.get("command_timeout") == expected


async def test_command_timeout_defaults_to_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    connect: typing.Final = mock.AsyncMock()
    monkeypatch.setattr("asyncpg.connect", connect)

    await build_connection_factory(url=sqlalchemy.make_url("postgresql+asyncpg://user:password@host/db"), timeout=1.0)()

    assert connect.call_args.kwargs["command_timeout"] == 60.0  # noqa: PLR2004
