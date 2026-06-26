# Retry

`postgres_retry` (in `db_retry/retry.py`) is an async decorator that retries a
coroutine function when PostgreSQL raises a transient error — a serialization
failure or a lost connection — and gives up on everything else.

## Public surface

```python
@postgres_retry                      # bare — uses the default retry count
async def handler(...) -> ...: ...

@postgres_retry(retries=5)           # per-callsite override
async def handler(...) -> ...: ...
```

Two `typing.overload`s back the dual form: called with a function it returns the
wrapped function; called with `func=None` (i.e. `@postgres_retry(...)`) it
returns a decorator. The wrapped function keeps its signature via
`functools.wraps`. `retries` defaults to `None`, which defers to
[`settings.get_retries_number()`](settings.md) **at call time** — so the env var
is read per invocation, not frozen at decoration.

## Retry engine

Each call builds a `tenacity.AsyncRetrying` with:

- `stop=stop_after_attempt(retries or get_retries_number())`
- `wait=wait_exponential_jitter()` — exponential backoff with jitter
- `retry=retry_if_exception(_retry_handler)` — the predicate below
- `reraise=True` — the **original** exception propagates after the last attempt,
  not tenacity's `RetryError`
- `before=before_log(logger, DEBUG)` — debug log before each attempt

## What counts as retriable

`_is_retriable_dbapi_error` returns `True` only for a `sqlalchemy.exc.DBAPIError`
whose `.orig` is set and whose `.orig.__cause__` is an
`asyncpg.SerializationError` (SQLSTATE `40001`) or
`asyncpg.PostgresConnectionError` (class `08`, e.g. `08000`/`08003`). This
deliberately excludes lookalikes such as `StatementCompletionUnknownError`
(`40002`), where the statement's outcome is unknown and a blind retry is unsafe.

## Cause-chain walk

`_retry_handler` does not inspect only the raised exception — it walks the
`__cause__`/`__context__` chain (following `__cause__` first, then
`__context__`), guarding against cycles with a `seen` set of `id()`s, and
returns `True` as soon as any link is a retriable `DBAPIError`.

The walk matters because the `DBAPIError` is often re-raised inside another
exception. For example advanced-alchemy's `wrap_sqlalchemy_exception()` surfaces
it as `RepositoryError`/`IntegrityError` with the real `DBAPIError` hanging off
`__cause__`; the walk lets the retry still fire. Both retry and give-up paths
emit a debug log.

## Related

- [settings.md](settings.md) — where the default attempt count comes from.
