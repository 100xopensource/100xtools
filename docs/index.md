# 100xtools knowledge bundle

Shared documentation in [Open Knowledge Format](https://okf.md/spec/) (OKF v0.1): one
markdown file per concept, YAML frontmatter, cross-linked. Readable by a person and
navigable by an agent that wants one idea at a time rather than a whole guide.

This bundle explains **what the concepts are and why they exist**. It does not tell you how
to run anything — the tools carry their own operating instructions, and this bundle links to
them rather than restating them. A marketplace install ships the plugin without this
directory, so nothing here is ever load-bearing for using a tool.

## Tools

* [100xeval](100xeval/index.md) - Behavioral and static evaluation for Claude Code plugins

## Conventions

* **Links are relative, not bundle-absolute.** OKF recommends absolute paths from the bundle
  root (`/100xeval/grader.md`), but GitHub resolves those against the repository root and
  they render dead. This repo is public and read on GitHub, so relative paths win — the spec
  permits them, and they resolve for both audiences.
* **`resource` points at the implementation.** Most concept files name the file that
  implements them, so the bundle doubles as a concept → code map.
* **`type` vocabulary**: `tool` for a whole tool, `concept` for an idea you need to reason
  about it, `reference` for lookup data.
