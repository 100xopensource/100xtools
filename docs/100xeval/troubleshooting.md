---
type: how-to
title: Troubleshooting
description: The failures people actually hit when installing and running 100xeval, and what each one means.
resource: ../../plugins/100xeval/skills/100xeval/scripts/run.py
tags: [100xeval, troubleshooting, how-to]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-13T00:00:00Z
---

# Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| `command not found: python3` | Python is not installed | Install Python 3.11+ |
| `100xeval needs Python 3.11 or newer` | Your Python is too old | Install a newer one, then use `python3.12` |
| `Invalid marketplace source format` | You typed `.` instead of `./` | Add the slash — a bare dot is rejected |
| `` `claude` CLI not found on PATH `` | Test runs need Claude Code itself | Install Claude Code; the static check still works without it |
| `is not a directory` (exit 2) | The `--target` path is wrong | Check it. The tool refuses to invent a score for a folder that isn't there |
| `No findings. Nothing to fix.` | Nothing detectable is wrong | This is a pass |
| A case says a tool was `called 0×` | Usually a bad or expired token, not a broken plugin | Check the token before blaming the skill — see [MCP auth](mcp-auth.md) |
| A case fails on its first ever run | Usually the case, not the plugin | Case defects outran skill defects ~3:1 for us — see [eval case](eval-case.md) |
| A wall of red text | A real bug in the tool | Please report it, with the command you ran |

## Two failures that look like success

Worth knowing because neither shows up as an error.

**A grader that cannot fail.** `min: 0, max: 0` passes when nothing matched, and a mistyped
tool name also matches nothing — see [grader](grader.md).

**A score compared against the wrong baseline.** `design_score` is only comparable within one
scoring version — see [design score](design-score.md).

## See also

* [Run folder](run-folder.md) - the evidence every invocation writes
* [MCP auth](mcp-auth.md) - the failure that surfaces as "called 0×"
