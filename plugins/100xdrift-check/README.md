# 100xdrift-check — keep sibling plugin files from silently diverging

**For a repo that holds several plugins.** If two of them carry copies of a skill,
command, agent or hook that share a shape — one per team, per tenant, or per product
line — a bug fixed in one copy stays broken in the others, and nobody notices until a
user hits it.

100xdrift-check is the reviewer that notices. When a PR edits a watched plugin file, a
headless Claude run reads the diff, finds the sibling copies **elsewhere in the same
repo**, and posts a non-blocking PR comment saying which siblings the change probably
applies to and which are legitimately different.

One repository is the whole scope: the diff, the siblings, and the PR comment all belong
to the repo the workflow runs in. Nothing is cloned or fetched, and no run — CI or local —
reads another repository. See [One repository, by design](#one-repository-by-design).

**What counts as a watched file is yours to set** — one `paths:` list in the workflow, see
[What gets reviewed](#what-gets-reviewed). It ships watching every skill, command and
agent.

**It reports. It never edits, never enforces parity, never blocks a merge.** Divergence
between siblings is usually deliberate — the point is to surface the cases where it isn't.

```
🟡 Skill drift check — Warning
Non-blocking. Nothing is broken, but findings below need a human decision.

_Scope: this repository._

### plugins/team-a/skills/report-run
| sibling plugin | sibling skill | verdict | why |
| --- | --- | --- | --- |
| plugins/team-b | report-run | likely-applies | same off-by-one in the week boundary |
| plugins/team-c | report-run | sibling-specific | team-c reports on fiscal weeks by design |
```

---

## What you need

- **A git repository holding more than one plugin.** Siblings are the copies in your
  *other* plugins, so with a single plugin there is nothing to compare and every report
  says so in one line.
- **Claude Code**, which you already have if you are reading this inside it.
- **Only if you want the automatic pull-request check:** GitHub Actions turned on, and
  permission to add a repository secret (step 4). Reviews you run yourself need neither.

Nothing to host, nothing to pay for beyond the Claude usage each review costs, no database,
no build step.

## Install

Five short steps, and you can stop after two if you only want to run reviews yourself.
Everything is typed **inside Claude Code** unless a block says `bash` — those go in your
terminal. You never have to edit a file by hand.

> **New to plugins?** A *plugin* adds new `/commands` to Claude Code. A *marketplace* is
> just a place plugins are listed — here, this GitHub repository. You add the marketplace
> once, then install from it.

### Step 1 — install the plugin

Open Claude Code in the repository you want checked, and type:

```
/plugin marketplace add 100xopensource/100xtools
/plugin install 100xdrift-check@100xtools
```

If Claude Code says `Run /reload-plugins to activate.`, type `/reload-plugins`.

**How to tell it worked:** type `/` and you should see `100xdrift-check:install-skill` and
`100xdrift-check:install-workflow` in the list.

<details>
<summary>Other ways to install</summary>

Already cloned this repository next to yours? Point at the folder instead — any folder
holding `.claude-plugin/marketplace.json` works as a marketplace:

```
/plugin marketplace add ../100xtools
/plugin install 100xdrift-check@100xtools
```

Just trying it out, without installing anything? Start Claude Code from a clone of this
repo like this — it lasts for that one session:

```bash
claude --plugin-dir plugins/100xdrift-check
```

Note there is no reviewer command yet at this point. The plugin ships only the two
installers; the reviewer arrives in step 2.
</details>

### Step 2 — add the reviewer to your repository

```
/100xdrift-check:install-skill
```

This copies one folder into your repository: `.claude/skills/drift-check/`. **Commit it**
like any other file, and push. That copy is what lets everyone on the team — and the
automatic check in step 3 — run the review. Without it there is nothing to run.

**Try it now.** On a branch where you changed a plugin file:

```
/drift-check
```

You get a file called `drift-report.md` and a short summary in the chat. Nothing else is
touched: the reviewer only reads and reports, and never edits your files.

Happy with reviews you run by hand? You can stop here.

### Step 3 — have it run automatically on every pull request

```
/100xdrift-check:install-workflow
```

This adds `.github/workflows/drift-check.yml` — the instructions GitHub follows on each
pull request. (It also does step 2 for you if you skipped it.) Commit and push both files.

### Step 4 — give GitHub permission to run Claude

Step 3 only takes effect once GitHub can talk to Claude on your behalf. One-time setup:

1. In your terminal, run `claude setup-token` and copy the token it prints.
2. On GitHub, open your repository → **Settings** → **Secrets and variables** →
   **Actions** → **New repository secret**.
3. Name it exactly `CLAUDE_CODE_OAUTH_TOKEN`, paste the token, save.

Ask your admin if you cannot see Settings. An organisation-wide secret with the same name
also works and saves doing this per repository.

**If you skip this**, nothing breaks: the check still runs and simply posts a note saying
it was skipped. It never blocks anyone's work.

### Step 5 — see it work

Open a pull request that changes a plugin file. Within a few minutes a comment appears,
headed 🟢, 🟡 or 🔴. It updates itself each time you push, so there is only ever one.

🟢 means nothing to do. 🟡 and 🔴 are worth a read — they never stop you merging.

### If something looks wrong

| What you see | What it means |
|---|---|
| `/100xdrift-check:...` is not offered | The plugin is not loaded — repeat step 1, then `/reload-plugins` |
| `/drift-check` is not offered | Step 2 has not run in this repository yet |
| No comment on the pull request | Nothing you changed is watched — see [What gets reviewed](#what-gets-reviewed) |
| Comment says the token is not configured | Step 4 is missing or the secret name is misspelled |
| A verdict looks wrong | Open the run on GitHub's **Actions** tab and download the artifact; it holds the full transcript |

### Optional — choose the model

CI reads a repository *variable* named `DRIFT_CHECK_MODEL` (Settings → Secrets and
variables → Actions → **Variables**). Leave it unset to use Sonnet. A variable rather than
a workflow edit, so retuning it needs no pull request against a trust-boundary file.

### Doing it by hand

If you would rather not run the setup skills, copy the same two things yourself:

```bash
mkdir -p .github/workflows .claude/skills
cp plugins/100xdrift-check/templates/workflows/drift-check.yml .github/workflows/drift-check.yml
cp -R plugins/100xdrift-check/templates/skills/drift-check .claude/skills/drift-check
```

Changing the workflow's `paths:` filter means changing the `git diff -- '<pathspec>'` in
the *Collect changed skill files* step to match — if they disagree, the job runs and
finds nothing.

## What gets reviewed

A plugin is more than its skills. Commands, agents, hooks, MCP wiring and manifests get
copied between plugins too, and drift exactly the same way — a fix to one plugin's
`commands/deploy.md` leaves the other three stale, silently.

drift-check has no opinion about which of those you care about. **One list decides:
`paths:` in `.github/workflows/drift-check.yml`.** It is the only scope knob — there is no
config file, and the reviewer skill reads that list instead of assuming what a
"reviewable" file is. It ships as:

```yaml
paths:
  - "**/SKILL.md"
  - "**/commands/**"                 # slash commands
  - "**/agents/**"                   # subagent definitions
```

The three prompt surfaces — the files that are literally instructions to a model, where
"this copy has the same bug" is a claim the reviewer can actually judge. Delete a line
your repo does not use.

The template carries the rest commented out. These are config and code rather than
prompts, so they are opt-in — uncomment what your plugins actually contain:

```yaml
  - "**/skills/**/references/**"     # content a SKILL.md points at
  - "**/hooks/**"                    # hook scripts and config
  - "**/.mcp.json"                   # MCP server wiring
  - "**/.claude-plugin/plugin.json"  # manifests
```

Two rules when you edit it:

1. **Mirror it in the diff.** The *Collect changed skill files* step runs
   `git diff ... -- '<pathspec>'` and must list the same globs. `paths:` decides which PRs
   start a run; the pathspec decides which files reach the reviewer. Disagree and the job
   runs, finds nothing, and posts a green-looking "no files changed" note.
2. **Widen deliberately.** Each glob added means more PRs spend a Claude session, and more
   files competing for the 15-file cap. Watch what you copy between plugins; leave the
   rest out. Trimming is just as valid — a repo with no commands should drop that line.

Reviewing non-prompt files works but shifts what a verdict means — for `hooks/` or
`plugin.json` the reviewer is comparing config and code, where "the same fix applies" is a
weaker claim than it is for two copies of a prompt. Treat those verdicts as pointers.

## One repository, by design

The diff is this repo's; the siblings are this repo's other plugins; the comment lands on
this repo's PR. drift-check never diffs repo A against repo B, never reads outside the
repo root, and never clones or fetches. There is no flag for it.

That is a deliberate ceiling, not a missing feature. Reviewing across repos would mean
checking out each one in CI and pinning its refs, and a comparison against whatever
happened to be on disk is worse than no comparison — it reads as authoritative and isn't.
If you want copies compared, put the plugins in one repo.

A repo with one plugin gets a one-line "no siblings" report. That is a real answer. Every
report states its scope on the second line, so nobody mistakes it for a wider check.

## Using it

Locally, on a branch with plugin changes:

```
/drift-check
```

It works out by itself which of your changes are new compared with `main`, writes
`drift-report.md`, and summarises the verdicts in the reply. To compare against something
other than `main`, pass a commit: `/drift-check abc1234`. This is the fastest way to see what CI will say before you push — same
prompt, same scope, same file. It resolves only after step 2; there is no plugin-side
reviewer.

In CI it runs by itself on every PR touching a watched file and posts one sticky comment,
updated in place on every push.

**Status headline.** The report's first line is a status marker the workflow turns into
an icon:

| | When |
| --- | --- |
| 🟢 Good | Every sibling is legitimately different, or the changed files have no siblings |
| 🟡 Warning | Something is `likely-applies` or `unclear` — a human decides |
| 🔴 Critical | A verdict is `conflicts`, **or the check itself broke** |

Critical covering both "found a conflict" and "the check is broken" is deliberate: a
silently broken advisory reads as a clean bill of health, which is worse than no check.

**Opt out per PR** with the `skip-drift-check` label. Adding or removing it re-runs the job
immediately and replaces the comment, so a stale advisory never sits on a PR that opted
out. Use it for mass renames and formatting sweeps.

**Bulk changes are capped at 15 changed files.** Past that the job posts a note instead of
judging 200 pairs badly. For a big refactor, run the pass locally. Watching more paths
makes this cap easier to hit.

**Artifacts.** Each run uploads `drift-report.md`, `changed-skill-files.txt`, and Claude's
full execution transcript — every message, tool call and result — as
`drift-check-pr<N>-run<N>`, kept 7 days. That transcript is where you look when a verdict
seems wrong. Note that artifacts are visible to anyone with read access to the repo.

## Tuning it

There is no config file — each knob lives where it takes effect:

| Want | Change |
|---|---|
| Which files trigger and get reviewed | The workflow's `paths:` filter **and** the `git diff -- '<pathspec>'` in *Collect changed skill files* — together. The only scope knob; see [What gets reviewed](#what-gets-reviewed) |
| Which model judges | The `DRIFT_CHECK_MODEL` Actions variable |
| Where siblings are looked for | Nothing to set — this repository's other plugins, always. See [One repository, by design](#one-repository-by-design) |

## Cost

One Claude session per PR that touches a watched file, capped at 50 turns and 15 minutes.
Concurrency is set to cancel superseded runs, so a PR pushed five times costs roughly one
review, not five. PRs that touch nothing watched cost nothing — the `paths:` filter means
the job never starts, which is also why widening it is a cost decision.

## Security model

The review reads contributor-authored content — skills, commands and agents are literally
prompts — so a malicious file could try to instruct the model. The mitigation is
structural rather than instructional:

- Claude gets **read-only tools** plus `Write` (for the report). No `Edit`, no `WebFetch`,
  no `WebSearch`, no git write.
- The workflow's `permissions:` are `contents: read` and `pull-requests: write` — enough
  to post one comment, not enough to change code.
- The sticky comment is posted by a separate `github-script` step, not by Claude.
- Nothing merges, blocks, or commits based on the result.

The tool allowlist lives in the workflow, not in the skill: permissions belong to the
caller. Treat both `drift-check.yml` and `SKILL.md` as trust-boundary files and review
changes to them with author ≠ reviewer — including the vendored
`.claude/skills/drift-check/SKILL.md` in your own repo, which is the prompt CI actually
runs and is editable by anyone who can open a PR.

## Layout

```
.claude-plugin/plugin.json                    manifest
skills/install-skill/SKILL.md                 vendors the reviewer to .claude/skills/ in your repo
skills/install-workflow/SKILL.md              installs the CI workflow (and the reviewer, if missing)
templates/skills/drift-check/SKILL.md         the review contract — one prompt, shared by CI and local runs
templates/workflows/drift-check.yml           the CI job, and the paths: list that defines scope
```

`skills/` holds only the two installers — those are what Claude loads from the plugin.
Everything under `templates/` is copied into your repo at the mirrored path
(`templates/skills/…` → `.claude/skills/…`, `templates/workflows/…` →
`.github/workflows/…`) and runs from there, never from the plugin.
