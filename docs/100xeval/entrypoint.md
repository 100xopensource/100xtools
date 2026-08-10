---
type: concept
title: Entrypoint
description: The surface being emulated — that surface's real system prompt, swapped in for the run.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/entrypoints/README.md
tags: [100xeval, evals, execution]
timestamp: 2026-08-10T00:00:00Z
---

# Entrypoint

An entrypoint is the **surface** a case emulates: that surface's real system prompt, passed
with `--system-prompt` so it *replaces* the runtime's own rather than appending to it. It is
the second of the two execution axes — the first is the [harness](harness.md).

Your users are not on a bare runtime. They are on some product surface whose system prompt
shapes how a skill behaves. Evaluating against the wrong prompt measures something nobody
experiences.

## `none` is the default, and that is deliberate

**No entrypoint files ship with this repo**, and `.gitignore` keeps it that way. A surface's
system prompt belongs to whoever operates that surface — including when a third-party site
has published a capture of it. Redistributing someone else's prompt is not ours to do.

So the default is `entrypoint: none`: no `--system-prompt` is passed and the run uses the
harness's own prompt. That is the honest default, and it is the right one when the surface
you care about *is* Claude Code.

## Naming a surface with no file aborts

Any entrypoint other than `none` must resolve to a file, or preflight aborts.

This looks strict until you consider the alternative. A missing file used to mean an empty
system prompt: the case still ran, still scored, and still reported a number — while
emulating nothing at all. A pass for the wrong reason is worse than a failure, because
nobody investigates a pass.

## Supplying your own

Drop the prompt at `engine/entrypoints/<name>.md` and reference it from a case. Two things
worth doing:

* **Record provenance** at the top — where the text came from and when it was captured.
  These files go stale silently; a prompt captured six months ago produces runs that no
  longer match production, and nothing in the score will tell you.
* **Keep it out of git** if it is not yours to redistribute. The engine only needs the file
  to exist at run time, so each developer can supply their own copy.

## Fidelity caveat

Swapping in a system prompt reproduces a surface's *instructions*, not its *implementation*.
If the real surface is a separate service rather than the same engine, this emulates the
prompt on a different runtime — good enough to test skill behavior and prompt-driven
routing, not a proof of how that service behaves.

## See also

* [Harness](harness.md) - the runtime axis, and why the two get confused
