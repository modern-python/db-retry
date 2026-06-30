# python-3.11-3.12-support — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower the supported Python floor from 3.13 to 3.11 — rewrite
`retry.py` off PEP 695, widen packaging metadata, and prove 3.11-3.14 in a CI
matrix.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/python-3.11-3.12-support` (already created and checked out;
the design commit is on it).

**Commit strategy:** Per-task commits.

## Global Constraints

- Python floor: `requires-python = ">=3.11,<4"`. Code must parse and run on
  3.11 through 3.14.
- No new dependency. `ParamSpec`, `TypeVar`, `TypeAlias` are stdlib `typing`
  since 3.10 — do not add `typing_extensions`.
- No runtime behavior change: retry/failover/transaction semantics stay
  identical. The existing test suite is the behavior contract.
- All imports at module level (project rule). Annotate all function arguments.
- Type-checker is `ty`; suppression comments are `ty: ignore` (never
  `type: ignore`).
- Coverage gate `--cov-fail-under=100` must stay green on every version.
- Promote behavior changes into `architecture/<capability>.md` in this same PR;
  finalize the bundle `summary` at ship. Run `just check-planning` before push.

---

### Task 1: Rewrite `retry.py` off PEP 695

**Files:**
- Modify: `db_retry/retry.py:22-38`
- Modify: `architecture/retry.md:17-19`
- Test: `tests/test_retry.py` (existing, unchanged)

**Interfaces:**
- Consumes: nothing new.
- Produces: `postgres_retry` keeps its exact public contract — two
  `typing.overload`s, callable as bare `@postgres_retry` (returns the wrapped
  `_Func`) and as `@postgres_retry(retries=N)` (returns a `_Decorator`). The
  named module-level aliases `_Func` and `_Decorator` are retained.

This is a behavior-preserving typing refactor. There is no new local test that
can prove 3.11 syntax-compatibility (the local interpreter is 3.13+); the proof
is the 3.11 CI leg added in Task 3. Locally we verify the rewrite preserves
typing (`ty check`) and behavior (existing `test_retry.py`).

- [ ] **Step 1: Confirm the existing retry tests pass before touching code**

  Run: `uv run pytest tests/test_retry.py -v`
  Expected: PASS (all existing tests green). This is the green baseline the
  refactor must preserve.

- [ ] **Step 2: Replace the PEP 695 declarations**

  In `db_retry/retry.py`, replace the current lines 22-38:

  ```python
  type _Func[**P, T] = typing.Callable[P, typing.Coroutine[None, None, T]]
  type _Decorator[**P, T] = typing.Callable[[_Func[P, T]], _Func[P, T]]


  @typing.overload
  def postgres_retry[**P, T](func: _Func[P, T], *, retries: int | None = ...) -> _Func[P, T]: ...


  @typing.overload
  def postgres_retry[**P, T](func: None = ..., *, retries: int | None = ...) -> _Decorator[P, T]: ...


  def postgres_retry[**P, T](
      func: _Func[P, T] | None = None,
      *,
      retries: int | None = None,
  ) -> _Func[P, T] | _Decorator[P, T]:
  ```

  with the pre-695 form (module-level `P`/`T`, `TypeAlias` aliases):

  ```python
  P = typing.ParamSpec("P")
  T = typing.TypeVar("T")

  _Func: typing.TypeAlias = typing.Callable[P, typing.Coroutine[None, None, T]]
  _Decorator: typing.TypeAlias = typing.Callable[[_Func], _Func]


  @typing.overload
  def postgres_retry(func: _Func, *, retries: int | None = ...) -> _Func: ...


  @typing.overload
  def postgres_retry(func: None = ..., *, retries: int | None = ...) -> _Decorator: ...


  def postgres_retry(
      func: _Func | None = None,
      *,
      retries: int | None = None,
  ) -> _Func | _Decorator:
  ```

  Leave the function body (the `decorator` / `wrapped_method` nesting and the
  `tenacity.AsyncRetrying` construction, currently lines 39-55) completely
  unchanged. `import typing` is already present at the top — do not re-import.

- [ ] **Step 3: Type-check the rewrite**

  Run: `uv run ty check`
  Expected: PASS, no errors. Confirms the overloads and aliases still
  type-check (no inference regression from dropping PEP 695).

- [ ] **Step 4: Run the retry tests to confirm behavior is preserved**

  Run: `uv run pytest tests/test_retry.py -v`
  Expected: PASS — same set of tests green as in Step 1.

- [ ] **Step 5: Promote into `architecture/retry.md`**

  In `architecture/retry.md`, in the "Public surface" section, append a
  sentence to the paragraph ending at line 19 (after
  "...it returns a decorator.") noting the typing form:

  ```markdown
  The generics are expressed with module-level `typing.ParamSpec`/`TypeVar`
  and `TypeAlias` aliases (`_Func`, `_Decorator`) rather than PEP 695 syntax,
  so the module parses on Python 3.11+.
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add db_retry/retry.py architecture/retry.md
  git commit -m "refactor: express postgres_retry generics pre-PEP-695 for 3.11"
  ```

---

### Task 2: Widen packaging metadata and docs

**Files:**
- Modify: `pyproject.toml:8` (requires-python), `:11-18` (classifiers), `:58`
  (ruff target-version)
- Modify: `README.md:216`

**Interfaces:**
- Consumes: nothing.
- Produces: a package installable on 3.11+; ruff linting at `py311` target
  (which, being below 3.12, will not suggest reverting to PEP 695 syntax).

- [ ] **Step 1: Lower the Python floor in `pyproject.toml`**

  Change line 8 from:

  ```toml
  requires-python = ">=3.13,<4"
  ```

  to:

  ```toml
  requires-python = ">=3.11,<4"
  ```

- [ ] **Step 2: Add the 3.11 and 3.12 classifiers**

  In the `classifiers` list, add the two entries above the existing 3.13 line
  so the block reads:

  ```toml
      "Programming Language :: Python :: 3.11",
      "Programming Language :: Python :: 3.12",
      "Programming Language :: Python :: 3.13",
      "Programming Language :: Python :: 3.14",
  ```

- [ ] **Step 3: Lower the ruff target version**

  Change line 58 from:

  ```toml
  target-version = "py313"
  ```

  to:

  ```toml
  target-version = "py311"
  ```

- [ ] **Step 4: Update the README support line**

  In `README.md`, change line 216 from `- Python 3.13+` to `- Python 3.11+`.

- [ ] **Step 5: Run the full lint gate**

  Run: `just lint-ci`
  Expected: PASS — ruff `--check`, ruff format `--check`, eof-fixer, and
  `ty check` all clean at the new `py311` target. In particular, ruff must NOT
  raise UP040/UP046/UP047 (PEP 695 upgrade hints) against the Task 1 rewrite;
  if it does, the target lowering in Step 3 was not applied.

- [ ] **Step 6: Commit**

  ```bash
  git add pyproject.toml README.md
  git commit -m "chore: lower supported Python floor to 3.11"
  ```

---

### Task 3: Add the CI version matrix

**Files:**
- Modify: `.github/workflows/_checks.yml:18-44` (the `pytest` job)

**Interfaces:**
- Consumes: the 3.11-compatible package from Tasks 1-2.
- Produces: a `pytest` job that runs once per `3.11/3.12/3.13/3.14`, each
  against the postgres service, each holding the 100% coverage gate.

- [ ] **Step 1: Add the matrix and parameterize the interpreter**

  In `.github/workflows/_checks.yml`, edit the `pytest` job (lines 18-44). Add
  a `strategy` block under `runs-on`, and change the hardcoded
  `uv python install 3.13` to use the matrix value. The job becomes:

  ```yaml
    pytest:
      runs-on: ubuntu-latest
      strategy:
        fail-fast: false
        matrix:
          python-version:
            - "3.11"
            - "3.12"
            - "3.13"
            - "3.14"
      services:
        postgres:
          image: postgres:latest
          env:
            POSTGRES_DB: postgres
            POSTGRES_PASSWORD: password
            POSTGRES_USER: postgres
          ports:
            - 5432:5432
          options: >-
            --health-cmd pg_isready
            --health-interval 10s
            --health-timeout 5s
            --health-retries 5
      steps:
        - uses: actions/checkout@v6
        - uses: astral-sh/setup-uv@v8.2.0
        - run: uv python install ${{ matrix.python-version }}
        - run: |
            uv sync --all-extras --no-install-project
            uv run --no-sync pytest . --cov=. --cov-report xml
          env:
            PYTHONDONTWRITEBYTECODE: 1
            PYTHONUNBUFFERED: 1
            DB_DSN: postgresql+asyncpg://postgres:password@127.0.0.1/postgres
  ```

  Leave the `lint` job (lines 5-16) unchanged — it stays pinned to 3.13.

- [ ] **Step 2: Validate the workflow YAML parses**

  Run: `uv run python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/_checks.yml').read_text())"`
  Expected: no output, exit 0 (valid YAML).

- [ ] **Step 3: Commit**

  ```bash
  git add .github/workflows/_checks.yml
  git commit -m "ci: run pytest across Python 3.11-3.14"
  ```

---

### Task 4: Finalize the planning bundle and open the PR

**Files:**
- Modify: `planning/changes/2026-06-30.01-python-3.11-3.12-support/design.md`
  (frontmatter `summary`)

**Interfaces:**
- Consumes: the shipped Tasks 1-3.
- Produces: a validated planning bundle and a PR with CI running.

- [ ] **Step 1: Finalize the bundle summary to the realized result**

  The `summary:` was written as intent; confirm it states what shipped. Leave
  it as-is if still accurate, or tighten to the realized result (one line).

- [ ] **Step 2: Validate planning shape**

  Run: `just check-planning`
  Expected: `planning: OK`.

- [ ] **Step 3: Run the full local pipeline once**

  Run: `just lint-ci` then `uv run pytest`
  Expected: both PASS locally (DB_DSN set, or via `just test` in Docker).

- [ ] **Step 4: Push and open the PR**

  ```bash
  git push -u origin feat/python-3.11-3.12-support
  gh pr create --fill
  ```

  Then watch CI: `gh pr checks --watch`. The four pytest matrix legs
  (3.11-3.14) and the lint leg must all go green. The 3.11 leg is the real
  proof that the Task 1 rewrite is syntax-compatible.

---

## Self-review notes

- **Spec coverage:** retry.py rewrite (Task 1), pyproject requires-python +
  classifiers + ruff target (Task 2), README (Task 2), CI matrix (Task 3),
  architecture promotion (Task 1 Step 5), bundle finalize (Task 4). All design
  sections mapped.
- **No new tests:** by design — the existing suite is the behavior contract and
  the CI matrix is the cross-version proof. No version-gated branches added.
- **Type consistency:** alias names `_Func` / `_Decorator` and the public name
  `postgres_retry` are used identically across Task 1 and the architecture
  promotion.
