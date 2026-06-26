# Glossary

The project's ubiquitous language — the domain terms that code, specs, and
capability pages share. Living prose, no frontmatter, dated by git. Each entry is
a term, what it *is* (not what it does), and the synonyms to avoid. No
implementation detail; this is a glossary, not a spec.

**Retriable error**:
A PostgreSQL failure transient enough to retry the operation unchanged: a
serialization failure or a lost connection. The operation may succeed if retried
without modification, because the failure does not reflect a logical error in the
request itself.
_Avoid_: transient error, recoverable error
