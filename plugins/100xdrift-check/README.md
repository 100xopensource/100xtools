# 100xdrift-check — stop fixes from landing in only one copy

**For a repo that holds several plugins.** Teams usually end up with near-identical copies
of the same skill, command or agent — one per team, per customer, per product line. Those
copies are *siblings*. Fix a bug in one sibling, forget the other four, and the bug lives on
where nobody is looking.

100xdrift-check is the reviewer that notices. When a pull request edits a file it watches,
Claude reads the change, finds the sibling copies **elsewhere in the same repo**, and leaves
a comment saying which ones probably need the same fix — and which are different on purpose.

> **Wrong tool?** If you have one plugin and want to know whether it is any good, you want
> [100xeval](../100xeval/README.md) instead. This one only helps when copies exist to compare.

> **Draft.** Usable, and it does what this page describes — but it has not yet been run
> against a large multi-plugin repo under load. Treat early reports as advice to check, not
> as a verdict.

**It reports, and only reports.** Never edits a file, never enforces sameness, never blocks
a merge.

## Setup

Work in the repository you want checked. `bash` blocks go in your terminal; everything else
is typed **inside Claude Code**. Steps 1–2 are enough to run reviews yourself; 3–4 add the
automatic check on every pull request.

**1. Install the plugin**

Clone this repo somewhere alongside your own, then point at that clone:

```bash
git clone https://github.com/100xopensource/100xtools.git
claude plugin marketplace add ../100xtools
claude plugin install 100xdrift-check@100xtools
```

Adjust `../100xtools` if you cloned it elsewhere — any folder holding
`.claude-plugin/marketplace.json` works as a marketplace. Once this repo is public you can
skip the clone and use `claude plugin marketplace add 100xopensource/100xtools` instead.

If it says `Run /reload-plugins to activate.`, type `/reload-plugins`. Type `/` — you should
now see `100xdrift-check:install-skill` in the list.

**2. Add the reviewer to your repo**

```
/100xdrift-check:install-skill
```

Copies one folder in: `.claude/skills/drift-check/`. **Commit it and push** — that copy is
what everyone on the team, and the automatic check, actually runs.

Try it on a branch where you changed a plugin file:

```
/drift-check
```

You get `drift-report.md` and a summary in the chat. **Stop here if you only want reviews
you run yourself.**

**3. Turn on the automatic check**

```
/100xdrift-check:install-workflow
```

Adds `.github/workflows/drift-check.yml`. Commit and push.

**4. Let GitHub run Claude**

Run `claude setup-token` in your terminal and copy the token. On GitHub: your repo →
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Name it
exactly `CLAUDE_CODE_OAUTH_TOKEN`, paste, save. (Ask your admin if you cannot see Settings.)

Skip this and nothing breaks — the check posts a note saying it was skipped.

**Done.** Open a pull request that changes a plugin file. A comment appears within a few
minutes and updates itself on every push, so there is only ever one.

## What you get

A markdown file, `drift-report.md`, posted as a pull request comment. See a worked one:
[**an example drift report**](https://github.com/100xopensource/100xtools/blob/main/examples/plugin-drift-check/drift-report.md)
— one fix to a weekly-report plugin, three changed files, three different answers.

A **sibling** is a copy of the changed file in one of your *other* plugins. Each one gets a
**verdict**, and they often disagree with each other — that is normal:

| Verdict | Means | What you do |
| --- | --- | --- |
| `likely-applies` | The same bug or improvement is in that copy too | Consider porting the change |
| `different on purpose` | That copy varies for a good reason of its own | Ignore it, deliberately |
| `conflicts` | Your change contradicts a rule that copy depends on | Look before merging either |
| `unclear` | Not enough signal to call it | Read the two files yourself |

**Two sets of colours, measuring different things.** The headline grades the whole report:
🟢 nothing to do · 🟡 a human should decide · 🔴 a conflict, **or the check itself broke**.
The band on each section says what that one file asks of you: 🔴 `[!CAUTION]` means port it
in its own pull request, 🟡 `[!WARNING]` means nothing to port — read its first line. So a
yellow headline over a red section is normal, not a glitch.

## If something looks wrong

| What you see | What it means |
|---|---|
| `/100xdrift-check:...` is not offered | The plugin is not loaded — repeat step 1, then `/reload-plugins` |
| `/drift-check` is not offered | Step 2 has not run in this repository yet |
| No comment on the pull request | Nothing you changed is watched — check the `paths:` list in `.github/workflows/drift-check.yml` |
| Comment says the token is not configured | Step 4 is missing or the secret name is misspelled |
| A verdict looks wrong | Open the run on GitHub's **Actions** tab and download the saved files; they hold the full transcript |

## Two things to know

- **You choose which files it watches.** One list decides it — `paths:` in
  `.github/workflows/drift-check.yml`, commented inline. There is no config file. It ships
  watching every skill, command and agent; delete a line your repo does not use. If you
  edit it, change the `git diff -- '<pathspec>'` in the *Collect changed skill files* step
  to match, or the job runs and finds nothing.
- **One repository is the whole scope.** The change, the copies, and the comment all belong
  to the repo it runs in. Nothing is cloned or fetched, and there is no flag for it. A repo
  with one plugin gets a one-line "no siblings" report — that is a real answer.

## Good to know

- **Read-only by design.** Claude gets read-only tools plus `Write` for the report; the
  workflow can post a comment and nothing more. Treat `.github/workflows/drift-check.yml`
  and `.claude/skills/drift-check/SKILL.md` as trust-boundary files — anyone who can open a
  pull request can edit them, so review changes with author ≠ reviewer.
- **One Claude session per pull request** that touches a watched file, capped at 50 turns
  and 15 minutes, and at 15 changed files. Superseded runs are cancelled, so pushing five
  times costs roughly one review. Pull requests touching nothing watched cost nothing.
- **Skip a pull request** with the `skip-drift-check` label — useful for mass renames.
- **Choose the model** with a `DRIFT_CHECK_MODEL` repository variable. Unset means Sonnet.
- **Every run saves** the report and Claude's full transcript to the **Actions** tab for 7
  days. That transcript is where you look when a verdict seems wrong.
