# Connections

`build_connection_factory` (in `db_retry/connections.py`) returns an async
callable `() -> asyncpg.Connection` suitable for SQLAlchemy's
`async_engine_from_config` (the `async_creator` hook). Its job is to connect to
PostgreSQL across a multi-host DSN with load balancing and per-host failover.

## Signature

```python
build_connection_factory(url: sqlalchemy.URL, timeout: float)
    -> Callable[[], Awaitable[asyncpg.Connection]]
```

The `url` is translated into asyncpg connect args **once**, at factory-build
time, via `PGDialect_asyncpg().create_connect_args(url)`. `target_session_attrs`
is popped from those args and, if present, wrapped in asyncpg's
`SessionAttribute` enum — so a `target_session_attrs` carried on the DSN (e.g.
`read-write`/`prefer-standby` set by [`build_db_dsn`](dsn.md)) **is honored**,
not discarded.

## Host handling

`host` and `port` are popped from the connect args:

- **Multi-host** (both are lists): they are zipped into `(host, port)` pairs
  (`strict=True` — lengths must match), the pair list is `random.shuffle`d for
  load balancing, then split back into parallel `hosts`/`ports` lists. The
  shuffled pair list is also retained for the failover path.
- **Single-host** (scalars): used as-is; the retained pair list is empty.

## Connect and failover

The returned `_connection_factory`:

1. Attempts one `asyncpg.connect(...)` against the full host/port set with the
   given `timeout` and `target_session_attrs`. On success, returns immediately.
2. On `TimeoutError`, if there is no multi-host pair list it re-raises. With a
   pair list, it logs a warning and falls through to host-by-host probing.
3. Re-shuffles a copy of the pairs and tries each `(host, port)` individually,
   swallowing `TimeoutError`, `OSError`, and `asyncpg.TargetServerAttributeNotMatched`
   (logging a warning per failed host) and returning the first that connects.
4. If every host fails, raises `asyncpg.TargetServerAttributeNotMatched` naming
   the unmet `target_session_attrs`.

The two-stage design lets the fast path use asyncpg's own multi-host attempt,
and only pays the per-host cost when the bulk attempt times out — typically when
`target_session_attrs` (e.g. `read-write`) excludes some hosts.

## Related

- [dsn.md](dsn.md) — how multi-host DSNs and `target_session_attrs` are encoded.
