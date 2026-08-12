---
name: install-workflow
description: Install the drift-check GitHub Actions workflow into the current repo at .github/workflows/drift-check.yml, and vendor the reviewer skill to .claude/skills/drift-check/ if it is not there yet, so drift review runs on every PR. Run once per repo, invoked explicitly as /100xdrift-check:install-workflow. Do NOT use to run a drift review (that is /drift-check, once vendored).
---

# Install the drift-check CI workflow

Set the repo up to run drift review on every pull request. You write at most two paths,
then report. Nothing else.

Read from the plugin at `${CLAUDE_PLUGIN_ROOT}`, write into the user's repo root.

## What you create

| Path | Purpose |
|---|---|
| `.github/workflows/drift-check.yml` | Runs drift-check on every PR touching a watched file |
| `.claude/skills/drift-check/` | The review skill — **only if it is not already there** |

Both are required for CI to work, and both must be committed. The Action starts a bare
Claude Code session with no plugins installed, and the plugin ships the reviewer as a
template rather than as one of its own skills — so the workflow's `/drift-check` prompt
resolves against the vendored copy or nothing at all. Vendoring also pins the review
contract to the commit under review rather than to whatever the marketplace holds that
day.

## Steps

### 1. Require a git repo

Run `git rev-parse --show-toplevel`. On failure, stop without writing anything: drift
review is a diff, so a repo is the precondition. Say so and suggest `git init`.

### 2. Look at what will be reviewed

The template watches the three prompt surfaces: `**/SKILL.md`, `**/commands/**`,
`**/agents/**`. Count what this repo has of each, plus what it has that stays unwatched:

```bash
# Watched by default.
find . -name SKILL.md -not -path './.git/*' | head -50
find . -path '*/commands/*' -name '*.md' -not -path './.git/*' | head -50
find . -path '*/agents/*' -name '*.md' -not -path './.git/*' | head -50
# NOT watched by default — opt-in globs, commented out in the workflow.
find . \( -name hooks -o -name .mcp.json -o -name references \) -not -path './.git/*' | head -20
```

Report the counts in step 5. If nothing watched exists yet, still install — say that
nothing is reviewable until a watched file lands.

Siblings come from this repository's other plugins and nowhere else, so a repo with one
plugin will get "no siblings" reports until a second one lands. Say that plainly rather
than implying the check is broken — and do not go looking outside the repo, there is no
setting for it.

If the repo has hooks, `.mcp.json` or skill `references/`, say so and point at the
commented-out globs. If it has no commands or no agents, say that too — those lines are
dead weight and can be deleted. Either way do NOT edit the list yourself: scope is the
repo owner's call, and every watched glob costs CI runs.

### 3. Make sure the skill is vendored

```bash
ls .claude/skills/drift-check/SKILL.md
```

If it is missing, read `${CLAUDE_PLUGIN_ROOT}/skills/install-skill/SKILL.md` and carry
out its copy step. One source of truth for how the vendoring is done — do not restate the
commands here, they change there.

If it is already present, leave it alone and say so. The repo's copy wins, including one
that was deliberately edited; refreshing it is `/100xdrift-check:install-skill`'s job, not
this skill's.

### 4. Write the workflow

Create `.github/workflows/` if it does not exist, then copy
`${CLAUDE_PLUGIN_ROOT}/templates/workflows/drift-check.yml` to
`.github/workflows/drift-check.yml` **unchanged**. It is layout-agnostic — it triggers on
any skill, command or agent file wherever they sit — so it needs no per-repo edits to work.

Leave the `paths:` list exactly as shipped. It is the one place that defines what
drift-check reviews, it carries wider globs commented out with guidance, and choosing that
scope belongs to whoever owns the repo — not to an install step.

If the file already exists, diff it against the template, show what differs, and ask
whether to keep or replace. Default to keep.

### 5. Verify and report

Confirm the workflow file and `.claude/skills/drift-check/SKILL.md` both exist. Then print
exactly this, filling in the real status:

```
✓ Added:     .github/workflows/drift-check.yml
✓ Reviewer:  .claude/skills/drift-check/   (<added now | already there, left as is>)
✓ Watching:  skills <N>   commands <N>   agents <N>
！Unwatched: <hooks | .mcp.json | skill references/> found — uncomment the matching
             glob in the workflow's paths: list to review them too
✓ Scope:     this repository — <N> plugins, siblings found among them

Next:
  1. Commit and push both paths — the check reads them from the pull request itself
  2. Let GitHub run Claude: run `claude setup-token`, copy the token, then add it at
     GitHub → Settings → Secrets and variables → Actions → New repository secret,
     named exactly CLAUDE_CODE_OAUTH_TOKEN
     (Skip it and the check still runs — it just posts a note saying it was skipped.)
  3. Open a pull request that touches a watched file and watch for the comment
```

Drop any line that does not apply. If something failed, say which step and why.

## Notes

- Never overwrite an existing file without asking
- The workflow is non-blocking — it reports drift but never fails a PR
- Without the token the job still runs and posts a note saying it was skipped
- Every CI run uploads an artifact holding `drift-report.md`, `changed-skill-files.txt`,
  and Claude's full execution transcript — that is where a reviewer looks when a verdict
  seems wrong
- Widening `paths:` later means mirroring the same globs in the `git diff -- '<pathspec>'`
  of the *Collect changed skill files* step; the two must agree or the job finds nothing
