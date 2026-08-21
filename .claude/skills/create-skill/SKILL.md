---
name: create-skill
description: Writes or sharpens a SKILL.md inside one of this repo's plugins — frontmatter, the trigger description, progressive disclosure into references/ and scripts/ — and takes it through both linters. Use when someone says "create a skill", "add a skill to <plugin>", "make a skill that…", "turn this workflow into a skill", or asks why a skill never fires. Do NOT use for scaffolding a whole new plugin; that is create-plugin.
---

# Write a skill

Grounded in [the skills docs](https://code.claude.com/docs/en/skills). A skill is the
instructions Claude follows once it decides this task is yours. Two things decide whether it
works: whether the description fires at the right moment, and whether the body earns the
context it spends.

Before writing, check whether a skill in this repo already does the job — a thin skill that
routes to an existing one beats a second copy of its logic, and duplicate prose across sibling
SKILL.md files is what the `token_efficiency` sub-score is looking for.

## The frontmatter

Only `description` really matters; everything else is optional.

```yaml
---
name: <kebab-case, matches the directory>
description: <what it does, when to use it, what it is not for>
---
```

| Field | Use it for |
| --- | --- |
| `name` | In a plugin skill this replaces the last segment of the command: `name: fancy` in `plugins/p/skills/review/` gives `/p:fancy` |
| `description` | The trigger surface. If omitted, the first paragraph of the body is used instead |
| `when_to_use` | Extra trigger phrases and example requests, appended to `description` in the listing |
| `allowed-tools` | Tools that skip the permission prompt for the turn that invokes the skill |
| `disallowed-tools` | Tools removed from the pool while the skill is active |
| `disable-model-invocation` | `true` when only a person should fire it — anything with side effects |
| `paths` | Glob patterns that gate automatic loading to matching files |
| `model`, `effort`, `context`, `agent`, `background`, `hooks`, `argument-hint`, `arguments`, `shell`, `metadata`, `license`, `compatibility` | Everything else the runtime accepts |

`description` and `when_to_use` are concatenated in the listing and **truncated at 1,536
characters**, so the trigger and the "not for" clause go first — a boundary clause past the cut
does not reach the model at all.

## The description is the whole trigger

It is the only part of the skill that is always in context, and the model chooses from it alone.
Write it in the third person, present tense, and make it name:

- **what the skill does**, in a verb-first clause;
- **when to use it** — the situations and the phrases a person actually types;
- **what it is not for**, pointing at the skill that is. This is what stops two skills fighting
  over the same turn.

`Analyzes data.` never fires. `Scores a plugin's design and explains every finding … do NOT use
for running behavioral evals` fires exactly when it should.

## The body

Keep `SKILL.md` under 500 lines and put depth where it is paid for on demand:

```
skills/<name>/
├── SKILL.md        the workflow: lean, imperative, says why a step matters
├── references/     long material the body tells the model to read by name
└── scripts/        code the model runs instead of re-deriving it every time
```

Two habits the linter checks, both worth understanding rather than obeying:

- **Ship no reference the body never names.** An unread `references/` file is pure weight, and
  a body naming a file that does not exist sends the model looking for nothing.
- **Reference files do not chain.** A reference pointing at another reference makes the model
  read the whole tree to find one fact.

Invoke a bundled script through `${CLAUDE_PLUGIN_ROOT}` and, when it should run without a
prompt, name the same path in `allowed-tools`:

```yaml
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/render.py *)
```

The rendered body enters the conversation once and stays there for the session — the file is
not re-read on later turns. Write guidance that applies throughout the task as standing
instruction, not as a step that happens once.

## Pass the gates

```bash
python3 scripts/validate_plugins.py plugins/<plugin>
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval --static-only
```

The static score must be 1.00 before merge; **lint-plugin** prints the findings behind the
number. Then check the description against behavior rather than taste: three cases — one that
should fire it, one that should not, one genuinely ambiguous — say more than another reread.
