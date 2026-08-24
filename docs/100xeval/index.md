# 100xeval

Behavioral and static evaluation for Claude Code plugins. Start with the
[overview](overview.md).

## Core concepts

* [Overview](overview.md) - What 100xeval is, and the two layers it runs
* [Eval case](eval-case.md) - The unit of work: one scenario, one folder, one `case.yaml`
* [Grader](grader.md) - One checkable claim about the result of a run
* [Scoring](scoring.md) - How runs become a pass rate, a case score, and a verdict

## Execution model

* [Harness](harness.md) - The runtime that executes and observes a turn
* [Entrypoint](entrypoint.md) - The surface being emulated, and why the default is `none`
* [MCP auth](mcp-auth.md) - Two auth paths, two tool-name schemes, one silent failure

## The static layer

* [Design score](design-score.md) - Sub-scores, weights, and the flag penalty
* [Check IDs](check-ids.md) - Every static check, and the sub-score its prefix feeds

## Debugging

* [Run folder](run-folder.md) - What an invocation writes, and where to look when it fails

## Troubleshooting and internals

* [Troubleshooting](troubleshooting.md) - what each failure means, including two that look like success
* [Internals](internals.md) - directory layout, and the engine's own test suite

## Installing and first run

Install steps and the ask-Claude walkthrough are in the tool's own README, which ships with
the plugin:

* [Plugin README](../../plugins/100xeval/README.md) - install, what you need, get started
* [Case schema](../../plugins/100xeval/skills/100xeval/references/case-schema.md) - every
  `case.yaml` field and grader parameter
* [Managing testcases](../../plugins/100xeval/skills/100xeval/references/managing-testcases.md) -
  lifecycle, best practice, and gotchas that have actually bitten
