---
status: accepted
summary: Keep the default retry count as a call-time env read in settings.get_retries_number(); do not inject a resolver dependency or inline the module.
supersedes: null
superseded_by: null
---

# Retry default stays env-configured

**Decision:** `postgres_retry`'s default attempt count keeps coming from
`settings.get_retries_number()` — a call-time read of `DB_RETRY_RETRIES_NUMBER`
(default `3`). We do **not** make the default an injectable dependency, and we do
**not** inline `settings.py` into `retry.py`.

## Context

An architecture review flagged this as a deepening candidate: `settings.py` is a
**shallow** module (one caller; the deletion test reads it as a pass-through),
and `postgres_retry`'s retry count enters through a process-global env var that
is invisible at the decorator's interface — a "hidden input." The proposed
deepenings were:

- **Inject a resolver** — add `default_retries: Callable[[], int] =
  settings.get_retries_number` to `postgres_retry`, making env-reading the
  default *adapter* at an explicit seam.
- **Inline `settings.py`** — fold the one-liner into `retry.py` and delete the
  module.

The countervailing fact: the current form is **deliberate and documented**
(`architecture/settings.md`) — a function, not a constant, so the value is
re-read per call (tests `monkeypatch.setenv`; deployments retune without
re-import).

## Decision & rationale

The current design stands. The deepening pattern pays off when it buys
**testability or locality you don't already have** — and here both are already
present:

- **Testability is already solved two ways.** The input is controllable at the
  seam via an explicit `retries=N` per call site, and the default is
  controllable via `monkeypatch.setenv("DB_RETRY_RETRIES_NUMBER", …)`. There is
  no "hard to test" symptom to relieve.
- **`settings.py` is shallow-but-correct.** The deletion test detects
  pass-throughs that *hide nothing*; this module hides a real decision — the env
  var **name**, the `3` **default**, and the **call-time-reread contract** —
  concentrated in one named place. Inlining would scatter that contract across
  `retry.py`, costing locality, not gaining it.
- **Env-var config is the intended interface, not a hidden global.** For a
  library consumed by applications, a 12-factor env default is the conventional,
  documented configuration surface — listed in the interface, not smuggled
  through it.
- **Injecting a resolver is YAGNI.** It is a seam with exactly one
  *hypothetical* adapter (no second resolver exists), it does not remove the env
  read — only relocates who performs it — and it widens the public surface. Net
  loss against "one adapter = hypothetical seam; two = real."

So: no resolver seam, no inlining. The retry-count input remains a call-time
`retries=` override layered over an env-configured default.

## Revisit trigger

Reopen if a **second** source for the default appears — e.g. a config file or a
settings object the package must read — **or** if a real caller needs to set the
default programmatically (not via env and not via a per-call-site `retries=`).
Either makes the resolver seam a *real* seam with two adapters rather than a
hypothetical one.
