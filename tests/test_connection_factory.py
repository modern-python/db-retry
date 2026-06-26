import os
import typing
from unittest import mock

import asyncpg
import pytest
import sqlalchemy
from asyncpg.connect_utils import SessionAttribute
from sqlalchemy.ext import asyncio as sa_async

from db_retry.connections import ConnectionPlan, build_connection_factory, build_connection_plan


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


def test_build_connection_plan_multihost() -> None:
    url: typing.Final = sqlalchemy.make_url(
        "postgresql+asyncpg://user:password@/database?host=host1:5432&host=host2:5432&target_session_attrs=read-write"
    )
    plan: typing.Final[ConnectionPlan] = build_connection_plan(url)
    assert set(plan.failover) == {("host1", 5432), ("host2", 5432)}
    assert isinstance(plan.primary_host, list)
    assert isinstance(plan.primary_port, list)
    assert list(zip(plan.primary_host, plan.primary_port, strict=True)) == list(plan.failover)
    assert plan.target_session_attrs == SessionAttribute("read-write")
    assert "host" not in plan.connect_args
    assert "port" not in plan.connect_args
    assert "target_session_attrs" not in plan.connect_args


def test_build_connection_plan_single_host() -> None:
    port: typing.Final = 5432
    url: typing.Final = sqlalchemy.make_url(f"postgresql+asyncpg://user:password@host1:{port}/database")
    plan: typing.Final[ConnectionPlan] = build_connection_plan(url)
    assert plan.failover == ()
    assert plan.primary_host == "host1"
    assert plan.primary_port == port
    assert plan.target_session_attrs is None
    assert "host" not in plan.connect_args
    assert "port" not in plan.connect_args
    assert "target_session_attrs" not in plan.connect_args
