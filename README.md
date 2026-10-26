<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/db-retry/lockup-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/db-retry/lockup-light.svg">
    <img alt="db-retry" src="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/db-retry/lockup.png" width="420">
  </picture>
</p>

[![PyPI version](https://img.shields.io/pypi/v/db-retry.svg)](https://pypi.org/project/db-retry/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/db-retry.svg)](https://pypi.org/project/db-retry/)
[![Downloads](https://static.pepy.tech/badge/db-retry/month)](https://pepy.tech/projects/db-retry)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/modern-python/db-retry/actions/workflows/ci.yml)
[![CI](https://github.com/modern-python/db-retry/actions/workflows/ci.yml/badge.svg)](https://github.com/modern-python/db-retry/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/modern-python/db-retry.svg)](https://github.com/modern-python/db-retry/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/modern-python/db-retry)](https://github.com/modern-python/db-retry/stargazers)
[![Context7](https://img.shields.io/badge/Context7-docs-blue)](https://context7.com/modern-python/db-retry)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

Retry helpers for PostgreSQL and SQLAlchemy, plus multi-host connection and transaction utilities.

## Features

- `postgres_retry`: retries a coroutine on serialization failures, deadlocks, and lost connections.
- `build_connection_factory`: multi-host asyncpg connections with failover on timeout.
- `build_db_dsn` and `is_dsn_multihost`: DSN parsing and manipulation.
- `Transaction`: transaction context manager that rolls back and closes the session on exit.

## Installation

### Using uv

```bash
uv add db-retry
```

### Using pip

```bash
pip install db-retry
```

## Usage examples

### 1. Database operations with automatic retry

Retry a coroutine on serialization failures, deadlocks, and lost connections. Each of these errors ends the whole Postgres transaction, so the retried coroutine has to own its transaction from start to finish: open it with `Transaction`, as below, or work on a fresh session it creates itself. A coroutine that runs on a session someone else began cannot be retried. Postgres has already discarded the statements that ran before it, and SQLAlchemy refuses the next attempt with `PendingRollbackError` instead of committing part of the work. One case is recovered for you: if the connection is lost on a query or flush that runs after the `Transaction` block, entering `Transaction` on the next attempt rolls back the dead transaction and starts on a fresh connection.

```python
import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from db_retry import Transaction, postgres_retry


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String())
    email: Mapped[str] = mapped_column(sa.String(), index=True)


# Total attempts come from DB_RETRY_RETRIES_NUMBER (default 3: the first call plus 2 retries)
@postgres_retry
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    async with Transaction(session=session):
        return await session.scalar(sa.select(User).where(User.email == email))


async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb")
    async with AsyncSession(engine) as session:
        # Automatically retries on connection failures, serialization errors, or deadlocks
        user = await get_user_by_email(session, "john.doe@example.com")
        if user:
            print(f"Found user: {user.name}")


asyncio.run(main())
```

Per-callsite override of the total number of attempts:

```python
@postgres_retry(retries=5)
async def create_order(session: AsyncSession, order: Order) -> Order: ...
```

### 2. High availability database connections

Connect to one of several hosts:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from db_retry import build_connection_factory, build_db_dsn

# Configure multiple database hosts for high availability
multi_host_dsn = "postgresql://user:password@/myapp_db?host=primary-db:5432&host=secondary-db:5432&host=backup-db:5432"

# Set the database name, driver and target_session_attrs
dsn = build_db_dsn(db_dsn=multi_host_dsn, database_name="production_database", drivername="postgresql+asyncpg")

# Create connection factory with timeout
connection_factory = build_connection_factory(
    url=dsn,
    timeout=5.0,  # 5 second connection timeout
)

# On a connect timeout, the factory tries each host in turn
engine = create_async_engine(dsn, async_creator=connection_factory)
```

### 3. Transaction management

Wrap a unit of work in a transaction that is rolled back and closed on exit:

```python
import dataclasses
import datetime
import typing

from schemas import AnalyticsEventCreate, AnalyticsEvent
from db_retry import Transaction, postgres_retry

from your_service_name.database.tables import EventsTable
from your_service_name.producers.analytics_service_events_producer import AnalyticsEventsProducer
from your_service_name.repositories.events_repository import EventsRepository
from your_service_name.settings import settings


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class CreateEventUseCase:
    events_repository: EventsRepository
    transaction: Transaction
    analytics_events_producer: AnalyticsEventsProducer

    @postgres_retry
    async def __call__(
        self,
        event_create_data: AnalyticsEventCreate,
    ) -> AnalyticsEvent:
        async with self.transaction:
            model: typing.Final = EventsTable(
                **event_create_data.model_dump(),
                created_at=datetime.datetime.now(tz=settings.common.default_timezone),
            )
            saved_event: typing.Final[EventsTable] = await self.events_repository.create(model)
            event: typing.Final = AnalyticsEvent.model_validate(saved_event)
            await self.analytics_events_producer.send_message(event)
            await self.transaction.commit()
            return event
```

These projects use this use-case shape in full, with `pool_pre_ping` off and `postgres_retry` handling connections that died while idle in the pool:

- [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template/tree/main/app/use_cases)
- [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template/tree/main/app/use_cases)
- [chat-app](https://github.com/modern-python/chat-app/tree/main/app/use_cases)

### 4. Serializable transactions

Use the serializable isolation level to prevent race conditions:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from db_retry import Transaction


async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb")

    async with AsyncSession(engine) as session:
        strict_transaction = Transaction(
            session=session,
            isolation_level="SERIALIZABLE",
        )
        # use strict_transaction where needed
```

## Configuration

The library can be configured using environment variables:

| Variable                  | Description                              | Default |
|---------------------------|------------------------------------------|---------|
| `DB_RETRY_RETRIES_NUMBER` | Total attempts (first call plus retries) | 3       |

Example:
```bash
export DB_RETRY_RETRIES_NUMBER=5
```

## API reference

### Retry decorator
- `@postgres_retry` - Decorator for async functions that should retry on database errors (total attempts, first call plus retries, from `DB_RETRY_RETRIES_NUMBER`)
- `@postgres_retry(retries=N)` - Override the total attempts (first call plus retries) per callsite
- Retries a serialization failure (`40001`), a detected deadlock (`40P01`), a connection error (class `08`), and any `DBAPIError` that SQLAlchemy marks with `connection_invalidated`. The last one covers asyncpg's `InterfaceError: connection is closed` on a pooled connection that died while idle, which is what `pool_pre_ping=True` otherwise catches
- The retried coroutine must own its whole transaction, through `Transaction` or a fresh session; on a session another caller began, the next attempt raises `PendingRollbackError`
- Retries also fire when the retriable `asyncpg` error is wrapped by [`advanced-alchemy`](https://github.com/litestar-org/advanced-alchemy)'s `wrap_sqlalchemy_exception()` (i.e. surfaced as `RepositoryError` / `IntegrityError`); the handler walks the `__cause__` / `__context__` chain.

### Connection utilities
- `build_connection_factory(url, timeout)` - Creates a connection factory for multi-host setups
- `build_db_dsn(db_dsn, database_name, use_replica=False, drivername="postgresql")` - Builds a DSN with the given database name and driver, and sets `target_session_attrs` to `read-write`, or to `prefer-standby` when `use_replica=True`
- `is_dsn_multihost(db_dsn)` - Checks if a DSN contains multiple hosts

### Transaction helper
- `Transaction(session, isolation_level=None)` - Context manager for transaction handling; on entry, rolls back a transaction that can no longer continue (a failed flush or a lost connection), otherwise joins the session's open transaction or begins one; on exit, rolls back if still in a transaction, then closes the session

## Requirements

- Python 3.11+
- SQLAlchemy with asyncio support
- asyncpg PostgreSQL driver

## Links

- [PyPI](https://pypi.org/project/db-retry)
- [License](https://github.com/modern-python/db-retry/blob/main/LICENSE)

## Part of `modern-python`

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python); see the org profile for the categorized index.
