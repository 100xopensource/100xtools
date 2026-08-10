# Update Log

## 2026-08-10

* **Create**: Established the 100xtools knowledge bundle in Open Knowledge Format v0.1.
* **Create**: Added the [100xeval](100xeval/index.md) concept set — the eval case, graders,
  the harness/entrypoint axes, scoring, the design score, MCP auth, and the run folder.
* **Create**: Added the [check ID reference](100xeval/check-ids.md), covering every static
  check the linter emits. CI verifies it against `engine/lint.py`, so a new check that
  skips this file fails the build rather than going undocumented.
