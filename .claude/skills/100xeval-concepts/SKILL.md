---
name: 100xeval-concepts
description: Explains 100xeval's concepts — graders, eval cases, scoring, design_score, check IDs, the harness/entrypoint axes, MCP auth, and run folders. Use when someone asks what a grader is, what a design_score means, why a check fired, what entrypoint does, or where to look when a case fails. Do NOT use for running evals or writing cases; those are the 100xeval plugin's own skill.
---

# 100xeval concepts

The concept files live in `docs/100xeval/`, an [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle: one idea per file, so you read one rather than a whole guide.

**Read the one file that answers the question. Do not read them all.**

| Question | Read |
| --- | --- |
| What is 100xeval, what are the two layers? | `docs/100xeval/overview.md` |
| What is a case, why `runs: 3`, why not delete one? | `docs/100xeval/eval-case.md` |
| What is a grader, why one claim each? | `docs/100xeval/grader.md` |
| How does a run become a score or a verdict? | `docs/100xeval/scoring.md` |
| What does `design_score 0.68` mean? Weights? | `docs/100xeval/design-score.md` |
| What is `FM3` / `SEC2` / any check ID? | `docs/100xeval/check-ids.md` |
| What is a harness? Why is `codex` a stub? | `docs/100xeval/harness.md` |
| What is an entrypoint, why default `none`? | `docs/100xeval/entrypoint.md` |
| Why does `tool_used` say "called 0×"? | `docs/100xeval/mcp-auth.md` |
| A case failed — where is the evidence? | `docs/100xeval/run-folder.md` |

`docs/100xeval/index.md` lists them all if the table above does not cover the question.

## Boundaries

**Concepts only.** These files explain what a thing is and why it exists. For *doing* the
work, the 100xeval plugin ships its own instructions:

- Running evals, flags, reading a scorecard → the `100xeval` skill
- Every `case.yaml` field and grader parameter → `plugins/100xeval/skills/100xeval/references/case-schema.md`
- Writing, editing and debugging cases → `.../references/managing-testcases.md`

**Not shipped with the plugin.** A marketplace install gets `plugins/100xeval/` and not
`docs/`, so never tell someone to rely on these files to operate the tool — cite the
plugin's own references for that.

## Answering from them

Quote the file you used and link it, so the reader can go deeper. If the bundle does not
answer the question, say so and read the source — `docs/` is deliberately conceptual and
will not have implementation detail the code has.
