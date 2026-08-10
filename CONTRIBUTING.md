# Contributing to 100xtools

Thanks for looking. This is a small repo with a narrow scope, so the fastest path from idea
to merged is usually a short issue first — especially for anything that adds a check, a
grader, or a dependency.

## Ground rules

**Python stdlib only.** The eval engine has no third-party dependencies and we intend to
keep it that way. A test harness that needs its own dependency management is one more thing
to break. If you genuinely need a library, open an issue explaining why the stdlib can't do
it before writing the PR.

**No secrets, ever.** Not in a case file, not in a fixture, not in a test. Tokens come from
the environment (`EVAL_MCP_BEARER`) and configs reference them as `${VAR}`. The linter's X1
check will catch the obvious cases; it will not catch a clever one.

**No internal, customer, or tenant data.** Fixtures use `example.com` / `Acme`. If you are
contributing from a company that uses these tools internally, scrub before you push: real
connector URLs, real plugin names, real store or customer names, and captured `claude mcp
list` output all count.

**Don't commit a system prompt you don't own.** `engine/entrypoints/` deliberately ships
empty. A surface's system prompt belongs to whoever operates that surface — including when
a third-party site has published a capture of it.

## Development

Everything runs from a clone with no setup step.

```bash
# engine tests — offline, no model or MCP calls
cd plugins/100xeval/skills/100xeval/scripts
python3 -m unittest discover -s engine/tests -p 'test_*.py'
```

The `cd` matters: tests import `engine.*`, so `scripts/` must be the working directory.

```bash
# static self-check — both plugins should score 1.00
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only
```

CI runs exactly these two commands. If they pass locally they pass there.

## Changing the linter

`engine/lint.py` is the one place house style could creep in, so it gets an extra rule:

**A check earns its place by catching something that is probably wrong** — not something
that merely differs from how you write skills. "This skill has no Data Source section" is a
convention. "This skill ships `references/` and never tells the model to read them" is a
defect. Only the second belongs here.

Every check needs a test that builds a real plugin on disk and asserts both directions: the
dirty case fires, and the clean fixture stays clean. A check that only ever fires is as
useless as one that never does.

If you add a check ID, map it to a sub-score in `engine/static.py` — an unmapped ID is
silently ignored, and a sub-score with nothing mapped to it sits at 1.00 forever and
dilutes the result.

## Changing a trust-boundary file

These drive what CI does with model output and what permissions the model gets:

- `plugins/drift-check/workflows/drift-check.yml`
- `plugins/drift-check/skills/drift-check/SKILL.md`
- `.github/workflows/*`

Changes here need review by someone other than the author, and checks should only ever
tighten. If a change relaxes a permission or removes a guard, say so explicitly in the PR
description rather than letting a reviewer find it in the diff.

## Adding an eval case

A case is the unit of work in this repo — a bug report with a failing case attached is the
most useful issue you can file. The full guidance is in
[`managing-testcases.md`](./plugins/100xeval/skills/100xeval/references/managing-testcases.md);
the short version:

- Assert the **query shape**, not the figure. A hard-coded number is a scheduled false
  failure.
- **One claim per grader**, so a red scorecard names what broke.
- Keep `runs: 3`. Skills are non-deterministic and one run reports a coin flip as a fact.
- Park with `skip: "<reason>"` rather than deleting — deleting a case deletes the
  regression it guards. Never delete one to make a suite green.

## Commits and PRs

Conventional commits (`fix:`, `feat:`, `docs:`, `refactor:`, `test:`, `chore:`), one
logical change per PR. In the description, say what breaks if the change is wrong — that is
the part reviewers actually need.

## Reporting a security issue

Please don't open a public issue. See [SECURITY.md](./SECURITY.md).

## Licence

By contributing you agree that your contributions are licensed under
[Apache 2.0](./LICENSE).
