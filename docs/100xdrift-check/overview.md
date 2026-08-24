---
type: tool
title: 100xdrift-check
description: Drift review for a repo holding several plugins — when a PR edits a plugin file, report which sibling copies elsewhere in the repo the change likely applies to.
resource: ../../plugins/100xdrift-check/templates/skills/drift-check/SKILL.md
tags: [100xdrift-check, drift, review, ci]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-12T00:00:00Z
---

# Overview

A repo that holds several plugins ends up holding several copies of the same thing — one
`weekly-report` skill per region, one `deploy` command per team. They are copied once and
then edited separately. A bug fixed in one copy stays broken in the others, and nobody
notices until a user hits it.

drift-check is the reviewer that notices. When a pull request edits a watched plugin file,
a headless Claude run reads the diff, finds the sibling copies in the repo's *other*
plugins, and posts a non-blocking comment saying which siblings the change probably applies
to and which are legitimately different.

**It reports.** It never edits a file, never enforces parity, never blocks a merge.
Divergence between siblings is usually deliberate — see [verdict](verdict.md) for how that
judgment is expressed.

## Three moving parts

| Part | Lives | Job |
| --- | --- | --- |
| Two install skills | in the plugin, `skills/` | copy the other two into your repo |
| The reviewer | your repo, `.claude/skills/drift-check/` | reads diffs, writes `drift-report.md` |
| The workflow | your repo, `.github/workflows/drift-check.yml` | runs the reviewer on a PR, posts the comment |

The plugin itself reviews nothing. It is an installer, and everything that does the work
runs from the consuming repo — see [vendored reviewer](vendored-reviewer.md) for why that
is load-bearing rather than a packaging accident.

## What it will not do

It searches [one repository](one-repository.md) and no other. What counts as a reviewable
file is not its decision either — that is the [watch list](watch-list.md), which the
reviewer reads rather than assumes.
