# Transaction

`Transaction` (in `db_retry/transaction.py`) is an async context manager that
wraps a SQLAlchemy `AsyncSession`, opening a transaction on entry and cleaning
up on exit.

## Shape

```python
@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class Transaction:
    session: AsyncSession
    isolation_level: IsolationLevel | None = None
```

A frozen, slotted, keyword-only dataclass: `Transaction(session=..., isolation_level=...)`.
`__aenter__` returns `typing.Self` (no `typing_extensions` dependency).

## Entry

`async with Transaction(session=s) as tx:`

1. If `isolation_level` is set, calls `session.connection(execution_options={"isolation_level": ...})`
   to apply it (e.g. `"SERIALIZABLE"`).
2. If the session is **not** already in a transaction, calls `session.begin()`.
   An already-open transaction is adopted rather than nested.

## Exit

`__aexit__` does **not** suppress exceptions (returns `None`) and always runs,
on both the success and error path:

1. If the session is still in a transaction, `session.rollback()`. This is the
   auto-rollback: a block that neither `.commit()`s nor `.rollback()`s — or that
   raises — leaves the transaction open, and exit rolls it back. A block that
   already committed/rolled back is no longer in a transaction, so nothing is
   undone.
2. `session.close()` — always, regardless of outcome.

So commit is explicit: call `tx.commit()` inside the block to persist; otherwise
the work is rolled back. `tx.rollback()` is also exposed for an explicit early
rollback. Both delegate straight to the session.
