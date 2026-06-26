# Settings

`db_retry/settings.py` holds the package's one piece of runtime configuration:
the default retry count.

## `get_retries_number`

```python
def get_retries_number() -> int:
    return int(os.getenv("DB_RETRY_RETRIES_NUMBER", "3"))
```

Reads the `DB_RETRY_RETRIES_NUMBER` environment variable **at call time**,
defaulting to `3`. It is a function — not a module-level constant — precisely so
the value is re-read on every call: tests can `monkeypatch.setenv(...)` and see
the new value, and a deployment can change the env without re-importing.

[`postgres_retry`](retry.md) calls this whenever its own `retries` argument is
`None`, so the env var sets the default attempt count while a per-callsite
`retries=N` overrides it.

## Related

- [retry.md](retry.md) — the sole consumer.
