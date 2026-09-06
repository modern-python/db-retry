# Retry default stays env-configured

**Decision:** `postgres_retry`'s default attempt count keeps coming from
`settings.get_retries_number()` — a call-time read of `DB_RETRY_RETRIES_NUMBER`, defaulting to `3`.
We do not make the default an injectable dependency, and we do not inline `settings.py` into
`retry.py`.

An architecture review flagged this as a deepening candidate. `settings.py` is a shallow module —
one caller, one line — and the attempt count enters through a process-global env var that is
invisible at the decorator's interface. Two deepenings were proposed: inject a resolver
(`default_retries: Callable[[], int] = settings.get_retries_number`) so env-reading becomes the
default adapter at an explicit seam, or inline the one-liner and delete the module.

Both were declined, because the deepening pattern pays off when it buys testability or locality you
do not already have, and here both are already present. Testability is solved twice over: a call
site controls the count explicitly with `retries=N`, and the default is controllable with
`monkeypatch.setenv("DB_RETRY_RETRIES_NUMBER", …)`, so there is no hard-to-test symptom to relieve.
`settings.py` is shallow but not a pass-through: it hides a real decision — the env var's **name**,
the `3` **default**, and the **call-time re-read contract** — in one named place, and inlining would
scatter that across `retry.py`, costing locality rather than gaining it. For a library consumed by
applications, a 12-factor env default is the conventional documented configuration surface, listed
in the interface rather than smuggled through it. And the resolver seam would have exactly one
adapter, which is hypothetical, not real: it does not remove the env read, only relocates who
performs it, while widening the public surface.

**Revisit trigger:** a second source for the default appears — a config file, or a settings object
the package must read — or a real caller needs to set the default programmatically, neither via env
nor via a per-call-site `retries=`. Either turns the resolver into a seam with two adapters rather
than one.
