# 100xeval — keep plugins working as they change

**Testcases for Claude Code plugins.** You save the questions your plugin must get right, run
them, and find out when an edit breaks one. That is how a plugin's quality survives months of
changes and more than one person editing it.

A plugin is a folder of written instructions. Nothing checks instructions — no compiler, no
test that goes red. A reworded sentence that quietly stops the plugin filtering by store looks
exactly like a change that broke nothing. Testcases are how you tell the difference.

**The loop:**

1. **Write a case** — the question a user really asks, and what a correct answer must do.
2. **Run it** — the plugin executes for real, with its data connection attached.
3. **Grade it** — did it query the right data, present it properly, get the numbers right?
4. **Keep it** — every bug a user reports becomes a case, so a fixed bug stays fixed.

The corpus is the asset. A case you wrote a year ago is what stops today's edit from
reintroducing last year's bug.

| | What it does | Cost | Needs |
| --- | --- | --- | --- |
| **Test run** | Runs your plugin on saved cases and grades the answers | **~$1–2 per run** | Claude Code CLI |
| **Static check** | A quick run-free pass over the plugin's files | **Free** | Just Python |

The **static check** is a cheap extra, not a substitute: it reads the files and reports
problems visible without executing anything. Useful on every commit, but it cannot tell you
whether the plugin still answers correctly. Only a case does that.

Everything ships in one folder — the skill Claude talks to and the Python engine underneath.
**Python 3.11+, standard library only:** no `pip install`, no virtualenv, no lockfile.

---

## What you need

| | Needs |
| --- | --- |
| **Static check** | Python 3.11+ — check with `python3 --version`. Nothing else: no key, no internet, no account |
| **Test runs** | That, plus the Claude Code CLI on your `PATH` |

The runner executes your plugin by shelling out to `claude`, so the CLI has to be installed
and working. On an old Python the tool says so plainly rather than showing a traceback.

---

## Get started

Install once, then ask Claude for what you want in plain words — you never type an engine
command.

**1. Get the code.** In a terminal:

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
```

**2. Install the plugin.** Two more lines in the same terminal — the first tells Claude where
to find the tools, the second installs this one:

```bash
claude plugin marketplace add ./
claude plugin install 100xeval@100xtools
```

> **Type `./` and not `.`** — a bare dot is rejected with *"Invalid marketplace source
> format"*. The `/` is not a typo.

**How to tell it worked:** the first line answers `Successfully added marketplace: 100xtools`.

**3. Open Claude and ask.** Start Claude Code, or open the Claude desktop app, in the folder
your plugin lives in. From here you only type plain English — copy any line below.

**Start here — free, instant, changes nothing:**

> *"static-check my plugin"*

It only reads files. Nothing is edited, uploaded, or sent over the network, and it costs
nothing. Then, once you have a result:

> *"explain that score in plain english"*
> *"what should I fix first?"*
> *"is that finding a real problem, or a false alarm?"*

**Building up testcases** — the part that keeps the plugin working over time:

> *"what should I be testing in this plugin?"*
> *"add a testcase for askinventory"*
> *"turn this bug report into a testcase: <paste the report>"*
> *"show me the testcases we already have"*

**Running them** — this is the part that costs money, so ask the price first:

> *"how much would it cost to run these testcases?"*
> *"run the evals for asksales, just once"*
> *"did my change break anything?"*
> *"why did that case fail?"*

**If you get stuck**, ask Claude that too — it has the tool's own documentation:

> *"I don't understand this result, walk me through it"*
> *"what does token_efficiency mean?"*

You never have to learn a command or a flag.

---

## Documentation

Concepts and how-to live in the [`docs/100xeval`](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/index.md) bundle. They are **not**
copied by a marketplace install, so these are links rather than files beside you:

| | |
| --- | --- |
| [Eval case](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/eval-case.md) | What a case is, what one looks like, and how to create one |
| [Grader](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/grader.md) | The four types, one claim each, and the assertion that cannot fail |
| [Run folder](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/run-folder.md) | Cost, `--dry-run`, exit codes, and the evidence a run writes |
| [MCP auth](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/mcp-auth.md) | Two auth paths, and the failure that looks like nothing |
| [Design score](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/design-score.md) | Running the static check, reading it, and where it is wrong |
| [Troubleshooting](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/troubleshooting.md) | What each failure means |
| [Internals](https://github.com/100xopensource/100xtools/blob/main/docs/100xeval/internals.md) | Layout, and the engine's own test suite |

Shipped inside the plugin, for writing cases in depth:
[`case-schema.md`](./skills/100xeval/references/case-schema.md) ·
[`managing-testcases.md`](./skills/100xeval/references/managing-testcases.md)

Two worked examples live in
[`examples/plugin-eval/`](../../examples/plugin-eval/README.md).
