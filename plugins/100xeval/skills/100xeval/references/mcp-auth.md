# MCP auth — getting the plugin's data access into a run

A plugin that declares an MCP server needs that server connected, or the run answers from
nothing and every `tool_used` grader reports "called 0×". This page is how to get it connected.
`ci-setup.md` covers the CI wiring; the concepts live in `docs/100xeval/mcp-auth.md`.

## Two recommended methods for headless runs

Headless means anything with no human at a browser: CI, a cron job, `claude -p` in a script.
Both methods end the same way — a bearer credential in an `Authorization` header, injected from
the environment and never written to disk.

| Method | Use when | Credential lifetime |
| --- | --- | --- |
| **API key** | The server issues long-lived keys, or you are getting started | Until rotated by hand |
| **OAuth client credentials** | The server sits behind an IdP that issues machine tokens | Minutes to hours; re-minted per run |

**Prefer client credentials where the server supports it.** A static key in a CI secret is valid
until someone remembers to rotate it; a client-credentials token is minted per run and expires
on its own. The engine handles both identically, so this is a choice about the credential's
lifetime, not about how the eval works.

### Method 1 — API key

Set one variable per declared server and run:

```bash
export MCP_ACME_API_KEY='<key>'
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag <suite>
```

The variable name is built from the server's own name — non-alphanumerics become underscores
and the whole thing uppercases, so the server `Acme-Feedback` reads
`MCP_ACME_FEEDBACK_API_KEY`. Server names are the keys in the plugin's `.mcp.json`.

There is **no variable that covers every server**, deliberately: a plugin can declare servers
from two vendors, and one shared key would hand each vendor the other's credential.

### Method 2 — OAuth client credentials

**Claude Code cannot perform this grant itself.** Its OAuth support is the authorization-code
flow with a browser callback — even the "pre-configured OAuth credentials" path
(`oauth.clientId`, `--client-secret`, `callbackPort`) ends at a browser login, which a headless
runner has no way to complete. So the exchange happens *before* the run: mint an access token
from the IdP, then hand it to the eval as the same `MCP_<SERVER>_API_KEY` variable.

```bash
# 1. Mint a short-lived token (client_id + client_secret → access token)
ACCESS_TOKEN=$(curl -sS -X POST "$TOKEN_ENDPOINT" \
  -d grant_type=client_credentials \
  -d client_id="$CLIENT_ID" \
  -d client_secret="$CLIENT_SECRET" \
  -d scope="$SCOPE" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# 2. Hand it to the run under the server's variable name
export MCP_ACME_API_KEY="$ACCESS_TOKEN"
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag <suite>
```

Three things to get right:

- **Mask the token if you are in CI.** Echoing it into `$GITHUB_ENV` without
  `echo "::add-mask::$ACCESS_TOKEN"` first puts it one careless `set -x` away from the build
  log. The client secret stays a repository secret; only the minted token moves.
- **Mint inside the job, never ahead of it.** A token minted at workflow-authoring time is a
  static key with extra steps.
- **Check the expiry against the run length.** A suite of 20 cases at `runs: 3` can outlive a
  5-minute token, and the failure arrives mid-run as "called 0×" on the later cases only — which
  reads exactly like a flaky skill. If the token is short-lived, narrow the suite or mint one
  per case batch.

## Interactive runs — the account connector

On your own machine there is a third option that needs no variable at all: connect the server
once in the claude.ai UI, log in with `claude`, and the run picks it up. Convenient, and fine
for local work.

**It cannot be carried into a headless run.** claude.ai connectors load only when the active
credential is an interactive claude.ai login — not under `CLAUDE_CODE_OAUTH_TOKEN`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`, a cloud provider, or an Anthropic
profile. Every credential a runner can hold is on that exclusion list. Do not promise a CI run
will work through a connector; move that server to method 1 or 2 first.

## What the engine actually does with the credential

Worth knowing before debugging: 100xeval never sees the secret's value.

It writes `"Authorization": "Bearer ${MCP_ACME_API_KEY}"` — the literal `${VAR}` reference — into
the MCP config it passes to `--strict-mcp-config`, and Claude Code expands it from the
environment at load time. So no token value lands in any file the tool writes, including run
folders and reports.

Consequences that follow from that, and surprise people:

- A config that already sets an `Authorization` header is passed through untouched. Your own
  `${VAR}` wins.
- A declared server with no key set is still included in the strict config — hiding it would
  change what the plugin under test receives — but goes without an `Authorization` header.
- Setting any server's key switches the whole run into strict mode, which ignores account
  connectors entirely. A half-configured run is therefore worse than none: the keyed server
  works, the unkeyed one silently stops resolving.

## When it goes wrong

**A bad, expired, missing, or misnamed key surfaces as `tool_used` "called 0×" — never as an
auth error.** The run completes, the model answers from nothing, and every instinct blames the
skill. Check the credential first. With per-server names, a name that does not match the server
is the most common version of this.

Preflight catches the connector case but not this one: the runner checks `claude mcp list` and
aborts when a declared server is not connected, but it cannot see through a key that is present
and wrong. Verify a suspect endpoint directly before spending a suite:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer $MCP_ACME_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"preflight","version":"1"}}}' \
  <the plugin's MCP url>
```

`200` means the credential reaches the server. `401`/`403` means fix the credential, not the
skill. One request costs nothing; a blocked endpoint costs the whole suite scoring zero.

If the MCP sits behind an IP allowlist, confirm the runner's egress is allowed before a long
run — that failure looks identical.
