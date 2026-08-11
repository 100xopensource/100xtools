---
type: concept
title: Harness
description: The runtime that executes a turn and observes what happened — one of the two independent execution axes.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/harnesses/base.py
tags: [100xeval, evals, execution]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# Harness

A harness is the **runtime** that executes a turn and reports what happened. It is one of
two independent axes; the other is the [entrypoint](entrypoint.md), and confusing them is
the single easiest mistake to make here.

| Axis | Answers | Example |
| --- | --- | --- |
| `harness` | What *runtime* executes and observes the turn? | `claude_code` |
| `entrypoint` | What *surface* is the user on? | `none`, or a surface you supply |

**A surface is never a harness.** If a surface runs on top of the Claude Code engine, then
emulating it is `harness: claude_code` plus that surface's entrypoint — one runtime wearing
a different prompt. Add a harness only for a genuinely different runtime.

The loader enforces this: `harness: cowork` and `harness: claude_chat` are rejected with a
message naming the correct pair, because they are surfaces misfiled as runtimes and the
alternative is a case that silently runs something other than what it claims.

## What a harness owes the engine

* **Execute the turn** and return a result: the final text, the tool calls, cost, tokens,
  duration.
* **Declare what it can observe.** Not every runtime can expose tool calls. A harness that
  cannot must say so, and the engine will not fail a `tool_used` grader for the absence — a
  false failure is worse than a skipped check.
* **Preflight.** Abort *before* spending money when something required is missing, rather
  than producing a confident dataless run.

## Implemented harnesses

`claude_code` drives the Claude Code CLI single-turn and reads tool calls from the session
transcript, because the result JSON omits them. `codex` exists as a registered seam that
aborts in preflight — it marks where a second runtime would attach, without pretending to
be one.

## See also

* [Entrypoint](entrypoint.md) - the other axis
* [MCP auth](mcp-auth.md) - what the harness has to get right for tools to work
