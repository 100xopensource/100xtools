# Example eval cases

Two worked cases showing what a `case.yaml` looks like and how graders are written. They
run against real, third-party plugins — vendored here so they work from a clean clone with
no network. See [`NOTICE`](./NOTICE) for provenance.

**These are examples of the pattern, not a suite to adopt.** Your cases should assert things
about *your* plugin. Copy the shape, not the content.

## Run them

```bash
# From the repo root. Free — parses the cases, resolves the plugins, spends nothing.
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --cases-dir examples/plugin-eval/cases --skip-static --dry-run

# For real. One model call per case, roughly $2-6 for the pair.
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --cases-dir examples/plugin-eval/cases --skip-static
```

`--cases-dir examples/plugin-eval/cases` matters: the default is `evals/`, so without it the
runner looks elsewhere and correctly reports finding nothing. (`--root` is the old spelling
and still works.)

Run artifacts land in `.runs/` by default, which is gitignored. `--runs-dir` moves them — transcripts
can contain whatever your MCP returned, so writing them outside the repo is often the right
call:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --cases-dir examples/plugin-eval/cases --runs-dir ~/.100xeval-runs --skip-static
```

## Run them under a different surface

The cases declare `entrypoint: cowork` — the surface these plugins were written for.
`--entrypoint` overrides that for every case in a run, without editing any file, so you can
compare surfaces:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --cases examples/plugin-eval/cases --skip-static --entrypoint none
```

This is the more interesting way to run them. `harness` and `entrypoint` are independent
axes: the harness is the *runtime* executing the turn, the entrypoint is the *surface* whose
system prompt gets swapped in. Same plugin, same question, different surface — and the
answer can legitimately differ, because a surface's prompt shapes how a skill behaves.

That difference is the thing worth measuring. If a plugin respects its own scope boundary
under one surface and ignores it under another, you want to know before your users do.

The override is announced in the output (`↺ entrypoint overridden to 'cowork'`) rather than
applied quietly — a scorecard whose surface silently differs from the case file is one
nobody can reproduce. Naming a surface with no file on disk aborts in preflight rather than
running with no system prompt at all.

## Expected result: 2 of 2 pass

`Overall 1.00 · 2/2 cases passed`. Measured 2026-08-11 under `entrypoint: cowork`, one run
each, $0.18 total, all six graders at 100%.

| Case | Asserts |
| --- | --- |
| `code-review-finds-sql-injection` | a pasted function with a concatenated SQL string is flagged as injection, with a parameterised fix |
| `ux-copy-rewrites-an-error-message` | `Error 500: Something went wrong.` is rewritten with what happened, why, and what to do |

## What they test, and why that shape

Both assert a contract the plugin **states about itself**, which is the whole trick to
writing a case that stays honest:

- `code-review` documents *"STANDALONE (always works) — paste a diff, security audit
  (OWASP top 10, injection, auth)"*. So the case pastes a diff and expects injection named.
- `ux-copy` documents an error-message structure: *"What happened + Why + How to fix"*.
  So the case checks the rewrite has all three.

Neither asserts a house style, a format, or a phrasing. Assert what the plugin promises and
the case survives rewordings; assert your own preferences and it fails correct answers.

Both also carry `worked-standalone` — a `tool_used` grader asserting **no MCP tool was
called at all**. These plugins declare optional connectors (Slack, Figma, Notion…) and
describe a core that works without them. That grader is what proves the claim, and it is
why the cases need no credentials.

## Reading the graders

Each case carries three, and each makes exactly **one** claim:

```yaml
- {type: tool_used, name: worked-standalone, tool: mcp__*, min: 0, max: 0}
- {type: regex,     name: names-the-vulnerability-class, pattern: "(?i)sql injection"}
- {type: llm,       name: flags-it-and-shows-the-fix, focus: last_message, criteria: "..."}
```

Split that way, a red scorecard names *which* property broke: it reached for a connector,
it missed the vulnerability, or it named it without a usable fix. One grader asserting all
three would just say "failed".


Note `runs: 1` here. Real suites should keep `runs: 3` — skills are non-deterministic, and a
single run reports a coin flip as a fact. One run is enough for an example that people will
mostly read rather than execute.

## When these break

They assert how a snapshot of someone else's plugin behaves. If they start failing, the
question is *which* changed — the model, or the pinned plugin. Read the run folder before
assuming the harness is wrong; the transcript shows what was actually said.

Updating the vendored snapshot is described in [`NOTICE`](./NOTICE).

## Write your own

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  init my-first-case --plugin <your-plugin-dir> --prompt "<a real user question>"
```

Then read
[`managing-testcases.md`](../../plugins/100xeval/skills/100xeval/references/managing-testcases.md)
for the lifecycle and the mistakes that have actually bitten, and
[`case-schema.md`](../../plugins/100xeval/skills/100xeval/references/case-schema.md) for every
field.
