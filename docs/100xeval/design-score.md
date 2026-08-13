---
type: concept
title: Design score
description: The static layer's 0-1 verdict on plugin design, folded from weighted sub-scores and a flag penalty.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/static.py
tags: [100xeval, static, scoring]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
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

## Comparable only within a scoring version

The rules that produce the number change. `scoringVersion` is printed with every report and
carried in the JSON; a score is only comparable to another from the same version. Pin it
alongside any threshold you gate CI on — see the repo's CHANGELOG.

## What a score means

Nothing on its own. `0.89` is not a grade — it is a prompt to read the findings, which name
the specific files and rules. A score with no findings behind it tells you nothing about
what to fix.

## Running it

Free, no model call, no network:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target <plugin-dir>
```

```
# 100xeval — static design quality  (scoring v1)

## demo-plugin — design_score 0.77
- frontmatter_quality: 0.50
- progressive_disclosure: 1.00
- reference_hygiene: 1.00
- structural_completeness: 0.75
- token_efficiency: 1.00
- ecosystem_coherence: 1.00
- security: 1.00

### findings (3)
- demo-plugin: [ST1] plugin has no README.md at its root
- skills/report/SKILL.md: [FM3] skill has no description — the model cannot decide when to load it
- skills/report/SKILL.md: [FM4] unrecognized frontmatter key 'descriptionn' (did you mean 'description'?)
```

**Read the findings, not the number.** The number only summarises; the findings say what to
do. Here they earn their keep — someone typed `descriptionn` with two n's, and Claude was
silently ignoring the description. Below about `0.85`, read every line.

A `--target` that is not a plugin is an error (exit `2`), not a score. It will not quietly
hand back a passing number for a folder that isn't there.

## Where it is wrong

* **It is heuristics over prose, and has been wrong repeatedly.** Run against Anthropic's own
  published plugins it produced five classes of false positive in one pass. If more than
  about one finding in five is noise for you, it is costing attention rather than saving it.
* **`token_efficiency` never emits a finding.** It is measured, not detected, so a low score
  there beside an empty findings list is normal rather than a display bug.
* **A score only compares within its scoring version**, printed on every report and carried
  in the JSON as `scoringVersion`. If you gate CI on a threshold, pin the version you tuned
  it against — see [CHANGELOG.md](../../CHANGELOG.md).

## See also

* [Check IDs](check-ids.md) - every check, and the sub-score it feeds
* [Grader](grader.md) - the `static` grader thresholds against this score
