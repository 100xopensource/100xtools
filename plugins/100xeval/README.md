# 100xeval — check whether a plugin is any good

100xeval answers one question: **did this plugin actually give the right answer?**

A *plugin* is a folder of instructions telling Claude how to do a job. Nothing checks
instructions — there is no spell-check and no test that goes red. This is that check.

It works in two ways, very different in cost. Start with the free one.

| | What it does | Cost | Needs |
| --- | --- | --- | --- |
| **Static check** | Reads your plugin's files and reports problems it can see, without running anything | **Free** | Just Python |
| **Real test run** | Actually runs your plugin on saved questions and grades the answers | **~$1–2 per run** | Claude Code CLI, and a login or API key |

The **static check** is the one most people use, and most never need more. It catches what
you cannot see by reading — a skill with no description, a misspelled setting Claude has been
silently ignoring, a password left in a file.

The **real test run** is for proving an edit did not change the answers. It runs the plugin
for real with its data connection attached, then checks three things: did it look up the
right data, did it present the result properly, and are the numbers right.

Everything ships in one folder — the skill Claude talks to and the Python engine underneath.
**Python 3.11+, standard library only:** no `pip install`, no virtualenv, no lockfile.

---

## What you need

**For the static check: Python 3.11 or newer, and nothing else.** No API key, no internet, no
account. Check yours:

```bash
python3 --version
```

`3.11` or higher is fine. If the number is lower, install a newer one (`brew install
python@3.12` on Mac) and use `python3.12` below. If the command is not found at all, get
Python from [python.org/downloads](https://www.python.org/downloads/). Run it on an old
Python and the tool says so in plain words rather than showing a wall of red text.

**For real test runs: the Claude Code CLI on your `PATH`**, plus a login or an
`ANTHROPIC_API_KEY`. The runner executes your plugin by shelling out to `claude`, so a key on
its own is not enough — without the CLI it stops before spending anything and tells you to
install Claude Code. If your plugin connects to a data source you may also need a token, see
[Real test runs](#real-test-runs).

**Claude Code or the Claude desktop app**, if you would rather ask in plain words than type
commands.

---

## Get started

The easiest way is to let Claude drive. Install once, then ask for things in plain words —
you never type an engine command.

**1. Get the code.** In a terminal:

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
```

**2. Install the plugin.** Two more lines in the same terminal — the first tells Claude where
to find the tools, the second installs this one:

```bash
claude plugin marketplace add ./
claude plugin install 100xeval@100xtools
```

> **Type `./` and not `.`** — a bare dot is rejected with *"Invalid marketplace source
> format"*. The `/` is not a typo.

**How to tell it worked:** the first line answers `Successfully added marketplace: 100xtools`.

**3. Ask for a check.** Point Claude at the folder your plugin is in, and say:

> *"static-check my plugin"*

**How to tell it worked:** Claude runs the check and shows a score with findings underneath.
If it instead asks what you mean, the plugin did not install — repeat step 2.

That is the whole thing: no key, no internet, no cost, and nothing on your computer is
changed. The static check only *reads* files. It never edits your plugin, never uploads it,
and never touches the network.

Worth asking once you have a result:

> *"why did it score 0.77?"* · *"what should I fix first?"* · *"is that finding real?"* ·
> *"run the evals for asksales"* · *"add a testcase for askinventory"*

---

## Reading your scorecard

A real result from a plugin with problems:

```
# 100xeval — static design quality  (scoring v1)

## demo-plugin — design_score 0.77
- frontmatter_quality: 0.50
- progressive_disclosure: 1.00
- reference_hygiene: 1.00
- structural_completeness: 0.75
- token_efficiency: 1.00
- ecosystem_coherence: 1.00
- security: 1.00

### findings (3)
- demo-plugin: [ST1] plugin has no README.md at its root
- skills/report/SKILL.md: [FM3] skill has no description — the model cannot decide when to load it
- skills/report/SKILL.md: [FM4] unrecognized frontmatter key 'descriptionn' (did you mean 'description'?)
```

**Read the findings, not the number.** The number only summarises; the findings tell you what
to do. Here they earn their keep: someone typed `descriptionn` with two n's, and Claude was
silently ignoring the description.

| Score | Meaning |
| --- | --- |
| **1.00** | Nothing found. Does not prove the plugin *works* — only that nothing obvious is broken. |
| **0.85–0.99** | Small things. Worth a look, not urgent. |
| **below 0.85** | Read every finding. Something real is usually in there. |

You do not need to learn the check IDs (`ST1`, `FM3`). The message beside each says what is
wrong in plain words.

**Three honest warnings:**

**This tool is sometimes wrong.** It reads your writing and guesses. Run against Anthropic's
own published plugins, it produced five classes of false alarm in one pass. If more than about
**one finding in five** is nonsense for your plugin, the tool is wasting your attention — say
so; that is a bug in the tool, not in you.

**`token_efficiency` never shows a finding.** It is measured, not detected — it counts
repeated text across your files. A low score there with an empty findings list is normal, not
a display bug.

**Scores only compare within the same `scoring v1`**, printed at the top. If the rules change
the number moves, and old numbers stop being comparable. See [Known traps](#known-traps) if
you gate CI on a threshold.

A `--target` that is not a plugin is an error (exit `2`), not a score — it will not quietly
hand you a passing number for a folder that isn't there.

---

## Running the engine yourself

You do not need this section; Claude runs these for you. It is here for people who prefer
seeing the command.

```bash
RUN=plugins/100xeval/skills/100xeval/scripts/run.py

python3 "$RUN" eval --static-only --target <your-plugin-dir>   # free — start here
python3 "$RUN" eval --static-only                              # every plugin it can find
python3 "$RUN" eval --case '<case-name>' --dry-run             # what would run, and rough cost
python3 "$RUN" eval --case '<case-name>' --runs 1              # one case, for real
python3 "$RUN" eval --tag <suite>                              # a whole suite
```

Nothing to try it on yet? Use a plugin that ships with the repo:

```bash
python3 "$RUN" eval --static-only --target examples/plugin-eval/vendor/design
```

**See a worked case.** [`examples/plugin-eval/`](../../examples/plugin-eval/README.md) ships
two, running against real third-party plugins vendored into the repo — read them before
writing your own:

```bash
python3 "$RUN" eval --cases-dir examples/plugin-eval/cases --skip-static --dry-run   # free
```

Exit codes: `0` all pass · `1` a case below `--threshold` · `2` usage or engine error. That
makes `eval` usable directly as a CI gate.

---

## Real test runs

**Read this before running anything here — it costs real money.**

A real test run executes your plugin and asks Claude to grade the answers. Roughly **$1–2 per
run**, and the default of 3 runs lands around **$3–5 for a single test**. There is no free
tier and no undo.

**Always check the price first.** `--dry-run` lists exactly what would execute and the rough
spend, without spending it:

```bash
python3 "$RUN" eval --case '<case-name>' --dry-run
```

**Expect the first run to fail for a boring reason.** Usually the *test* is wrong, not the
plugin — for us, case defects outnumbered skill defects about **3:1**.

### Auth

Set `ANTHROPIC_API_KEY`, or be logged into Claude Code. If your plugin declares an MCP server,
either authenticate the connector interactively (`claude` → `/mcp`) or inject a bearer token
for headless runs:

```bash
export EVAL_MCP_BEARER='<service-token>'      # applied to every declared server
python3 "$RUN" eval --tag <suite>
```

Token injection is also the **higher-fidelity** path: the runner isolates the run to the
plugin's *own* declared MCP with `--mcp-config … --strict-mcp-config`, ignoring whatever
account connector happens to be logged in on your machine, so runs behave the same locally and
in CI. The token is read from the environment only — never committed, never written into any
`.mcp.json`.

**Preflight before you spend.** A blocked endpoint otherwise burns a whole suite scoring zero.
The runner checks `claude mcp list` and aborts with guidance rather than producing a
misleading dataless run — but if your MCP sits behind an IP allowlist, confirm your egress is
allowed before starting a large suite.

### The run folder

Every invocation writes a self-contained `.runs/<run_id>/<case>/`: the full `cases.json`,
per-run `result.json` + transcript + `claude --debug-file` log, `scorecard.json`, and
`report.{md,json,html}` with cost and token usage split run vs judge. When something fails,
the answer is in there.

---

## If something goes wrong

| What you see | What it means | What to do |
| --- | --- | --- |
| `command not found: python3` | Python is not installed | Install it — see [What you need](#what-you-need) |
| `100xeval needs Python 3.11 or newer` | Your Python is too old | Install a newer one, then use `python3.12` |
| `Invalid marketplace source format` | You typed `.` instead of `./` | Add the slash |
| `repository not found` | You lack access to the repo | Ask to be added to `100xopensource` |
| `is not a directory` (exit 2) | The folder path is wrong | Check it. **The tool refuses to invent a score for a folder that isn't there** |
| `No findings. Nothing to fix.` | Nothing detectable is wrong | This is a pass |
| A test says a tool was `called 0×` | Usually a **bad or expired token**, not a broken plugin | Check the token before blaming the skill |
| A wall of red text | A real bug in the tool | Please report it, with the command you ran |

---

## The eval dataset

Cases live at `evals/<case-name>/case.yaml` — one scenario per folder, plain YAML, no index or
registry. A case names the plugin, the prompt, and the graders:

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
**runtime** (`claude_code`). `entrypoint` is the **surface** whose system prompt gets swapped
in. The default `none` runs on Claude Code's own prompt. One entrypoint ships — `cowork` — and
`--entrypoint <name>` overrides every case in a run without editing files. See
`skills/100xeval/scripts/engine/entrypoints/README.md` before adding another: a surface's
system prompt usually belongs to whoever operates that surface.

---

## Best practice for the dataset

Distilled from actually running it — the full versions, with the evidence, are in
[`references/managing-testcases.md`](skills/100xeval/references/managing-testcases.md).

**Assert the query shape, not the figure.** `tool_used` with `input_match` survives next
week's data; a hard-coded number is a scheduled false failure.

**When you must check numbers, hardcode the query in the criteria.** Left to itself the judge
writes a different query per vote and the "ground truth" moves, so a failure tells you nothing.
Verify the query by lifting it from a successful run — and don't trust the plugin's own docs
for table names.

**Keep `runs: 3`.** Skills are non-deterministic: one case answered `0.148×` (correct) and
`0.24×` (62% off) to the same prompt. A single run reports a coin flip as a fact.

**One claim per grader.** When a case fails you want the scorecard to name *which* property
broke.

**Grade what the prompt asks.** A criterion the user never requested fails correct answers. If
you add a stricter rule of your own, say so in a comment.

**Cover more than the happy path.** A suite of well-formed in-scope questions tests little.
Include a case the plugin should **refuse** (assert `tool_used` `min: 0, max: 0`), one a
sibling skill owns, and one exercising a documented business rule.

**Park, don't delete.** `skip: "<reason>"` keeps the scenario and prints the reason every run.
Deleting a case deletes the regression it guards — and never delete one to make a suite green.

**Mind the cost.** Judges are up to nine extra model calls per case; a case at `runs: 3` lands
around $3–5. Reports break out `Run $ / Judge $ / Total $`.

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

A check ID's **prefix is its sub-score** (`FM3` → `frontmatter_quality`), so the two are wired
together by construction rather than by a lookup table someone has to remember to update.
`engine/lint.py`'s docstring lists every ID and what it means.

These encode *published* Claude Code skill guidance plus generic hygiene, deliberately
conservative: a finding should mean "this is probably wrong", not "this differs from how we
write skills". House-style rules belong in your fork of `lint.py`, not here. Extend the allowed
network destinations with `EVAL_LINT_ALLOWED_DOMAINS=internal.corp,cdn.example`.

---

## Known traps

Two ways this tool can report success without having checked anything. Both have bitten us.

**Absence assertions fail open.** `min: 0, max: 0` passes when nothing matched — and a mistyped
pattern also matches nothing, so a typo silently gives you a grader that *cannot* fail. Before
trusting one, confirm the same pattern can pass with `min: 1` on a run where the tool really
was used.

**`design_score` is only comparable within a scoring version.** The version is printed on every
report and carried in the JSON as `scoringVersion`. It is bumped whenever a change would move
an unchanged plugin's score, so a number from one version means nothing against another. If you
gate CI on a threshold, pin the version you tuned it against — see
[CHANGELOG.md](../../CHANGELOG.md).

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

`tests/` deliberately sits *beside* `scripts/` rather than inside it: `scripts/` is the runtime
payload — it ships with the plugin as-is and is the directory Claude invokes — so the suite has
no business being in there. Tests import `engine.*` absolutely, which is what
`PYTHONPATH=scripts` resolves. No live model or MCP calls; the suite runs offline.
