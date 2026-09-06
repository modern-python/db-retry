# db-retry

Retry helpers for PostgreSQL applications on SQLAlchemy's asyncio extension and asyncpg: a
decorator that re-runs a coroutine when Postgres fails in a way that is safe to repeat, a
connection factory that load-balances and fails over across a multi-host DSN, and a session
context manager that rolls back whatever a block left uncommitted.

## Language

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it. General programming vocabulary does not belong here, however heavily this
package uses it.

**Retriable error**:
A PostgreSQL failure that can be re-run unchanged, because it says nothing about the request being
wrong: a serialization failure (`40001`) or a lost connection (class `08`).
`RETRIABLE_ASYNCPG_ERRORS` is the whole of it — an error outside that tuple is not retriable,
however temporary it looks.
_Avoid_: transient error — it describes how long the failure lasts, not whether repeating the work
is safe, and the two come apart: `StatementCompletionUnknownError` (`40003`) is as short-lived as
`40001` and must never be retried.

**Attempt**:
One call of the wrapped coroutine. `postgres_retry(retries=N)` bounds *attempts*, not retries — `N`
goes to tenacity's `stop_after_attempt`, so `retries=1` runs the body once and never re-runs it,
and the `DB_RETRY_RETRIES_NUMBER` default of `3` allows two re-runs.
_Avoid_: retry, as a count. The knob is spelled `retries` for callers and cannot be renamed without
breaking them, but every number in this package counts attempts.

**Primary host**:
The host a `ConnectionPlan`'s first connect attempt is aimed at — which, for a multi-host DSN, is
*every* host in shuffled order, handed to asyncpg to walk itself. "Primary" is a position in the
two-stage connect (one bulk attempt, then host-by-host through `failover`), not a PostgreSQL
replication role; replication role is `target_session_attrs`, where `read-write` selects a writable
node and `prefer-standby` a replica.
