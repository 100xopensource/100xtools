# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Public, Apache-2.0 tooling for maintaining Claude Code plugins, extracted from a private
plugin fleet. One repo, one directory per tool under `plugins/`. Each tool is an ordinary
Claude Code plugin *and* a CI gate — that dual role is why they are built to run offline,
from a clean clone, with no install step.

```
.claude-plugin/marketplace.json   one entry per plugin; CI checks it against plugins/
docs/                             OKF knowledge bundle — concepts, NOT shipped with plugins
examples/<tool>/                  worked eval cases + vendored third-party plugins
plugins/<name>/                   self-contained plugin: manifest, README, skills/
scripts/check_docs.py             OKF bundle conformance + link check
.github/workflows/ci.yml          test · static · examples · docs · manifests
```

Two things about `examples/` that look odd until you know why:

- **`examples/plugin-eval/cases` is a second case root.** The default is `evals/`, so the
  example cases are only found with `--cases-dir examples/plugin-eval/cases`. CI dry-runs them, which proves they parse and
  resolve their plugins without a model call.
- **`vendor/` is skipped by plugin discovery** (`lint.py`). Third-party code copied in for
  fixtures is not ours to score, and discovering it would turn our own sweep into a report
  card on someone else's plugin. Lint it deliberately with `--target` if you want to.

## Repo-wide invariants

These hold for every plugin here and explain most of the layout decisions. Read them before
moving files.

**1. A plugin must be self-contained.** A marketplace install copies `plugins/<name>/` and
nothing else — no repo root, no `docs/`, no sibling plugin. Everything a plugin needs to
*operate* lives inside its own directory. Consequences worth knowing, because each looks
arbitrary in isolation:

- Skill `references/` stay the source of truth for how to use a tool; `docs/` links to them
  rather than restating them.
- `scripts/check_docs.py` is a repo-level script, not a plugin unit test — the plugin suite
  has to pass for someone who has only the plugin.
- Anything a plugin genuinely needs is duplicated *into* it, not imported from the root.

**2. Python stdlib only.** No third-party dependencies anywhere, including tests. Hard
constraint, not a preference — `yamlmin.py` exists rather than a PyYAML dependency.

**3. Nothing internal, customer-specific, or unlicensed ships.** This repo was extracted
from a private one. Fixtures use `Acme` and `example.com`/`example.net`. Real connector
URLs, plugin names, store/customer names, captured `claude mcp list` output, ticket IDs
(`AIP-`/`OST-`), internal doc paths, and vendor system prompts must not appear. Sweep before
committing — a captured `claude mcp list` fixture leaked through the first port and was
caught only on a second pass.

**4. Trust-boundary files need author ≠ reviewer.** `.github/workflows/*`,
`plugins/100xdrift-check/templates/workflows/drift-check.yml`,
and `plugins/100xdrift-check/templates/skills/drift-check/SKILL.md` decide what CI does with
model output and what tools the model gets. Checks there only ever tighten; if a change relaxes a guard, say
so explicitly rather than letting a reviewer find it.

**5. Every plugin scores 1.00** on the static linter this repo ships. CI dogfoods it, so a
change that makes our own plugins look bad fails here rather than in someone else's repo.

## The three documentation surfaces

Easy to put something in the wrong one. They have different audiences and different
lifetimes:

| Surface | Answers | Ships with the plugin? |
| --- | --- | --- |
| `plugins/<name>/README.md` | How do I install and run this? | Yes |
| `skills/<name>/SKILL.md` + `references/` | How should Claude operate it? | Yes |
| `docs/` (OKF bundle) | What is this concept and why does it exist? | **No** |

`docs/` is [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
v0.2: one concept per file, YAML frontmatter, `type` required, `index.md`/`log.md` reserved,
provenance in a `generated: { by, at }` mapping whose `by` follows the spec's actor
convention. The bundle root declares `okf_version` in `index.md` frontmatter — the one place
a reserved file is allowed any.

It is concept-only by design and must never become load-bearing for operating a plugin, per
invariant 1. Links inside it are relative rather than bundle-absolute so they resolve on
GitHub; `docs/index.md` records that deviation.

`scripts/check_docs.py` enforces all of the above plus link resolution, and fails on a
leftover v0.1 `timestamp` field so a spec migration cannot half-happen.

## Commands

No install, build, or lockfile step anywhere.

```bash
# From the REPO ROOT
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only   # design quality, free
python3 scripts/check_docs.py                                                # docs bundle

# Why a plugin scored what it scored (the report prints scores, not findings)
python3 -c "
import sys; sys.path.insert(0, 'plugins/100xeval/skills/100xeval/scripts')
from engine import static
for f in static.analyze('plugins/100xeval')['findings']: print(f)"
```

```bash
# 100xeval engine tests — offline; no model, MCP, or network calls
cd plugins/100xeval/skills/100xeval
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'

# One module / class / test
PYTHONPATH=scripts python3 -m unittest tests.test_lint
PYTHONPATH=scripts python3 -m unittest tests.test_lint.TestSecurityChecks.test_path_traversal_flagged
```

**`tests/` sits beside `scripts/`, not inside it** — `scripts/` is the runtime payload that
ships and that Claude invokes, so the suite stays out of it. Both the `cd` and
`PYTHONPATH=scripts` are required: tests import `engine.*` absolutely and have no idea where
they live. Note the shell's cwd persists between tool calls — a command run from the repo
root fails if you are still inside the skill directory, and vice versa.

CI runs exactly these. If they pass locally they pass there. Behavioral eval runs cost money
and need credentials, so they are **not** wired into this repo's CI — see
`plugins/100xeval/README.md` to run them.

`scripts/hooks/pre-commit` runs all of the above plus a secret and internal-reference sweep
over **staged** content, in about two seconds. Enable per clone with `git config
core.hooksPath scripts/hooks`; `--no-verify` bypasses it. Generic secret shapes live in the
hook; org-specific names go in the gitignored `scripts/hooks/leak-patterns.local` (copy the
`.example`) — a public list of the names you are hiding publishes them.

## Plugins

### 100xeval — behavioral + static evaluation

**Eval flow:** `run.py` → `cli` → `loader` → `orchestrator` → harness → graders → `reporter`.

- **`loader.py`** walks `evals/**/case.yaml`, flattens `execution.*` onto a `Case`, and
  validates. Paths in `plugins:` resolve **relative to the case file**, not the repo root.
- **`orchestrator.run_case`** runs one case `runs` times concurrently, scores each grader as
  `passRate = passed/runs`, and takes a weighted mean. Concurrency is a **suite-wide**
  budget shared across cases, not per-case.
- **`harnesses/`** is the runtime seam, registered via `base.register_harness`. Only
  `claude_code` is implemented; `codex` is a seam that aborts in preflight.
- **`graders.py`** holds a `_GRADERS` name→function registry populated at import time
  (`tool_used`, `regex`, `llm`, `static`). `llm` delegates to `judge.py`, majority voting
  over N votes.
- **`reporter.py`** emits markdown/JSON/HTML with a `schemaVersion` on the JSON.

**The two axes — `harness` vs `entrypoint`** are independent and the single easiest thing to
get wrong. `harness` is the **runtime** that executes and observes the turn; `entrypoint` is
the **surface** emulated, its real system prompt swapped in with `--system-prompt`
(replacing, not appending). A surface is never a harness — the loader rejects
`harness: cowork` and `harness: claude_chat` with a message naming the right pair.

Default `entrypoint: none` passes no `--system-prompt`. **`cowork` is the one entrypoint
tracked here**, by explicit decision — see the git history for that file. Any *other*
surface prompt stays gitignored by default, because it usually belongs to whoever operates
that surface. `--entrypoint <name>` overrides every case in a run. Any *other* name must resolve to a file or preflight aborts — a case that
emulates nothing still scores, and a pass for the wrong reason is worse than a failure.

**The static layer — lint → check ID → sub-score.** `lint.py` emits `Finding`s whose `.msg`
**starts with** a bracketed ID (`[FM3]`, `[PD1]`, `[SEC1]`). The **prefix names the
sub-score**, so `static.py` derives the mapping from `_PREFIX_TO_SUBCHECK`
(`FM` · `PD` · `RH` · `ST` · `EC` · `SEC`) rather than keeping a per-ID table, then weights
them (`security` ×2, `token_efficiency` ×0.5) and applies a flag-count penalty.

- **Adding a check:** pick the prefix for its sub-score, take the next free number, add a row
  to `docs/100xeval/check-ids.md`. An unregistered prefix *raises* (`UnknownCheckPrefix`)
  instead of scoring nothing; `TestCheckIdContract` fails in both directions, and
  `scripts/check_docs.py` fails if the docs page and `lint.py` disagree.
- `_ID_RE` is anchored to the start of the message on purpose — findings interpolate content
  from the plugin under test, and a bracketed token in there must not read as a check ID now
  that unknown prefixes raise.
- **SEC1 (secrets) scans every text file; SEC2/SEC3 scan skill prose only**
  (`_PROSE_SUFFIXES`). SEC2/SEC3 read a file as *instructions to the model*, so applying them
  to bundled source flagged every plugin that ships a script. SEC3 further requires a read
  verb near the `../`, so `plugins: ["../../plugins/x"]` doesn't fire.
- `token_efficiency` is the one sub-score with no check ID — computed directly by counting
  duplicate ≥20-char lines across **all** of a plugin's SKILL.md files. Its `seen` set spans
  the whole plugin on purpose: scoped per file it only caught a skill repeating itself and
  scored copy-paste between siblings at a clean 1.00, which is the case it exists for.
- `static.analyze()` only reads `.msg`, so any module exposing `lint_plugin(dir, root)` can
  replace `lint.py`.

**MCP auth produces two different tool-name schemes:** ambient account connector gives
`mcp__claude_ai_<Server>__<tool>`, strict plugin config (`--mcp-config … --strict-mcp-config`)
gives `mcp__<Server>__<tool>`. `canonical_tool_name` / `expand_tool_aliases` normalize across
both. Strict mode is preferred — auth comes from `MCP_<SERVER>_API_KEY` in the environment,
or from `MCP_<SERVER>_CLIENT_ID`/`_CLIENT_SECRET` which `mcp_oauth.py` exchanges for a
short-lived token (discovering the endpoint via RFC 9728 → RFC 8414, Basic auth and no scope by
default because that is what real connectors accept), rather than from whichever account is logged in, so runs behave
identically locally and in CI. A minted token is published to the **child process env** so the
config on disk still holds only `${VAR}` — both spawn sites (harness and agentic judge) apply
the overlay, and missing the judge would fail the grader that checks the numbers. The
variable is **per server, with no global fallback**: a plugin can declare two vendors' servers,
and one shared key would hand each vendor the other's credential. A server with no key set is
still passed through to `--strict-mcp-config`, just without an `Authorization` header. **A bad or
expired token surfaces as `tool_used` "called 0×", not as an auth error.** Check the token
before blaming the skill.

### 100xdrift-check — cross-plugin drift review

**Nothing in `skills/` reviews anything.** The plugin exposes exactly two installer skills;
the reviewer and the workflow live under `templates/` and are copied into the *user's* repo:

| Plugin path | Installed to | By |
| --- | --- | --- |
| `templates/skills/drift-check/` | `.claude/skills/drift-check/` | `install-skill` |
| `templates/workflows/drift-check.yml` | `.github/workflows/drift-check.yml` | `install-workflow` |

`install-workflow` installs the reviewer too **if absent**, and deliberately does not
refresh an existing copy — refreshing is `install-skill`'s job, so a repo that edited its
vendored copy keeps it. A file added under `templates/` is a file written into someone
else's repo.

**The vendoring is load-bearing, not a convenience.** The Action starts a bare Claude Code
session with no plugins installed, and the plugin ships no reviewer skill of its own, so
the workflow's `/drift-check` prompt resolves against the vendored copy or nothing at all.
It also pins the contract to the commit under review. The cost: the copy goes stale
silently, and in the consuming repo anyone who can open a PR can edit it.

This repo does **not** vendor a copy — `.claude/skills/` carries only the two `-concepts`
skills, which explain the tools rather than operate them. To try the reviewer here, install
it into a scratch repo, or use the fixture under `examples/plugin-drift-check/`.

`templates/skills/drift-check/SKILL.md` and `templates/workflows/drift-check.yml` are **one
contract split across two files**. The skill writes `drift-report.md` whose first line must
be `<!-- drift-status: critical|warning|good -->`; the workflow's `github-script` step
parses that marker to pick the comment's icon and headline, and classifies marker-less
skip/fallback notes itself. Change the vocabulary in one file without the other and every
report silently degrades to "warning".

The tool allowlist lives in the **workflow**, never in the skill — permissions belong to the
caller.

**Scope is one repository and there is no setting for it.** Siblings are the repo's other
plugins; the reviewer never reads `../`, never clones, never fetches. What counts as a
reviewable file is the workflow's `paths:` list — the single scope knob, which the reviewer
reads rather than assuming. That list and the `git diff -- '<pathspec>'` in the collect step
must change together; if they disagree, the job runs and finds nothing.

The workflow is not active in this repo — it is a template for repos that install it.

**No `disable-model-invocation` on these skills**, though all three want it: three SKILL.md
files carrying that one line read as duplication to `token_efficiency`, which counts
frontmatter. Re-add it together with a fix excluding frontmatter from that metric.

## Adding a plugin

1. `plugins/<name>/` with `.claude-plugin/plugin.json` and a `README.md` — CI's manifest job
   fails if a plugin is missing from `.claude-plugin/marketplace.json` or vice versa, and
   `ST1` fires without the README.
2. Keep it self-contained (invariant 1). Tests beside the runtime payload, not inside it.
3. Run the static check — it must score 1.00 before merge.
4. Optionally add `docs/<name>/` to the OKF bundle, and list it in `docs/index.md`.

## Gotchas

**Secret-shaped strings in test fixtures must be assembled at run time** (see
`tests/test_lint.py`), or the linter permanently flags its own fixtures and the security
sub-score becomes noise nobody reads.

**Linter checks earn their place by catching something probably wrong**, not something that
merely differs from a house style. The internal version's convention checks were dropped on
purpose. Every check needs a test asserting both directions: the dirty case fires and the
clean fixture stays clean.
