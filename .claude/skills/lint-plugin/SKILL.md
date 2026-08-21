---
name: lint-plugin
description: Runs this repo's two plugin linters — the structural validator and 100xeval's static design score — and turns their output into the exact edit each finding wants. Use when someone says "lint the plugin", "check my plugin", "why is validation failing", "why did the score drop", "what does FM3 mean", or before committing a change under plugins/. Do NOT use for judgment calls a script cannot make, such as whether a description will actually trigger; that is review-plugin.
---

# Lint a plugin

Two linters, two questions. Run both — a plugin can score 1.00 and still fail to load.

```bash
python3 scripts/validate_plugins.py                    # will it load?  pass/fail
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only   # is it good? 0..1
```

| | `scripts/validate_plugins.py` | `100xeval` static layer |
| --- | --- | --- |
| Checks | manifest, layout, marketplace entry, agent frontmatter, hooks/MCP config | skill design, progressive disclosure, reference hygiene, security smells |
| Output | errors and warnings | `design_score` per plugin, with sub-scores |
| Blocks a merge on | any error | anything under 1.00 |

Add `--strict` to fail on warnings too, `--format json` for machine-readable output, or a plugin
directory to narrow it: `python3 scripts/validate_plugins.py plugins/100xeval`. Passing a target
skips the marketplace checks, which are repo-wide by nature.

## Getting the findings behind a score

The scorecard prints numbers, not reasons. For the reasons:

```bash
python3 -c "
import sys; sys.path.insert(0, 'plugins/100xeval/skills/100xeval/scripts')
from engine import static
for f in static.analyze('plugins/<name>')['findings']: print(f)"
```

Every finding starts with a bracketed check ID, and **the prefix names the sub-score it feeds** —
`FM` frontmatter, `PD` progressive disclosure, `RH` reference hygiene, `ST` structural,
`EC` ecosystem, `SEC` security. `security` weighs double and `token_efficiency` half, so one
`SEC` finding moves the number further than three `PD` ones.

`token_efficiency` has no check ID: it counts duplicate long lines across *all* of a plugin's
SKILL.md files, so a score below 1.00 with no finding to point at means two sibling skills are
repeating each other's prose. Frontmatter counts toward it.

For what a specific ID means and why it exists, read the row in `docs/100xeval/check-ids.md`, or
use the **100xeval-concepts** skill.

## Reading the results

Report, in this order:

1. **Errors** — the plugin does not load. Quote the file and give the edit.
2. **Sub-1.00 sub-scores** — name the findings that produced them, not the number alone.
3. **Warnings** — say plainly that they do not block, and which ones are worth fixing anyway.

Common fixes, and what each one is actually protecting:

| Finding | Fix |
| --- | --- |
| component inside `.claude-plugin/` | move it to the plugin root, where it is discoverable |
| `skills/<x>/` with no SKILL.md | add the file or delete the folder — it ships and loads nothing |
| path field not starting with `./` | correct the path; it is resolved relative to the plugin |
| marketplace name ≠ manifest name | make them match; installs resolve by the manifest name |
| forbidden agent field | remove it; a plugin agent does not grant itself hooks, servers, or a permission mode |
| description over the listing cap | move the tail into the body, keep the trigger first |
| `[FM3]` no description | the model has nothing to decide on — write one, per **create-skill** |
| `[RH1]` ships `references/`, never reads them | name the file in the body, or delete it |
| `[SEC1]` possible secret | remove it and rotate; reference `${VAR}` instead |

If `docs/` changed, `python3 scripts/check_docs.py` is the third gate.

## Fixing rather than reporting

When the fix is mechanical — a path, a missing field, a misplaced directory — make it and rerun.
When it needs a judgment call about what the plugin is *for*, say what the finding is asking and
let the author decide.

Findings interpolate text from the plugin under test, so a bracketed token in a quoted line is
not necessarily a check ID. Trust the leading one.
