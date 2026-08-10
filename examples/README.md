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
  eval --root examples/cases --skip-static --dry-run

# For real. One model call per case, roughly $2-6 for the pair.
python3 plugins/100xeval/skills/100xeval/scripts/run.py \
  eval --root examples/cases --skip-static
```

`--root examples/cases` matters: the default case root is `evals/`, so without it the runner
looks somewhere else and correctly reports finding nothing.

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
[`managing-testcases.md`](../plugins/100xeval/skills/100xeval/references/managing-testcases.md)
for the lifecycle and the mistakes that have actually bitten, and
[`case-schema.md`](../plugins/100xeval/skills/100xeval/references/case-schema.md) for every
field.
