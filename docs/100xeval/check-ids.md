---
type: reference
title: Static check IDs
description: Every check the static linter emits, grouped by the sub-score its prefix feeds.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/lint.py
tags: [100xeval, static, reference]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# Static check IDs

Every finding from the static linter starts with a bracketed ID. The **prefix names the
[sub-score](design-score.md) it feeds**; the number is just an identifier, not a severity.

`engine/lint.py`'s docstring is the source of truth; keep this page in step when you add
a check.

## `FM` — frontmatter_quality

| ID | Fires when |
| --- | --- |
| `FM1` | frontmatter `name` does not match the skill's directory name |
| `FM2` | skill name unusable: over the length limit, exactly a reserved name, or too vague to trigger |
| `FM3` | no description — the model cannot decide when to load the skill |
| `FM4` | unrecognized frontmatter key (likely a typo) |
| `FM5` | description contains XML-like tags — rejected by Skills API upload |
| `FM6` | description not written in third person |
| `FM7` | frontmatter block missing or not closed — nothing else about the skill can be read |

## `PD` — progressive_disclosure

| ID | Fires when |
| --- | --- |
| `PD1` | SKILL.md body over the line cap; detail belongs in references/ |
| `PD2` | references/ is empty, or the body names a reference file that is missing |

## `RH` — reference_hygiene

| ID | Fires when |
| --- | --- |
| `RH1` | ships references/ but never instructs the model to read them |
| `RH2` | a reference file points at further reference files |
| `RH3` | Windows-style separator in a bundled path |

## `ST` — structural_completeness

| ID | Fires when |
| --- | --- |
| `ST1` | plugin has no README.md at its root |
| `ST2` | a "self-check" section that is not a real checklist |

## `EC` — ecosystem_coherence

| ID | Fires when |
| --- | --- |
| `EC1` | routes to a companion skill that does not exist in this plugin |

## `SEC` — security

| ID | Fires when |
| --- | --- |
| `SEC1` | possible secret committed in plugin content |
| `SEC2` | network destination outside the allowed set |
| `SEC3` | a read instruction escaping the skill directory via `../` |

## Scoping worth knowing

`SEC1` scans **every** text file — a committed credential is a problem wherever it sits.
`SEC2` and `SEC3` scan **skill prose only** (`.md`, `.txt`), because they read a file as
*instructions to the model*. Applied to bundled source they flagged every plugin that ships
a script, which is exactly the noise that teaches people to ignore a security score.

`SEC3` further requires a read verb near the `../`, so a config example like
`plugins: ["../../plugins/x"]` — data the skill never opens — does not fire.

## These are deliberately conservative

Each check earns its place by catching something *probably wrong*, not something that
merely differs from a house style. The internal version of this linter carried convention
checks; they were dropped on purpose. Add your own in a fork.

## See also

* [Design score](design-score.md) - how these findings become a number
