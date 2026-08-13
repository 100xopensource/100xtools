# 100xtools

**Two tools that check your Claude Code plugins for problems.** Open source, free to run,
and built while maintaining a fleet of plugins in production.

A *plugin* is a folder of written instructions that tells Claude how to do a job. The
trouble with instructions is that nothing checks them. There is no spell-check, no compiler,
and no test that goes red. Someone edits a sentence, the plugin quietly gets worse, and you
find out when a user complains.

These tools are that missing check.

## Which one do you need?

Pick by the problem you have, not by the tool name.

| Your problem | Use | What it costs |
| --- | --- | --- |
| *"Is anything obviously wrong with my plugin?"* | [**100xeval**](./plugins/100xeval/README.md) — the free static check | **Nothing.** No key, no internet, no setup |
| *"Does my plugin still give the right answers after we edited it?"* | [**100xeval**](./plugins/100xeval/README.md) — a real test run | About $1–2 per run |
| *"We have several plugins, and a fix in one never made it to the others."* | [**100xdrift-check**](./plugins/100xdrift-check/README.md) | Claude usage per review |

If you only try one thing, make it the **free static check**. It takes about five minutes,
cannot change or break anything, and it finds real mistakes — a misspelled `descriptionn`
that Claude had been silently ignoring, for example.

## Start here

**Not a developer, or you'd rather not use a terminal?**
→ [**Getting started, step by step**](./plugins/100xeval/GETTING-STARTED.md). No jargon, free
path first, and you can do it all by talking to Claude.

**Using the Claude desktop app?** Install a tool from inside the app, then just ask for what
you want in plain words:

```
/plugin marketplace add 100xopensource/100xtools
/plugin install 100xeval@100xtools
```

> *"static-check my plugin"* · *"why did it score 0.77?"* · *"what should I fix first?"*

**Comfortable in a terminal?** Clone the repo and run the free check directly — nothing to
install first:

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target <your-plugin-folder>
```

To try a tool without installing it, point Claude Code at a folder for one session:

```bash
claude --plugin-dir plugins/100xeval            # then: "run the evals for <skill>"
claude --plugin-dir plugins/100xdrift-check     # then: /100xdrift-check:install-skill
```

Each tool's own README has the full setup:
[100xeval](./plugins/100xeval/README.md) · [100xdrift-check](./plugins/100xdrift-check/README.md).

## What you need

For the **free static check — nothing but Python.** No account, no key, no internet.

- **Python 3.11 or newer.** Check with `python3 --version`. If that command is not found or
  the number is lower, see
  [Getting started](./plugins/100xeval/GETTING-STARTED.md#before-you-start). There is
  nothing else to install — these tools use only what Python already ships with, on purpose:
  a testing tool that needs its own installation is one more thing that breaks.
- **Claude Code or the Claude desktop app** — only for the parts that actually run your
  plugin, and for the drift reviewer.
- **An Anthropic API key, or being logged in to Claude** — only for the parts that call a
  model and cost money. The static check needs neither.

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
CHANGELOG.md                      releases + the scoring-version contract
docs/                             OKF knowledge bundle — concepts, not how-to
plugins/
├── 100xeval/                     eval engine + skill
└── 100xdrift-check/              two install skills + the reviewer and workflow they install
scripts/check_docs.py             OKF bundle conformance + link check (runs in CI)
```

One repo, one folder per tool. Each plugin is self-contained: you can copy a single
directory into your own repo and it will work.

## What this is not

- **Not a general LLM eval framework.** It grades Claude Code *plugins* — skills, their
  tool calls, their MCP servers. If you want to benchmark models, use something else.
- **Not a replacement for review.** 100xdrift-check is advisory. It tells you where to look; it
  does not decide.
- **Not a hosted service.** There is no server to run and no account to create. Everything
  here executes in your CI or on your laptop.

The house-style rules we run internally are deliberately **not** here. The static linter
encodes published Claude Code guidance plus generic hygiene, so a finding means "this is
probably wrong", not "this differs from how we write skills". Add your own conventions in
your fork.

## What this gets wrong

Worth knowing before you wire it into anything.

**The static layer is heuristics over prose, and it has been wrong repeatedly.** Running it
against Anthropic's own published plugins found five false-positive classes in one pass — it
flagged licence files, a plugin's own vendor documentation, and `password: 'meeting-password'`
from a code sample. Each is fixed and tested, but the same *class* of bug will recur: a rule
that reads documentation as instruction. **Read the findings, don't just take the number.**
If more than about one in five is noise for your plugins, the tool is costing you attention.

**Absence assertions fail open.** `min: 0, max: 0` passes when nothing matched — and a wrong
pattern also matches nothing, so a typo gives you a grader that cannot fail. Check the same
pattern can pass with `min: 1` on a run where the tool *was* used.

**Behavioral runs are non-deterministic and cost money.** Roughly $1–2 per run. `runs: 3` is
the default because a single run reports a coin flip as a fact. Expect the first run to
debug your *case*, not your skill — case defects outran skill defects about 3:1 for us.

**`design_score` is comparable only within a scoring version.** It is printed with every
report and carried in the JSON. If you gate CI on a threshold, pin the version you tuned it
against — see [CHANGELOG.md](./CHANGELOG.md).

**100xdrift-check is a draft.** It works, but it has not been run against a real
multi-plugin repo under load.

**Nobody outside 100x has used this yet.** It is dogfooded — CI scores this repo's own
plugins on every push — but dogfooding is not the same as external validation.

## Roadmap

Continuity sessioning (save and resume a session's artifacts and conversation) and a
feedback → eval loop are in progress and will land here as additional plugins.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Issues and PRs welcome — especially bug reports
with a failing case, since a case is the unit of work in this repo.

## Licence

[Apache 2.0](./LICENSE).
