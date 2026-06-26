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

`build_connection_factory` is the only public symbol of this capability;
`build_connection_plan` and `ConnectionPlan` are **internal seams** (not in
`__all__`) and not part of the public API.

## Connection plan (internal)

`build_connection_plan(url)` is the pure parse phase — no I/O, no logging, no
`asyncpg.connect`. It calls `PGDialect_asyncpg().create_connect_args(url)` once,
pops `host`/`port`/`target_session_attrs` from the result, and returns a frozen,
slotted `ConnectionPlan`:

```python
class ConnectionPlan:
    connect_args: Mapping[str, Any]           # base kwargs, minus host/port/target_session_attrs
    target_session_attrs: SessionAttribute | None
    primary_host: str | list[str]             # list for multi-host, scalar for single
    primary_port: int | list[int] | None
    failover: tuple[tuple[str, int], ...]     # per-host pairs; () for single-host
```

`target_session_attrs` (e.g. `read-write`/`prefer-standby` set by
[`build_db_dsn`](dsn.md)) is wrapped in asyncpg's `SessionAttribute` enum so it
is **honored**, not discarded.

**Multi-host** (both `host` and `port` are lists): the hosts and ports are zipped
(`strict=True` — lengths must match), the resulting `(host, port)` pairs are
`random.shuffle`d **once** at build time, then split back into `primary_host` and
`primary_port` lists and also stored as `failover`. Key invariant:
`list(zip(primary_host, primary_port)) == list(failover)` — primary and failover
come from the **same** shuffle, so host/port stay paired throughout.

**Single-host** (scalars): `primary_host`/`primary_port` are the scalars;
`failover = ()`.

## Connect and failover

`build_connection_factory` calls `build_connection_plan(url)` once at build time,
then returns `_connection_factory`, a thin async loop that consumes the plan via a
single `_connect(plan, host, port, timeout)` helper (one `asyncpg.connect` call
site):

1. Attempts `_connect` against `plan.primary_host`/`plan.primary_port` with the
   given `timeout`. On success, returns immediately.
2. On `TimeoutError`, if `plan.failover` is empty (single-host), re-raises. With a
   failover list, logs a warning and falls through.
3. Calls `_reshuffled(plan.failover)` — a **per-call** shuffle of a copy of the
   failover pairs — and tries each `(host, port)` individually, swallowing
   `TimeoutError`, `OSError`, and `asyncpg.TargetServerAttributeNotMatched`
   (logging a warning per failed host) and returning the first that connects.
4. If every host fails, raises `asyncpg.TargetServerAttributeNotMatched` naming
   the unmet `target_session_attrs`.

**Two shuffle lifetimes**: the bulk/primary order is shuffled **once** when
`build_connection_plan` runs (at factory-build time); the failover list is
re-shuffled **per connection** in the loop via `_reshuffled`. These are distinct:
the plan is immutable; the per-call re-shuffle is ephemeral.

The two-stage design lets the fast path use asyncpg's own multi-host attempt,
and only pays the per-host cost when the bulk attempt times out — typically when
`target_session_attrs` (e.g. `read-write`) excludes some hosts.

## Related

- [dsn.md](dsn.md) — how multi-host DSNs and `target_session_attrs` are encoded.
