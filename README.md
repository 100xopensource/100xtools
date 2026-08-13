# 100xtools

**Two tools that check your Claude Code plugins for problems.** Open source, free to run,
built while maintaining a plugin fleet in production.

A *plugin* is a folder of written instructions telling Claude how to do a job — and nothing
checks instructions. No spell-check, no compiler, no test that goes red. Someone edits a
sentence, the plugin quietly gets worse, and you find out when a user complains.

## Which one do you need?


| Your problem                                                 | Use                                                          | What it costs                    |
| ------------------------------------------------------------ | ------------------------------------------------------------ | -------------------------------- |
| *"Is anything obviously wrong with my plugin?"*              | **[100xeval](./plugins/100xeval/README.md)** — static check  | **Nothing.** No key, no internet |
| *"Does it still give the right answers after we edited it?"* | **[100xeval](./plugins/100xeval/README.md)** — real test run | ~$1–2 per run                    |
| *"A fix in one plugin never reached the others."*            | **[100xdrift-check](./plugins/100xdrift-check/README.md)**   | Claude usage per review          |


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

New to this? [**100xeval's README**](./plugins/100xeval/README.md) walks the same path more
slowly, with a troubleshooting table.

## What you need

- **Python 3.11+** — check with `python3 --version`. Nothing else to install; these tools use
only the standard library.
- **Claude Code or the Claude desktop app** — for anything that runs your plugin.

## Concepts

The plugin READMEs cover how to run things. *Why* the pieces are shaped as they are — what a
grader is, what a `design_score` of 0.68 means — lives in `[docs/](./docs/index.md)`, written
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

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Issues and PRs welcome — especially bug reports with
a failing case, since a case is the unit of work in this repo.

## Licence

[Apache 2.0](./LICENSE).