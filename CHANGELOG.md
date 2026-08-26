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
- `--comment PATH` writes a PR-comment-shaped scorecard: verdict first, one section per
  plugin, detail folded away, and hard-capped under GitHub's 65536-character comment limit.
  What it drops to fit is named in the body rather than silently cut. The documented CI
  workflow posts it as a sticky comment, which needs `pull-requests: write` on those jobs.
- Report JSON `schemaVersion` **2.1**: each case gained a `plugins` list of plugin names, so
  a report can be grouped by plugin. Additive — a 2.0 reader keeps working. **The scoring
  version is unchanged at 1**; no score moves.

### 100x-continuity

- **A factory, not a handoff plugin.** An Operator installs it, answers questions about
  their team and their storage, and it writes a *Kit* — a tailored plugin, with the store
  baked in — into their own plugin repo with its marketplace row. Their teammates install
  the Kit and use `hand-off` / `pick-up` in Cowork; they never see the factory.
- Three skills: `set-up-handoff` (interview → plan → your approval → write → verify),
  `verify`, and `store-service`. One entry point on purpose — see
  `docs/adr/0001-one-setup-skill.md`.
- **A setup run is put up as a board before it happens.** `status/board.html` and
  `status/tasks.json` land in the Operator's repo at plan time with every task still todo
  — the factory's steps and the ones that stay theirs — so they approve a plan they can
  see. Each is marked off as it lands, with the evidence that settled it and whether it
  was proven here or against a stand-in. It outlives the conversation: what is still
  outstanding, who each piece waits on, and what was never actually proven. Its operator
  half and the checklist in their `CLAUDE.md` are rendered from one list, and everything
  written to it is redacted first.
- Two store kinds: a **folder** a sync client already watches, or a **service** — object
  storage behind an MCP server the Operator runs, which mints presigned URLs so a Kit
  never holds a credential. `s3` is not a kind; it is what a service store sits on.
- A publication is one reproducible zip plus a marker written last. The same conversation
  and files pack to identical bytes, so handing unchanged work over twice is recognised
  rather than filed twice.
- Emitting also writes a marked section into the destination repo's `CLAUDE.md`. The
  factory runs once, so what is still the Operator's to do lives in their repository
  rather than in the conversation that set it up.
- Every emitted Kit carries `tests/contract_test.py` — deterministic, offline, no model,
  driven from a synthetic session — plus the `claude plugin eval` cases its store can
  actually run. CI emits a Kit of each store kind and route, and runs its contract test.

### 100xdrift-check

- Two install skills — `install-skill` vendors the reviewer to `.claude/skills/drift-check/`,
  `install-workflow` adds the GitHub Actions job — plus the reviewer and workflow templates
  they install.
- **Draft.** Usable, but it has not been run against a real multi-plugin repo in anger.
