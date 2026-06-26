---
summary: Split build_connection_factory into a pure build_connection_plan(url) -> ConnectionPlan and a thin failover loop, so host-plan parsing/ordering is unit-tested without mocking asyncpg.connect and the connect call is written once.
---

# Design: Split the connection factory into plan + failover loop

## Summary

`build_connection_factory` is one 79-line closure that entangles two concerns:
**pure** host-plan parsing/ordering (parse the URL into asyncpg connect args,
wrap `target_session_attrs`, pop host/port, zip + shuffle multi-host pairs) and
**async** connect-with-failover I/O — and it writes the `asyncpg.connect(...)`
call twice (the bulk attempt and the per-host loop). This change extracts the
pure half into a `build_connection_plan(url) -> ConnectionPlan` and leaves a thin
loop that consumes the plan through a single `_connect` helper. Parsing/ordering
becomes unit-testable with **no `asyncpg.connect` mock**; the connect call is
written **once**. Behaviour is preserved exactly, including the two-stage
strategy and its two-lifetime shuffle.

## Motivation

- The pure ordering logic (zip + shuffle + multi/single-host branch) is testable
  today only by mocking `asyncpg.connect` and inferring order from call
  arguments — there is no seam at the parse boundary.
- The `asyncpg.connect(...)` call is duplicated (the bulk attempt and the
  per-host attempt), so a change to connect kwargs must be made in two places.
- The genuinely bug-prone part — keeping `host` and `port` **paired** through
  `zip(strict=True)` and the `itemgetter` split — has no direct, mock-free test.

## Non-goals

- No behaviour change. Same connect kwargs, same two-stage primary→failover
  strategy, same exceptions (`TimeoutError` reraised for single-host; per-host
  swallowing of `TimeoutError`/`OSError`/`TargetServerAttributeNotMatched`;
  `TargetServerAttributeNotMatched` raised when every host fails), same logs.
- No public-API change: `build_connection_plan` / `ConnectionPlan` are
  **internal seams** (not added to `__init__.py`'s `__all__`);
  `build_connection_factory` stays the only public symbol of this capability.
- No new file: the plan is an internal seam **within** `connections.py`, not a
  separate module.
- Not touching the multi-host detection overlap with `dsn.py` (separate concern).
- Not changing the two-lifetime shuffle (bulk shuffled once at build; failover
  re-shuffled per connection). If the build-once bulk shuffle later looks like a
  load-balancing weakness, that is a separate behaviour decision for
  `deferred.md`, not this refactor.

## Design

### 1. `ConnectionPlan` — the pure plan (internal)

A frozen, slotted, keyword-only dataclass (house style, as `Transaction`):

```python
@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class ConnectionPlan:
    connect_args: Mapping[str, Any]            # base kwargs, minus host/port/target_session_attrs
    target_session_attrs: SessionAttribute | None
    primary_host: str | list[str]              # bulk attempt: list for multi-host, scalar for single
    primary_port: int | list[int] | None
    failover: tuple[tuple[str, int], ...]      # per-host pairs; () for single-host
```

`build_connection_plan(url: sqlalchemy.URL) -> ConnectionPlan` does the entire
parse phase, pure: `PGDialect_asyncpg().create_connect_args(url)`, pop + wrap
`target_session_attrs` into `SessionAttribute`, pop `host`/`port`, and:

- **multi-host** (both lists): `zip(strict=True)` into pairs, `random.shuffle`
  once, derive `primary_host`/`primary_port` from the shuffled order, and keep
  the same shuffled pairs as `failover`. So
  `list(zip(primary_host, primary_port)) == list(failover)` — primary and
  failover come from one shuffle, host/port paired throughout.
- **single-host** (scalars): `primary_host`/`primary_port` are the scalars;
  `failover = ()`.

No timeout (an I/O concern), no logging, no `asyncpg.connect`.

### 2. `build_connection_factory` — the thin loop

```python
def build_connection_factory(url, timeout):
    plan = build_connection_plan(url)          # parse-once, at build time

    async def _connection_factory():
        try:
            return await _connect(plan, plan.primary_host, plan.primary_port, timeout)
        except TimeoutError:
            if not plan.failover:
                raise
            logger.warning("Failed to fetch asyncpg connection. Trying host by host.")
        for host, port in _reshuffled(plan.failover):   # per-call re-shuffle
            try:
                return await _connect(plan, host, port, timeout)
            except (TimeoutError, OSError, asyncpg.TargetServerAttributeNotMatched) as exc:
                logger.warning("Failed to fetch asyncpg connection from %s, %s", host, exc)
        raise asyncpg.TargetServerAttributeNotMatched(
            f"None of the hosts match the target attribute requirement {plan.target_session_attrs}"
        )

    return _connection_factory
```

`_connect(plan, host, port, timeout)` is the single `asyncpg.connect(...)` call:

```python
async def _connect(plan, host, port, timeout):
    return await asyncpg.connect(
        **plan.connect_args, host=host, port=port,
        timeout=timeout, target_session_attrs=plan.target_session_attrs,
    )
```

`_reshuffled(failover)` returns a freshly-shuffled copy each call (the per-call
failover re-shuffle that lives in the loop, not the plan).

## Testing

- **New** mock-free `build_connection_plan` tests in
  `tests/test_connection_factory.py`:
  - multi-host: `set(failover) == {(h1,p1),(h2,p2)}`;
    `list(zip(primary_host, primary_port)) == list(failover)` (pairing preserved);
    `target_session_attrs` wrapped to `SessionAttribute`;
    `connect_args` has no `host`/`port`/`target_session_attrs`.
  - single-host: `failover == ()`; scalar `primary_host`/`primary_port`; tsa.
  - These assert order-independent properties — no seed, no `asyncpg.connect` mock.
- **Keep** the four existing loop tests (they mock `asyncpg.connect` and prove
  the failover orchestration: success, single-host timeout reraise, multi-host
  all-fail → `TargetServerAttributeNotMatched`, primary-fail-then-failover
  success). Plan tests and loop tests cover different things (parsing vs
  orchestration) — complementary, not duplicative.
- `just test` (Docker Postgres) green; `just lint-ci` clean.

## Risk

- **Low. Behaviour-preserving refactor.** The parse/zip/shuffle/branch logic and
  the connect kwargs are moved verbatim; the two-stage loop and its exception
  handling are unchanged. Risk is accidental drift in the connect-arg assembly or
  the single/multi branch — mitigated by writing the mock-free plan tests first
  (they pin the pairing and branch) and keeping the four loop tests as a
  live/mock backstop on orchestration.
- **Shuffle lifetimes**: the per-call failover re-shuffle must stay in the loop
  (not the once-built plan), or load-balancing behaviour changes — called out
  explicitly so the implementer does not fold it into `build_connection_plan`.
