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

> Quick orientation only. The authoritative, code-current account of each
> capability lives in [`architecture/`](architecture/) — one file per
> capability. **When a change alters a capability's behavior, update the matching
> `architecture/<capability>.md` in the same PR** — that promotion is what keeps
> `architecture/` true; code that changes without it silently rots the truth home.

The package (`db_retry/`) exposes five public symbols via `__init__.py`. Read
the matching capability file before changing behavior:

| Symbol(s) | Source | Capability file |
|---|---|---|
| `postgres_retry` | `retry.py` | [architecture/retry.md](architecture/retry.md) |
| `build_connection_factory` | `connections.py` | [architecture/connections.md](architecture/connections.md) |
| `build_db_dsn`, `is_dsn_multihost` | `dsn.py` | [architecture/dsn.md](architecture/dsn.md) |
| `Transaction` | `transaction.py` | [architecture/transaction.md](architecture/transaction.md) |
| `get_retries_number` | `settings.py` | [architecture/settings.md](architecture/settings.md) |

- **`postgres_retry`** is an async tenacity decorator that retries on
  `asyncpg.SerializationError` (40001) and `asyncpg.PostgresConnectionError`
  (08xxx), walking the `__cause__`/`__context__` chain to find a retriable
  `DBAPIError` even when re-wrapped. Bare `@postgres_retry` or
  `@postgres_retry(retries=N)`.
- **`build_connection_factory`** returns an async creator for
  `async_engine_from_config`, load-balancing and failing over across multi-host
  DSNs before raising `TargetServerAttributeNotMatched`.

## Linting / Type Checking

Ruff is configured with `select = ["ALL"]` plus specific exclusions; line length
is 120. Type checking uses `ty` (not mypy) — in code, use `ty: ignore` for
suppression comments (not `type: ignore`).
