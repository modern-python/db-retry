import dataclasses
import logging
import random
import types
import typing
from operator import itemgetter

import asyncpg
import sqlalchemy
from asyncpg.connect_utils import SessionAttribute
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg


if typing.TYPE_CHECKING:
    ConnectionType = asyncpg.Connection[typing.Any]


logger = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class ConnectionPlan:
    connect_args: typing.Mapping[str, typing.Any]
    target_session_attrs: SessionAttribute | None
    failover: tuple[tuple[str, int], ...]


def parse_connect_args(url: sqlalchemy.URL) -> tuple[dict[str, typing.Any], list[tuple[str, int]]]:
    connect_args: typing.Final[dict[str, typing.Any]] = PGDialect_asyncpg().create_connect_args(url)[1]
    hosts: typing.Final = connect_args.get("host")
    ports: typing.Final = connect_args.get("port")
    if isinstance(hosts, list) and isinstance(ports, list):
        return connect_args, list(zip(hosts, ports, strict=True))
    return connect_args, []


def build_connection_plan(url: sqlalchemy.URL) -> ConnectionPlan:
    connect_args, hosts_and_ports = parse_connect_args(url)
    raw_target_session_attrs: str | None = connect_args.pop("target_session_attrs", None)
    target_session_attrs: SessionAttribute | None = (
        SessionAttribute(raw_target_session_attrs) if raw_target_session_attrs else None
    )
    if hosts_and_ports:
        del connect_args["host"], connect_args["port"]
    return ConnectionPlan(
        connect_args=types.MappingProxyType(connect_args),
        target_session_attrs=target_session_attrs,
        failover=tuple(hosts_and_ports),
    )


async def _connect(
    plan: ConnectionPlan,
    timeout: float,  # noqa: ASYNC109
    **address: str | int | list[str] | list[int],
) -> "ConnectionType":
    return await asyncpg.connect(
        **plan.connect_args,
        **address,
        timeout=timeout,
        target_session_attrs=plan.target_session_attrs,
    )


def _shuffled(failover: tuple[tuple[str, int], ...]) -> list[tuple[str, int]]:
    return random.sample(failover, len(failover))


def build_connection_factory(
    url: sqlalchemy.URL,
    timeout: float,
) -> typing.Callable[[], typing.Awaitable["ConnectionType"]]:
    plan: typing.Final = build_connection_plan(url)

    async def _connection_factory() -> "ConnectionType":
        if not plan.failover:
            return await _connect(plan, timeout)

        bulk_order: typing.Final = _shuffled(plan.failover)
        try:
            return await _connect(
                plan,
                timeout,
                host=list(map(itemgetter(0), bulk_order)),
                port=list(map(itemgetter(1), bulk_order)),
            )
        except TimeoutError:
            logger.warning("Failed to fetch asyncpg connection. Trying host by host.")

        for host, port in _shuffled(plan.failover):
            try:
                return await _connect(plan, timeout, host=host, port=port)
            except (TimeoutError, OSError, asyncpg.TargetServerAttributeNotMatched) as exc:
                logger.warning("Failed to fetch asyncpg connection from %s, %s", host, exc)
        msg: typing.Final = f"None of the hosts match the target attribute requirement {plan.target_session_attrs}"
        raise asyncpg.TargetServerAttributeNotMatched(msg)

    return _connection_factory
