# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
just install       # uv lock --upgrade && uv sync
just lint          # ruff format + eof-fixer (auto-fix)
just lint-ci       # ruff check only (no fixes)
just build         # build docker image
just test          # run pytest inside docker (requires postgres)
just               # install lint build test (full pipeline)
```

To run tests locally without Docker, set `DB_DSN` and run:
```bash
uv run pytest
uv run pytest tests/test_retry.py::test_postgres_retry  # single test
```

The CI `DB_DSN` format: `postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`

## Architecture

The package (`db_retry/`) exposes five public symbols via `__init__.py`:

- **`postgres_retry`** (`retry.py`) — async tenacity decorator that retries on `asyncpg.SerializationError` (40001) and `asyncpg.PostgresConnectionError` (08000/08003). Walks the exception chain via `DBAPIError.orig.__cause__` to distinguish retriable errors from others like `StatementCompletionUnknownError` (40002). Supports bare `@postgres_retry` (uses default) and `@postgres_retry(retries=N)` for per-callsite override.

- **`build_connection_factory`** (`connections.py`) — returns an async callable suitable for SQLAlchemy's `async_engine_from_config`. Handles multi-host DSNs by randomizing host order (load balancing) and attempting all hosts on timeout before raising `TargetServerAttributeNotMatched`.

- **`build_db_dsn`** / **`is_dsn_multihost`** (`dsn.py`) — parse and construct `sqlalchemy.URL` objects. Multi-host DSNs encode additional hosts in query parameters. Existing `target_session_attrs` in the DSN is preserved (not overwritten).

- **`Transaction`** (`transaction.py`) — frozen dataclass context manager wrapping `AsyncSession`. Supports optional isolation level (e.g., `"SERIALIZABLE"`). Auto-rolls back on `__aexit__` if the session is still in a transaction (i.e. no explicit `.commit()` or `.rollback()` was called). Uses `typing.Self` (no `typing_extensions` dependency).

- **`settings.py`** — exposes `get_retries_number()` which reads `DB_RETRY_RETRIES_NUMBER` env var at call time (default: 3), allowing `monkeypatch.setenv` to work in tests.

## Linting / Type Checking

Ruff is configured with `select = ["ALL"]` plus specific exclusions. Line length is 120. Run `just lint` before committing.

Type checking uses `ty` (not mypy). In code, use `ty: ignore` for suppression comments (not `type: ignore`).
