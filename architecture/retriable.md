# Retriable

`db_retry/retriable.py` classifies a PostgreSQL exception as retriable — a pure
predicate that can be tested in memory without a live database.

## `is_retriable`

```python
def is_retriable(exception: BaseException) -> bool: ...
```

Returns `True` if `exception` or any exception in its `__cause__`/`__context__`
chain is a `sqlalchemy.exc.DBAPIError` whose `.orig` is set and whose `.orig.__cause__` is one of the
[retriable asyncpg errors](glossary.md).

The predicate is **pure**: no logging, no side effects. `postgres_retry` wraps it
in `_log_and_decide`, which adds the two debug lines and feeds the result to
tenacity.

## `RETRIABLE_ASYNCPG_ERRORS`

```python
RETRIABLE_ASYNCPG_ERRORS = (asyncpg.SerializationError, asyncpg.PostgresConnectionError)
```

The two asyncpg error classes that make a `DBAPIError` retriable:

| Class | SQLSTATE | Meaning |
|---|---|---|
| `asyncpg.SerializationError` | `40001` | Serialization failure — transaction conflicted with a concurrent write; retry may succeed. |
| `asyncpg.PostgresConnectionError` | class `08` (e.g. `08000`, `08003`) | Lost or refused connection — transient network or server state; retry may reconnect. |

`StatementCompletionUnknownError` (`40002`) is **not** included: when the
statement's outcome is unknown, a blind retry risks duplicating a write that
already committed. Classification stops at the unknown boundary.

## Cause-chain walk

`is_retriable` does not inspect only the top exception — it walks the chain:

1. Follow `__cause__` first (an explicit `raise … from …`), then `__context__`
   (an implicit exception chain).
2. Guard against cycles with a `seen` set of `id()`s — if the same exception
   object appears twice, the walk terminates.
3. Return `True` at the **first** link that is a retriable `DBAPIError`.

The walk matters because `DBAPIError` is often re-wrapped before it surfaces.
For example, advanced-alchemy's `wrap_sqlalchemy_exception()` raises a
`RepositoryError` (or `IntegrityError`) with the real `DBAPIError` attached as
`__cause__`; without the walk, the decorator would see only the outer wrapper and
give up.

## Related

- [retry.md](retry.md) — `postgres_retry`, which consumes `is_retriable` via `_log_and_decide`.
- [glossary.md](glossary.md) — **Retriable error** definition.
