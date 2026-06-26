import dataclasses
import logging
import random
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
    primary_host: str | list[str]
    primary_port: int | list[int] | None
    failover: tuple[tuple[str, int], ...]


def build_connection_plan(url: sqlalchemy.URL) -> ConnectionPlan:
    connect_args: dict[str, typing.Any] = PGDialect_asyncpg().create_connect_args(url)[1]
    raw_target_session_attrs: str | None = connect_args.pop("target_session_attrs", None)
    target_session_attrs: SessionAttribute | None = (
        SessionAttribute(raw_target_session_attrs) if raw_target_session_attrs else None
    )
    raw_hosts: str | list[str] = connect_args.pop("host")
    raw_ports: int | list[int] | None = connect_args.pop("port", None)
    primary_host: str | list[str]
    primary_port: int | list[int] | None
    failover: tuple[tuple[str, int], ...]
    if isinstance(raw_hosts, list) and isinstance(raw_ports, list):
        hosts_and_ports: list[tuple[str, int]] = list(zip(raw_hosts, raw_ports, strict=True))
        random.shuffle(hosts_and_ports)
        primary_host = list(map(itemgetter(0), hosts_and_ports))
        primary_port = list(map(itemgetter(1), hosts_and_ports))
        failover = tuple(hosts_and_ports)
    else:
        primary_host = raw_hosts
        primary_port = raw_ports
        failover = ()
    return ConnectionPlan(
        connect_args=connect_args,
        target_session_attrs=target_session_attrs,
        primary_host=primary_host,
        primary_port=primary_port,
        failover=failover,
    )


async def _connect(
    plan: ConnectionPlan,
    host: str | list[str],
    port: int | list[int] | None,
    timeout: float,  # noqa: ASYNC109
) -> "ConnectionType":
    return await asyncpg.connect(
        **plan.connect_args,
        host=host,
        port=port,
        timeout=timeout,
        target_session_attrs=plan.target_session_attrs,
    )


def _reshuffled(failover: tuple[tuple[str, int], ...]) -> list[tuple[str, int]]:
    return random.sample(failover, len(failover))


def build_connection_factory(
    url: sqlalchemy.URL,
    timeout: float,
) -> typing.Callable[[], typing.Awaitable["ConnectionType"]]:
    plan: typing.Final = build_connection_plan(url)

    async def _connection_factory() -> "ConnectionType":
        try:
            return await _connect(plan, plan.primary_host, plan.primary_port, timeout)
        except TimeoutError:
            if not plan.failover:
                raise

            logger.warning("Failed to fetch asyncpg connection. Trying host by host.")

        for host, port in _reshuffled(plan.failover):
            try:
                return await _connect(plan, host, port, timeout)
            except (TimeoutError, OSError, asyncpg.TargetServerAttributeNotMatched) as exc:
                logger.warning("Failed to fetch asyncpg connection from %s, %s", host, exc)
        msg: typing.Final = f"None of the hosts match the target attribute requirement {plan.target_session_attrs}"
        raise asyncpg.TargetServerAttributeNotMatched(msg)

    return _connection_factory
