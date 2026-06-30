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

A Python library providing robust retry mechanisms, connection utilities, and transaction helpers for PostgreSQL and SQLAlchemy applications.

## Features

- **Retry Decorators**: Automatic retry logic for transient database errors
- **Connection Factories**: Robust connection handling with multi-host support
- **DSN Utilities**: Flexible Data Source Name parsing and manipulation
- **Transaction Helpers**: Simplified transaction management with automatic cleanup

## Installation

### Using uv

```bash
uv add db-retry
```

### Using pip

```bash
pip install db-retry
```

## ORM-Based Usage Examples

### 1. Database Operations with Automatic Retry

Protect your database operations from transient failures using ORM models:

```python
import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from db_retry import postgres_retry


class User(DeclarativeBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String())
    email: Mapped[str] = mapped_column(sa.String(), index=True)


# Apply retry logic to ORM operations (uses DB_RETRY_RETRIES_NUMBER, default 3)
@postgres_retry
async def get_user_by_email(session: AsyncSession, email: str) -> User:
    return await session.scalar(
        sa.select(User).where(User.email == email)
    )


async def main():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb")
    async with AsyncSession(engine) as session:
        # Automatically retries on connection failures or serialization errors
        user = await get_user_by_email(session, "john.doe@example.com")
        if user:
            print(f"Found user: {user.name}")


asyncio.run(main())
```

Per-callsite retry count override:

```python
@postgres_retry(retries=5)
async def create_order(session: AsyncSession, order: Order) -> Order:
    ...
```

### 2. High Availability Database Connections

Set up resilient database connections with multiple fallback hosts:

```python
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from db_retry import build_connection_factory, build_db_dsn

# Configure multiple database hosts for high availability
multi_host_dsn = (
    "postgresql://user:password@/"
    "myapp_db?"
    "host=primary-db:5432&"
    "host=secondary-db:5432&"
    "host=backup-db:5432"
)

# Build production-ready DSN
dsn = build_db_dsn(
    db_dsn=multi_host_dsn,
    database_name="production_database",
    drivername="postgresql+asyncpg"
)

# Create connection factory with timeout
connection_factory = build_connection_factory(
    url=dsn,
    timeout=5.0  # 5 second connection timeout
)

# Engine will automatically try different hosts on failure
engine = create_async_engine(dsn, async_creator=connection_factory)
```

### 3. Simplified Transaction Management

Handle database transactions with automatic cleanup using ORM:

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

### 4. Serializable Transactions for Consistency

Use serializable isolation level to prevent race conditions with ORM:

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

| Variable                | Description                                      | Default |
|-------------------------|--------------------------------------------------|---------|
| `DB_RETRY_RETRIES_NUMBER` | Number of retry attempts for database operations | 3       |

Example:
```bash
export DB_RETRY_RETRIES_NUMBER=5
```

## API Reference

### Retry Decorator
- `@postgres_retry` - Decorator for async functions that should retry on database errors (uses `DB_RETRY_RETRIES_NUMBER`)
- `@postgres_retry(retries=N)` - Override retry count per callsite
- Retries also fire when the retriable `asyncpg` error is wrapped by [`advanced-alchemy`](https://github.com/litestar-org/advanced-alchemy)'s `wrap_sqlalchemy_exception()` (i.e. surfaced as `RepositoryError` / `IntegrityError`); the handler walks the `__cause__` / `__context__` chain.

### Connection Utilities
- `build_connection_factory(url, timeout)` - Creates a connection factory for multi-host setups
- `build_db_dsn(db_dsn, database_name, use_replica=False, drivername="postgresql")` - Builds a DSN with specified parameters
- `is_dsn_multihost(db_dsn)` - Checks if a DSN contains multiple hosts

### Transaction Helper
- `Transaction(session, isolation_level=None)` - Context manager for transaction handling; auto-rolls back on exit if no explicit `.commit()` or `.rollback()` was called

## Requirements

- Python 3.11+
- SQLAlchemy with asyncio support
- asyncpg PostgreSQL driver
- tenacity for retry logic

## 📦 [PyPI](https://pypi.org/project/db-retry)

## 📝 [License](LICENSE)

## Part of `modern-python`

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the categorized index.
