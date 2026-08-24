---
type: concept
title: One repository
description: Siblings are the repo's other plugins and nothing else — a deliberate ceiling, because a comparison against whatever happened to be on disk reads as authoritative and is not.
resource: ../../plugins/100xdrift-check/templates/skills/drift-check/SKILL.md
tags: [100xdrift-check, scope, design]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-12T00:00:00Z
---

# One repository

The diff is this repo's. The siblings are this repo's other plugins. The comment lands on
this repo's pull request. The reviewer never reads `../`, never follows a symlink out of the
repo root, never clones, never fetches. There is no flag for it.

## Why not compare across repos

It is the obvious next feature and it is a trap.

Reviewing repo A against repo B means checking B out somewhere and pinning it to a ref. In
CI that is a checkout step someone has to maintain; locally it is whatever happens to be in
your sibling directory — a branch from three weeks ago, or a half-finished experiment. The
report would not say which; it would just render verdicts against it.

**A comparison against an unknown revision reads as authoritative and is not.** It produces
confident-looking `likely-applies` rows about a version nobody is shipping. That is worse
than no comparison, because a reviewer acts on it.

The honest version of cross-repo review needs pinned refs, a fetch step, and a report that
names the revision it compared against. Until that exists, the ceiling stays.

If you want copies compared, put the plugins in one repo. That is also usually the right
answer for the underlying problem.

## What you get instead

Every report states its scope on the second line, so nobody mistakes it for a wider check:

```
_Scope: this repository — 4 plugins searched._
```

A repo with a single plugin gets a one-line "no siblings" report for everything. That is a
[valid result](verdict.md#no-siblings-is-an-answer), not a misconfiguration.
