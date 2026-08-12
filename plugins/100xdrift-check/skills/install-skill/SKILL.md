---
name: install-skill
description: Vendor the drift-check reviewer into the current repo at .claude/skills/drift-check/, so everyone working in the repo can run /drift-check without installing the plugin. Required before any review can run — the plugin ships the reviewer as a template, not as a loadable skill. Run once per repo, invoked explicitly as /100xdrift-check:install-skill. Do NOT use to run a drift review (that is /drift-check, after this), and do NOT use to set up CI (that is /100xdrift-check:install-workflow).
---

# Install the drift-check skill into this repo

Copy the reviewer skill template from this plugin into the user's repo. One directory,
then a report. Nothing else.

You run from the USER's repo, not from the plugin. The plugin's own files live at
`${CLAUDE_PLUGIN_ROOT}`; write into the repo root.

## What you create

| Path | Purpose |
|---|---|
| `.claude/skills/drift-check/` | The review skill, committed to the repo |

The plugin holds the reviewer under `templates/`, NOT under its own `skills/` — so Claude
never loads it from the plugin, and this copy is the only place it runs from. That is
deliberate: the reviewer is repo content. Committed, it reaches every collaborator and
every headless CI session with nothing installed, and the prompt CI runs is pinned to the
commit under review. The plugin itself exposes only the two installers.

## Steps

### 1. Check this is a git repo

```bash
git rev-parse --show-toplevel
```

If this fails, stop. Tell the user drift-check needs git to diff changed files, and that
they should run `git init` or move to a repo first. Do not create files.

### 2. Copy the skill

```bash
mkdir -p .claude/skills
cp -R "${CLAUDE_PLUGIN_ROOT}/templates/skills/drift-check" .claude/skills/drift-check
```

Copy the whole directory, not just `SKILL.md` — any `references/` must come along.

If `.claude/skills/drift-check/` already exists, diff it against the template, show what
differs, and ask whether to keep or replace. Default to keep: a repo that deliberately
edited its vendored copy must not have that silently reverted.

### 3. Verify and report

Confirm `.claude/skills/drift-check/SKILL.md` exists, then print exactly this:

```
✓ Added:  .claude/skills/drift-check/
          Nothing else in the repo was touched.

Next:
  1. Commit and push that folder — it is what shares the reviewer with your team
  2. Try it now: /drift-check   (on a branch where you changed a plugin file)
  3. Want it on every pull request? /100xdrift-check:install-workflow
```

If something failed, say which step and why.

## Notes

- Never overwrite without asking
- `/drift-check` only resolves once this copy exists — the plugin has no reviewer skill of
  its own to fall back on
- The copy goes stale when the plugin updates. Re-running this skill is the only refresh
- Once committed, `.claude/skills/drift-check/SKILL.md` is a trust-boundary file in that
  repo: it is the prompt CI runs, and anyone who can open a PR can edit it
