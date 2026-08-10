# drift-check — keep sibling skills from silently diverging

If you maintain several Claude Code plugins that share a shape — one per team, per tenant,
or per product line — you end up with the same skill written five times. A bug fixed in
one copy stays broken in the other four, and nobody notices until a user hits it.

drift-check is the reviewer that notices. When a PR edits a skill in plugin A, a headless
Claude run reads the diff, finds the sibling skills in your other plugins, and posts a
non-blocking PR comment saying which siblings the change probably applies to and which are
legitimately different.

**It reports. It never edits, never enforces parity, never blocks a merge.** Divergence
between siblings is usually deliberate — the point is to surface the cases where it isn't.

```
🟡 Cross-plugin drift check — Warning
Non-blocking. Nothing is broken, but findings below need a human decision.

### plugins/team-a/skills/report-run
| sibling plugin | sibling skill | verdict | why |
| --- | --- | --- | --- |
| team-b | report-run | likely-applies | same off-by-one in the week boundary |
| team-c | report-run | plugin-specific | team-c reports on fiscal weeks by design |
```

---

## Requirements

- A repo with **more than one plugin**, each with its own `skills/` directory. With a
  single plugin there are no siblings and every report will say so.
- A Claude Code auth secret in the repo: `CLAUDE_CODE_OAUTH_TOKEN` (from
  `claude setup-token`) or an organization `ANTHROPIC_API_KEY`.
- GitHub Actions enabled. Nothing else — no server, no database, no self-hosted runner.

## Install

### Option A — install the plugin (for local review runs)

From a marketplace that lists this repo:

```
/plugin marketplace add 100xopensource/100xtools
/plugin install drift-check
```

Or point Claude Code at a clone:

```bash
claude --plugin-dir plugins/drift-check
```

Then, on a branch with skill changes:

```
/drift-check
```

It computes the merge base itself, writes `drift-report.md`, and summarizes the verdicts
in the reply. This is the fastest way to see what CI will say before you push.

### Option B — install the GitHub Action (for every PR)

1. **Copy the workflow** into your repo:

   ```bash
   mkdir -p .github/workflows
   cp plugins/drift-check/workflows/drift-check.yml .github/workflows/drift-check.yml
   ```

2. **Adjust the paths filter** to match your layout. The default assumes
   `plugins/<name>/skills/<skill>/SKILL.md`:

   ```yaml
   on:
     pull_request:
       paths:
         - "plugins/**/skills/**"
   ```

   Change it in two places — the `paths:` filter (which decides whether the job runs at
   all) and the `git diff -- '<pathspec>'` in the *Collect changed skill files* step (which
   decides what gets reviewed). If they disagree, the job runs and finds nothing.

3. **Make the skill reachable from CI.** The workflow invokes `/drift-check`, so the skill
   must resolve in the checked-out repo. Either vendor it:

   ```bash
   mkdir -p .claude/skills
   cp -R plugins/drift-check/skills/drift-check .claude/skills/drift-check
   ```

   or add a marketplace + plugin install step to the workflow before the Claude step.
   Vendoring is simpler and pins the review contract to the commit being reviewed, which
   is what you want for a check that gates review.

4. **Add the secret**: repo → Settings → Secrets and variables → Actions →
   `CLAUDE_CODE_OAUTH_TOKEN`. Without it the job still runs and posts a note explaining
   that it was skipped — it never fails the PR.

5. **Optional: pin the model** with an Actions *variable* named `DRIFT_CHECK_MODEL`
   (Settings → Secrets and variables → Actions → Variables). Defaults to Sonnet. A
   variable rather than a workflow edit, so retuning it doesn't need a PR to a
   trust-boundary file.

Open a PR that touches a skill. The job posts one sticky comment and updates it in place
on every push.

## Using it

**Status headline.** The report's first line is a status marker the workflow turns into an
icon:

| | When |
| --- | --- |
| 🟢 Good | Every sibling is legitimately different, or the changed skills have no siblings |
| 🟡 Warning | Something is `likely-applies` or `unclear` — a human decides |
| 🔴 Critical | A verdict is `conflicts`, **or the check itself broke** |

Critical covering both "found a conflict" and "the check is broken" is deliberate: a
silently broken advisory reads as a clean bill of health, which is worse than no check.

**Opt out per PR** with the `skip-drift-check` label. Adding or removing it re-runs the job
immediately and replaces the comment, so a stale advisory never sits on a PR that opted
out. Use it for mass renames and formatting sweeps.

**Bulk changes are capped at 15 changed skill files.** Past that the job posts a note
instead of judging 200 pairs badly. For a big refactor, run the pass locally per plugin.

**Artifacts.** Each run uploads the report, the changed-file list, and Claude's full
execution transcript (7-day retention) — that transcript is where you look when a verdict
seems wrong. Note that artifacts are visible to anyone with read access to the repo.

## Cost

One Claude session per PR that touches a skill, capped at 50 turns and 15 minutes.
Concurrency is set to cancel superseded runs, so a PR pushed five times costs roughly one
review, not five. PRs that touch no skills cost nothing — the `paths:` filter means the
job never starts.

## Security model

The review reads contributor-authored content, so a malicious skill file could try to
instruct the model. The mitigation is structural rather than instructional:

- Claude gets **read-only tools** plus `Write` (for the report). No `Edit`, no `WebFetch`,
  no `WebSearch`, no git write.
- The workflow's `permissions:` are `contents: read` and `pull-requests: write` — enough
  to post one comment, not enough to change code.
- The sticky comment is posted by a separate `github-script` step, not by Claude.
- Nothing merges, blocks, or commits based on the result.

The tool allowlist lives in the workflow, not in the skill: permissions belong to the
caller. Treat both `drift-check.yml` and `SKILL.md` as trust-boundary files and review
changes to them with author ≠ reviewer.

## Layout

```
.claude-plugin/plugin.json          manifest
skills/drift-check/SKILL.md         the review contract — one prompt, shared by CI and local runs
workflows/drift-check.yml           copy this into .github/workflows/
```
