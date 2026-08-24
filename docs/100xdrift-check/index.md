# 100xdrift-check

Drift review for a repository that holds several Claude Code plugins. Start with the
[overview](overview.md).

## Core concepts

* [Overview](overview.md) - What drift-check is, and the three moving parts
* [Verdict](verdict.md) - The four per-sibling calls, and the status marker they roll up to
* [Watch list](watch-list.md) - The one `paths:` list that defines what gets reviewed

## Why it is shaped this way

* [Vendored reviewer](vendored-reviewer.md) - Why the plugin ships no reviewer skill
* [One repository](one-repository.md) - The scope ceiling, and why it is not a missing feature

## How to actually run it

This bundle is conceptual. For installing and running, see the tool's own documentation,
which ships with the plugin:

* [Plugin README](../../plugins/100xdrift-check/README.md) - install, first run, CI token
* [install-skill](../../plugins/100xdrift-check/skills/install-skill/SKILL.md) - what the
  reviewer install does
* [install-workflow](../../plugins/100xdrift-check/skills/install-workflow/SKILL.md) - what
  the CI install does
