# 100xeval — engine

Behavioral + static eval for Claude Code plugins. Dependency-free (Python stdlib only,
no virtualenv, no install step).

## Run

```bash
# scaffold a new case
python3 plugins/100xeval/skills/100xeval/scripts/run.py init <name> --plugin plugins/<p> --tag <skill> --prompt "…"

# run static + behavioral (default)
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag asktickets

# design quality only, no execution (free)
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target plugins/acme-analytics

# behavioral only
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --skip-static --case 'asktickets-*'
```

Exit codes: `0` all pass · `1` a case below `--threshold` (default 1.0) · `2` engine error.

## Behavioral runs need auth — two credentials

MCP always goes through `--mcp-config … --strict-mcp-config`: the runner isolates to the
plugin's *own* declared servers and injects the `Authorization` header from the environment.
claude.ai account connectors are **not** supported — they load only under an interactive
claude.ai login, so a run that leaned on one could never be reproduced in CI. Same path
locally and headless, which is the point.

```bash
export MCP_ACME_API_KEY='<acme-key>'                     # one var per declared server
export MCP_ACME_FEEDBACK_API_KEY='<acme-feedback-key>'   # `Acme-Feedback` → ACME_FEEDBACK

# …or let the runner mint a short-lived token instead of holding a static key.
# Two vars: the token endpoint is discovered from the MCP URL (RFC 9728 -> RFC 8414).
export MCP_ACME_CLIENT_ID='<client-id>'
export MCP_ACME_CLIENT_SECRET='<client-secret>'
# optional: _TOKEN_URL to skip discovery, _AUTH_STYLE=post, _SCOPE (usually omit)
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag asktickets
```

The credential is read from the environment only — **never committed, never written to any
`.mcp.json`**; the config on disk holds the literal `${VAR}` and Claude Code expands it.
A declared server with no credential is still passed through, just without the header, and
answers 401 — which surfaces at run time as `tool_used` "called 0×", never as an auth error.
Tool names are the strict-config scheme only, `mcp__<Server>__<tool>`, and the server-name
**case** is significant: a grader written `mcp__acme__*` never matches a server declared
`Acme` and the failure looks identical to a bad credential.

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
  comment.py                report dict → one PR comment that fits GitHub's size cap
  judge.py                  LLM judge: grader system prompt + majority vote over `votes`
  cli.py                    argparse: init, eval
  entrypoints/              SURFACE system prompts (none ship — see its README)
```
