---
type: concept
title: Watch list
description: The paths: list in the workflow is the single definition of what drift-check reviews — and it must be mirrored in the collect step's pathspec.
resource: ../../plugins/100xdrift-check/templates/workflows/drift-check.yml
tags: [100xdrift-check, scope, ci]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-12T00:00:00Z
---

# Watch list

A plugin is more than its skills. Commands, agents, hooks, MCP wiring and manifests get
copied between plugins too, and drift the same way — a fix to one plugin's
`commands/deploy.md` leaves the other three stale.

drift-check has no opinion about which of those you care about. **One list decides:
`paths:` in `.github/workflows/drift-check.yml`.** There is no config file, and the reviewer
reads that list rather than assuming what a reviewable file is.

It ships watching the three prompt surfaces:

```yaml
paths:
  - "**/SKILL.md"
  - "**/commands/**"
  - "**/agents/**"
```

Those three are literally instructions to a model, which is where "this copy has the same
bug" is a claim the reviewer can actually judge. The template carries wider globs — skill
`references/`, `hooks/`, `.mcp.json`, `plugin.json` — commented out. Those are config and
code, still reviewable, but the same-fix-applies claim is weaker there, so they are opt-in.

## Two rules when you edit it

**Mirror it in the diff.** The *Collect changed skill files* step runs
`git diff … -- '<pathspec>'` and must list the same globs. `paths:` decides which pull
requests start a run; the pathspec decides which files reach the reviewer. When they
disagree the job runs, finds nothing, and posts a green-looking "no files changed" note —
the worst failure mode available, because it looks like a pass.

**Widen deliberately.** Every added glob means more PRs spend a Claude session, and more
files competing for the 15-file cap that keeps a bulk change from being judged badly.
Trimming is equally valid: a repo with no `agents/` should drop that line.

## Why scope lives in the workflow

Permissions and cost belong to the caller, not to the prompt. The same reasoning puts the
tool allowlist in the workflow rather than in the reviewer skill: the repo owner decides
what a check is allowed to touch and what it is allowed to spend, and neither should be
changeable by editing a prompt.
