# Retry default stays env-configured

A bare `@postgres_retry` resolves its attempt count inside `wrapped_method` on every call, from
`settings.get_retries_number()`, a read of `DB_RETRY_RETRIES_NUMBER` defaulting to `3`; a call site
that wants its own bound passes `retries=N`. A review proposed two deepenings of the one-line
`settings` module: inject a resolver so the env read becomes an explicit default adapter, or inline
the function and delete the module. Both were declined. The env var is this library's whole
configuration surface, and the per-call re-read is the point, because an operator lowering it during
an incident expects the retry storm to stop without a restart. A resolver would relocate the env
read rather than remove it, with exactly one adapter, and inlining would scatter the var's name, the
`3` and the re-read contract across `retry.py`. A second source for the default, a config file or a
caller that must set it programmatically, is what would make the seam real.
