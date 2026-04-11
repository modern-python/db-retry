import os
import typing
from unittest import mock

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.ext import asyncio as sa_async

from db_retry.connections import build_connection_factory


async def test_connection_factory_success() -> None:
    url: typing.Final = sqlalchemy.make_url(os.getenv("DB_DSN", ""))
    engine: typing.Final = sa_async.create_async_engine(
        url=url, echo=True, echo_pool=True, async_creator=build_connection_factory(url=url, timeout=1.0)
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(sqlalchemy.text("""SELECT 1"""))
    finally:
        await engine.dispose()


async def test_connection_factory_failure_single_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncpg.connect", mock.Mock(side_effect=TimeoutError))
    url: typing.Final = sqlalchemy.make_url(os.getenv("DB_DSN", ""))
    engine: typing.Final = sa_async.create_async_engine(
        url=url, echo=True, echo_pool=True, async_creator=build_connection_factory(url=url, timeout=1.0)
    )
    try:
        with pytest.raises(TimeoutError):
            await engine.connect().__aenter__()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("target_session_attrs", ["read-only", "read-write"])
async def test_connection_factory_failure_several_hosts(
    monkeypatch: pytest.MonkeyPatch, target_session_attrs: str
) -> None:
    monkeypatch.setattr("asyncpg.connect", mock.Mock(side_effect=TimeoutError))
    url: typing.Final = sqlalchemy.make_url(
        f"postgresql+asyncpg://user:password@/database?host=host1:5432&host=host2:5432&"
        f"target_session_attrs={target_session_attrs}"
    )
    engine: typing.Final = sa_async.create_async_engine(
        url=url, echo=True, echo_pool=True, async_creator=build_connection_factory(url=url, timeout=1.0)
    )
    try:
        with pytest.raises(asyncpg.TargetServerAttributeNotMatched):
            await engine.connect().__aenter__()
    finally:
        await engine.dispose()


async def test_connection_factory_failure_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_connection: typing.Final = mock.AsyncMock(spec=asyncpg.Connection)
    monkeypatch.setattr("asyncpg.connect", mock.AsyncMock(side_effect=(TimeoutError, mock_connection)))
    url: typing.Final = sqlalchemy.make_url(
        "postgresql+asyncpg://user:password@/database?host=host1:5432&host=host2:5432"
    )
    factory: typing.Final = build_connection_factory(url=url, timeout=1.0)
    result = await factory()
    assert result is mock_connection
