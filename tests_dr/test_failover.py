"""Primary/replica failover drills. Run via ``just test-dr``, one fresh cluster per scenario."""

import asyncio
import collections
import http
import logging
import os
import socket
import time
import typing

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.ext import asyncio as sa_async

from db_retry import Transaction, build_connection_factory, build_db_dsn, postgres_retry


DB_DSN: typing.Final = os.environ.get("DB_DSN", "")
DATABASE: typing.Final = "dr"
DRIVER: typing.Final = "postgresql+asyncpg"
DOCKER_SOCKET: typing.Final = "/var/run/docker.sock"
PRIMARY_CONTAINER: typing.Final = "db-retry-dr-primary"
PRIMARY_HOST: typing.Final = "pg-primary"
STANDBY_HOST: typing.Final = "pg-standby"
REPLICA_HOST: typing.Final = "pg-replica"
CONNECT_TIMEOUT_SECONDS: typing.Final = 2.0
COMMAND_TIMEOUT_SECONDS: typing.Final = 3
FRESH_CONNECTIONS: typing.Final = 10
RECOVERY_BUDGET_SECONDS: typing.Final = 60.0
TEST_BUDGET_SECONDS: typing.Final = 180.0

pytestmark = pytest.mark.skipif(not DB_DSN, reason="needs the docker-compose.dr.yml cluster")


def _host_dsn(host: str) -> str:
    return sa.make_url(DB_DSN).set(host=host, database=DATABASE, query={}).render_as_string(hide_password=False)


async def _docker(method: str, path: str) -> None:
    reader, writer = await asyncio.open_unix_connection(DOCKER_SOCKET)
    writer.write(f"{method} {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode())
    await writer.drain()
    status_line = await reader.readline()
    writer.close()
    assert int(status_line.split(b" ", 2)[1]) < http.HTTPStatus.MULTIPLE_CHOICES, status_line.decode(errors="replace")


async def _kill_primary() -> None:
    await _docker("POST", f"/containers/{PRIMARY_CONTAINER}/kill")


async def _pause_primary() -> None:
    """Freeze the primary: its name resolves and the kernel accepts connects, but nothing ever answers."""
    await _docker("POST", f"/containers/{PRIMARY_CONTAINER}/pause")


async def _address(host: str) -> str:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return str(infos[0][4][0])


async def _wait_replica_caught_up() -> None:
    primary = await asyncpg.connect(_host_dsn(PRIMARY_HOST))
    replica = await asyncpg.connect(_host_dsn(REPLICA_HOST))
    try:
        target = await primary.fetchval("SELECT pg_current_wal_lsn()")
        deadline = time.monotonic() + 30
        while await replica.fetchval("SELECT pg_last_wal_replay_lsn() < $1::pg_lsn", target):
            assert time.monotonic() < deadline, "replica did not catch up"
            await asyncio.sleep(0.1)
    finally:
        await primary.close()
        await replica.close()


async def _promote_replica() -> None:
    replica = await asyncpg.connect(_host_dsn(REPLICA_HOST))
    try:
        assert await replica.fetchval("SELECT pg_promote()")
    finally:
        await replica.close()


async def _standby_in_recovery() -> bool:
    standby = await asyncpg.connect(_host_dsn(STANDBY_HOST))
    try:
        return bool(await standby.fetchval("SELECT pg_is_in_recovery()"))
    finally:
        await standby.close()


async def _write_until_accepted(
    write: typing.Callable[[int], typing.Awaitable[None]], n: int, deadline: float
) -> collections.Counter[str]:
    failures: collections.Counter[str] = collections.Counter()
    while True:
        try:
            await write(n)
        except Exception as exc:
            if time.monotonic() > deadline:
                raise
            failures[type(exc).__name__] += 1
            await asyncio.sleep(0.5)
        else:
            return failures


async def _landed_hosts(url: sa.URL) -> collections.Counter[str]:
    factory = build_connection_factory(url=url, timeout=CONNECT_TIMEOUT_SECONDS)
    landed: collections.Counter[str] = collections.Counter()
    for _ in range(FRESH_CONNECTIONS):
        connection = await factory()
        try:
            landed[await connection.fetchval("SELECT host(inet_server_addr())")] += 1
        finally:
            await connection.close()
    return landed


def _engine(url: sa.URL) -> sa_async.AsyncEngine:
    return sa_async.create_async_engine(
        url,
        async_creator=build_connection_factory(
            url=url, timeout=CONNECT_TIMEOUT_SECONDS, command_timeout=COMMAND_TIMEOUT_SECONDS
        ),
    )


@pytest.mark.parametrize("fail_primary", [_kill_primary, _pause_primary], ids=["kill", "pause"])
async def test_writes_reach_promoted_replica(
    fail_primary: typing.Callable[[], typing.Awaitable[None]], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="db_retry.connections")
    writes_url = build_db_dsn(DB_DSN, DATABASE, drivername=DRIVER)
    reads_url = build_db_dsn(DB_DSN, DATABASE, use_replica=True, drivername=DRIVER)
    writes = _engine(writes_url)
    reads = _engine(reads_url)
    sessions = sa_async.async_sessionmaker(writes, expire_on_commit=False)
    attempts = 0

    @postgres_retry
    async def write(n: int) -> None:
        nonlocal attempts
        attempts += 1
        async with Transaction(session=sessions()) as transaction:
            await transaction.session.execute(sa.text("INSERT INTO dr (n) VALUES (:n)"), {"n": n})
            await transaction.commit()

    @postgres_retry
    async def read() -> int:
        async with reads.connect() as connection:
            return int(await connection.scalar(sa.text("SELECT count(*) FROM dr")) or 0)

    try:
        async with asyncio.timeout(TEST_BUDGET_SECONDS):
            async with writes.begin() as connection:
                await connection.execute(sa.text("CREATE TABLE dr (n int PRIMARY KEY)"))
            await write(0)
            await _wait_replica_caught_up()
            assert await read() == 1

            failed_at = time.monotonic()
            await fail_primary()
            assert await read() == 1
            await _promote_replica()

            attempts = 0
            failures = await _write_until_accepted(write, 1, failed_at + RECOVERY_BUDGET_SECONDS)
            recovered = time.monotonic() - failed_at
            assert await read() >= 1

            assert await _landed_hosts(writes_url) == {await _address(REPLICA_HOST): FRESH_CONNECTIONS}
            assert await _standby_in_recovery()
    finally:
        await writes.dispose()
        await reads.dispose()

    fallbacks = sum("Trying host by host" in r.getMessage() for r in caplog.records)
    print(  # noqa: T201
        f"\nwrite recovered {recovered:.1f}s, postgres_retry attempts {attempts}, "
        f"failed outer calls {sum(failures.values())} {dict(failures)}, host-by-host fallbacks {fallbacks}"
    )
