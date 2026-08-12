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
the environment (`EVAL_MCP_BEARER`) and configs reference them as `${VAR}`. The linter's SEC1
check will catch the obvious cases; it will not catch a clever one.

**No internal, customer, or tenant data.** Fixtures use `example.com` / `Acme`. If you are
contributing from a company that uses these tools internally, scrub before you push: real
connector URLs, real plugin names, real store or customer names, and captured `claude mcp
list` output all count.

**Think before committing a system prompt.** `engine/entrypoints/` tracks `cowork` and
ignores everything else by default. A surface's system prompt usually belongs to whoever
operates that surface — including when a third-party site has published a capture of it —
so adding another should be a deliberate decision, not the by-product of dropping a file
in that directory.

## Development

Everything runs from a clone with no setup step.

```bash
# engine tests — offline, no model or MCP calls
cd plugins/100xeval/skills/100xeval
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

`tests/` sits beside `scripts/`, not inside it — `scripts/` is what ships in the plugin
and what Claude invokes at runtime, so the suite stays out of that payload. Tests import
`engine.*` absolutely, so `PYTHONPATH=scripts` is what makes them resolve.

```bash
# static self-check — both plugins should score 1.00
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only
```

CI runs these two plus `scripts/check_docs.py` and a manifest-consistency check. If they
pass locally they pass there.

### The pre-commit hook

Optional, recommended, and enabled once per clone:

```bash
git config core.hooksPath scripts/hooks
```

It runs everything CI runs, plus a sweep for internal references and secret-shaped strings,
in about two seconds. Nothing is conditional on which files you staged — a check that
decides for itself whether to run is a check that silently stops running.

The leak sweep is first because it is the only failure here you cannot undo: once an
internal reference is in git history, removing it is a rewrite, not a revert. This repo has
already had one such leak reach a commit and get caught only on a second manual pass. It
reads the **staged** blob rather than the working tree, so scrubbing a file after
`git add` does not smuggle the earlier version through.

`git commit --no-verify` skips the hook — intentionally, because a hook you cannot bypass is
a hook people disable permanently. CI is the real gate; this just moves the feedback earlier.

## Changing the linter

`engine/lint.py` is the one place house style could creep in, so it gets an extra rule:

**A check earns its place by catching something that is probably wrong** — not something
that merely differs from how you write skills. "This skill has no Data Source section" is a
convention. "This skill ships `references/` and never tells the model to read them" is a
defect. Only the second belongs here.

Every check needs a test that builds a real plugin on disk and asserts both directions: the
dirty case fires, and the clean fixture stays clean. A check that only ever fires is as
useless as one that never does.

Check IDs carry their sub-score in the prefix — `FM` frontmatter, `PD` progressive
disclosure, `RH` reference hygiene, `ST` structural, `EC` ecosystem, `SEC` security. To add
a check, pick the right prefix and take the next free number; `engine/static.py` derives
the mapping, so there is no second file to update. An unregistered prefix raises rather
than scoring nothing, and `TestCheckIdContract` fails both ways — on a prefix with no
sub-score, and on a sub-score no check feeds (which would sit at 1.00 forever and dilute
every result). `engine/lint.py`'s docstring is the ID reference; keep it in step.

A new check also wants a row in [`docs/100xeval/check-ids.md`](./docs/100xeval/check-ids.md).

## Changing a trust-boundary file

These drive what CI does with model output and what permissions the model gets:

- `plugins/100xdrift-check/templates/workflows/drift-check.yml`
- `plugins/100xdrift-check/templates/skills/drift-check/SKILL.md`
- `.claude/skills/drift-check/SKILL.md` (this repo's vendored copy)
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
