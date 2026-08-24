# Entrypoints — surface system prompts

An **entrypoint** is the real system prompt of the surface a case emulates. The harness
runs the case with `claude --system-prompt engine/entrypoints/<name>.md` — *replacing*
Claude Code's own prompt, not appending to it — so the run behaves like the surface your
users are actually on.

A case selects one with `execution.entrypoint: <name>`. The default is `none`.

## `none` — the default

`entrypoint: none` passes no `--system-prompt` at all, so the run uses the harness's own
system prompt. That is the right choice when the surface you care about *is* Claude Code,
and it is the only honest default: this repo ships no entrypoint files, because a surface's
system prompt belongs to whoever operates that surface, not to us.

Any other name must resolve to a file. Naming a surface with no file on disk **aborts in
preflight** rather than running with an empty prompt — a case that emulates nothing still
scores, and a passing score for the wrong reason is worse than a failure.

## Entrypoint vs harness — the two axes

They are independent, and mixing them up is the easy mistake:

| axis | answers | lives in | values |
| --- | --- | --- | --- |
| `harness` | *what **runtime** executes and observes the turn?* | `engine/harnesses/` | `claude_code` · `codex` (seam) |
| `entrypoint` | *what **surface** is the user on?* | `engine/entrypoints/*.md` | `none` · whatever you add |

A surface is **not** a harness. If a surface runs on top of the Claude Code engine, then
emulating it is `harness: claude_code` + `entrypoint: <that surface>` — one runtime wearing
that surface's prompt. Add a *harness* only for a genuinely different runtime; add an
*entrypoint* for every new surface. (The loader rejects `harness: cowork` and
`harness: claude_chat` with a message naming the right pair — those are surfaces misfiled
as runtimes.)

## Add an entrypoint

1. Obtain the surface's system prompt **from a source you are entitled to use**. If it is
   your own product surface, export it from your own configuration. Do not commit a prompt
   you do not have the rights to redistribute — that includes vendor prompts recovered from
   third-party capture sites, whatever their licence claims to be.
2. Save it as `engine/entrypoints/<name>.md`.
3. Record its **provenance** in a comment at the top: where the text came from, and the date
   captured. These files go stale silently — a prompt captured six months ago produces runs
   that no longer match production, and nothing about the score will tell you.
4. Reference it from a case with `execution.entrypoint: <name>`.

If the prompt is not redistributable but you still want it in your runs, keep the file out
of git (`.gitignore` it) and have each developer supply their own copy. The engine only
needs the file to exist at run time.

## Fidelity caveat

Emulating a surface by swapping in its system prompt reproduces that surface's *instructions*,
not its *implementation*. If the real surface is a separate service rather than the Claude
Code engine, this pair emulates the surface's prompt on the Claude Code runtime — good enough
to test skill behavior and prompt-driven routing, not a proof of how that service behaves.
