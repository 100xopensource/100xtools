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

### 100xdrift-check

- Two install skills — `install-skill` vendors the reviewer to `.claude/skills/drift-check/`,
  `install-workflow` adds the GitHub Actions job — plus the reviewer and workflow templates
  they install.
- **Draft.** Usable, but it has not been run against a real multi-plugin repo in anger.
