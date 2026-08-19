# CI setup — run evals on every pull request

Use this when someone asks to run evals automatically, gate a merge on them, or "set up CI for
the evals". The user-facing walkthrough of the same setup is in the plugin README; this page is
what to do when *you* are wiring it up.

**Getting the plugin's MCP credential is a separate question — see `mcp-auth.md`.** This page
assumes you know which `MCP_<SERVER>_API_KEY` values the run needs; that one covers where they
come from, the API-key and OAuth-client-credentials options, and why the claude.ai account
connector is not a supported path anywhere.

**Two jobs, because the layers cost differently.** The static check is free, needs no
credentials, and can run on every pull request including forks. Behavioral cases cost roughly
$1–2 a run, need a token, and must be guarded.

## Decide four things before writing the file

Ask only what you cannot read off the repository. Each answer changes the file:

| Decide | How to settle it |
| --- | --- |
| Which cases run per PR | Read the `tags` in existing `case.yaml` files. If there is no cheap subset, propose adding a `pr` tag rather than running the whole suite on every push |
| Whether behavioral runs at all | If no `evals/**/case.yaml` exists yet, write the static job only. A `cases` job with no cases is a red build with nothing to fix |
| Whether the plugin needs MCP, and which credential shape | Look for `.mcp.json` in the plugin, or `mcp_config` in a case. Its server names decide the variable names. Ask which the server issues: a static key (`MCP_<SERVER>_API_KEY`) or client credentials (four vars). No MCP means neither |
| The threshold | Default `1.0` fails on one bad run of a repeated case. `0.8` is the sane starting gate; say which you chose and why |

## The file

`.github/workflows/plugin-evals.yml`. Same content as the README's copy — keep the two in step
if you change one.

```yaml
name: plugin-evals

on:
  pull_request:

permissions:
  contents: read

concurrency:
  group: plugin-evals-${{ github.ref }}
  cancel-in-progress: true

jobs:
  static:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - uses: actions/checkout@v5
        with:
          repository: 100xopensource/100xtools
          path: vendor/100xtools
          ref: main            # pin to a tag or SHA
      - name: Static design quality
        run: |
          python3 vendor/100xtools/plugins/100xeval/skills/100xeval/scripts/run.py \
            eval --static-only --report static.md
          { echo '## Static design quality'; echo; cat static.md; } >> "$GITHUB_STEP_SUMMARY"

  cases:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    if: github.event.pull_request.head.repo.full_name == github.repository
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - uses: actions/checkout@v5
        with:
          repository: 100xopensource/100xtools
          path: vendor/100xtools
          ref: main            # pin to a tag or SHA
      - name: Check for a token
        id: creds
        env:
          TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: |
          if [ -z "$TOKEN" ]; then
            echo 'No CLAUDE_CODE_OAUTH_TOKEN set — skipped the paid run.' >> "$GITHUB_STEP_SUMMARY"
            echo "ok=false" >> "$GITHUB_OUTPUT"
          else
            echo "ok=true" >> "$GITHUB_OUTPUT"
          fi
      - name: Install Claude Code CLI
        if: steps.creds.outputs.ok == 'true'
        run: |
          curl -fsSL https://claude.ai/install.sh | bash
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"
      - name: Run cases
        if: steps.creds.outputs.ok == 'true'
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          MCP_ACME_API_KEY: ${{ secrets.MCP_ACME_API_KEY }}   # one per declared server
        run: |
          python3 vendor/100xtools/plugins/100xeval/skills/100xeval/scripts/run.py \
            eval --tag pr --threshold 0.8 --report evals.md --json evals.json
          { echo '## Plugin evals'; echo; cat evals.md; } >> "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: eval-run
          path: evals.json
          if-no-files-found: ignore
```

## Four things in that file that are load-bearing

Do not "tidy" any of these — each is there because the obvious alternative is wrong.

1. **The engine checkout goes under `vendor/`.** With no `--target`, `--static-only` walks from
   the repo root and discovers every directory holding `.claude-plugin/plugin.json`. It skips
   `vendor`, `runs`, `.runs`, `.git`, `node_modules`, `__pycache__` — and nothing else, so a
   checkout at `.100xtools` or `tools/100xtools` *is* discovered and the user's scorecard grows
   two plugins they do not own. `vendor/` is the documented skip: third-party code is not theirs
   to score.
2. **`ref:` should be a tag or SHA, not `main`.** The example says `main` for readability. An
   eval engine that silently changes what it scores makes a score move with no diff to explain
   it. Say this when you write the file.
3. **The fork guard on `cases`.** A public repo withholds secrets from fork pull requests, so an
   unguarded job runs credential-less and every `tool_used` grader reports "called 0×" — red for
   a reason unrelated to the plugin. Skipping is the honest outcome.
4. **The token check before the CLI install.** It makes the secret optional: a repo that has the
   workflow but no token gets a summary note instead of a failing build, so the free static gate
   is usable on its own.

## Secrets — tell the user to do this part

Two kinds, authenticating different things. One will not do the other's job:

| Secret | Authenticates | Source |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | The model — the run itself | `claude setup-token`, valid one year |
| `MCP_<SERVER>_API_KEY` | One MCP server — its data access | One per server in the plugin's `.mcp.json`. **See `mcp-auth.md`** |
| `MCP_<SERVER>_CLIENT_ID` + `_CLIENT_SECRET` | The same server, via OAuth client credentials | Their IdP. Use **instead of** the API key when the server issues machine tokens — the runner mints the token and discovers the endpoint itself. `_TOKEN_URL` / `_AUTH_STYLE` / `_SCOPE` are optional; see `mcp-auth.md` |

Added under **Settings → Secrets and variables → Actions → New repository secret**, with the
name spelled exactly as above.

**Never write either value into a file, a case, or a workflow.** Both are read from the
environment at run time. If a user pastes a token into the conversation, use it for that run
only and tell them to add it as a secret instead.

**A `setup-token` token only makes model requests — it carries no MCP access.** MCP is a
separate credential per server, and the claude.ai account connector is not a path here or
locally. Settle the MCP credential with `mcp-auth.md` before promising a CI run will work.

**If the server issues short-lived tokens** rather than static keys, set `_CLIENT_ID` and
`_CLIENT_SECRET` instead of the API key. The workflow needs no mint step and no `::add-mask::`
line: the exchange happens inside the engine, so the token never passes through the shell and is
never written to the config or the run folder. See `mcp-auth.md`.

## Verify before declaring it done

- `--dry-run` the selection the workflow uses. It resolves every case and its plugins and spends
  nothing, so a bad `--tag` or plugin path surfaces free rather than as a failed build.
- Confirm the tag actually selects cases: a `--tag` matching nothing runs zero cases and exits
  `0`. A gate that passes because it evaluated nothing is the failure mode this tool exists to
  catch, so check the case count in the report, not just the exit code.
- Say plainly that `pull_request` workflows only take effect once merged to the default branch.

## Failure modes

| Symptom | Cause |
| --- | --- |
| Scorecard lists plugins the user does not own | Engine checked out somewhere other than `vendor/` |
| `no plugins found under …` | No `.claude-plugin/plugin.json` beneath the walk root; pass `--target` |
| `cases` reports it was skipped | No `CLAUDE_CODE_OAUTH_TOKEN`, or the name is misspelled |
| `cases` never runs on a contributor's PR | Fork pull request on a public repo; expected |
| `tool_used` "called 0×" | A missing, bad, or expired `MCP_<SERVER>_API_KEY` — including a name that does not match the server. Check the key before the skill |
| Exit `2` | Engine error — a case that will not parse, a missing plugin path. Nothing was evaluated |
| Green build, zero cases run | `--tag` matches no case |

Exit codes: `0` at or above threshold, `1` a case below it, `2` engine error.
