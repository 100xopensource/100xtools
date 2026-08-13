# Getting started with 100xeval

**For people who are not developers.** No coding needed. If you can copy and paste a line
into a terminal, you can do everything on this page.

The [README](./README.md) is the reference version of all of this. It assumes you already
know the vocabulary. This page does not.

---

## What this tool is for

You have a Claude Code **plugin** — a folder of instructions that tells Claude how to do a
job. The problem: when someone edits those instructions, nothing tells you if they made it
worse. There is no spell-check for instructions.

100xeval is that check. It works in two ways:

| | What it does | Cost | Needs |
| --- | --- | --- | --- |
| **Static check** | Reads your plugin's files and reports problems it can see | **Free** | Nothing |
| **Behavioral run** | Actually runs your plugin and grades the answers | **~$1–2 each** | An API key |

**Start with the static check.** It is free, it cannot break anything, and it finds real
problems. Most people never need more than this. This page covers it first, and the paid
part is at the end, clearly marked.

---

## Before you start

**Claude Code or the Claude desktop app**, which you probably already have.

**Python 3.11 or newer.** The tool is written in Python, so it has to be there — but you
almost never interact with it directly. To check, you need a terminal:

- On Mac, press `Cmd + Space`, type `Terminal`, press Enter. A window with text appears.
  That is it — that is the terminal.

Copy this line into it and press Enter:

```bash
python3 --version
```

You want to see `Python 3.11` or higher — `3.12`, `3.13`, `3.14` are all fine.

- **If the number is lower** (like `3.9`), install a newer one: `brew install python@3.12`
  on Mac, then use `python3.12` instead of `python3` everywhere below.
- **If you get "command not found"**, Python is not installed. Get it from
  [python.org/downloads](https://www.python.org/downloads/).

If you skip this and your Python is too old, the tool tells you so in plain words. It does
not show you a wall of red error text.

**You do not need anything else.** No `pip install`, no accounts, no setup wizard. This is
deliberate: a testing tool that needs its own installation is one more thing that breaks.

---

## Part 1 — Your first check (about 5 minutes, free)

**The easiest way is to let Claude do it.** You install the tool once, then ask for things in
plain words. You never type a command.

**Step 1. Get the code.** In a terminal:

```bash
git clone https://github.com/100xopensource/100xtools.git
cd 100xtools
```

> **If this fails with "repository not found":** the repo is private until 14 Aug. You need
> to be added to the `100xopensource` GitHub organisation. Ask Thuan.

**Step 2. Install the tool.** Start Claude Code in that folder, then type these two lines.
The first tells Claude where to find the tools; the second installs the one you want.

```
/plugin marketplace add .
/plugin install 100xeval@100xtools
```

If Claude tells you to run `/reload-plugins`, do that.

**Step 3. Ask for a check.** Point Claude at the folder your plugin is in, and say:

> *"static-check my plugin"*

**How to tell it worked:** Claude runs the check and shows you a score with a list of
findings underneath. If instead it asks what you mean, the tool did not install — go back to
step 1.

That is the whole thing. No key, no internet, no cost, and nothing on your computer is
changed — the check only *reads* files.

Other things worth asking once you have a result:

> *"why did it score 0.77?"* · *"what should I fix first?"* · *"is that finding a real problem?"*

---

## Part 2 — Reading your scorecard

Here is a real result from a plugin with problems:

```
# 100xeval — static design quality  (scoring v1)

## demo-plugin — design_score 0.77
- frontmatter_quality: 0.50
- progressive_disclosure: 1.00
- reference_hygiene: 1.00
- structural_completeness: 0.75
- token_efficiency: 1.00
- ecosystem_coherence: 1.00
- security: 1.00

### findings (3)
- demo-plugin: [ST1] plugin has no README.md at its root
- skills/report/SKILL.md: [FM3] skill has no description — the model cannot decide when to load it
- skills/report/SKILL.md: [FM4] unrecognized frontmatter key 'descriptionn' (did you mean 'description'?)
```

**Read the findings, not the number.** The number is a summary. The findings tell you what
to actually do — and here they are genuinely useful: someone typed `descriptionn` with two
n's, and Claude was silently ignoring it.

Rough guide to the number:

| Score | Meaning |
| --- | --- |
| **1.00** | Nothing found. Does not prove the plugin *works* — only that nothing obvious is broken. |
| **0.85–0.99** | Small things. Worth a look, not urgent. |
| **below 0.85** | Read every finding. Something real is usually in there. |

**Three honest warnings:**

**This tool is sometimes wrong.** It reads your writing and guesses. Running it against
Anthropic's own published plugins found five different kinds of false alarm in one pass. If
more than about **one finding in five** is nonsense for your plugin, the tool is wasting
your attention — say so, that is a bug in the tool, not in you.

**`token_efficiency` never shows a finding.** It is measured, not detected — it counts
repeated text across your files. So a low score there with an empty findings list is normal,
not a display bug.

**A score only compares to another score from the same `scoring v1`.** That version is
printed at the top. If the rules change, the number moves, and old numbers stop being
comparable.

---

## Part 3 — If you would rather type the command yourself

You do not need this section. It is here for people who prefer seeing the command run.

From the folder you cloned in Part 1, replace `<your-plugin-folder>` with the folder you
want checked:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target <your-plugin-folder>
```

Nothing to try it on yet? Use a plugin that ships with the repo:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only --target examples/plugin-eval/vendor/design
```

This is the same check Claude runs for you in Part 1 — same output, same cost of nothing.

---

## Part 4 — The part that costs money

**Read this before running anything in this section.**

A *behavioral* run really runs your plugin and asks Claude to grade the answers. This costs
roughly **$1–2 per run**, and the normal setting of 3 runs per test lands around **$3–5 for
a single test**. There is no free tier and no undo.

**Always check the price first.** `--dry-run` shows exactly what would run and the rough
cost, and spends nothing:

```bash
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --cases-dir examples/plugin-eval/cases --skip-static --dry-run
```

To run for real you need `ANTHROPIC_API_KEY` set, or to be logged into Claude Code. If your
plugin connects to a data source, you may also need a token in `EVAL_MCP_BEARER` — ask a
developer for that part.

**Expect the first run to fail for a boring reason.** Usually the *test* is wrong, not the
plugin. For us, broken tests outnumbered real plugin bugs about 3 to 1.

---

## If something goes wrong

| What you see | What it means | What to do |
| --- | --- | --- |
| `command not found: python3` | Python is not installed | Install it — see "Before you start" |
| `100xeval needs Python 3.11 or newer` | Your Python is too old | Install a newer one, then use `python3.12` |
| `repository not found` | The repo is private, or you lack access | Ask to be added to `100xopensource` |
| `is not a directory` (exit 2) | The folder path you typed is wrong | Check the path. **The tool refuses to invent a score for a folder that isn't there** |
| `No findings. Nothing to fix.` | Nothing detectable is wrong | This is a pass |
| A test says a tool was `called 0×` | Usually a **bad or expired token**, not a broken plugin | Check the token before blaming the plugin |
| A wall of red text | A real bug in the tool | Please report it with the command you ran |

---

## What you do not need to worry about

- **You cannot break anything.** The static check only *reads* files. It never edits your
  plugin, never uploads it, and never touches the network.
- **You do not need an API key** for anything in Parts 1–3.
- **You do not need to understand the check IDs** (`ST1`, `FM3`). The message next to each
  one says what is wrong in plain words.

---

## Where to go next

- [README.md](./README.md) — the full reference, including writing your own tests
- [`examples/plugin-eval/`](../../examples/plugin-eval/README.md) — two complete worked
  examples, running against real third-party plugins
- Something confusing on this page? That is a documentation bug. Please report it.
