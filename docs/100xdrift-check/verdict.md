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

## Rolling up to a section callout

Each changed file's section *is* a GitHub alert — title, diff, table, action line and all —
so the whole section renders as one coloured band a reviewer can skim past or stop at:

| Callout | When | What the section asks of a reader |
| --- | --- | --- |
| `[!CAUTION]` (red) | Any sibling is `likely-applies` | Port it, in its own pull request |
| `[!WARNING]` (yellow) | Everything else — `conflicts`, `unclear`, `different on purpose`, or no siblings | Nothing to port |

The callout is a call to action, not a severity, and it answers one question: *is a pull
request owed?* That is why `conflicts` is yellow rather than red — nothing should be copied
across. It is not a demotion: a conflict is usually the most important thing in the report,
its verdict line says so, and the `critical` status marker below is what makes it loud.

Two levels rather than one per verdict is deliberate. GitHub offers five alert types, and
mapping each verdict to its own would render a long report as a wall of coloured bars —
which destroys exactly the skimming the callouts exist for. The cost lands on yellow, which
now spans "a sibling contradicts this, read it before merging" and "nothing to see here".
Colour cannot separate those, so the band's first line has to: `**Alert** — …` against
`**No action** — …`.

GitHub's alert label (`Caution` / `Warning`) cannot be renamed, so the section title —
`Changed in <plugin>: <path>` — is the first bold line inside the band rather than the
alert's own heading. It is not a `###` heading either: a heading cannot sit inside an alert
without ending it, so banding the section trades away the outline entries and heading
anchors that headings would give a rendered report.

The other cost is the prefix. Every line has to carry `> `, blank lines included, and one
missed prefix ends the band early and drops the rest of the section out of it. The reviewer
generates this markdown, so that is a real failure mode rather than a theoretical one. It
degrades visibly — a half-banded section — rather than silently, which is why it is an
acceptable trade for a formatting feature. The status marker the workflow parses is a plain
HTML comment on line 1, outside every band, so no prefix slip can affect it.

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
