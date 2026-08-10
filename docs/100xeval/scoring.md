---
type: concept
title: Scoring
description: How repeated runs become a pass rate, a weighted case score, and a pass/fail verdict.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/orchestrator.py
tags: [100xeval, evals, scoring]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# Scoring

A case runs on exactly **one harness and one model**, repeated `runs` times. Scoring rolls
those repetitions up in three steps.

1. **Per grader: `passRate = passed / runs`.** A [grader](grader.md) that passed twice out of
   three runs scores `0.67`, not "pass".
2. **Per case: the weighted mean of grader pass rates.** Graders carry a `weight`, so a
   presentation nit need not count the same as a wrong number.
3. **Verdict: pass if the case score is at or above `--threshold`**, which defaults to `1.0`.

## Why a rate rather than a boolean

Because skills are non-deterministic, and a boolean throws away the only signal that tells
you so. `0.67` says "this works two times in three" — a different and more actionable
problem than either a clean pass or a clean fail. Flattening it hides whether you are
looking at a broken skill or a flaky one.

The default threshold of `1.0` then says: every grader must pass on every run. Loosen it
deliberately, per suite, not by accident.

## Concurrency is suite-wide

`--concurrency` is the number of plugin runs in flight across the **whole suite**, not per
case. Cases share one budget, so a suite finishes in roughly `total_runs / N` waves instead
of case-by-case.

Raising it raises real load — each run is a live model call *and* a hit on the plugin's MCP
— so raise it only as far as the endpoint tolerates. Set it to `1` when debugging a single
case, so the output is readable and the failure is yours alone.

Report order always follows case order, whatever finishes first, so a diff between two runs
stays readable.

## Exit codes

`0` all passed · `1` a case fell below threshold · `2` engine error. The split matters for
CI: a real regression and a broken harness should not look the same to a build.

## See also

* [Eval case](eval-case.md) - where `runs` and grader weights are declared
* [Run folder](run-folder.md) - the evidence behind a score
