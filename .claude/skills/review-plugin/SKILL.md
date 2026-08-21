---
name: review-plugin
description: Reviews a new or changed plugin in this repo before commit or on a PR — whether its skills will trigger, whether it stays self-contained, whether documentation lands on the right surface, and whether a trust-boundary file quietly loosened. Use when someone says "review my plugin", "is this plugin good?", "review this PR", or asks for a second pass before merging. Do NOT use to run the linters and explain their findings; that is lint-plugin.
---

# Review a plugin

The judgment pass over what the linters cannot see. Read the change first —
`git status --short`, `git diff --name-only`, then every touched `SKILL.md`, manifest, README,
and template — and run `lint-plugin` before reviewing by hand, so mechanical findings are not
re-derived as prose.

Report what you find. Do not edit the author's files unless asked.

## What to look at

**Will it trigger?** The highest-value thing in the review. Each `description` is the only part
of a skill always in context. Check it names the situations and the phrases someone types, and
says what the skill is *not* for. Two skills whose descriptions overlap will fight over the same
turn, and the loser looks broken rather than unselected. Quote the line and propose replacement
wording, not a verdict.

**Is it self-contained?** A marketplace install copies `plugins/<name>/` and nothing else. Any
reference outward — to `docs/`, to the repo root, to a sibling plugin — is a runtime failure for
whoever installs it. Bundled paths go through `${CLAUDE_PLUGIN_ROOT}`; an absolute path is
correct on the author's machine only.

**Is the documentation on the right surface?** Three surfaces, three audiences, and the wrong
one is a common miss:

| Surface | Answers | Ships |
| --- | --- | --- |
| `plugins/<name>/README.md` | how do I install and run this? | yes |
| `SKILL.md` + `references/` | how should Claude operate it? | yes |
| `docs/` | what is this concept, and why does it exist? | no |

Operating instructions in `docs/` are unreachable for an installed plugin. Concepts restated in
both places drift apart, and nothing says which copy is current.

**Does the skill earn its context?** Body under 500 lines, depth in `references/` the body names
by file, repeated code in `scripts/`. Long prose duplicated between sibling skills is what drags
`token_efficiency` down, and it reads as copy-paste to the next author too.

**Do the parts match?** README describes the skills that exist and all of them; the marketplace
entry matches the manifest; every MCP server a skill calls is declared in `.mcp.json`; secrets
come from the environment rather than the file.

**Did a trust-boundary file change?** `.github/workflows/*`,
`plugins/100xdrift-check/templates/workflows/drift-check.yml`, and
`plugins/100xdrift-check/templates/skills/drift-check/SKILL.md` decide what CI does with model
output and which tools the model gets. Checks there only ever tighten. A change that removes a
guard, widens a tool allowlist, or relaxes a permission needs saying out loud in the PR
description, and review by someone other than the author.

Two coupled contracts worth checking together, because either half alone degrades silently: the
drift-check skill's `drift-status` marker and the workflow that parses it, and the workflow's
`paths:` list and the `git diff` pathspec in its collect step.

**Would this leak?** Real connector URLs, customer or store names, internal ticket prefixes,
internal doc paths, captured tool output, vendor system prompts. Fixtures use `Acme` and
`example.com`. This repo was extracted from a private one and has had a leak reach a commit, so
read added fixtures rather than skimming them.

## What to report

- **Verdict** — ready, or needs changes.
- **Must fix** — each with the file, the line, and the edit. Anything that fails to load, leaks,
  or loosens a guard belongs here.
- **Worth fixing** — ordered by how much it changes the plugin's behavior in a real session.
- **Considered and fine** — one line, so the author knows what was actually looked at.

Be specific enough to act on: `skills/foo/SKILL.md:3 — the description says what it does but
never when; add "Use when someone says …"` beats "descriptions could be sharper".
