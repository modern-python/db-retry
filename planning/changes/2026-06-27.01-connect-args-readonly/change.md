---
summary: Wrapped ConnectionPlan.connect_args in types.MappingProxyType so the Mapping annotation is literally read-only at runtime; no behavior change.
---

# Change: Make ConnectionPlan.connect_args read-only

**Lane:** lightweight — ≲30 LOC net, ≤2 files, no new file, no public-API
change, a single straightforward test.

## Goal

`ConnectionPlan.connect_args` is annotated `Mapping[str, Any]` (read-only intent)
but stored the live `dict`. Make the annotation literally true so the seam can't
be mutated through. Cosmetic hardening folded in from the connection-plan-split
final review; no behavior change (the dict was never mutated post-construction).

## Approach

`build_connection_plan` wraps the popped `connect_args` dict in
`types.MappingProxyType(...)` when constructing the `ConnectionPlan`. `_connect`
spreads it with `**plan.connect_args`, which works unchanged on a
`MappingProxyType`. Internal seam only — no public-API or `architecture/`
contract change.

## Files

- `db_retry/connections.py` — `import types`; `connect_args=types.MappingProxyType(connect_args)`.
- `tests/test_connection_factory.py` — test that `plan.connect_args` rejects mutation.

## Verification

- [x] Failing test first — `plan.connect_args["injected"] = "value"` succeeded on
  the plain dict (no `TypeError`).
- [x] Apply the wrap — mutation now raises `TypeError`.
- [x] `just test` — full suite green (28 passed, 100% coverage); `**` unpacking
  in `_connect` still works (loop tests pass).
- [x] `just lint-ci` — clean.
