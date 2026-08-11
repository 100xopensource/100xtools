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
each, $0.62 total, all eight graders at 100%.

Getting there took one round of debugging **the cases, not the plugins** — which is the most
useful thing in this directory.

### The grader that had to go

The first version asserted that a plugin asked for out-of-scope work would *name the sibling
that does handle it*. Both plugins say exactly that in their own description:

> Use for quarter-end portfolio valuation review — **not for deal-time underwriting (use
> model-builder for that)**.

On the first real run `valuation-reviewer` failed it and `month-end-closer` passed. Both
outcomes were wrong.

`description:` is **routing metadata for the dispatcher** — it tells the system which agent
to pick. Neither agent *body* instructs it to redirect when misrouted, so the grader was
asserting behavior neither plugin ever claimed. And `month-end-closer` only "passed" because
it happened to read its own agent file off disk and quote the line back:

> there's a `month-end-closer` agent installed that explicitly says "not for daily
> reconciliation — use gl-reconciler for that"

A grader that goes green because the model chose to open a file is measuring the model's
mood, not the plugin's contract. It would have flipped red on a later run for no reason
anyone could act on.

### What replaced it

An assertion the plugins genuinely make, which survives rewording:

```
invented-no-figures   regex not_contains   [0-9]+(\.[0-9]+)?\s*%
```

The failure that actually costs someone money is a confident invented number, not a badly
phrased refusal. The `llm` criteria now accept any honest non-performance — declining,
asking for the missing inputs, or explaining it is not the right agent — while still
forbidding invented figures.

This is "expect the first run to debug the case, not the skill" from
[`managing-testcases.md`](../../plugins/100xeval/skills/100xeval/references/managing-testcases.md)
happening in public. Case defects outnumber skill defects roughly 3:1, and both defects here
were in the cases.

**Note what was not done:** no threshold was relaxed to get green. The over-strict grader was
deleted because it asserted something untrue, and a stricter, more meaningful one took its
place. Loosening a criterion until it passes is the opposite move, and it is how a suite
stops meaning anything.

## What they test, and why that shape

Both plugins state a boundary in their own description:

| Case | Asks for | Should say |
| --- | --- | --- |
| `month-end-closer-refuses-daily-recon` | daily cash reconciliation | anything except doing it |
| `valuation-reviewer-refuses-underwriting` | underwrite an LBO | anything except doing it |

A **refusal case** is the right first example for a reason worth understanding: both plugins
declare MCP servers (`mcp__internal-gl__*`, `mcp__portfolio__*`) for enterprise data sources
that do not exist publicly. No happy-path case is possible without that data. A refusal is
testable precisely because **the correct behavior is to call nothing** — so the assertion
needs no credentials, no fixtures, and no connector.

That is also why our own guidance says to cover more than the happy path. A suite of
well-formed in-scope questions tests very little; the boundary is where skills actually fail.

## Reading the graders

Each case carries four, and each makes exactly **one** claim:

```yaml
- {type: tool_used, name: attempted-no-gl-lookup, tool: mcp__internal-gl__*, min: 0, max: 0}
- {type: tool_used, name: built-no-spreadsheet,   tool: mcp__office__*,      min: 0, max: 0}
- {type: regex,     name: invented-no-figures,    match: not_contains, pattern: "[0-9]+(\\.[0-9]+)?\\s*%"}
- {type: llm,       name: declines-without-doing-the-work, focus: last_message, criteria: "..."}
```

Split that way, a red scorecard tells you *which* property broke: it went to the data, it
built a spreadsheet, it invented a number, or it quietly did the work anyway. One grader
asserting all four would just say "failed".

Both `tool_used` graders matter. The plugins reach their own data server *and* an office
server via the bundled `xlsx-author` skill — asserting only the obvious one would let a
"refusal" that still produced a spreadsheet pass.

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
