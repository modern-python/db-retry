# Architecture

The living truth about what `db-retry` does **now** — one file per capability,
updated by hand whenever a change ships. The *why* and *how it got here* live in
[`../planning/changes/`](../planning/changes/) — and decisions deliberately taken,
including options rejected, in [`../planning/decisions/`](../planning/decisions/);
this directory is the present.

These files carry **no frontmatter** — they are prose, dated by git.

## Capabilities

- [retry.md](retry.md) — `postgres_retry`, the async tenacity decorator and its
  cause-chain retry predicate.
- [connections.md](connections.md) — `build_connection_factory`, multi-host
  load balancing and failover.
- [dsn.md](dsn.md) — `build_db_dsn` / `is_dsn_multihost`, DSN parsing and
  construction.
- [transaction.md](transaction.md) — `Transaction`, the session context manager.
- [settings.md](settings.md) — `get_retries_number`, the env-driven retry count.

## Promotion rule

Shipping a change hand-edits the affected capability file(s) here to match the
new reality, in the same PR as the code. The change bundle stays in place under
[`../planning/changes/`](../planning/changes/) — no folder move.
