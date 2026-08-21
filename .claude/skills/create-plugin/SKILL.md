---
name: create-plugin
description: Scaffolds a new plugin in this repo — manifest, layout, first skill, README, marketplace entry — and takes it through both linters. Use when someone says "create a plugin", "start a new plugin", "add a plugin for X", or "scaffold a plugin" here. Do NOT use for writing one skill inside a plugin that already exists; that is create-skill. Do NOT use for authoring an eval case; that is the 100xeval plugin's own skill.
---

# Create a plugin in this repo

Grounded in [the plugin reference](https://code.claude.com/docs/en/plugins-reference). The
repo invariants in `CLAUDE.md` all apply — most of all that **a plugin is self-contained**: a
marketplace install copies `plugins/<name>/` and nothing else, so anything the plugin needs to
operate lives inside that directory.

Ask what the plugin should *do* before scaffolding anything. If the answer is one workflow, it
is a skill in an existing plugin, not a new plugin.

## 1. Name it

Kebab-case, unique in `.claude-plugin/marketplace.json`. The name becomes the command
namespace, so a skill `foo` in plugin `bar` is `/bar:foo` — read the pair out loud before
committing to it.

## 2. Lay it out

```
plugins/<name>/
├── .claude-plugin/plugin.json   the ONLY thing in this directory
├── README.md                    how to install and run it
└── skills/<skill>/SKILL.md      one directory per skill
```

Every component directory (`skills/`, `agents/`, `commands/`, `hooks/`, `workflows/`) sits at
the plugin root. Inside `.claude-plugin/` they are never found, and the plugin installs looking
empty. Create only the directories the plugin actually uses.

## 3. Write the manifest

```json
{
  "name": "<name>",
  "displayName": "<Display Name>",
  "description": "<one sentence: what it does, for whom>",
  "version": "0.1.0",
  "license": "Apache-2.0",
  "keywords": ["<discovery>", "<tags>"]
}
```

`skills/` is picked up by default — add a `skills` field only for a directory somewhere else.
Path-valued fields (`skills`, `agents`, `commands`, `workflows`, `hooks`, `mcpServers`,
`outputStyles`, `lspServers`) must start with `./` and exist.

If the plugin talks to a data source, declare it in `.mcp.json` at the plugin root and
reference bundled files through `${CLAUDE_PLUGIN_ROOT}` — never an absolute path, which is
correct on your machine only.

## 4. Write the first skill

Hand off to **create-skill**. A plugin whose skills are stubs scores badly and teaches the next
reader the wrong shape.

## 5. Register it

Add an entry to `.claude-plugin/marketplace.json` whose `name` matches `plugin.json` exactly —
installs resolve by the manifest name, and a mismatch fails at install time with a worse
message than the linter's:

```json
{
  "name": "<name>",
  "source": "./plugins/<name>",
  "description": "<same sentence as the manifest>",
  "version": "0.1.0",
  "license": "Apache-2.0",
  "keywords": ["<discovery>", "<tags>"]
}
```

## 6. Optionally add concepts to `docs/`

Only if the plugin introduces ideas a reader needs *explained* rather than *operated* — one
concept per file, listed in `docs/index.md`. Operating instructions stay in the plugin, because
`docs/` is not shipped with it.

## 7. Pass the gates

```bash
python3 scripts/validate_plugins.py                                          # will it load?
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only    # is it any good?
python3 scripts/check_docs.py                                                # only if docs/ changed
```

The static score must be **1.00** before merge. When it is not, **lint-plugin** prints the
findings behind the number; **review-plugin** covers what neither linter can see.
