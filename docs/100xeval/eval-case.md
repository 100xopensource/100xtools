---
type: concept
title: Eval case
description: The unit of work — one scenario, one folder, one case.yaml declaring the plugin, the prompt, and the graders.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/loader.py
tags: [100xeval, evals, cases]
timestamp: 2026-08-10T00:00:00Z
---

# Eval case

A case is one scenario: a folder containing a `case.yaml` that names the plugin under test,
the prompt to send, and the [graders](grader.md) that decide whether the answer was right.
There is no index and no registry — discovery walks `evals/**/case.yaml`, so adding a case
means adding a folder.

## What a case declares

* **The prompt**, verbatim as a user would type it. Resist tidying it: resolving a loose
  store name or an ambiguous date range is the skill's job, and cleaning the question up
  removes the thing being tested.
* **The plugin**, as a path relative to *the case file* rather than the repo root — a case
  in `evals/<name>/` points at `../../plugins/<p>`.
* **The graders**, one claim each.
* **`runs`**, defaulting to 3.

## Why `runs: 3` is the default

Skills are non-deterministic. One case in our own corpus answered `0.148×` (correct) and
`0.24×` (62% off) to the same prompt on different runs. A single run reports a coin flip as
a fact. Three runs turn a pass into a rate you can reason about — see [scoring](scoring.md).

## Park, don't delete

A case carries a `skip:` field whose value is the reason. Setting it keeps the scenario in
the corpus and prints the reason on every run.

Deleting a case deletes the regression it guards. The temptation is strongest exactly when
it should be resisted — never delete a case to make a suite green.

## Expect the first run to debug the case

Measured across the first six cases written against this engine, *case* defects outnumbered
*skill* defects roughly 3:1 — wrong table, ungranted tool, over-strict criteria, an
off-by-one date bound. Budget a single-run pass to shake the case out before trusting what
it says about the skill.

## See also

* [Grader](grader.md) - what does the judging
* [Case schema](../../plugins/100xeval/skills/100xeval/references/case-schema.md) - every field
* [Managing testcases](../../plugins/100xeval/skills/100xeval/references/managing-testcases.md) - the full lifecycle
