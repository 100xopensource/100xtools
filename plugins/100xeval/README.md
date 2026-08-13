# 100xeval — check whether a plugin is any good

100xeval answers one question: **did this plugin actually give the right answer?**

It works in two ways, and they are very different in cost. Start with the free one.

| | What it does | Cost | Needs |
| --- | --- | --- | --- |
| **Static check** | Reads your plugin's files and reports problems it can see, without running anything | **Free** | Just Python |
| **Real test run** | Actually runs your plugin on saved questions and grades the answers | **~$1–2 per run** | An API key |

The **static check** is the one most people use. It catches things you cannot see by
reading — a skill with no description, a misspelled setting Claude has been silently
ignoring, a password left in a file.

The **real test run** is for when you need to know that an edit did not change the answers.
It runs the plugin for real with its data connection attached, then checks three things:
did it look up the right data, did it present the result properly, and are the numbers
right. Details in [The eval dataset](#the-eval-dataset).

Everything ships in one folder — the skill Claude talks to and the Python engine underneath.
**Python 3.11+, standard library only:** no `pip install`, no virtualenv, no lockfile.

---

## What you need

- **For the static check: Python 3.11 or newer, and nothing else.** No API key, no internet
  connection, no account. Check yours with `python3 --version`.
- **For real test runs:** an `ANTHROPIC_API_KEY`, or to be logged in to Claude Code. If your
  plugin connects to a data source you may also need a token — see step 5.
- **Claude Code or the Claude desktop app**, if you would rather ask for things in plain
  words than type commands.

---

## Get started

> **Prefer a slower walkthrough?** [GETTING-STARTED.md](./GETTING-STARTED.md) covers the same
> ground with nothing assumed — no jargon, free path first. This section is quicker and
> expects you to know what a plugin and a data connection are.

**1. Install it.** In Claude Code or the Claude desktop app, type:

```
/plugin marketplace add 100xopensource/100xtools
/plugin install 100xeval@100xtools
```

If you are told to run `/reload-plugins`, do that. Or skip installing and point at a clone
for one session: `claude --plugin-dir plugins/100xeval`.

**How to tell it worked:** ask Claude *"static-check my plugin"* and it should offer to run
the check rather than ask you what you mean.

**2. Just ask for what you want.** Claude drives the engine, so there are no flags to learn.
For most people this is the whole interface:

> *"static-check my plugin"* · *"run the evals for asksales"* ·
> *"add a testcase for askinventory"* · *"why did it score 0.92?"*

**3. Or run it yourself.** Start with the static check — free, no API key, no network:

```bash
RUN=plugins/100xeval/skills/100xeval/scripts/run.py

python3 "$RUN" eval --static-only --target <your-plugin-dir>   # free — start here
python3 "$RUN" eval --static-only                              # every plugin it can find
python3 "$RUN" eval --case '<case-name>' --dry-run             # what would run, and rough cost
python3 "$RUN" eval --case '<case-name>' --runs 1              # one case, for real
python3 "$RUN" eval --tag <suite>                              # a whole suite
```

**Read the findings, not the score.** The number is only a summary. Under it the check lists
each problem and the file it is in, and that list is what you act on. Below about `0.85`,
read every line. How to interpret the rest is in
[GETTING-STARTED](./GETTING-STARTED.md#part-2--reading-your-scorecard).

A `--target` that is not a plugin is an error (exit `2`), not a score — it will not quietly
hand you a passing number for a folder that isn't there.

**Real test runs cost real money.** Roughly $1–2 per run, and the default of 3 runs with
`llm` graders lands around $3–5 for a single test. **Always use `--dry-run` first** — it
lists exactly what would happen and the rough price, and spends nothing.

**4. See a worked case.** [`examples/plugin-eval/`](../../examples/plugin-eval/README.md) ships two, running against
real third-party plugins vendored into the repo — read them before writing your own:

```bash
python3 "$RUN" eval --cases-dir examples/plugin-eval/cases --skip-static --dry-run   # free
```

Exit codes: `0` all pass · `1` a case below `--threshold` · `2` usage or engine error. That
makes `eval` usable directly as a CI gate.

**5. Behavioral runs need model auth**, and MCP auth if your plugin declares an MCP server.
Set `ANTHROPIC_API_KEY` (or be logged into Claude Code), then either authenticate the
connector interactively (`claude` → `/mcp`) or inject a bearer token for headless runs:

```bash
export EVAL_MCP_BEARER='<service-token>'      # applied to every declared server
python3 "$RUN" eval --tag <suite>
```

Token injection is also the **higher-fidelity** path: the runner isolates the run to the
plugin's *own* declared MCP with `--mcp-config … --strict-mcp-config`, ignoring whatever
account connector happens to be logged in on your machine. Runs then behave the same
locally and in CI. The token is read from the environment only — never committed, never
written into any `.mcp.json`.

**Preflight before you spend.** A blocked endpoint otherwise burns a whole suite scoring
zero. The runner checks `claude mcp list` and aborts with guidance rather than producing a
misleading dataless run — but if your MCP sits behind an IP allowlist, confirm your egress
is allowed before starting a large suite.

**6. Read the run folder.** Every invocation writes a self-contained
`.runs/<run_id>/<case>/`: the full `cases.json`, per-run `result.json` + transcript +
`claude --debug-file` log, `scorecard.json`, and `report.{md,json,html}` with cost and
token usage split run vs judge. When something fails, the answer is in there.

---

## The eval dataset

Cases live at `evals/<case-name>/case.yaml` — one scenario per folder, plain YAML, no
index or registry. A case names the plugin, the prompt, and the graders:

```yaml
name: asksales-slowest-hours
description: >-
  What this case proves. Source: who asked for it (issue id).
plugins: ["../../plugins/acme-analytics"]   # relative to THIS file
tags: [acme, asksales]                      # select with --tag
runs: 3
execution:
  prompt: "What were the slowest hours at the Northgate store last week?"
  model: claude-sonnet-5
  harness: claude_code        # the RUNTIME that executes the turn
  entrypoint: none            # the SURFACE emulated; `none` = the harness's own prompt
  allowed_tools: [Read, Glob, Grep, Skill, mcp__Acme__run_query]
  mcp_config: ../mcp-config.json
graders:
  - {type: tool_used, name: filtered-to-store, tool: mcp__Acme__run_query, input_match: "Northgate", min: 1}
  - {type: llm, name: presentation, focus: last_message, criteria: "cites source; clear table; disclaimer"}
```

Scaffold one with `python3 "$RUN" init <name> --plugin plugins/<p> --tag <skill> --prompt
"<question>"`, then edit.

`harness` and `entrypoint` are independent axes and easy to confuse. `harness` is the
**runtime** (`claude_code`). `entrypoint` is the **surface** whose system prompt gets
swapped in. The default `none` runs on Claude Code's own prompt. One entrypoint ships — `cowork` —
and `--entrypoint <name>` overrides every case in a run without editing files. See
`skills/100xeval/scripts/engine/entrypoints/README.md` before adding another: a surface's
system prompt usually belongs to whoever operates that surface.

---

## Best practice for the dataset

Distilled from actually running it — the full versions, with the evidence, are in
[`references/managing-testcases.md`](skills/100xeval/references/managing-testcases.md).

**Assert the query shape, not the figure.** `tool_used` with `input_match` survives next
week's data; a hard-coded number is a scheduled false failure.

**When you must check numbers, hardcode the query in the criteria.** Left to itself the
judge writes a different query per vote and the "ground truth" moves, so a failure tells
you nothing. Verify the query by lifting it from a successful run — and don't trust the
plugin's own docs for table names.

**Keep `runs: 3`.** Skills are non-deterministic: one case answered `0.148×` (correct) and
`0.24×` (62% off) to the same prompt. A single run reports a coin flip as a fact.

**One claim per grader.** When a case fails you want the scorecard to name *which*
property broke.

**Grade what the prompt asks.** A criterion the user never requested fails correct
answers. If you add a stricter rule of your own, say so in a comment.

**Cover more than the happy path.** A suite of well-formed in-scope questions tests
little. Include a case the plugin should **refuse** (assert `tool_used` `min: 0, max: 0`),
one a sibling skill owns, and one exercising a documented business rule.

**Expect the first run to debug the case, not the skill.** Measured across the first six
cases we wrote, case defects outnumbered skill defects about **3:1** — wrong table,
ungranted tool, over-strict criteria, an off-by-one date bound. Budget a `--runs 1` pass
for it.

**Park, don't delete.** `skip: "<reason>"` keeps the scenario and prints the reason every
run. Deleting a case deletes the regression it guards — and never delete one to make a
suite green.

**Mind the cost.** Judges are up to nine extra model calls per case; a case at `runs: 3`
lands around $3–5. Reports break out `Run $ / Judge $ / Total $`.

**No secrets in a case, ever.** `mcp_config` holds a *path*; the config it points to uses
`Bearer ${EVAL_MCP_BEARER}`, expanded from the environment at run time.

---

## The static layer

`--static-only` scores plugin *design* with no model call at all. `engine/lint.py` walks the
plugin and emits tagged findings; `engine/static.py` maps them to sub-scores:

| Sub-score | Fed by | Catches |
| --- | --- | --- |
| `frontmatter_quality` | `FM1`–`FM7` | name/dir mismatch, unusable or missing description, unknown keys, malformed frontmatter |
| `progressive_disclosure` | `PD1` `PD2` | SKILL.md over the 500-line cap, dangling or empty `references/` |
| `reference_hygiene` | `RH1`–`RH3` | references nobody is told to read, references pointing at references, Windows separators |
| `structural_completeness` | `ST1` `ST2` | no plugin README, a "self-check" that isn't a checklist |
| `ecosystem_coherence` | `EC1` | routing to a companion skill that doesn't exist |
| `security` (weight ×2) | `SEC1`–`SEC3` | committed secrets, unknown network destinations, `../` traversal |
| `token_efficiency` (weight ×0.5) | — | instruction blocks copy-pasted between sibling skills, or repeated inside one |

A check ID's **prefix is its sub-score** (`FM3` → `frontmatter_quality`), so the two are
wired together by construction rather than by a lookup table someone has to remember to
update. `engine/lint.py`'s docstring lists every ID and what it means.

These encode *published* Claude Code skill guidance plus generic hygiene, deliberately
conservative: a finding should mean "this is probably wrong", not "this differs from how we
write skills". House-style rules belong in your fork of `lint.py`, not here. Extend the
allowed network destinations with `EVAL_LINT_ALLOWED_DOMAINS=internal.corp,cdn.example`.

---

## Layout

```
.claude-plugin/plugin.json              manifest
skills/100xeval/
├── SKILL.md                            the model-invoked skill (the front door)
├── references/
│   ├── case-schema.md                  every case.yaml field + every grader parameter
│   └── managing-testcases.md           lifecycle, best practice, gotchas, reading a red scorecard
├── scripts/                            ← the runtime payload: what ships and what Claude invokes
│   ├── run.py                          CLI entrypoint
│   └── engine/                         loader · orchestrator · graders · judge · reporter · lint · static
│       ├── entrypoints/                surface system prompts (none ship — see its README)
│       └── harnesses/                  runtimes: claude_code · codex (seam)
└── tests/                              stdlib unittest, no live calls — beside scripts/, not in it
```

## Tests

```bash
cd plugins/100xeval/skills/100xeval
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

`tests/` deliberately sits *beside* `scripts/` rather than inside it: `scripts/` is the
runtime payload — it ships with the plugin as-is and is the directory Claude invokes — so
the suite has no business being in there. Tests import `engine.*` absolutely, which is what
`PYTHONPATH=scripts` resolves. No live model or MCP calls; the suite runs offline.
