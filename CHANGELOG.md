# Changelog

Notable changes to 100xtools. Two things are versioned separately here, because they break
in different ways:

- **Releases** — the repo as a whole.
- **Scoring version** — the static `design_score` contract, printed with every report and
  carried in the JSON as `scoringVersion`. **A score is only comparable to another from the
  same scoring version.** It is bumped whenever a change would move an unchanged plugin's
  score: weights, the penalty, what counts as a finding, or which checks feed which
  sub-score. If you pin a threshold in CI, pin the scoring version you tuned it against.

## Unreleased

First public release. Scoring version **1**.

### 100xeval

- Behavioral layer: runs a plugin against saved `case.yaml` cases and grades with
  `tool_used`, `regex`, `llm` (format and agentic), and `static` graders.
- Static layer: `design_score` from a stdlib linter, no model or network.
- `--dry-run` shows what would execute and the rough spend before spending it.
- `--cases-dir` selects the case root, `--runs-dir` the artifact location (default
  `.runs/`), `--entrypoint` overrides the emulated surface for a whole run.

### 100x-continuity

- **A factory, not a handoff plugin.** An Operator installs it, answers questions about
  their team and their storage, and it writes a *Kit* — a tailored plugin, with the store
  baked in — into their own plugin repo with its marketplace row. Their teammates install
  the Kit and use `hand-off` / `pick-up` in Cowork; they never see the factory.
- Three skills: `set-up-handoff` (interview → plan → your approval → write → verify),
  `verify`, and `store-service`. One entry point on purpose — see
  `docs/adr/0001-one-setup-skill.md`.
- Two store kinds: a **folder** a sync client already watches, or a **service** — object
  storage behind an MCP server the Operator runs, which mints presigned URLs so a Kit
  never holds a credential. `s3` is not a kind; it is what a service store sits on.
- A publication is one reproducible zip plus a marker written last. The same conversation
  and files pack to identical bytes, so handing unchanged work over twice is recognised
  rather than filed twice.
- Every emitted Kit carries `tests/contract_test.py` — deterministic, offline, no model,
  driven from a synthetic session — plus six `claude plugin eval` cases. CI emits a Kit of
  each store kind and runs its contract test.
- **Supersedes 100xcontinuity**, which is removed. Same engine lineage, different product:
  v1 answered "let my later session pick this up", this answers "let *someone else* pick
  this up".

### 100xdrift-check

- Two install skills — `install-skill` vendors the reviewer to `.claude/skills/drift-check/`,
  `install-workflow` adds the GitHub Actions job — plus the reviewer and workflow templates
  they install.
- **Draft.** Usable, but it has not been run against a real multi-plugin repo in anger.
