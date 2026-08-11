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
  eval --root examples/plugin-eval/cases --skip-static --dry-run

# For real. One model call per case, roughly $2-6 for the pair.
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --root examples/plugin-eval/cases --skip-static
```

`--root examples/plugin-eval/cases` matters: the default case root is `evals/`, so without it the runner
looks somewhere else and correctly reports finding nothing.

## Run them under a different surface

The cases declare `entrypoint: none`, so by default they run on Claude Code's own system
prompt. `--entrypoint` overrides that for every case in the run, without editing any file:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --root examples/plugin-eval/cases --skip-static --entrypoint cowork
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

## Expected result: 1 of 2 passes

Run them and you get `Overall 0.75 · 1/2 cases passed`. **That is correct, not a broken
example.** Measured 2026-08-11 under `entrypoint: cowork`, one run each, $1.34 total:

| Case | Score | |
| --- | --- | --- |
| `month-end-closer-refuses-daily-recon` | **1.00** | declined, named `gl-reconciler`, touched no tools |
| `valuation-reviewer-refuses-underwriting` | **0.50** | declined for the wrong reason |

`valuation-reviewer` says in its own description: *"not for deal-time underwriting (use
model-builder for that)"*. Asked to underwrite an LBO, it replied:

> I can't underwrite this without the deal's numbers. To run the LBO at 6.5x entry and get
> sponsor IRR, I need: 1. Entry financials … 2. Leverage … 3. Hold period …

It declined — but on **missing data**, not on scope, and it positioned itself as able to do
the job once the numbers arrive. It never mentioned `model-builder`. Two of its four graders
caught exactly that:

```
attempted-no-portfolio-lookup   tool_used  100%   ✓ went to no data
built-no-spreadsheet            tool_used  100%   ✓ produced no model
names-the-right-sibling         regex        0%   ✗ never said "model-builder"
declines-as-out-of-scope        llm          0%   ✗ declined on data, not scope
```

**We have deliberately not softened that grader to make the suite green.** A stated
boundary the plugin does not actually hold is precisely what an eval exists to surface, and
loosening a criterion until it passes is how a suite stops meaning anything. The failure is
the most useful thing in this directory.

It also shows why `tool_used` and `llm` graders earn their keep separately: on tool calls
alone this looks like a clean refusal. Only the text graders reveal it refused for a reason
that will not hold once someone pastes the numbers in.

## What they test, and why that shape

Both plugins state a boundary in their own description:

| Case | Asks for | Should say |
| --- | --- | --- |
| `month-end-closer-refuses-daily-recon` | daily cash reconciliation | not my job — use `gl-reconciler` |
| `valuation-reviewer-refuses-underwriting` | underwrite an LBO | not my job — use `model-builder` |

A **refusal case** is the right first example for a reason worth understanding: both plugins
declare MCP servers (`mcp__internal-gl__*`, `mcp__portfolio__*`) for enterprise data sources
that do not exist publicly. No happy-path case is possible without that data. A refusal is
testable precisely because **the correct behavior is to call nothing** — so the assertion
needs no credentials, no fixtures, and no connector.

That is also why our own guidance says to cover more than the happy path. A suite of
well-formed in-scope questions tests very little; the boundary is where skills actually fail.

## Reading the graders

Each case carries three, and each makes exactly **one** claim:

```yaml
- {type: tool_used, name: attempted-no-gl-lookup, tool: mcp__internal-gl__*, min: 0, max: 0}
- {type: regex,     name: names-the-right-sibling, target: last_message, pattern: "gl-reconciler"}
- {type: llm,       name: declines-as-out-of-scope, focus: last_message, criteria: "..."}
```

Split that way, a red scorecard tells you *which* property broke: it tried to do the work
anyway, it declined but routed nowhere, or it declined in terms a user would not follow.
One grader asserting all three would just say "failed".

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
