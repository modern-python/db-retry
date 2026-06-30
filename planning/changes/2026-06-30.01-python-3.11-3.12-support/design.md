---
summary: Lower the supported Python floor from 3.13 to 3.11, rewriting retry.py off PEP 695 and proving 3.11-3.14 in a CI matrix.
---

# Design: Add Python 3.11 / 3.12 support

## Summary

Lower the package's supported Python floor from 3.13 to 3.11. The runtime
dependencies (tenacity, sqlalchemy, asyncpg) already support 3.11+, so the only
source change is `retry.py`, which uses PEP 695 generic syntax that is a syntax
error before 3.12. We rewrite those declarations to the pre-695 stdlib
`ParamSpec`/`TypeVar`/`TypeAlias` form (no new dependency), widen
`requires-python` and the classifiers, lower the ruff target, and add a CI
pytest matrix over 3.11-3.14 that proves every supported version at runtime.
This mirrors the established `faststream-redis-timers` convention in the same
org.

## Motivation

`postgres_retry` and friends have no runtime feature that requires 3.13 — the
floor is incidental, set by the PEP 695 syntax in `retry.py`. Widening to 3.11
broadens adoption (3.11 and 3.12 are still widely deployed) at the cost of one
mechanical typing rewrite. The sibling `faststream-redis-timers` package already
ships `requires-python = ">=3.11,<4"` with a 3.11-3.14 CI matrix; aligning
`db-retry` keeps the org's packages consistent.

## Non-goals

- No runtime behavior change: the retry/failover/transaction semantics are
  identical on every version.
- No new dependency: `typing_extensions` is not needed — `ParamSpec`,
  `TypeVar`, and `TypeAlias` are stdlib since 3.10.
- No new tests and no version-gated code branches: the existing suite runs
  unchanged across the matrix.

## Design

### 1. `retry.py` — rewrite off PEP 695

The current module uses two 3.12+ constructs that are hard syntax errors on
3.11: the `type` alias statement and generic-function syntax (`def f[**P, T]`).

Today (3.12+ only):

```python
type _Func[**P, T] = typing.Callable[P, typing.Coroutine[None, None, T]]
type _Decorator[**P, T] = typing.Callable[[_Func[P, T]], _Func[P, T]]

@typing.overload
def postgres_retry[**P, T](func: _Func[P, T], *, retries: int | None = ...) -> _Func[P, T]: ...
```

Rewritten (3.11-compatible), keeping the named aliases:

```python
P = typing.ParamSpec("P")
T = typing.TypeVar("T")

_Func: typing.TypeAlias = typing.Callable[P, typing.Coroutine[None, None, T]]
_Decorator: typing.TypeAlias = typing.Callable[[_Func], _Func]

@typing.overload
def postgres_retry(func: _Func, *, retries: int | None = ...) -> _Func: ...
@typing.overload
def postgres_retry(func: None = ..., *, retries: int | None = ...) -> _Decorator: ...
def postgres_retry(func: _Func | None = None, *, retries: int | None = None) -> _Func | _Decorator:
    ...  # body unchanged (lines 39-55)
```

`P` and `T` move to module scope; the bare aliases re-bind them per signature,
which is exactly how pre-695 generic aliases work. The function body — the
`tenacity.AsyncRetrying` construction and the `decorator`/`wrapped_method`
nesting — is untouched. The two public call forms (`@postgres_retry` and
`@postgres_retry(retries=N)`) and their inferred types are preserved.

### 2. `pyproject.toml`

- `requires-python = ">=3.13,<4"` -> `">=3.11,<4"`.
- Add classifiers `Programming Language :: Python :: 3.11` and `:: 3.12` (the
  3.13 / 3.14 entries stay).
- `[tool.ruff] target-version = "py313"` -> `"py311"`, so lint catches any
  3.11-incompatible syntax introduced later (and stops suggesting 3.12+-only
  upgrades).

### 3. CI — `.github/workflows/_checks.yml`

The `pytest` job gains a version matrix mirroring `faststream-redis-timers`:

```yaml
  pytest:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13", "3.14"]
    services:
      postgres:
        ...  # unchanged
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v8.2.0
      - run: uv python install ${{ matrix.python-version }}
      - run: |
          uv sync --all-extras --no-install-project
          uv run --no-sync pytest . --cov=. --cov-report xml
        env:
          ...  # unchanged
```

The `lint` job stays pinned to `uv python install 3.13` (single-version gate).

### 4. Docs

- `README.md:216`: "Python 3.13+" -> "Python 3.11+". The pyversions badge is
  driven by PyPI metadata and updates automatically.
- Promote into `architecture/retry.md` in the implementing PR (note the
  pre-695 typing form so the capability page stays code-current).

## Testing

- `just lint-ci` (ruff `--check` + `ty check`) passes with `target-version =
  py311`; `ty check` confirms the rewritten overloads still type-check.
- `uv run pytest` passes locally against `DB_DSN`.
- CI proves runtime correctness on 3.11, 3.12, 3.13, and 3.14, each holding the
  existing `--cov-fail-under=100` gate.

## Risk

- **Low: the rewritten generic aliases type-check differently than PEP 695.**
  Mitigation: `ty check` in the lint gate plus the unchanged overload tests
  catch any inference regression before merge.
- **Low: a transitive dependency drops 3.11 wheels.** Mitigation: the 3.11 CI
  leg fails loudly at `uv sync` if so; deps are unpinned and currently all
  publish 3.11 wheels.
