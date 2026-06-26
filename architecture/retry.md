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
- `retry=retry_if_exception(_log_and_decide)` — delegates to
  [`is_retriable`](retriable.md); `_log_and_decide` adds the two debug log lines
  (`"postgres_retry, retrying"` / `"postgres_retry, giving up on retry"`) around
  the pure predicate
- `reraise=True` — the **original** exception propagates after the last attempt,
  not tenacity's `RetryError`
- `before=before_log(logger, DEBUG)` — debug log before each attempt

## Related

- [settings.md](settings.md) — where the default attempt count comes from.
- [retriable.md](retriable.md) — the retriable-error predicate: error taxonomy,
  cause-chain walk, and cycle guard.
