# Update Log

## 2026-08-10

* **Update**: Migrated the bundle from OKF v0.1 to
  [v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).
  The breaking change that applied here was `timestamp` giving way to the `generated`
  provenance mapping; every concept file now records the actor that drafted it in the §7
  actor form. The bundle root declares `okf_version: "0.2"`. `scripts/check_docs.py` grew
  matching checks, including one that fails on a leftover `timestamp` so the migration
  cannot half-happen.

* **Create**: Established the 100xtools knowledge bundle in Open Knowledge Format v0.1.
* **Create**: Added the [100xeval](100xeval/index.md) concept set — the eval case, graders,
  the harness/entrypoint axes, scoring, the design score, MCP auth, and the run folder.
* **Create**: Added the [check ID reference](100xeval/check-ids.md), covering every static
  check the linter emits. CI verifies it against `engine/lint.py`, so a new check that
  skips this file fails the build rather than going undocumented.
