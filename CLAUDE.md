# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Recipes live in the `Justfile` (`just --list`); the bare `just` runs the full
`install lint build test` pipeline. Non-obvious notes:

- `just test` runs pytest inside Docker (needs the compose postgres). To run
  locally without Docker, set `DB_DSN` and use `uv run pytest` directly
  (e.g. `uv run pytest tests/test_retry.py::test_postgres_retry` for one test).
- `just lint` auto-fixes (eof-fixer, ruff format, ruff check --fix, ty check);
  `just lint-ci` is the same checks in no-fix/`--check` mode (CI gate).

The CI `DB_DSN` format: `postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`

## Workflow

Planning follows [`planning/README.md`](planning/README.md) — its **Quick path**
is the authoritative convention for making a change (choose a lane, create a
bundle under `planning/changes/`, ship the `architecture/` promotion in the same
PR). Run `just check-planning` (also wired into `just lint-ci`) before pushing.

## Architecture

When a change alters a capability's behavior, update the matching
`architecture/<capability>.md` in the same PR.

The package (`db_retry/`) exposes five public symbols via `__init__.py`:

- **`postgres_retry`** (`retry.py`) — async tenacity decorator that retries on `asyncpg.SerializationError` (40001) and `asyncpg.PostgresConnectionError` (08000/08003). Walks the outer `__cause__`/`__context__` chain to find any `DBAPIError`, then inspects `DBAPIError.orig.__cause__` to distinguish retriable errors from others like `StatementCompletionUnknownError` (40002). The chain walk lets retries fire when the `DBAPIError` is re-raised by a wrapper (e.g. advanced-alchemy's `wrap_sqlalchemy_exception()` surfacing it as `RepositoryError`/`IntegrityError`). Supports bare `@postgres_retry` (uses default) and `@postgres_retry(retries=N)` for per-callsite override.

- **`build_connection_factory`** (`connections.py`) — returns an async callable suitable for SQLAlchemy's `async_engine_from_config`. Handles multi-host DSNs by randomizing host order (load balancing) and attempting all hosts on timeout before raising `TargetServerAttributeNotMatched`.

- **`build_db_dsn`** / **`is_dsn_multihost`** (`dsn.py`) — parse and construct `sqlalchemy.URL` objects. Multi-host DSNs encode additional hosts in query parameters. Existing `target_session_attrs` in the DSN is preserved (not overwritten).

- **`Transaction`** (`transaction.py`) — frozen dataclass context manager wrapping `AsyncSession`. Supports optional isolation level (e.g., `"SERIALIZABLE"`). Auto-rolls back on `__aexit__` if the session is still in a transaction (i.e. no explicit `.commit()` or `.rollback()` was called). Uses `typing.Self` (no `typing_extensions` dependency).

- **`settings.py`** — exposes `get_retries_number()` which reads `DB_RETRY_RETRIES_NUMBER` env var at call time (default: 3), allowing `monkeypatch.setenv` to work in tests.

## Linting / Type Checking

Ruff is configured with `select = ["ALL"]` plus specific exclusions; line length
is 120. Type checking uses `ty` (not mypy) — in code, use `ty: ignore` for
suppression comments (not `type: ignore`).
