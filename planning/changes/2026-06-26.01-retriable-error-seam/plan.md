# retriable-error-seam — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking. Each bug/behaviour is TDD —
> failing test first.

**Goal:** Move the retriable-error decision behind a pure
`is_retriable(exc) -> bool` seam in `db_retry/retriable.py`, tested in memory,
with `postgres_retry` as a thin consumer.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/retriable-error-seam`

**Commit strategy:** Per-task commits.

---

### Task 1: Pin the domain term (glossary)

**Files:**
- Create: `architecture/glossary.md`

Author `architecture/glossary.md` lazily with its first term, **Retriable
error**, using the `planning/_templates/glossary.md` shape.

- [ ] **Step 1: Write the term**

  Entry: **Retriable error** — a PostgreSQL failure transient enough to retry
  the operation unchanged: a serialization failure (`40001`) or a lost
  connection (class `08`). `_Avoid_:` transient error, recoverable error.
  No implementation detail.

- [ ] **Step 2: Commit**

  ```bash
  git add architecture/glossary.md
  git commit -m "docs: add Retriable error to glossary"
  ```

---

### Task 2: New `retriable.py` seam, TDD

**Files:**
- Create: `tests/test_retriable.py`
- Create: `db_retry/retriable.py`

Build the pure predicate test-first.

- [ ] **Step 1: Write the failing matrix**

  `tests/test_retriable.py`: a `_make_dbapi_error(cause)` helper building a
  `DBAPIError("...", None, orig)` whose `orig.__cause__ = cause`. Parametrized
  cases per the spec's Testing section — 40001, 08000, an 08-subclass
  (`ConnectionDoesNotExistError`), non-retriable `PostgresError`, re-wrapped
  `RepositoryError.__cause__` chain, `__context__`-only link, a `__cause__`
  cycle, and a bare non-DBAPI exception. Import `is_retriable` and
  `RETRIABLE_ASYNCPG_ERRORS` from `db_retry.retriable`.

  Run: `uv run pytest tests/test_retriable.py` → fails (ModuleNotFound).

- [ ] **Step 2: Write the module to green**

  `db_retry/retriable.py`: `RETRIABLE_ASYNCPG_ERRORS` tuple, private
  `_is_retriable_link`, pure `is_retriable` with the cause/context walk + cycle
  guard. No logger.

  Run: `uv run pytest tests/test_retriable.py` → all pass. No DB needed.

- [ ] **Step 3: Commit**

  ```bash
  git add db_retry/retriable.py tests/test_retriable.py
  git commit -m "feat: extract is_retriable predicate into retriable.py"
  ```

---

### Task 3: Rewire `retry.py` onto the seam

**Files:**
- Modify: `db_retry/retry.py`

Replace the private predicate with a thin logging wrapper over `is_retriable`.

- [ ] **Step 1: Edit**

  Import `is_retriable` from `db_retry.retriable`. Add `_log_and_decide`
  (preserves both debug lines verbatim). Point `retry=tenacity.retry_if_exception`
  at it. Delete `_is_retriable_dbapi_error` and `_retry_handler`. Remove the now
  unused `asyncpg` / `DBAPIError` imports if no longer referenced.

- [ ] **Step 2: Verify lint + types**

  Run: `just lint-ci` → passes (ruff, ty, eof, planning).

- [ ] **Step 3: Commit**

  ```bash
  git add db_retry/retry.py
  git commit -m "refactor: wire postgres_retry through is_retriable seam"
  ```

---

### Task 4: Trim the integration suite

**Files:**
- Modify: `tests/test_retry.py`

Move the classification matrix to Task 2; keep two wiring proofs.

- [ ] **Step 1: Edit**

  Reduce to two integration cases against the live engine: `40001` (retriable →
  retries, assert attempt count) and `40002` (non-retriable → single call,
  original `DBAPIError` reraised). Keep `test_postgres_retry_with_retries`
  (per-callsite `retries=` override). Delete the full parametrized matrix and
  the advanced-alchemy case (now covered in `test_retriable.py`).

- [ ] **Step 2: Verify**

  Run: `just test` (Docker Postgres) → green. `just lint-ci` → passes.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/test_retry.py
  git commit -m "test: trim retry integration suite to wiring proofs"
  ```

---

### Task 5: Promote architecture docs + finalize bundle

**Files:**
- Create: `architecture/retriable.md`
- Modify: `architecture/retry.md`, `architecture/README.md`
- Modify: `planning/changes/2026-06-26.01-retriable-error-seam/design.md` (summary)

- [ ] **Step 1: Write `architecture/retriable.md`**

  Document `is_retriable`, `RETRIABLE_ASYNCPG_ERRORS`, the cause-chain walk +
  cycle guard, and why `40002` is excluded. No frontmatter.

- [ ] **Step 2: Edit `architecture/retry.md`**

  Drop "What counts as retriable" / "Cause-chain walk"; replace with a one-line
  pointer to `retriable.md` and note the `_log_and_decide` wiring.

- [ ] **Step 3: Edit `architecture/README.md`**

  Add the `retriable.md` capability row; update the `retry.md` row so it no
  longer claims the predicate.

- [ ] **Step 4: Finalize `summary:` and verify planning**

  Set `design.md` `summary:` to the realized result. Run `just check-planning`
  → `planning: OK`.

- [ ] **Step 5: Commit**

  ```bash
  git add architecture/ planning/
  git commit -m "docs: promote retriable capability into architecture/"
  ```

---

### Task 6: Ship

- [ ] **Step 1:** `just lint-ci` and `just test` both green.
- [ ] **Step 2:** Push `feat/retriable-error-seam`, open PR, watch CI.
