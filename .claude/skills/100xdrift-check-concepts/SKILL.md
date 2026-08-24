---
name: 100xdrift-check-concepts
description: Explains 100xdrift-check's concepts — verdicts and status markers, the watch list that defines scope, why the reviewer is vendored into the consuming repo, and why review stops at one repository. Use when someone asks what a verdict means, why a comment says warning, what gets reviewed, or why the plugin ships no reviewer skill. Do NOT use for installing or running a drift review; those are the plugin's own skills.
---

# 100xdrift-check concepts

The concept files live in `docs/100xdrift-check/`, an [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle: one idea per file, so you read one rather than a whole guide.

**Read the one file that answers the question. Do not read them all.**

| Question | Read |
| --- | --- |
| What is drift-check, what are the moving parts? | `docs/100xdrift-check/overview.md` |
| What does `likely-applies` / `conflicts` mean? | `docs/100xdrift-check/verdict.md` |
| Why is the comment 🟡 and not 🟢? | `docs/100xdrift-check/verdict.md` |
| Which files get reviewed? How do I change that? | `docs/100xdrift-check/watch-list.md` |
| Why did the job run and find nothing? | `docs/100xdrift-check/watch-list.md` |
| Why is there no reviewer skill in the plugin? | `docs/100xdrift-check/vendored-reviewer.md` |
| Why is my vendored copy out of date? | `docs/100xdrift-check/vendored-reviewer.md` |
| Why does it not compare against my other repo? | `docs/100xdrift-check/one-repository.md` |

`docs/100xdrift-check/index.md` lists them all if the table above does not cover the
question.

## Boundaries

**Concepts only.** These files explain what a thing is and why it exists. For *doing* the
work, the plugin ships its own instructions:

- Installing, the CI token, first run → `plugins/100xdrift-check/README.md`
- Putting the reviewer in a repo → the `100xdrift-check:install-skill` skill
- Setting up the PR check → the `100xdrift-check:install-workflow` skill
- Running a review → `/drift-check`, from the vendored copy in the repo under review

**Not shipped with the plugin.** A marketplace install gets `plugins/100xdrift-check/` and
not `docs/`, so never tell someone to rely on these files to operate the tool — cite the
plugin's own README and skills for that.

## Answering from them

Quote the file you used and link it, so the reader can go deeper. If the bundle does not
answer the question, say so and read the source — `docs/` is deliberately conceptual and
will not have implementation detail the templates have.
