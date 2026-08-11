# 100xtools

Open-source tooling for building and maintaining **Claude Code plugins and skills** — the
parts we needed badly enough to build, extracted from running a plugin fleet in production.

Two problems show up the moment you have more than one plugin and more than one person
editing them:

1. **You can't tell whether a skill still works.** Prompt changes have no compiler. A
   reworded instruction that quietly stops the model from filtering by store looks exactly
   like a change that didn't break anything.
2. **Sibling skills drift apart.** The same skill copied across five plugins gets fixed in
   one and stays broken in four, and nobody finds out until a user does.

| Tool | What it does |
| --- | --- |
| [**100xeval**](./plugins/100xeval) | Runs a plugin for real against saved testcases and grades the answers — did it query the right data, present it correctly, get the numbers right? Plus a free, model-free design-quality score. |
| [**drift-check**](./plugins/drift-check) | On every PR that edits a skill, finds the sibling skills in your other plugins and reports which ones the change probably applies to. Report-only, never blocks a merge. |

Both are ordinary Claude Code plugins, and both are usable as CI gates.

## Quick start

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
```

**Score a plugin's design — free, no model, no API key, no install:**

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target <your-plugin-dir>
```

**Load a tool into Claude Code:**

```bash
claude --plugin-dir plugins/100xeval      # then: "run the evals for <skill>"
claude --plugin-dir plugins/drift-check   # then: /drift-check
```

**Or install from the marketplace:**

```
/plugin marketplace add 100xopensource/100xtools
/plugin install 100xeval
/plugin install drift-check
```

Each plugin's README carries its own full setup — start there:
[100xeval](./plugins/100xeval/README.md) · [drift-check](./plugins/drift-check/README.md).

## Requirements

- **Python 3.11+** for the eval engine — stdlib only. No `pip install`, no virtualenv, no
  lockfile. This is deliberate: an eval harness that needs its own dependency management is
  one more thing to break on a Friday.
- **Claude Code** on `PATH` for behavioral eval runs and for the drift-check skill.
- **An Anthropic API key or Claude Code login** for anything that actually calls a model.
  The static layer needs neither.

## Concepts

Each plugin's README tells you how to run it. If you want to understand *why* the pieces are
shaped the way they are — what a grader is, what a `design_score` of 0.68 means, why
`entrypoint` defaults to `none` — that lives in [`docs/`](./docs/index.md), written in
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
v0.2: one small file per concept, cross-linked, and readable by an agent that wants one idea
rather than a whole guide.

## Repository layout

```
.claude-plugin/marketplace.json   the marketplace manifest (one entry per plugin)
docs/                             OKF knowledge bundle — concepts, not how-to
plugins/
├── 100xeval/                     eval engine + skill
└── drift-check/                  drift review skill + GitHub Actions workflow
scripts/check_docs.py             OKF bundle conformance + link check (runs in CI)
```

One repo, one folder per tool. Each plugin is self-contained: you can copy a single
directory into your own repo and it will work.

## What this is not

- **Not a general LLM eval framework.** It grades Claude Code *plugins* — skills, their
  tool calls, their MCP servers. If you want to benchmark models, use something else.
- **Not a replacement for review.** drift-check is advisory. It tells you where to look; it
  does not decide.
- **Not a hosted service.** There is no server to run and no account to create. Everything
  here executes in your CI or on your laptop.

The house-style rules we run internally are deliberately **not** here. The static linter
encodes published Claude Code guidance plus generic hygiene, so a finding means "this is
probably wrong", not "this differs from how we write skills". Add your own conventions in
your fork.

## Roadmap

Continuity sessioning (save and resume a session's artifacts and conversation) and a
feedback → eval loop are in progress and will land here as additional plugins.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Issues and PRs welcome — especially bug reports
with a failing case, since a case is the unit of work in this repo.

## Licence

[Apache 2.0](./LICENSE).
