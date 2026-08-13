---
type: concept
title: Verdict
description: The four calls the reviewer makes about one sibling pair, and the single status marker they roll up to for the PR comment.
resource: ../../plugins/100xdrift-check/templates/skills/drift-check/SKILL.md
tags: [100xdrift-check, review, output]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-12T00:00:00Z
---

# Verdict

A verdict is the reviewer's call about **one pair**: the file that changed, and one sibling
copy of it elsewhere in the repo. One changed file with three siblings gets three verdicts,
which may disagree with each other — that is normal and useful.

| Verdict | Means | What a reviewer does |
| --- | --- | --- |
| `likely-applies` | The same defect or improvement exists there | Consider porting the change |
| `different on purpose` | Legitimate variation for that plugin's context | Ignore, deliberately |
| `conflicts` | The change contradicts a rule the sibling relies on | Look before merging either |
| `unclear` | Not enough signal to call it | Read the two files yourself |

**Wording-only drift is never a recommendation.** Parity is not the goal, so formatting and
phrasing differences go in a collapsed FYI section rather than the table. A tool that
nagged about prose would train people to close the comment unread.

## Rolling up to a status marker

The report's first line is a marker the workflow turns into the comment's headline icon:

| Marker | When | Icon |
| --- | --- | --- |
| `critical` | Any verdict is `conflicts` — **or the check itself broke** | 🔴 |
| `warning` | No conflicts, but something is `likely-applies` or `unclear` | 🟡 |
| `good` | Every sibling is `different on purpose`, or there were no siblings | 🟢 |

Critical covering both "found a conflict" and "the check is broken" is deliberate. A
silently broken advisory reads as a clean bill of health, which is worse than having no
check at all — so a failed run is loud rather than green.

The marker is a contract between two files: the reviewer writes it, and the workflow's
comment step parses it. Change the vocabulary in one without the other and every report
quietly degrades to `warning`.

## No siblings is an answer

A changed file with no counterpart anywhere gets one line saying so. That is a real result,
not a failure — it says this file is unique in the repo, which is worth knowing. It is also
what a single-plugin repo gets for everything, every time.
