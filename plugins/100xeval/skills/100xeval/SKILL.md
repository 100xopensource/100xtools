---
name: 100xeval
description: Run behavioral and static evals for a Claude Code plugin or skill, write and maintain the testcases they run on, and interpret the scorecard. Use when someone says "run the evals for [skill]", "eval this plugin", "add a testcase for [skill]", "turn this bug report into a testcase", "what should I be testing", "static-check my plugin", "check [skill] before merge", "did my change regress", "why did it score [n]", or wants a pass/fail scorecard on a plugin's real answers. Do NOT use for authoring or fixing the plugin under test.
---

# 100xeval — run plugin evals

Drive the 100xeval engine (bundled with this skill under `scripts/`) to grade whether a
plugin's real answers are correct before merge, and explain the result. It runs in Claude
Code. Engine README: `scripts/README.md`.

**Resolve the engine entrypoint once**, then use `$RUN` below (works whether this skill is
loaded as a plugin or run from a clone of the repo):

```bash
RUN="${CLAUDE_PLUGIN_ROOT:-plugins/100xeval}/skills/100xeval/scripts/run.py"
```

What it grades: **behavioral** — really runs the plugin against saved `case.yaml` cases with
the plugin's own MCP attached, checking it queried the right data (`tool_used`, never a
hard-coded number), presented it correctly (`llm` format judge), and optionally that the
figures are right (`llm` agentic judge); and **static** — a run-free, model-free
design-quality score from the bundled linter (`engine/lint.py`). Two jobs follow: **manage
testcases** and **run evals**.

---

## 1) Manage testcases

A testcase is one `evals/<name>/case.yaml`. Scaffold, then edit.

```bash
# scaffold a stub (tool_used + llm graders pre-filled)
python3 "$RUN" init <name> --plugin plugins/<p> --tag <skill> --prompt "<question>"
```

**Before writing or changing a case, read the bundled references:**

| Read | For |
| --- | --- |
| `references/case-schema.md` | The template and every field/grader parameter, plus the YAML subset's limits. |
| `references/managing-testcases.md` | Add / edit / delete workflow, best practice, the coverage dimensions, the ground-truth SQL pattern, and gotchas that have actually bitten. |

The essentials:
- **`execution.prompt`** — the user question, verbatim (don't tidy it — resolving a loose
  name is the skill's job); **`tags`** — the skill under test plus a suite tag (select with
  `--tag`); **`plugins`** — path(s) to the plugin, relative to the case dir.
- **`graders`** — one claim per grader: a `tool_used` (right query shape, never a
  hard-coded figure), an `llm` (presentation); add an agentic `llm` with `allowed_tools`
  **and the exact query in its `criteria`** to verify numbers, or a `regex` for a phrase.
- **Keep `runs: 3`.** Skills are non-deterministic; one run reports a coin flip as fact.
- **Strict/CI mode** (optional): set `execution.mcp_config: mcp-config.json` and put the
  plugin's MCP servers there with `"Authorization": "Bearer ${EVAL_MCP_BEARER}"` — the token
  is expanded from the environment at run time, never hardcoded. No secret ever belongs in
  a case file.
- **Validate it loads before spending a run**, and expect the first run to debug the
  *case* (ungranted tool, wrong column) before it tests the skill.

Every scenario a user complains about should become a case here — that is how the corpus
grows, and how a fixed bug stays fixed.

## 2) Run evals

Run from the repo root; pick the narrowest selection that answers the question.

```bash
python3 "$RUN" eval --tag <skill>                       # a skill's cases (static + behavioral)
python3 "$RUN" eval --case '<case-glob>'                # one case by name
python3 "$RUN" eval --static-only --target plugins/<p>  # design quality only (free, no run)
python3 "$RUN" eval --skip-static --tag <skill>         # behavioral only
python3 "$RUN" eval --tag <skill> --report eval.md --json eval.json --html eval.html
```

Useful flags: `--runs N` (default 3), `--threshold X` (default 1.0), `--judge-model`,
`--judge-votes`, `--verbose`. Every run writes a self-contained folder under
`.runs/<run_id>/<case>/` — go there to debug. Per run you get: `result.json`
(RunResult plus the exact `command`, `returncode`, `stderr`), `workspace/claude-debug.log`
(Claude's own `--debug-file` trace), `transcript.jsonl` (tool calls), plus `scorecard.json`
and `report.{md,json,html}`.

**Parallelism — `--concurrency N` (default 4)** is the number of plugin runs in flight
across the **whole suite**: cases run concurrently and share that one budget, so a suite
finishes in roughly `total_runs / N` waves instead of case-by-case. Raising it raises real
load (each run is a `claude -p` hitting the API *and* the plugin's MCP), so raise it only
as far as the MCP endpoint tolerates; `--concurrency 1` is fully sequential, which is what
you want when debugging a single case. `--case-concurrency M` (default = `N`) caps how many
cases are in flight — grading doesn't hold a run slot, so a higher `M` overlaps judging
with runs. Report order always follows case order, whatever finishes first.

**Behavioral runs need MCP auth** when the plugin declares one. The runner pre-flights
`claude mcp list` and aborts with guidance if a declared server isn't connected. Fix and
retry:

```bash
claude mcp login <server-name>     # or run `claude` interactively and approve via /mcp
```

(A plugin with no `.mcp.json` runs directly. In strict `mcp_config` mode, auth is the
`${EVAL_MCP_BEARER}` token instead — a bad or expired token shows up as `tool_used`
"called 0×", not as an auth error, so check the token before blaming the skill.)

**Read the scorecard:** a case runs on exactly **one harness + one model**
(`execution.harness`, default `claude_code`, × `execution.model`) repeated `runs` times.
Per-case `score` = weighted mean of grader passRates (passes at `≥ threshold`); failing runs
print grader `detail` (wrong data = `tool_used` 0×, wrong presentation = `llm` format, wrong
numbers = `llm` agentic). Exit: `0` pass · `1` below threshold · `2` engine error.

**`harness` vs `entrypoint`** — two independent axes, easy to confuse. `harness` is the
**runtime** that executes the turn (`claude_code`; `codex` is a registered seam that
aborts). `entrypoint` is the **surface** being emulated, i.e. that surface's real system
prompt. The default is `entrypoint: none` — the run uses Claude Code's own prompt, which is
right when Claude Code is the surface you care about. To emulate a different surface,
supply its prompt yourself (`scripts/engine/entrypoints/README.md`). A new surface is a new
entrypoint, never a new harness.

## Report back

Summarize: overall pass/fail, which cases and graders failed and why (quote the `detail` or
the run's `result.json`), and the concrete next step (re-auth MCP, fix the skill, or fix the
case). Keep it short — root cause → what failed → what to do.
