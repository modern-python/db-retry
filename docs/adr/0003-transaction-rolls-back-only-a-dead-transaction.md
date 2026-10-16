# Transaction rolls back on entry only a transaction that is already dead

`Transaction.__aenter__` joins a transaction the session already has, so a caller's earlier work
commits with the block. A connection lost outside the block leaves the session holding a transaction
that cannot continue, and joining it fails the next attempt with `PendingRollbackError`. Entering
now rolls back first, but only when the transaction is dead: inactive, which is how SQLAlchemy marks
a failed flush, or holding a connection that is `invalidated`. Rolling back any open transaction was
rejected (#68) because it would silently drop a live caller's uncommitted work. Asking
`session.connection()` was rejected because it checks out a connection when there is none yet, which
loses a pending isolation level and raises on a session with only mapper binds. The held connections
are read from the private `SessionTransaction._connections`, through `getattr`, because SQLAlchemy
has no public accessor; if it disappears, entering falls back to joining. The rollback cannot help a
query that runs before the block on the retried attempt, or a serialization failure, which aborts
the transaction without losing the connection. For those the retried coroutine must still own its
whole transaction.
