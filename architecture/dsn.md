# DSN

`db_retry/dsn.py` parses and constructs `sqlalchemy.URL` objects for
multi-host PostgreSQL DSNs. Two public functions.

## `build_db_dsn`

```python
build_db_dsn(
    db_dsn: str,
    database_name: str,
    use_replica: bool = False,
    drivername: str = "postgresql",
) -> sqlalchemy.URL
```

Takes a stored DSN and returns a new `URL` with three things replaced:

- **`database`** ← `database_name`. The stored DSN carries a placeholder
  database (the maintained format is
  `postgresql://login:password@/db_placeholder?host=host1&host=host2` — empty
  host in the authority, real hosts in repeated `host` query params, per
  SQLAlchemy's [multiple-fallback-hosts](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#specifying-multiple-fallback-hosts)
  form); the real service database name is substituted here.
- **`drivername`** ← `drivername` (default `postgresql`; callers pass
  `postgresql+asyncpg` to get the async dialect).
- **`target_session_attrs`** ← `prefer-standby` when `use_replica` else
  `read-write`. This is a dict union (`existing_query | {target_session_attrs: …}`),
  so the computed value **overwrites** any `target_session_attrs` already on the
  DSN — `use_replica` is authoritative. (The other existing query params are
  preserved.) Note: honoring a *pre-existing* `target_session_attrs` happens
  downstream in [`build_connection_factory`](connections.md), not here.

## `is_dsn_multihost`

```python
is_dsn_multihost(db_dsn: str) -> bool
```

`True` when the DSN's `host` query param is a tuple of length > 1 — i.e. the
multiple-fallback-hosts form with at least two hosts. A single `host` param or a
host in the authority (`@host/db`) is **not** multi-host.

## Related

- [connections.md](connections.md) — consumes the constructed `URL` and the
  multi-host encoding.
