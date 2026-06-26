# connection-plan-split — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking. New behaviour/tests are TDD —
> failing test first.

**Goal:** Extract a pure `build_connection_plan(url) -> ConnectionPlan` out of
`build_connection_factory`, leaving a thin failover loop with a single `_connect`
helper — parsing/ordering testable without mocking `asyncpg.connect`, connect
call written once, behaviour unchanged.

**Spec:** [`design.md`](./design.md)

**Branch:** `feat/connection-plan-split`

**Commit strategy:** Per-task commits.

---

### Task 1: Pure plan + mock-free tests, TDD

**Files:**
- Modify: `tests/test_connection_factory.py` (add plan tests)
- Modify: `db_retry/connections.py` (add `ConnectionPlan` + `build_connection_plan`)

Introduce the pure plan, built test-first. Do NOT yet rewire
`build_connection_factory` (Task 2) — add the new code alongside the existing
closure.

- [ ] **Step 1: RED — write the plan tests**

  In `tests/test_connection_factory.py`, add mock-free tests importing
  `build_connection_plan` (and `ConnectionPlan`) from `db_retry.connections`:
  - multi-host DSN (`host=host1:5432&host=host2:5432`, with a
    `target_session_attrs`): assert `set(plan.failover) == {("host1",5432),("host2",5432)}`;
    `list(zip(plan.primary_host, plan.primary_port)) == list(plan.failover)`
    (host/port stay paired through the shuffle); `plan.target_session_attrs ==
    SessionAttribute("read-write")` (or whatever the DSN sets); `"host"`,
    `"port"`, `"target_session_attrs"` are NOT in `plan.connect_args`.
  - single-host DSN: `plan.failover == ()`; `plan.primary_host == "host"` (scalar);
    `plan.primary_port` is the scalar/None; tsa correct.
  Run `uv run pytest tests/test_connection_factory.py -k plan` → fails
  (ImportError / AttributeError). No DB needed for these.

- [ ] **Step 2: GREEN — write the plan**

  In `db_retry/connections.py` add the `ConnectionPlan` dataclass
  (`kw_only=True, frozen=True, slots=True`, `connect_args: Mapping`,
  `target_session_attrs`, `primary_host`, `primary_port`, `failover`) and the
  pure `build_connection_plan(url)` per the spec: `create_connect_args`, pop +
  wrap tsa, pop host/port, multi-host → `zip(strict=True)` + `random.shuffle`
  once → derive primary + failover from the same shuffled pairs; single-host →
  scalars + `failover=()`. No timeout, no logging, no `asyncpg.connect`.

  Run `uv run pytest tests/test_connection_factory.py -k plan` → pass. No mock.

- [ ] **Step 3: Commit**

  ```bash
  git add db_retry/connections.py tests/test_connection_factory.py
  git commit -m "feat: extract pure build_connection_plan from connection factory"
  ```

---

### Task 2: Rewire the factory onto the plan + single `_connect`

**Files:**
- Modify: `db_retry/connections.py`

Replace the factory's inline parse + duplicated connect with the plan + a single
`_connect` helper. Behaviour-preserving.

- [ ] **Step 1: Edit**

  - Add `async def _connect(plan, host, port, timeout)` — the single
    `asyncpg.connect(**plan.connect_args, host=host, port=port, timeout=timeout,
    target_session_attrs=plan.target_session_attrs)` call.
  - Add `_reshuffled(failover)` — returns a freshly shuffled copy each call
    (e.g. `random.sample(failover, len(failover))`), preserving the per-call
    failover re-shuffle.
  - Rewrite `build_connection_factory`: `plan = build_connection_plan(url)` once;
    the closure tries `_connect(plan, plan.primary_host, plan.primary_port,
    timeout)`, on `TimeoutError` reraises if `not plan.failover` else logs and
    falls through; iterates `_reshuffled(plan.failover)` calling `_connect`,
    swallowing `(TimeoutError, OSError, asyncpg.TargetServerAttributeNotMatched)`
    with the per-host warning; raises `TargetServerAttributeNotMatched` naming
    `plan.target_session_attrs` if all fail.
  - Remove the now-inlined parse code and the duplicated connect. Drop imports
    that are now only used inside `build_connection_plan` if they end up unused
    at module scope (most stay). Keep the warning log strings verbatim.
  - Keep the per-call re-shuffle in the loop — do NOT move it into
    `build_connection_plan`.

- [ ] **Step 2: Verify**

  - `just test` (Docker Postgres) → all green, including the four existing loop
    tests (success / single-host reraise / multi-host all-fail / fail-then-success).
  - `just lint-ci` → clean.

- [ ] **Step 3: Commit**

  ```bash
  git add db_retry/connections.py
  git commit -m "refactor: drive connection factory through ConnectionPlan and one _connect"
  ```

---

### Task 3: Promote the architecture doc + finalize bundle

**Files:**
- Modify: `architecture/connections.md`
- Modify: `planning/changes/2026-06-26.03-connection-plan-split/design.md` (summary)

- [ ] **Step 1: Edit `architecture/connections.md`**

  Document the split: `build_connection_plan` → `ConnectionPlan` (primary +
  failover, host/port paired through the shuffle), the single `_connect` helper,
  and that the per-call failover re-shuffle lives in the loop while the bulk
  shuffle is computed once at build. Keep the two-stage rationale and the
  signature of `build_connection_factory` (unchanged public surface). No
  frontmatter.

- [ ] **Step 2: Finalize summary + verify planning**

  Set `design.md` `summary:` to the realized result. `just check-planning` →
  `planning: OK`.

- [ ] **Step 3: Commit**

  ```bash
  git add architecture/connections.md planning/
  git commit -m "docs: promote connection-plan split into architecture/connections.md"
  ```

---

### Task 4: Ship

- [ ] **Step 1:** `just lint-ci` and `just test` both green.
- [ ] **Step 2:** Push `feat/connection-plan-split`, open PR, watch CI.
