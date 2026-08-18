# 100xeval — keep plugins working as they change

**Testcases for Claude Code plugins.** You save the questions your plugin must get right, run
them, and find out when an edit breaks one. That is how a plugin's quality survives months of
changes and more than one person editing it.

A plugin is a folder of written instructions. Nothing checks instructions — no compiler, no
test that goes red. A reworded sentence that quietly stops the plugin filtering by team looks
exactly like a change that broke nothing. Testcases are how you tell the difference.

**The loop:**

1. **Write a case** — the question a user really asks, and what a correct answer must do.
2. **Run it** — the plugin executes for real, with its data connection attached.
3. **Grade it** — did it query the right data, present it properly, get the numbers right?
4. **Keep it** — every bug a user reports becomes a case, so a fixed bug stays fixed.

The corpus is the asset. A case you wrote a year ago is what stops today's edit from
reintroducing last year's bug.

| | What it does | Cost | Needs |
| --- | --- | --- | --- |
| **Test run** | Runs your plugin on saved cases and grades the answers | **~$1–2 per run** | [Claude Code CLI](https://code.claude.com/docs/en/quickstart) |
| **Static check** | A quick run-free pass over the plugin's files | **Free** | Just Python |

The **static check** is a cheap extra, not a substitute: it reads the files and reports
problems visible without executing anything. Useful on every commit, but it cannot tell you
whether the plugin still answers correctly. Only a case does that.

Everything ships in one folder — the skill Claude talks to and the Python engine underneath.
**Python 3.11+, standard library only:** no `pip install`, no virtualenv, no lockfile.

---

## What you need

| | Needs |
| --- | --- |
| **Static check** | Python 3.11+ — check with `python3 --version`. Nothing else: no key, no internet, no account |
| **Test runs** | That, plus the [Claude Code CLI](https://code.claude.com/docs/en/quickstart) on your `PATH` |

The runner executes your plugin by shelling out to `claude`, so the CLI has to be installed
and working. On an old Python the tool says so plainly rather than showing a traceback.

**Only if you want the automatic pull-request check:** GitHub Actions turned on, and permission
to add a repository secret — see
[Run it automatically on every pull request](#run-it-automatically-on-every-pull-request). Runs
you do yourself need neither.

---

## Get started

Install once, then ask Claude for what you want in plain words — you never type an engine
command.

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

**3. Open Claude and ask.** Start Claude Code, or open the Claude desktop app, in the folder
your plugin lives in. From here you only type plain English — copy any line below.

**Start here — free, instant, changes nothing:**

> *"static-check my plugin"*

It only reads files. Nothing is edited, uploaded, or sent over the network, and it costs
nothing. Then, once you have a result:

> *"explain that score in plain english"*
> *"what should I fix first?"*
> *"is that finding a real problem, or a false alarm?"*

**Building up testcases** — the part that keeps the plugin working over time:

> *"what should I be testing in this plugin?"*
> *"add a testcase for askusage"*
> *"turn this bug report into a testcase: <paste the report>"*
> *"show me the testcases we already have"*

**Running them** — this is the part that costs money, so ask the price first:

> *"how much would it cost to run these testcases?"*
> *"run the evals for asktickets, just once"*
> *"did my change break anything?"*
> *"why did that case fail?"*

**If you get stuck**, ask Claude that too — it has the tool's own documentation:

> *"I don't understand this result, walk me through it"*
> *"what does token_efficiency mean?"*

You never have to learn a command or a flag.

---

## Run it automatically on every pull request

Asking Claude covers you while you are working. A check on every pull request covers the case
nobody is watching: someone reworded a skill on a Friday and nobody noticed until a user did.

Three short steps, and **you can stop after the first** if you only want the free check. This
is the one part of the tool where you add a file rather than ask in plain words — or ask Claude
to add it for you: *"add the plugin-evals workflow from the README"*.

**Two jobs, because the two layers cost different amounts.** The static check is free and needs
no credentials, so it runs on every pull request, including ones from forks. Cases cost roughly
$1–2 a run, so they get a credential and a guard.

### Step 1 — add the workflow

Save this as `.github/workflows/plugin-evals.yml`, commit it, and push:

```yaml
name: plugin-evals

on:
  pull_request:

permissions:
  contents: read

# A run costs money, so don't leave three of them racing after three quick pushes.
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

      # Pin the engine. An eval tool that silently changes what it scores is worse than
      # no eval tool: the number moves and the diff doesn't explain it.
      #
      # `vendor/` is not cosmetic. With no --target the static check walks the whole repo for
      # plugins, and it skips `vendor/` by design — third-party code is not yours to score.
      # Check this out anywhere else and your scorecard grows two plugins you don't own.
      - uses: actions/checkout@v5
        with:
          repository: 100xopensource/100xtools
          path: vendor/100xtools
          ref: main            # replace with a tag or commit SHA

      - name: Static design quality
        run: |
          python3 vendor/100xtools/plugins/100xeval/skills/100xeval/scripts/run.py \
            eval --static-only --report static.md
          { echo '## Static design quality'; echo; cat static.md; } >> "$GITHUB_STEP_SUMMARY"

  cases:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    # On a public repo GitHub withholds secrets from fork pull requests. Without this guard
    # the job runs credential-less and scores zero for a reason that has nothing to do with
    # the plugin — the worst kind of red build.
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
          ref: main            # replace with a tag or commit SHA

      # Without a token the paid run cannot work, so say so and stop rather than failing red.
      # Step 2 is what turns this on.
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

      # The runner executes your plugin by shelling out to `claude`, so the CLI has to exist.
      - name: Install Claude Code CLI
        if: steps.creds.outputs.ok == 'true'
        run: |
          curl -fsSL https://claude.ai/install.sh | bash
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Run cases
        if: steps.creds.outputs.ok == 'true'
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          # One line per MCP server the plugin declares, named after that server.
          # Delete if it declares none.
          MCP_ACME_API_KEY: ${{ secrets.MCP_ACME_API_KEY }}
        run: |
          python3 vendor/100xtools/plugins/100xeval/skills/100xeval/scripts/run.py \
            eval --tag pr --threshold 0.8 --report evals.md --json evals.json
          { echo '## Plugin evals'; echo; cat evals.md; } >> "$GITHUB_STEP_SUMMARY"

      # Keep the evidence even when the gate fails — that is the run you actually want to read.
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: eval-run
          path: evals.json
          if-no-files-found: ignore     # nothing to upload when the run was skipped
```

Both jobs write their scorecard to the run summary, so you read the result on the **Actions**
tab without downloading anything.

**How to tell it worked:** open a pull request that changes anything, and two jobs appear on
it — `static` with a score, and `cases` reporting it was skipped until you finish step 2.

**`pull_request` workflows run from your default branch**, so the check is not live until this
file is merged there. That is normal for GitHub, not something this tool does.

Happy with the free check alone? You can stop here.

### Step 2 — give GitHub permission to run Claude

Behavioral runs need two secrets, and they authenticate different things. One will not do the
other's job:

| Secret | Authenticates | Where it comes from |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | The **model** — the run itself | `claude setup-token` in your terminal. Valid one year |
| `MCP_<SERVER>_API_KEY` | **One MCP server** — its data access | Your MCP provider. One per server the plugin declares; skip if it declares none |

1. In your terminal, run `claude setup-token` and copy the token it prints. It is shown once
   and saved nowhere, so paste it straight into the next step.
2. On GitHub, open your repository → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**.
3. Name it exactly `CLAUDE_CODE_OAUTH_TOKEN`, paste, save. Then add one key per MCP server the
   plugin declares, if any.

**The MCP secret's name is built from the server's name**, uppercased with non-letters turned
into underscores: a server called `Acme` is `MCP_ACME_API_KEY`, and `Acme-Feedback` is
`MCP_ACME_FEEDBACK_API_KEY`. The server names are the keys in the plugin's `.mcp.json`.

**Its value can be a plain API key or a short-lived OAuth token.** If your MCP server sits
behind an identity provider that issues machine tokens, mint one per run with the
client-credentials grant instead of storing a static key — same variable, credential that
expires by itself. The recipe, and the masking line that keeps a minted token out of the build
log, are in [`mcp-auth.md`](./skills/100xeval/references/mcp-auth.md).

There is **no single key covering every server**, on purpose: a plugin can declare servers from
two different vendors, and one shared key would hand each vendor the other's credential. A
server you set no key for still runs, just unauthenticated — which shows up as "called 0×",
not as an error.

Ask your admin if you cannot see Settings. An organisation-wide secret of the same name also
works and saves doing this per repository.

Two traps worth knowing before you spend anything:

- **A `setup-token` token cannot carry your claude.ai connectors.** It can only make model
  requests. If the plugin's data access comes from a connector you added in the claude.ai UI,
  that works on your laptop and **cannot** work in CI — you need `MCP_<SERVER>_API_KEY` and the
  plugin's own MCP config instead. See [MCP auth](../../docs/100xeval/mcp-auth.md).
- **The token belongs to whoever ran `claude setup-token`.** Mint it from a bot account with
  its own seat, or the check breaks the day that person rotates their credentials or leaves.

**Before the first paid run, dry-run the suite locally.** `--dry-run` resolves every case and
its plugins, prints what it would execute, and spends nothing. A typo in a plugin path costs
you a build either way — better the free one.

### Step 3 — see it work

Open a pull request that changes a plugin file. Both jobs run; the scorecards appear in the run
summary on the **Actions** tab, and the JSON is attached as an artifact.

The runner's exit code is the gate, so no extra step decides pass or fail:

| Exit | Means |
| --- | --- |
| `0` | Everything at or above the threshold |
| `1` | A case scored below the threshold — a real regression, or a flaky case |
| `2` | Engine error: a case that will not parse, a missing plugin path, a bad `--target` |

**`2` is the one to look at first.** It means nothing was evaluated. A green-looking suite that
never ran is the failure this tool exists to prevent, so a load error fails the build rather
than passing quietly.

### If something looks wrong

| What you see | What it means |
|---|---|
| `no plugins found under …` | The static check found no `.claude-plugin/plugin.json` — point it at one with `--target <dir>` |
| Your scorecard lists plugins you don't own | The engine checkout is not under `vendor/` — see the comment in the workflow |
| `cases` says it was skipped | Step 2 is missing, or the secret name is misspelled |
| A grader says a tool was "called 0×" | Usually a missing, bad, or expired `MCP_<SERVER>_API_KEY`, not a broken skill. Check the key and its spelling first |
| `cases` never runs on a contributor's PR | Expected on a public repo: GitHub withholds secrets from fork pull requests, and the job skips rather than scoring zero |
| Exit `2` with nothing scored | A case failed to load. The report names the file |

### Choosing what runs on each pull request

Three knobs, each worth setting deliberately rather than inheriting:

- **`--tag pr`** runs only cases tagged `pr` in their `case.yaml`. Tag a fast, cheap subset for
  pull requests and keep the long suite for a nightly `schedule:` trigger. Drop the flag to run
  everything.
- **`--threshold 0.8`** is the pass bar per case. The default is `1.0`, so one bad run in a
  repeated case fails the build. Start at `0.8` and tighten once you know how much your cases
  wobble.
- **`runs:` in each case** repeats it and scores `passed/runs`. More runs cost more and flake
  less. `1` is fine for a smoke case; use `3` or more for anything you gate on.

### Cost

The `static` job is free — Python only, no model call, so it costs nothing beyond Actions
minutes. The `cases` job spends roughly $1–2 per run, which is why `concurrency` cancels
superseded runs: a pull request pushed five times costs about one suite, not five. Narrowing
`--tag` is the other lever.

---

## Documentation

Concepts and how-to live in the [`docs/100xeval`](../../docs/100xeval/index.md) bundle:

| | |
| --- | --- |
| [Eval case](../../docs/100xeval/eval-case.md) | What a case is, what one looks like, and how to create one |
| [Grader](../../docs/100xeval/grader.md) | The four types, one claim each, and the assertion that cannot fail |
| [Run folder](../../docs/100xeval/run-folder.md) | Cost, `--dry-run`, exit codes, and the evidence a run writes |
| [MCP auth](../../docs/100xeval/mcp-auth.md) | Two auth paths, and the failure that looks like nothing |
| [Design score](../../docs/100xeval/design-score.md) | Running the static check, reading it, and where it is wrong |
| [Troubleshooting](../../docs/100xeval/troubleshooting.md) | What each failure means |
| [Internals](../../docs/100xeval/internals.md) | Layout, and the engine's own test suite |

Shipped inside the plugin, for writing cases in depth:
[`case-schema.md`](./skills/100xeval/references/case-schema.md) ·
[`managing-testcases.md`](./skills/100xeval/references/managing-testcases.md) ·
[`ci-setup.md`](./skills/100xeval/references/ci-setup.md) ·
[`mcp-auth.md`](./skills/100xeval/references/mcp-auth.md)

Two worked examples live in
[`examples/plugin-eval/`](../../examples/plugin-eval/README.md).
