---
type: concept
title: Vendored reviewer
description: The plugin ships no reviewer skill — it ships a template that gets copied into the consuming repo, because CI runs with no plugins installed.
resource: ../../plugins/100xdrift-check/skills/install-skill/SKILL.md
tags: [100xdrift-check, install, trust-boundary]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-12T00:00:00Z
---

# Vendored reviewer

The plugin's `skills/` directory holds two installers and nothing else. The reviewer lives
under `templates/` and only ever runs from a copy inside the consuming repo, at
`.claude/skills/drift-check/`.

| Plugin path | Copied to | By |
| --- | --- | --- |
| `templates/skills/drift-check/` | `.claude/skills/drift-check/` | `install-skill` |
| `templates/workflows/drift-check.yml` | `.github/workflows/drift-check.yml` | `install-workflow` |

## Why not just ship it as a skill

**The GitHub Action starts a bare Claude Code session with no plugins installed.** A skill
that exists only inside the plugin is unreachable there, so the workflow's `/drift-check`
prompt would resolve to nothing. Shipping the reviewer as a plugin skill would produce a
tool that works when you run it by hand and silently does nothing in CI.

Installing the plugin inside the workflow instead would fix that, and buy a worse problem:
CI would fetch the reviewer from the marketplace at run time, so the prompt driving your PR
comments could change without any pull request against the repo being reviewed.

Vendoring pins the review contract to the commit under review. The reviewer that judges a
PR is the one in that PR's tree.

## What it costs

**The copy goes stale.** Nothing refreshes it — re-running `install-skill` is the only
update path, and `install-workflow` deliberately leaves an existing copy alone so a repo
that edited its own does not get silently reverted.

**It is a trust-boundary file in your repo.** `.claude/skills/drift-check/SKILL.md` is the
prompt CI runs, and anyone who can open a pull request can edit it. Review changes to it the
way you review changes to `.github/workflows/*`: author ≠ reviewer.

The mitigation for what the reviewer *can do* is structural rather than instructional — the
tool allowlist lives in the [workflow](watch-list.md#why-scope-lives-in-the-workflow), so an
edited prompt still cannot write code, reach the network, or post a comment itself.
