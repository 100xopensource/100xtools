# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Public, Apache-2.0 tooling for maintaining Claude Code plugins, extracted from a private
plugin fleet. One repo, one directory per tool under `plugins/`. Both tools are ordinary
Claude Code plugins *and* CI gates.

## Commands

The eval engine is stdlib-only — there is no install, build, or lockfile step.

```bash
# Full test suite (offline; no model, MCP, or network calls)
cd plugins/100xeval/skills/100xeval
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'

# One module / class / test
PYTHONPATH=scripts python3 -m unittest tests.test_lint
PYTHONPATH=scripts python3 -m unittest tests.test_lint.TestSecurityChecks
PYTHONPATH=scripts python3 -m unittest tests.test_lint.TestSecurityChecks.test_path_traversal_flagged
```

**`tests/` sits beside `scripts/`, not inside it.** `scripts/` is what ships in the plugin
and what Claude invokes at runtime, so the suite is deliberately kept out of that payload.
Both the `cd` and `PYTHONPATH=scripts` are required: tests import `engine.*` absolutely and
have no idea where they live, so without them you get `ModuleNotFoundError: No module named
'engine'`. Note the shell's cwd persists between tool calls — a later command run from the
repo root will fail if you are still inside the skill directory, and vice versa.

```bash
# Static design quality — free, no model, no API key. Run from the REPO ROOT.
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only

# Why a plugin scored what it scored (the report prints scores, not findings)
python3 -c "
import sys; sys.path.insert(0, 'plugins/100xeval/skills/100xeval/scripts')
from engine import static
for f in static.analyze('plugins/100xeval')['findings']: print(f)"
```

CI (`.github/workflows/ci.yml`) runs exactly the test suite, the static check, and a
manifest-consistency check. If those pass locally they pass there.

Behavioral eval runs cost money and need credentials, so they are **not** wired into this
repo's CI. See `plugins/100xeval/README.md` to run them.

## Architecture

### Eval flow

`run.py` → `cli` → `loader` → `orchestrator` → harness → graders → `reporter`.

- **`loader.py`** walks `evals/**/case.yaml` (root defaults to `evals`), flattens
  `execution.*` onto a `Case`, and validates. Paths in `plugins:` resolve **relative to the
  case file**, not the repo root — a scaffolded case in `evals/<name>/` points at
  `../../plugins/<p>`.
- **`orchestrator.run_case`** runs one case `runs` times concurrently, scores each grader as
  `passRate = passed/runs`, and takes a weighted mean. Concurrency is a **suite-wide**
  budget shared across cases, not per-case.
- **`harnesses/`** is the runtime seam, registered by name via `base.register_harness`.
  Only `claude_code` is implemented; `codex` exists as a seam that aborts in preflight.
- **`graders.py`** holds a `_GRADERS` name→function registry, populated at import time at
  the bottom of the file (`tool_used`, `regex`, `llm`, `static`). `llm` delegates to
  `judge.py`, which does majority voting over N votes.
- **`reporter.py`** emits markdown/JSON/HTML with a `schemaVersion` on the JSON.

### The two axes: `harness` vs `entrypoint`

These are independent and are the single easiest thing to get wrong here.

- `harness` = the **runtime** that executes and observes the turn (`claude_code`).
- `entrypoint` = the **surface** being emulated — that surface's real system prompt, swapped
  in with `--system-prompt` (replacing, not appending).

A surface is never a harness. The loader actively rejects `harness: cowork` and
`harness: claude_chat` with a message naming the right pair.

**No entrypoint files ship**, and `.gitignore` keeps it that way — a surface's system prompt
belongs to whoever operates that surface. The default `entrypoint: none` passes no
`--system-prompt`, so the run uses Claude Code's own. Any *other* name must resolve to a
file or preflight aborts: a case that emulates nothing still scores, and a pass for the
wrong reason is worse than a failure.

### The static layer: lint → check ID → sub-score

`lint.py` walks a plugin and emits `Finding`s whose `.msg` carries a bracketed check ID
(`[P2]`, `[S5]`, `[X1]`). `static.py` maps IDs → sub-scores via `_ID_TO_SUBCHECK`, weights
them (`security` ×2, `token_efficiency` ×0.5), and applies a flag-count penalty.

**Adding a check means touching both files.** An ID with no mapping is silently ignored, and
a sub-score with no ID mapped to it sits at 1.00 forever and dilutes every score. That is
why `output_contract` was dropped when the internal checklist was cut down.

Scoping rule worth knowing: **X1 (secrets) scans every text file; X3/X4 scan skill prose
only** (`_PROSE_SUFFIXES`). X3/X4 read a file as *instructions to the model*, so applying
them to bundled source flagged every plugin that ships a script. X4 further requires a read
verb near the `../`, so config examples like `plugins: ["../../plugins/x"]` don't fire.

`static.analyze()` only reads `.msg` off each finding, so any module exposing
`lint_plugin(dir, root)` can replace `lint.py`.

`token_efficiency` is the one sub-score with no check ID behind it — it is computed
directly in `static.py` by counting duplicate ≥20-char lines across **all** of a plugin's
SKILL.md files. Its `seen` set spans the whole plugin on purpose: scoped per file it only
caught a skill repeating itself and scored copy-paste between siblings at a clean 1.00,
which is the case the metric exists for.

### MCP: strict mode and tool-name canonicalization

Two auth paths, and they produce **different tool names**:

- Ambient account connector → `mcp__claude_ai_<Server>__<tool>`
- Strict plugin config (`--mcp-config … --strict-mcp-config`) → `mcp__<Server>__<tool>`

`claude_code.canonical_tool_name` / `expand_tool_aliases` normalize across both so one set
of grader tool names works either way. Strict mode is preferred: auth comes from
`EVAL_MCP_BEARER` in the environment rather than whichever account happens to be logged in,
so runs behave identically locally and in CI.

A bad or expired token surfaces as `tool_used` "called 0×" — not as an auth error. Check the
token before blaming the skill.

### drift-check: skill ↔ workflow coupling

`skills/drift-check/SKILL.md` and `workflows/drift-check.yml` are **one contract split
across two files**:

- The skill writes `drift-report.md` whose first line must be
  `<!-- drift-status: critical|warning|good -->`.
- The workflow's `github-script` step parses that marker to pick the comment's icon and
  headline, and classifies marker-less skip/fallback notes itself.

Changing the marker vocabulary in one file without the other silently degrades every report
to "warning". Both are trust-boundary files — the tool allowlist lives in the **workflow**,
never in the skill, because permissions belong to the caller.

The workflow is a copy-paste template for *other* repos, not active here. Its `paths:`
filter and the `git diff -- '<pathspec>'` in the collect step must be changed together; if
they disagree, the job runs and finds nothing.

## Constraints

**Python stdlib only.** No third-party dependencies in the engine, including in tests. This
is a hard constraint, not a preference — `yamlmin.py` exists rather than a PyYAML dependency.

**Nothing internal, customer-specific, or unlicensed.** This repo was extracted from a
private one. Fixtures use `Acme` and `example.com`/`example.net`. Real connector URLs,
plugin names, store/customer names, captured `claude mcp list` output, ticket IDs
(`AIP-`/`OST-`), internal doc paths, and vendor system prompts must not appear. Before
committing, sweep for them — a captured `claude mcp list` fixture leaked through the first
port and was caught only on a second pass.

**Secret-shaped strings in test fixtures must be assembled at run time** (see
`test_lint.py`), or the linter permanently flags its own fixtures and the security
sub-score becomes noise nobody reads.

**Linter checks earn their place by catching something probably wrong**, not something that
merely differs from a house style. The internal version's convention checks were dropped on
purpose. Every check needs a test asserting both directions: the dirty case fires and the
clean fixture stays clean.

**Both plugins must score 1.00** on their own static linter — CI dogfoods it.
