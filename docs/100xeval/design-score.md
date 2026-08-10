---
type: concept
title: Design score
description: The static layer's 0-1 verdict on plugin design, folded from weighted sub-scores and a flag penalty.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/static.py
tags: [100xeval, static, scoring]
timestamp: 2026-08-10T00:00:00Z
---

# Design score

The static layer walks a plugin, emits tagged findings, and folds them into a single
`design_score` between 0 and 1. No model, no network, no API key — which is what makes it
affordable to run on every commit.

## From finding to score

Each finding carries a [check ID](check-ids.md) whose **prefix names the sub-score it
feeds**. Findings in a category cost `0.25` each, floored at 0:

| Sub-score | Weight | Why that weight |
| --- | --- | --- |
| `frontmatter_quality` | 1.0 | |
| `progressive_disclosure` | 1.0 | |
| `reference_hygiene` | 1.0 | |
| `structural_completeness` | 1.0 | |
| `ecosystem_coherence` | 1.0 | |
| `security` | **2.0** | A leaked credential is not the same kind of problem as a long SKILL.md |
| `token_efficiency` | **0.5** | A proxy metric rather than a conformance finding |

The weighted mean is then multiplied by a **flag penalty** — `1 - 0.05 × flags`, floored at
`0.5`. Sub-scores alone let a plugin with many shallow problems across many categories look
fine; the penalty makes breadth cost something without letting it dominate.

## The prefix is the mapping

This is the design decision worth knowing. The sub-score is *derived* from the ID prefix
rather than looked up in a hand-maintained table.

The table version had a quiet failure mode: add a check, forget to register its ID, and it
sits there live and firing while changing no number. It looks like a working check. Deriving
the mapping removes the second file entirely, and an unregistered prefix now raises rather
than scoring nothing.

## `token_efficiency` is the odd one out

It has no check ID behind it — nothing emits a finding for it. It is computed directly by
counting duplicate lines across **all** of a plugin's `SKILL.md` files, because blocks
copy-pasted between sibling skills are the common way a multi-skill plugin quietly doubles
what it loads into context.

It does not measure tokens. It measures the habit that wastes them.

## What a score means

Nothing on its own. `0.89` is not a grade — it is a prompt to read the findings, which name
the specific files and rules. A score with no findings behind it tells you nothing about
what to fix.

## See also

* [Check IDs](check-ids.md) - every check, and the sub-score it feeds
* [Grader](grader.md) - the `static` grader thresholds against this score
