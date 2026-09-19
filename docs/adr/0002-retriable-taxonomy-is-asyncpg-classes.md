# The retriable taxonomy is a tuple of asyncpg classes, not SQLSTATE data

`RETRIABLE_ASYNCPG_ERRORS` is a flat tuple of asyncpg exception classes, consumed by the single
`isinstance` in `_is_retriable_link`. Modelling it as data recurs as a proposal, because the tuple
reads as a bare list of names with the codes that motivate it (`40001`, class `08`) nowhere near it.
It was declined because asyncpg's hierarchy already is the SQLSTATE taxonomy: every class carries
its own `sqlstate`, and subclassing tracks the code class, so naming `PostgresConnectionError`
(`08000`) covers `ConnectionDoesNotExistError` (`08003`) for free and keeps covering members asyncpg
adds later. A hand-written table would restate a mapping asyncpg maintains and drift from it
silently, losing subclass coverage as it did; the rationale it was meant to hold lives instead in
the executed `INVARIANT:` docstring in `tests/test_retriable.py` that pins the boundary against
`StatementCompletionUnknownError` (`40003`). Only a second axis the hierarchy does not encode, a
per-error retry budget or a different backoff per code, is beyond what the tuple can carry.
