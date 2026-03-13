# Project Context for Agents

## Project Overview

This is a Python library called `db-retry` that provides PostgreSQL and SQLAlchemy utilities, specifically focusing on:

1. **Retry decorators** for handling database connection issues and serialization errors
2. **Connection factory builders** for managing PostgreSQL connections with multiple hosts
3. **DSN (Data Source Name) utilities** for parsing and manipulating database connection strings
4. **Transaction helpers** for managing SQLAlchemy async sessions

The library is built with modern Python practices (3.13+) and uses type hints extensively. It's designed to work with PostgreSQL databases using the asyncpg driver and SQLAlchemy's asyncio extension.

## Key Technologies

- **Python 3.13+**
- **SQLAlchemy** with asyncio extension
- **asyncpg** PostgreSQL driver
- **tenacity** for retry logic
- **uv** for package management and building
- **Docker** for development and testing environments
- **pytest** for testing
- **ruff** and **ty** for linting and type checking

## Project Structure

```
db_retry/
├── __init__.py          # Exports all public APIs
├── connections.py       # Connection factory builders
├── dsn.py               # DSN parsing and manipulation utilities
├── retry.py             # Retry decorators for database operations
├── settings.py          # Configuration settings
├── transaction.py       # Transaction helper classes
└── py.typed             # Marker file for type checking
tests/
├── test_connection_factory.py
├── test_dsn.py
├── test_retry.py
├── test_transaction.py
├── conftest.py          # pytest configuration
└── __init__.py
```

## Main Components

### Retry Decorators (`retry.py`)
Provides `@postgres_retry` decorator that automatically retries database operations when encountering:
- PostgreSQL connection errors
- Serialization errors

The retry logic uses exponential backoff with jitter and is configurable via environment variables.

### Connection Factory (`connections.py`)
Provides `build_connection_factory()` function that creates connection factories for PostgreSQL databases with support for:
- Multiple fallback hosts
- Randomized host selection
- Target session attributes (read-write vs standby)

### DSN Utilities (`dsn.py`)
Provides functions for:
- `build_db_dsn()`: Parse and modify DSN strings, replacing database names and setting target session attributes
- `is_dsn_multihost()`: Check if a DSN contains multiple hosts

### Transaction Helpers (`transaction.py`)
Provides `Transaction` class that wraps SQLAlchemy AsyncSession with automatic transaction management.

## Building and Running

### Development Environment Setup
```bash
# Install dependencies
just install

# Run tests
just test

# Run linting and type checking
just lint

# Run all checks (default)
just
```

### Docker-based Development
```bash
# Run tests in Docker
just test

# Run shell in Docker container
just sh
```

### Testing
Tests are written using pytest and can be run with:
```bash
# Run all tests
just test

# Run specific test file
just test tests/test_retry.py

# Run tests with coverage
just test --cov=.
```

## Configuration

The library can be configured using environment variables:

- `DB_UTILS_RETRIES_NUMBER`: Number of retry attempts (default: 3)

## Development Conventions

1. **Type Safety**: Strict ty checking is enforced
2. **Code Style**: Ruff is used for linting with specific rules configured
3. **Testing**: All functionality should have corresponding tests
4. **Async/Await**: All database operations are asynchronous
5. **Documentation**: Public APIs should be documented with docstrings

## Common Tasks

### Adding New Features
1. Implement the feature in the appropriate module
2. Add tests in the corresponding test file
3. Update exports in `__init__.py` if adding public APIs
4. Run `just` to ensure all checks pass

### Modifying Retry Logic
The retry behavior is defined in `retry.py` and uses the tenacity library. Modify the `_retry_handler` function to change which exceptions trigger retries.

### Working with Connections
Connection handling is in `connections.py`. The `build_connection_factory` function handles connecting to PostgreSQL with support for multiple hosts and fallback mechanisms.
