import os
import typing
from unittest import mock

import asyncpg
import pytest
import sqlalchemy
from asyncpg.connect_utils import SessionAttribute
from sqlalchemy import exc as sa_exc
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
        with pytest.raises((asyncpg.TargetServerAttributeNotMatched, sa_exc.InternalError)) as exc_info:
            await engine.connect().__aenter__()
    finally:
        await engine.dispose()
    raised = exc_info.value
    root = raised.orig.__cause__ if isinstance(raised, sa_exc.InternalError) and raised.orig is not None else raised
    assert isinstance(root, asyncpg.TargetServerAttributeNotMatched)


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
    assert plan.target_session_attrs == SessionAttribute("read-write")
    assert "host" not in plan.connect_args
    assert "port" not in plan.connect_args
    assert "target_session_attrs" not in plan.connect_args


def test_host_and_port_stay_paired_through_the_shuffle() -> None:
    """INVARIANT: no plan ever pairs one host's name with another host's port.

    Broken by shuffling ``primary_host`` and ``primary_port`` as two independent lists, or by
    deriving ``failover`` from a second shuffle of its own rather than from the one that produced
    the primary order. Both read as tidier code and both silently mis-pair. Nothing downstream can
    catch it: ``_connect`` hands whatever pair it is given straight to asyncpg, so a swap surfaces
    as a refused connection that is indistinguishable from a host being down -- on the failover
    path, which by definition only runs when hosts are already failing. This is also why the DSN
    here gives each host a distinct port; with matching ports a swap is unobservable. Six hosts
    rather than two for the same reason: the assertions are order-independent, so a mis-pairing
    build can still be let through by a shuffle that happens to come out in step, and six hosts put
    that at one run in 720 instead of one in two.
    """
    expected: typing.Final = {(f"host{n}", 5431 + n) for n in range(1, 7)}
    hosts: typing.Final = "&".join(f"host={host}:{port}" for host, port in sorted(expected))
    plan: typing.Final[ConnectionPlan] = build_connection_plan(
        sqlalchemy.make_url(f"postgresql+asyncpg://user:password@/database?{hosts}")
    )
    assert isinstance(plan.primary_host, list)
    assert isinstance(plan.primary_port, list)
    assert set(plan.failover) == expected
    assert set(zip(plan.primary_host, plan.primary_port, strict=True)) == expected
    assert list(zip(plan.primary_host, plan.primary_port, strict=True)) == list(plan.failover)


def test_build_connection_plan_connect_args_is_read_only() -> None:
    url: typing.Final = sqlalchemy.make_url("postgresql+asyncpg://user:password@host1:5432/database")
    plan: typing.Final[ConnectionPlan] = build_connection_plan(url)
    with pytest.raises(TypeError):
        plan.connect_args["injected"] = "value"  # ty: ignore[invalid-assignment]  # read-only at runtime


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
