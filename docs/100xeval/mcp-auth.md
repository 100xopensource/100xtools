---
type: concept
title: MCP auth
description: The one authentication path a run has, the two credential shapes it accepts, and the failure that looks like nothing.
resource: ../../plugins/100xeval/skills/100xeval/scripts/engine/harnesses/claude_code.py
tags: [100xeval, mcp, auth]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-10T00:00:00Z
---

# MCP auth

If the plugin under test declares an MCP server, the run needs a credential for that server.
There is **one path** — the plugin's own servers passed with `--strict-mcp-config`, authenticated
by a bearer credential from the environment — and it is the same path locally and in CI.

That single path is also what fixes the tool names. Strict config produces exactly one scheme,
`mcp__<Server>__<tool>`, spelled as the server declares itself, so a grader written on a laptop
matches in CI. Matching is case-sensitive: `mcp__acme__*` does not match a server named `Acme`.

## Two credential shapes

Strict mode accepts any bearer credential, which leaves two shapes worth naming:

* **An API key** — a long-lived key the server issues, valid until someone rotates it.
* **An OAuth client-credentials token** — minted per run from an IdP and expiring on its own.
  The engine performs the exchange itself from a client ID and secret — discovering the token
  endpoint from the MCP URL per RFC 9728 and RFC 8414 — caches it per endpoint, re-mints inside
  an expiry margin, and publishes the result into the child process's environment. Claude Code still has
  no headless OAuth mode of its own; this works because 100xeval does the grant and hands over
  a bearer credential.

Prefer the second where the server supports it: the credential's lifetime is the whole
difference, and a token that expires by itself is one nobody has to remember to rotate. Once
the credential exists the engine treats them identically.

The how-to for both is
[`references/mcp-auth.md`](../../plugins/100xeval/skills/100xeval/references/mcp-auth.md),
which ships inside the plugin.

## Why strict mode is the only mode

Strict mode passes the plugin's own MCP config with `--strict-mcp-config`, which ignores account
connectors entirely. Two reasons it is the only path offered:

* **Auth is deterministic.** The credential comes from the environment, not from whoever happens
  to be logged in, so a run behaves identically on a laptop and in CI.
* **It tests what ships.** The plugin's declared MCP is what a user gets; an account
  connector is what *you* happen to have, and a pass through one attributes the win wrongly.

The key is read from the environment only. It is never committed and never written into
any `.mcp.json` — a case file holds a *path* to a config, and that config references
`${MCP_<SERVER>_API_KEY}`, expanded at run time.

## One variable per server, and no global

The variable name is built from the server's own name: non-alphanumerics become underscores
and the whole thing uppercases, so a server called `Acme-Feedback` reads
`MCP_ACME_FEEDBACK_API_KEY`.

**There is deliberately no key that applies to every declared server.** A plugin can declare
servers from two different vendors, and a single shared variable would hand each vendor the
other's credential. The cost of that safety is one variable per server, which is also one CI
secret per server.

A declared server with no key set is still passed to `--strict-mcp-config` — hiding it would
change what the plugin under test actually gets — but it goes without an `Authorization`
header. If that server is the one the case needs, the symptom is the "called 0×" failure
below, so set the key before blaming the skill.

## Why the account connector was removed

Connecting a server once in the claude.ai UI was the easier setup, and it worked for local runs.
It **could not** be carried into CI — a documented property of Claude Code, not a limitation
here — so it was dropped rather than left as a path that passes locally and cannot be reproduced.
Nothing falls back to it now.

claude.ai connectors are fetched only when the active credential is an interactive claude.ai
subscription login. They are not loaded when `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`apiKeyHelper`, a cloud provider, an Anthropic profile, or `CLAUDE_CODE_OAUTH_TOKEN` supplies
it — a `claude setup-token` token can only make model requests. Every credential a headless
runner can hold is on that list, so there is no supported way to reach a connector from CI.

What survives under a `CLAUDE_CODE_OAUTH_TOKEN` run is an MCP server the run configures
itself, which is exactly strict mode. So a job needs two credentials doing two jobs:
`CLAUDE_CODE_OAUTH_TOKEN` for the model, `MCP_<SERVER>_API_KEY` for each MCP server.

## The failure that looks like nothing

**A bad, expired, or missing token surfaces as `tool_used` "called 0×" — not as an auth error.**

This is the single most expensive gotcha here. The run completes, the model answers from
nothing, the grader reports that the tool was never called, and every instinct says the
skill stopped querying. Check the token before you touch the skill — and the server name's
case second, since a grader whose case is wrong fails identically.

Nothing preflights this. A credential that is present and wrong is indistinguishable from one
that is right until the server answers, so verify a suspect endpoint with one request before
spending a suite.

## Preflight before you spend

A blocked endpoint burns an entire suite scoring zero. If the MCP sits behind an IP
allowlist, confirm the egress is allowed before starting a long run — the cost of checking
is one request, and the cost of not checking is the whole suite.

## Setting it up

If the plugin declares an MCP server, set its credential in the environment:

```bash
export MCP_ACME_API_KEY='<acme-key>'          # one per server the plugin declares
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag <suite>
```

The token is read from the environment only — never committed, never written into any
`.mcp.json`.

## See also

* [Harness](harness.md) - what invokes the runtime and reads back tool calls
* [Grader](grader.md) - `tool_used` is what reports the symptom
