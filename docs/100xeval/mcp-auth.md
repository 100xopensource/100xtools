---
type: concept
title: MCP auth
description: Two authentication paths that produce two different tool-name schemes, how to set the token, and the failure that looks like nothing.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/harnesses/claude_code.py
tags: [100xeval, mcp, auth]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# MCP auth

If the plugin under test declares an MCP server, the run needs that server connected. There
are two ways to get there, and **they produce different tool names**.

| Path | Auth comes from | Tools are named |
| --- | --- | --- |
| Ambient account connector | Whichever account is logged in on this machine | `mcp__claude_ai_<Server>__<tool>` |
| Strict plugin config | `EVAL_MCP_BEARER` in the environment | `mcp__<Server>__<tool>` |

The engine canonicalizes across both, so one set of grader tool names works either way.
Without that, a case written locally would silently stop matching in CI — the tools would be
called, the names would not match, and `tool_used` would report zero.

## Prefer strict mode

Strict mode passes the plugin's own MCP config with `--strict-mcp-config`, ignoring ambient
connectors entirely. Two reasons it is the better path:

* **Auth is deterministic.** The token comes from the environment, not from whoever happens
  to be logged in, so a run behaves identically on a laptop and in CI.
* **It tests what ships.** The plugin's declared MCP is what a user gets; an account
  connector is what *you* happen to have.

The token is read from the environment only. It is never committed and never written into
any `.mcp.json` — a case file holds a *path* to a config, and that config references
`${EVAL_MCP_BEARER}`, expanded at run time.

## The failure that looks like nothing

**A bad or expired token surfaces as `tool_used` "called 0×" — not as an auth error.**

This is the single most expensive gotcha here. The run completes, the model answers from
nothing, the grader reports that the tool was never called, and every instinct says the
skill stopped querying. Check the token before you touch the skill.

Preflight helps: the runner checks `claude mcp list` and aborts with guidance when a
declared server is not connected, rather than producing a confident dataless run. But
preflight cannot see through a token that is present and wrong.

## Preflight before you spend

A blocked endpoint burns an entire suite scoring zero. If the MCP sits behind an IP
allowlist, confirm the egress is allowed before starting a long run — the cost of checking
is one request, and the cost of not checking is the whole suite.

## Setting it up

If the plugin declares an MCP server, either authenticate the connector interactively
(`claude` → `/mcp`) or inject a bearer token for headless runs:

```bash
export EVAL_MCP_BEARER='<service-token>'      # applied to every declared server
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag <suite>
```

The token is read from the environment only — never committed, never written into any
`.mcp.json`.

## See also

* [Harness](harness.md) - what invokes the runtime and reads back tool calls
* [Grader](grader.md) - `tool_used` is what reports the symptom
