# `case.yaml` — template & full schema

Every field the loader accepts, what it defaults to, and every grader type with its
parameters. Companion: [`managing-testcases.md`](./managing-testcases.md) (lifecycle,
best practice, gotchas).

**Contents**
- [Template](#template)
- [Case fields](#case-fields)
- [`execution` fields](#execution-fields)
- [Graders](#graders)
  - [`tool_used`](#tool_used--did-it-query-the-right-data)
  - [`regex`](#regex--phrase-present-or-absent)
  - [`llm` (format)](#llm-format--presentation)
  - [`llm` (agentic)](#llm-agentic--numeric-accuracy)
  - [`static`](#graders--static)
- [YAML subset — what the loader accepts](#yaml-subset--what-the-loader-accepts)

## Template

```yaml
name: askinventory-turn-full-score          # required, unique; also the run-folder name
description: >-
  What this case proves, in one or two sentences.

  Source: who asked for it (issue / report id).
plugins: ["../../plugins/acme-analytics"]   # path(s) RELATIVE TO THIS FILE
tags: [acme, askinventory]        # select with --tag (ALL given tags must match)
runs: 3                                     # repetitions; passRate = passed / runs
execution:
  prompt: "What were the slowest hours at the Northgate store last week?"
  model: claude-sonnet-5
  harness: claude_code                      # RUNTIME (see SKILL.md: harness vs entrypoint)
  entrypoint: none                          # SURFACE emulated; `none` = the harness's own prompt
  max_turns: 20                             # agent tool-loop budget (--max-turns)
  allowed_tools: [Read, Glob, Grep, Skill, mcp__Acme__run_query]
  append_system_prompt: null                # extra text layered after the entrypoint
  mcp_config: ../mcp-config.json            # strict mode; omit to auto-build from the plugin
graders:
  - {type: tool_used, name: filtered-to-store, tool: mcp__Acme__run_query, input_match: "Northgate", min: 1}
  - type: llm
    name: presentation
    focus: last_message
    criteria: >-
      Cites its data source, gives a clear table, ends with the disclaimer.
```

Scaffold a stub with `python3 "$RUN" init <name> --plugin plugins/<p> --tag <skill>
--prompt "<question>"`, then edit.

## Case fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | str | **required** | Unique. Used by `--case` (fnmatch) and as the run subfolder. |
| `description` | str | `""` | What the case proves. Record where the scenario came from. |
| `plugins` | list[str] | `[]` | Plugin path(s) **relative to the case dir**. Must exist or the case fails to load. The first entry is the one staged and run. |
| `tags` | list[str] | `[]` | Selection labels. Convention: the skill under test, plus a suite tag. `--tag` requires **all** given tags to be present. |
| `runs` | int | `3` | Repetitions. This is how flakiness becomes visible — a skill that answers differently run to run shows up as a partial passRate instead of a coin-flip verdict. |
| `skip` | str | `""` | Non-empty parks the case: it is excluded from runs and the value is printed as the reason each run. Prefer this to deleting a case — deleting loses the scenario, untagging hides it. |
| `graders` | list | **≥1 required** | See [Graders](#graders). Names must be unique within the case. |

`execution.*` may also be written at the top level; `execution` wins if both are set.

## `execution` fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `prompt` | str | **required** | The user question, **verbatim**. Do not tidy it — how a real user phrases it is part of what's under test. |
| `model` | str | `null` | The one runner model. `null` → the CLI default. |
| `harness` | str | `claude_code` | The **runtime**. Only `claude_code` is implemented; `codex` is a registered seam that aborts with guidance. Surface names (`cowork`, `claude_chat`) are rejected — those are entrypoints. |
| `entrypoint` | str | `none` | The **surface** emulated: its real system prompt at `engine/entrypoints/<name>.md`. `none` passes no system prompt, so the harness's own applies. Any other name with no file **aborts in preflight** rather than emulating nothing. No entrypoint files ship — see `engine/entrypoints/README.md`. |
| `max_turns` | int | `15` | Agent tool-loop budget, passed to the CLI as `--max-turns`. Raise it for long multi-step work (a report build needs far more than a single question). |
| `timeout_s` | int | `300` | Per-**run** wall clock, in seconds. A multi-step build is killed at the default; `--timeout` overrides it for a whole invocation. |
| `allowed_tools` | list[str] | `[]` | Tools granted to the run. Both `mcp__X__t` and `mcp__claude_ai_X__t` spellings are expanded automatically, so either works. |
| `append_system_prompt` | str | `null` | Case-specific text layered **after** the entrypoint prompt. |
| `mcp_config` | str | `null` | Path (relative to the case dir) to an MCP config JSON → strict mode. Omit and, when a bearer is in the env, one is auto-built from the plugin's own `.mcp.json`. |

## Graders

Common to all: `type` (required), `name` (required, unique in the case), `weight`
(default `1`). Everything else is type-specific.

Case score = `Σ(weight × passRate) / Σ(weight)`; the case passes at `score ≥ --threshold`
(default `1.0`, i.e. everything must pass every run).

### `tool_used` — did it query the right data?

Asserts the **shape** of what was queried, never a figure, so it doesn't go stale.

| Param | Default | Meaning |
| --- | --- | --- |
| `tool` | **required** | Tool name. Canonicalized, so account vs plugin-scoped spellings match. |
| `input_match` | — | Substring that must appear in the call's input (e.g. a store name). |
| `min` | `1` | Minimum matching calls. |
| `max` | — | Maximum matching calls. |

`min: 0, max: 0` asserts the tool was **never** called — the strongest signal for an
out-of-scope case (it declined without going to the data).

### `regex` — phrase present or absent

| Param | Default | Meaning |
| --- | --- | --- |
| `pattern` | **required** | Python regex. |
| `target` | `last_message` | `last_message` (final answer) or `trace` (tool calls + inputs). |
| `match` | `contains` | `contains` or `not_contains`. |
| `flags` | — | `re` flag names joined by `\|`, e.g. `IGNORECASE\|MULTILINE`. |

`not_contains` is how you assert an absence — e.g. that internal SQL or tool names never
leak into a user-facing report.

### `llm` (format) — presentation

No `allowed_tools` → format mode. The judge sees **only the text** and is told it has no
data access, so it can never fake a numeric verdict.

| Param | Default | Meaning |
| --- | --- | --- |
| `criteria` | **required** | What good looks like, in plain sentences. |
| `focus` | `last_message` | `last_message` or `trace`. |

### `llm` (agentic) — numeric accuracy

Non-empty `allowed_tools` → agentic mode: the judge gets those tools **and the case's MCP
config**, and verifies figures against live data.

| Param | Default | Meaning |
| --- | --- | --- |
| `criteria` | **required** | Include the **exact SQL** to run. See the ground-truth pattern in `managing-testcases.md`. |
| `allowed_tools` | **required for this mode** | e.g. `[mcp__Acme__run_query]`. |
| `focus` | `last_message` | As above. |

Judge behaviour is governed by a grader system prompt (`judge.system_prompt_for`) that
forbids asking for approval and requires any SQL in the criteria to be run verbatim.
Override per run with `--judge-system-prompt <path-or-text>`. Verdicts are a majority
over `--judge-votes` (default 3).

## YAML subset — what the loader accepts

`yamlmin` is a deliberately small, dependency-free parser. It supports block mappings and
sequences, inline flow collections, `#` comments, and block scalars (`|`, `>`, with `-`/`+`
chomping). Two limits bite in practice:

- **Flow collections must stay on ONE line.** `allowed_tools: [a, b, c]` wrapped across
  two lines raises `IndexError`/parse errors. Long lists stay long.
- **Anchors/aliases, multi-document `---`, and tags are unsupported** and raise `YamlError`.

Multi-line prose and SQL belong in block scalars — `|-` keeps newlines (use for SQL),
`>-` folds lines into one paragraph (use for descriptions and criteria).

## Graders — `static`

`static` gates the case's plugin on its design-quality score. Deterministic and free: no
run, no model. It reuses the same layer as `--static-only`, so a case and the standalone
report can never disagree.

| Param | Default | Meaning |
| --- | --- | --- |
| `min_score` | `0.8` | Minimum `design_score` (0–1). |

```yaml
  - {type: static, name: design-quality, min_score: 0.6}
```

A failure names the three weakest sub-scores, so it says *what* to fix:
`design_score 0.68 (needed >= 0.80) — weakest: progressive_disclosure 0.50, init_gates 0.75, security 0.75`.
