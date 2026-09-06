# The retriable taxonomy is a tuple of asyncpg classes, not SQLSTATE data

**Decision:** `RETRIABLE_ASYNCPG_ERRORS` stays a flat tuple of asyncpg exception classes consumed
by a single `isinstance`. We do not model the taxonomy as richer data — a mapping of SQLSTATE code
to rationale, or a table the predicate looks a code up in.

The proposal recurs because the tuple reads as a bare list of names: the codes that motivate it
(`40001`, class `08`) appear nowhere near it, so a reader cannot see *why* those two and not their
neighbours. Making it data would put the code and the reason next to the entry.

It was declined because asyncpg's exception hierarchy already **is** the SQLSTATE taxonomy. Every
class carries its own `sqlstate`, and subclassing tracks the code's class — `ConnectionDoesNotExistError`
(`08003`) is a subclass of `PostgresConnectionError` (`08000`), so naming the parent covers the whole
class for free and keeps covering it when asyncpg adds a member. A parallel SQLSTATE table would
restate a mapping asyncpg maintains, and would drift from it silently: the `isinstance` check cannot
disagree with asyncpg about which code an exception carries, but a hand-written table can, and would
lose subclass coverage the moment it did. The rationale that the table was meant to hold has a home
that cannot drift — the `INVARIANT:` docstring on the test asserting the boundary, which is executed.

**Revisit trigger:** the predicate needs to branch on something asyncpg's class hierarchy does not
encode — a per-error retry budget, a different backoff per code, or a code that is retriable only in
some contexts. A second axis is what the tuple genuinely cannot carry.
