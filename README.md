# 100xtools

**Two tools that check your Claude Code plugins for problems.** Open source, free to run,
built while maintaining a plugin fleet in production.

A *plugin* is a folder of written instructions telling Claude how to do a job — and nothing
checks instructions. No spell-check, no compiler, no test that goes red. Someone edits a
sentence, the plugin quietly gets worse, and you find out when a user complains.

## Which one do you need?

| Your problem | Use | What it costs |
| --- | --- | --- |
| *"Is anything obviously wrong with my plugin?"* | [**100xeval**](./plugins/100xeval/README.md) — static check | **Nothing.** No key, no internet |
| *"Does it still give the right answers after we edited it?"* | [**100xeval**](./plugins/100xeval/README.md) — real test run | ~$1–2 per run |
| *"A fix in one plugin never reached the others."* | [**100xdrift-check**](./plugins/100xdrift-check/README.md) | Claude usage per review |

Start with the **free static check**. Five minutes, changes nothing, and it catches what you
cannot spot by reading: a skill with no description, a setting name spelled just wrongly
enough to be ignored, a password left in a file.

## Start here

**1. Clone this repo:**

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
```

**2. Register it and install what you need:**

```bash
claude plugin marketplace add ./
claude plugin install 100xeval@100xtools
claude plugin install 100xdrift-check@100xtools
```

**Then just ask.** Open the folder your plugin is in and say what you want in plain words:

> *"static-check my plugin"* · *"why did it score 0.77?"* · *"what should I fix first?"*

New to this? [**Getting started**](./plugins/100xeval/GETTING-STARTED.md) walks the same path
slowly, with a troubleshooting table.

## What you need

- **Python 3.11+** — check with `python3 --version`. Nothing else to install; these tools use
  only the standard library.
- **Claude Code or the Claude desktop app** — for anything that runs your plugin.
- **An Anthropic API key, or a Claude login** — only for the parts that cost money. The
  static check needs neither.

## Concepts

The plugin READMEs cover how to run things. *Why* the pieces are shaped as they are — what a
grader is, what a `design_score` of 0.68 means — lives in [`docs/`](./docs/index.md), written
in [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
v0.2: one small file per concept, cross-linked, and readable by an agent that wants a single
idea rather than a whole guide.

## Repository layout

```
.claude-plugin/marketplace.json   the marketplace manifest (one entry per plugin)
CHANGELOG.md                      releases + the scoring-version contract
docs/                             OKF knowledge bundle — concepts, not how-to
plugins/
├── 100xeval/                     eval engine + skill
└── 100xdrift-check/              two install skills + the reviewer and workflow they install
scripts/check_docs.py             OKF bundle conformance + link check (runs in CI)
```

Each plugin is self-contained: copy a single directory into your own repo and it works.

## What this is not

- **Not a general LLM eval framework.** It grades Claude Code *plugins* — skills, their tool
  calls, their MCP servers. To benchmark models, use something else.
- **Not a replacement for review.** 100xdrift-check is advisory. It tells you where to look;
  it does not decide.
- **Not a hosted service.** Nothing to run, no account to create. It all executes in your CI
  or on your laptop.

Our internal house-style rules are deliberately **not** here. The linter encodes published
Claude Code guidance plus generic hygiene, so a finding means "this is probably wrong", not
"this differs from how we write skills". Add your own conventions in your fork.

## What this gets wrong

**The static layer is heuristics over prose, and it has been wrong repeatedly.** Run against
Anthropic's own published plugins, it produced five classes of false positive in one pass —
flagging licence files, a plugin's own vendor documentation, and `password: 'meeting-password'`
from a code sample. Each is fixed and tested, but the same *class* of bug will recur: a rule
that reads documentation as instruction. **Read the findings, don't just take the number.** If
more than about one in five is noise for your plugins, the tool is costing you attention.

**100xdrift-check is a draft.** It works, but has not been run against a real multi-plugin
repo under load.

**Nobody outside 100x has used this yet.** CI scores this repo's own plugins on every push,
but dogfooding is not external validation.

Per-tool caveats — what a score can and cannot be compared against, and how a grader can be
written so it never fails — are in
[100xeval's README](./plugins/100xeval/README.md#known-traps).

## Roadmap

Continuity sessioning (save and resume a session's artifacts and conversation) and a
feedback → eval loop are in progress, and will land here as additional plugins.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Issues and PRs welcome — especially bug reports with
a failing case, since a case is the unit of work in this repo.

## Licence

[Apache 2.0](./LICENSE).
