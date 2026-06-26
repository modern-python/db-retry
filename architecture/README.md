# Architecture

The truth home: living prose describing what `db-retry` does **now**, one file
per capability. No frontmatter — these pages are dated by git, not by header.

**Promotion rule.** When a change alters a capability's behavior, the
implementing PR hand-edits the matching `architecture/<capability>.md` in the
same diff — never as a separate post-merge step. That edit is what keeps these
files true; the change bundle in [`planning/changes/`](../planning/changes/)
stays as the *why*. See [`planning/README.md`](../planning/README.md) for the
full convention.

The repo authors one file per capability here as capabilities are documented.
