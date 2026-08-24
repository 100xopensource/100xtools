# Example drift review

Two fake plugins that were copied from one original and then edited apart. One of them gets
a fix; what that means for the other one is the interesting part. Use this to see what a
drift report looks like before pointing the tool at your own code.

**These plugins are fiction.** Acme, no real data, nothing to install. They exist to give
the reviewer something to disagree with.

## Run it

```bash
# From the repo root. Builds a throwaway git repo, applies the change, prints what to do.
./examples/plugin-drift-check/demo.sh

# Or choose where it lands:
./examples/plugin-drift-check/demo.sh ~/scratch/drift-demo
```

Then, in the directory it printed:

```bash
claude
```
```
/drift-check
```

The reviewer is vendored into the demo repo for you, so this works with nothing installed.
It writes `drift-report.md` and summarises the verdicts in the reply.

To rehearse the real setup instead, delete `.claude/skills/drift-check` from the demo repo
and run `/100xdrift-check:install-skill` with the plugin installed — that is the path a new
repo actually takes.

## What is in here

```
plugins/acme-north/    the plugin whose files change
plugins/acme-south/    the near-copy the review is about
the-change.patch       the fix under review, applied by demo.sh on a branch
```

Ordinary plugin directories — manifest, `skills/`, `commands/`, `agents/` — so the reviewer
sees the same shape it would in your repo. The patch is kept separate rather than as a
second copy of the tree: it *is* the diff, and reading it tells you what the review is
about.

## What is planted

`acme-north` fixes its weekly window: a rolling 7 days becomes the ISO week. Three files
follow from that one decision, and each lands differently against South's copy:

| Changed in North | South's copy | Verdict | Why |
| --- | --- | --- | --- |
| `skills/weekly-report/SKILL.md` | The same rolling-7-day window | `likely-applies` | Same bug, same fix |
| `agents/reconciler.md` | Keys ledger rows on the end date, and says so | `conflicts` | ISO week numbers repeat across years and would collide |
| `commands/export-csv.md` | Names files by fiscal period, one per store | `different on purpose` | Finance ingests it that way — deliberate |

Two plugins, three verdicts. That spread is the point: the same change is worth porting in
one place, dangerous in another, and irrelevant in a third. Telling those apart is the
judgment the tool exists to make, and the reason it never edits anything itself.

Because one verdict is `conflicts`, the whole report is 🔴 Critical. That is a prompt to
look, not a merge blocker.

[`drift-report.md`](./drift-report.md) shows the shape of a good answer. It is
illustrative, not asserted — the model's wording varies between runs, the three calls
should not.

## What it also demonstrates

**All three prompt surfaces are watched**, not just skills: the change touches a `SKILL.md`,
a `commands/` file and an `agents/` file, which is exactly what the shipped watch list
covers — the `paths:` list in `.github/workflows/drift-check.yml`.

**Siblings come from the same repo.** Two plugins in one tree is the shape this tool is for.
Nothing is cloned or fetched — see
[one repository](../../docs/100xdrift-check/one-repository.md).

## Cleaning up

The demo repo is a plain directory outside this one. Delete it when you are done:

```bash
rm -rf "${TMPDIR:-/tmp}/drift-check-demo"
```
