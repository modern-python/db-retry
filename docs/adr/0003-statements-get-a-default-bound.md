# Statements get a default bound

`build_connection_factory` passes asyncpg a `command_timeout` of 60 seconds unless the caller sets
the keyword or the DSN query carries its own `command_timeout`, which wins. `None` turns the bound
off. Before this, db-retry bounded only the connect, so a statement on a pooled connection to a
primary that stopped answering (a paused VM, a partition that drops packets) waited for TCP
keepalive, which can take hours, and failover never reached the caller (#85).

An opt-in keyword defaulting to `None` was considered and declined. It changes nothing for existing
users, but the people it misses are the ones who never read the failover docs, and they are the ones
who hang. The sibling libraries put a default bound inside the library too: faststream-outbox and
faststream-redis-timers default theirs to the lease. db-retry has no lease to borrow, so 60 seconds
is a chosen number, high enough for ordinary OLTP statements and low enough that a frozen primary
costs a minute instead of hours.

The cost is a behaviour change. A statement that runs longer than 60 seconds now raises
`TimeoutError`, and `postgres_retry` does not retry it, because the statement may have completed
(see [ADR 0002](0002-retriable-taxonomy-is-asyncpg-classes.md)). Engines that run migrations or
long reports must raise the keyword or pass `None`.

The bound needs asyncpg 0.32 or newer, which is now the floor. On 0.30 and 0.31 the statement times
out, but SQLAlchemy then discards the connection through asyncpg's `close()`, which waits with no
bound for the server to acknowledge the cancel. A frozen primary never does, so the caller hangs
there instead.
