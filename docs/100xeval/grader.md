---
type: concept
title: Grader
description: One checkable claim about the result of a run, scored pass or fail.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/graders.py
tags: [100xeval, evals, grading]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# Grader

A grader turns the result of a run into a pass or fail on **one** property. An
[eval case](eval-case.md) carries several, and the case's score is the weighted mean of
their pass rates.

## The four types

| Type | Answers | Costs a model call |
| --- | --- | --- |
| `tool_used` | Did it query the right data, with the right filter? | No |
| `regex` | Is a phrase present, or absent? | No |
| `llm` | Did it present the answer correctly, or get the numbers right? | Yes |
| `static` | Does the plugin's design clear a threshold? | No |

`llm` runs a judge over several votes and takes the majority, because a single judgement on
a subjective property is as noisy as the thing it is judging.

## One claim per grader

The rule that matters most. A grader asserting three things gives you a red scorecard that
does not say which one broke, and a red scorecard you have to investigate from scratch is
barely better than no scorecard.

Split them. `tool_used` for the query shape, `llm` for presentation, a second `llm` for the
figures. Then a failure names itself.

## Assert the query shape, not the figure

`tool_used` with an `input_match` survives next week's data. A hard-coded number is a
scheduled false failure — it will go red on a Tuesday for a reason that has nothing to do
with the skill, and the team will learn to ignore the suite.

When numbers genuinely must be checked, hardcode the ground-truth query in the judge's
criteria. Left to write its own, the judge writes a different one per vote and the "ground
truth" moves under you, so a failure tells you nothing.

## Grade what the prompt asked for

A criterion the user never requested fails correct answers. If you add a stricter rule of
your own, say so in a comment in the case, so the next person knows the failure is a policy
choice rather than a defect.

## Absence assertions fail open

`min: 0, max: 0` passes when nothing matched — and a mistyped tool name also matches nothing,
so a typo silently produces a grader that *cannot* fail. It is the most convincing green in
the suite and it checks nothing.

Before trusting one, confirm the same pattern can pass with `min: 1` on a run where the tool
really was used.

## See also

* [Scoring](scoring.md) - how grader results become a case verdict
* [Design score](design-score.md) - what the `static` grader thresholds against
* [Case schema](../../plugins/100xeval/skills/100xeval/references/case-schema.md) - every grader's parameters
