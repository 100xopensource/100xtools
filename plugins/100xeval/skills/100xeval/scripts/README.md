# 100xeval — engine

Behavioral + static eval for Claude Code plugins. Dependency-free (Python stdlib only,
no virtualenv, no install step).

## Run

```bash
# scaffold a new case
python3 plugins/100xeval/skills/100xeval/scripts/run.py init <name> --plugin plugins/<p> --tag <skill> --prompt "…"

# run static + behavioral (default)
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag asksales

# design quality only, no execution (free)
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target plugins/acme-analytics

# behavioral only
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --skip-static --case 'asksales-*'
```

Exit codes: `0` all pass · `1` a case below `--threshold` (default 1.0) · `2` engine error.

## Behavioral runs need auth — two paths

**Local (interactive):** authenticate the connector once (`claude` → `/mcp`), then run.
The run reuses your account-level connector (same server URL as the plugin's `.mcp.json`).
Pre-flight checks `claude mcp list` and aborts with guidance if it isn't connected,
rather than producing a misleading dataless run.

**Headless / CI (token injection) — also higher fidelity.** Set a bearer token in the
environment and the runner isolates to the plugin's *own* MCP via
`--mcp-config … --strict-mcp-config` (injecting the `Authorization` header, ignoring all
ambient/account MCP). This is what makes CI work without interactive OAuth, and it tests
the plugin's declared MCP as shipped rather than an account connector.

```bash
export MCP_ACME_API_KEY='<acme-key>'                     # one var per declared server
export MCP_ACME_FEEDBACK_API_KEY='<acme-feedback-key>'   # `Acme-Feedback` → ACME_FEEDBACK
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag asksales
```

The token is read from the environment only — **never committed, never written to any
`.mcp.json`**. In this mode pre-flight skips the account-connector
check (irrelevant); a bad token surfaces at run time as `tool_used` "called 0×". Tool-name
schemes differ between the two paths (`mcp__claude_ai_Acme__…` vs `mcp__Acme__…`); the
runner canonicalizes them so a case's graders match either way.

## Tests

The suite lives one level up, in `../tests/` — this directory is the runtime payload that
ships with the plugin, so tests stay out of it.

```bash
cd plugins/100xeval/skills/100xeval && PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

(`PYTHONPATH=scripts` matters — tests import `engine.*` absolutely and don't know where
they live, so `scripts/` has to be on `sys.path`.)

## Layout

```
run.py                      entrypoint → engine.cli:main
engine/
  yamlmin.py                stdlib YAML-subset loader
  models.py                 Case, Grader, RunResult, Scorecard
  loader.py                 discover + parse + validate case.yaml
  harnesses/                the RUNTIME seam — named per runtime, never per surface
    base.py                   Harness protocol + registry
    claude_code.py            claude -p adapter + transcript parse (tool_used)
    codex.py                  second runtime (seam only — preflight aborts, not implemented)
  orchestrator.py           per-case orchestration (one harness + one model × runs) + scoring + file persistence
  graders.py                tool_used, regex (+ llm/static registered elsewhere)
  lint.py                   standalone plugin conformance linter (tagged findings)
  static.py                 design-quality layer — scores lint.py's findings
  reporter.py               Scorecard → markdown + stable JSON (schemaVersion)
  judge.py                  LLM judge: grader system prompt + majority vote over `votes`
  cli.py                    argparse: init, eval
  entrypoints/              SURFACE system prompts (none ship — see its README)
```
