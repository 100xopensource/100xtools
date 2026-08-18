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
| **OAuth client credentials** | The server sits behind an IdP that issues machine tokens | Minutes to hours; minted per run by the runner |

**Prefer client credentials where the server supports it.** A static key in a CI secret is valid
until someone remembers to rotate it; a client-credentials token is minted per run and expires
on its own. Both are the same amount of setup — four variables instead of one — and the run
behaves identically either way.

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

**The runner mints the token itself.** Declare the credentials and it performs the exchange
before the run — no pre-step, no minting shell in your workflow, nothing to keep in sync:

```bash
export MCP_ACME_CLIENT_ID='<client-id>'
export MCP_ACME_CLIENT_SECRET='<client-secret>'
export MCP_ACME_TOKEN_URL='https://idp.example.com/oauth2/token'
export MCP_ACME_SCOPE='mcp:read'          # optional; omitted if unset
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --tag <suite>
```

Same `MCP_<SERVER>_…` naming as the static key, so `Acme-Feedback` reads
`MCP_ACME_FEEDBACK_CLIENT_ID` and so on. In CI these are four repository secrets and no extra
workflow steps.

What the runner does with them:

- **One exchange per process**, cached and shared. A suite at `runs: 3` with three graders hits
  the token endpoint once, not once per subprocess.
- **The token goes into the child process's environment**, never into the MCP config on disk.
  The config still holds `"Authorization": "Bearer ${MCP_ACME_API_KEY}"`, and Claude Code
  expands it there. Neither the client secret nor the minted token reaches any file the run
  writes, including the run folder you upload as a CI artifact.
- **The agentic judge gets the same token.** A ground-truth grader queries the MCP itself, so
  authenticating the run and not the judge would fail exactly the grader that checks the
  numbers.

**`MCP_<SERVER>_API_KEY` wins if both are set.** An explicitly supplied key is deterministic
and needs no network call, so it is not second-guessed — unset it to use the OAuth path.

Failures stop the run rather than degrading it, because an unauthenticated run reports
"called 0×" and reads as a broken skill:

| What you did | What you get |
| --- | --- |
| Set `CLIENT_ID` but not `CLIENT_SECRET` | Abort naming every missing variable |
| An `http://` token URL | Abort — a client secret in cleartext is a disclosed secret |
| Wrong credentials | Abort with the HTTP status. **The response body is withheld** — an error body can contain a token |
| Endpoint unreachable | Abort naming the error class, so you can tell DNS from a firewall |
| A response with no `access_token` | Abort listing the keys that did come back |
| A token expiring in under 5 minutes | A warning, not an abort. Recovering mid-suite is out of scope, so this is the one chance to notice before the later cases fail as "called 0×" |

**What Claude Code still cannot do**, so you don't go looking for it: its own OAuth support is
the authorization-code flow with a browser callback, including the "pre-configured OAuth
credentials" path (`oauth.clientId`, `--client-secret`, `callbackPort`). That needs a human at a
browser. This method works because 100xeval performs the grant and hands the result over as a
bearer credential — not because Claude Code gained a headless OAuth mode.

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
