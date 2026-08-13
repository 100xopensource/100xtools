---
type: concept
title: Run folder
description: What a run costs, how to check the price before spending it, and the self-contained evidence every invocation writes.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/reporter.py
tags: [100xeval, debugging, reports]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# Run folder

Every invocation writes a self-contained folder under `.runs/<run_id>/<case>/`. When a
case fails, the answer is in there — the score tells you *that* something broke, and this
tells you *what*.

| Artifact | Holds |
| --- | --- |
| `cases.json` | Every field of the case as executed |
| `result.json` | The run result, plus the exact command, return code, and stderr |
| `transcript.jsonl` | The tool calls the model actually made |
| `workspace/claude-debug.log` | The runtime's own debug trace of the invocation |
| `scorecard.json` | Per-grader pass rates and details |
| `report.{md,json,html}` | The rendered report, with cost split run vs judge |

## Why the whole case is dumped, not a summary

`cases.json` records every field — prompt, plugin, tools, graders — rather than a reference
to the `case.yaml`. Months later you have to be able to read exactly what was executed,
and by then the `case.yaml` may have changed. A run folder that points at mutable state is
not evidence.

No token or secret passes through it: a case holds a *path* to an MCP config, never
credentials. See [MCP auth](mcp-auth.md).

## Reading a red scorecard

The grader `detail` names the failure mode:

* **`tool_used` reports 0×** — it queried nothing. Suspect auth before the skill; see
  [MCP auth](mcp-auth.md).
* **`llm` format judge failed** — it found the data and presented it wrongly.
* **`llm` agentic judge failed** — the presentation was fine and the numbers were not.

That split is the whole point of [one claim per grader](grader.md). A single grader
asserting all three would leave you opening the transcript to find out which.

## Cost lives here too

A test run costs roughly **$1–2 per run**, and the default `runs: 3` lands around **$3–5 for
a single case**. There is no free tier and no undo.

Reports break out run cost against judge cost. Judges can be several extra model calls per
case, so a case at `runs: 3` can spend more on grading than on the thing being graded. If a
suite feels expensive, that split usually says why.

`--dry-run` lists exactly what would execute and the rough spend, without spending it:

```bash
RUN=plugins/100xeval/skills/100xeval/scripts/run.py

python3 "$RUN" eval --case '<case-name>' --dry-run    # what would run, and cost
python3 "$RUN" eval --case '<case-name>' --runs 1     # one case, for real
python3 "$RUN" eval --tag <suite>                     # a whole suite
```

Exit codes: `0` all pass · `1` a case below `--threshold` · `2` usage or engine error — which
is what makes `eval` usable directly as a CI gate.

The runner preflights the MCP connection before spending anything — see
[MCP auth](mcp-auth.md).

## See also

* [Scoring](scoring.md) - how the numbers in the scorecard are derived
* [Managing testcases](../../plugins/100xeval/skills/100xeval/references/managing-testcases.md) - the full red-scorecard walkthrough
