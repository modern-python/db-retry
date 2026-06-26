---
summary: Extracted the retriable-error predicate into a pure is_retriable(exc) -> bool in db_retry/retriable.py, enabling in-memory classification tests; postgres_retry now consumes it via _log_and_decide.
---

# Design: Give the retriable-error predicate its own seam

## Summary

The decision "is this exception worth retrying?" is the deepest logic in the
package — it unwraps a SQLAlchemy `DBAPIError`, classifies the underlying
asyncpg error, and walks the `__cause__`/`__context__` chain to find a retriable
link even when re-wrapped. Today it lives in two private functions in
`retry.py` (`_is_retriable_dbapi_error`, `_retry_handler`) reachable only
through `@postgres_retry`, so its only test surface is a live Postgres that
raises a chosen SQLSTATE. This change moves the seam: a pure
`is_retriable(exc) -> bool` in a new `db_retry/retriable.py`, tested directly
with in-memory exception chains built from real types. `postgres_retry` becomes
a thin consumer of the seam; the integration suite shrinks to proving the
wiring.

## Motivation

- The retriability logic is deep but sits behind the wrong seam — **the
  interface is not the test surface**. The classification matrix in
  `tests/test_retry.py` (which SQLSTATEs retry, re-wrapped chains, attempt
  counts) round-trips a real database via a `CREATE FUNCTION raise_error()`
  stored proc to exercise a pure predicate.
- The SQLSTATE/asyncpg taxonomy ("serialization failures and lost connections
  are transient; `40002` is not") is an inline `isinstance` tuple buried in a
  boolean expression — no name, no single place to change.
- Verified the in-memory approach works: a real `sqlalchemy.exc.DBAPIError`
  whose `.orig.__cause__` is a real `asyncpg.SerializationError`, optionally
  re-wrapped in another exception via `__cause__`, drives the current predicate
  to the correct verdict with no database.

## Non-goals

- No behaviour change to what counts as retriable — same SQLSTATE classes in,
  same out.
- No change to the public surface: `is_retriable` is an **internal seam**, not
  added to `__init__.py`'s `__all__`. The package keeps its five public symbols.
- No change to the retry loop's logging output — the two debug lines are
  preserved, only relocated.
- Not modelling the taxonomy as richer data (SQLSTATE codes / rationale as a
  structure) — the *why* lives in `architecture/retriable.md`; the *what* is a
  named tuple of asyncpg classes.

## Design

### 1. New module `db_retry/retriable.py`

A named constant and one pure public function (plus a private per-link helper):

```python
RETRIABLE_ASYNCPG_ERRORS = (asyncpg.SerializationError, asyncpg.PostgresConnectionError)

def is_retriable(exception: BaseException) -> bool:
    """Walk __cause__/__context__; True if any link is a retriable DBAPIError."""
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _is_retriable_link(current):
            return True
        current = current.__cause__ or current.__context__
    return False
```

`is_retriable` is **pure** — no logging, no side effects. `_is_retriable_link`
is the current `_is_retriable_dbapi_error` body, checking `DBAPIError` →
`.orig is not None` → `isinstance(.orig.__cause__, RETRIABLE_ASYNCPG_ERRORS)`.
The cycle guard (`seen` set of `id()`s) and the cause-first/context-second walk
order are preserved exactly.

### 2. `retry.py` consumes the seam

`postgres_retry` imports `is_retriable` and wraps it in a thin local predicate
that carries the relocated logging:

```python
def _log_and_decide(exception: BaseException) -> bool:
    if is_retriable(exception):
        logger.debug("postgres_retry, retrying")
        return True
    logger.debug("postgres_retry, giving up on retry")
    return False

retry=tenacity.retry_if_exception(_log_and_decide)
```

`_is_retriable_dbapi_error` and `_retry_handler` are deleted from `retry.py`.
The `retriable.py` module keeps no logger.

### 3. Architecture promotion

- **New** `architecture/retriable.md` — documents `is_retriable`, the
  `RETRIABLE_ASYNCPG_ERRORS` taxonomy, the cause-chain walk + cycle guard, and
  **why `40002` (`StatementCompletionUnknownError`) is excluded** (outcome
  unknown, blind retry unsafe). The cause-chain prose moves here from
  `retry.md`.
- **Edit** `architecture/retry.md` — drop the "What counts as retriable" /
  "Cause-chain walk" sections; leave a one-line pointer to `retriable.md` and
  note the predicate is wired in via `_log_and_decide`.
- **Edit** `architecture/README.md` — add the `retriable.md` capability row.
- **New** `architecture/glossary.md` — authored lazily (first term):
  **Retriable error**.

## Testing

- **New** `tests/test_retriable.py` — in-memory, no database. A small helper
  builds a `DBAPIError` whose `.orig.__cause__` is a given asyncpg error.
  Parametrized matrix covering: `SerializationError` (40001) → retriable;
  `PostgresConnectionError` and a subclass (08000/08003) → retriable; a
  non-retriable `PostgresError` → not; a re-wrapped chain (advanced-alchemy
  style, real `DBAPIError` hung off a `RepositoryError.__cause__`) → retriable;
  a `__context__`-only link → retriable; a `__cause__` cycle → terminates and
  returns the right verdict; a bare non-DBAPI exception → not.
- **Edit** `tests/test_retry.py` — keep exactly two integration cases (one
  retriable `40001` → retries, asserts attempt count; one non-retriable
  `40002` → no retry) proving the decorator wires the predicate into tenacity
  and `reraise=True` surfaces the original error. The exhaustive matrix and the
  advanced-alchemy case move to `test_retriable.py`.
- `just lint-ci` passes; `just test` (Docker Postgres) green for the trimmed
  integration cases.

## Risk

- **Low. Behaviour-preserving refactor.** The predicate body, walk order, and
  cycle guard are copied verbatim; the named constant is the same tuple. Risk is
  an accidental semantic drift during the move — mitigated by writing
  `test_retriable.py` first (TDD) against the documented matrix, and by keeping
  the two integration cases as a live-Postgres backstop on the wiring.
- **Logging relocation** could drop or duplicate a debug line — mitigated by
  `_log_and_decide` reproducing both lines verbatim and `retriable.py` carrying
  no logger.
