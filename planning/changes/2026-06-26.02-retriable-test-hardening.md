---
summary: Hardened tests/test_retriable.py — made the `.orig` invariant explicit in the helper and added a cycle case whose loop contains a retriable DBAPIError link.
---

# Change: Harden the retriable predicate tests

**Lane:** lightweight — ≲30 LOC net, ≤2 files, no new file, no public-API
change, a single straightforward test.

## Goal

Fold the two deferred Minor findings from the [retriable-error-seam
review](../2026-06-26.01-retriable-error-seam/design.md)'s final whole-branch
pass into the test suite, so the predicate's invariants are explicit rather than
implicit.

## Approach

Test-only hardening of the in-memory predicate suite. No production code or
capability contract changes, so no `architecture/` promotion.

- The `_make_dbapi_error` helper now asserts `err.orig is not None`. The whole
  matrix hinges on `.orig` being set (the predicate reads `.orig.__cause__`);
  the assertion makes that load-bearing invariant explicit instead of relying on
  the True-expected cases to fail if it ever broke.
- A new case complements `test_is_retriable_cause_cycle_terminates`: a cyclic
  chain that *contains* a retriable `DBAPIError` link returns `True` — the walk
  finds the link before the cycle guard would re-visit a node.

## Files

- `tests/test_retriable.py` — assertion in the helper; one new cycle-with-link test.

## Verification

- [x] `just test` — full suite green (25 passed, 100% coverage).
- [x] `just lint-ci` — clean.
