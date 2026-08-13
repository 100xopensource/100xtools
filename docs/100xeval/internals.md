---
type: reference
title: Internals
description: Directory layout of the 100xeval plugin, and how to run the engine's own test suite.
resource: ../../plugins/100xeval/skills/100xeval
tags: [100xeval, reference, contributing]
generated:
  by: claude-code/claude-opus-5
  at: 2026-08-13T00:00:00Z
---

# Internals

## Layout

```
.claude-plugin/plugin.json              manifest
skills/100xeval/
├── SKILL.md                            the model-invoked skill (the front door)
├── references/
│   ├── case-schema.md                  every case.yaml field + every grader parameter
│   └── managing-testcases.md           lifecycle, best practice, gotchas, reading a red scorecard
├── scripts/                            ← the runtime payload: what ships and what Claude invokes
│   ├── run.py                          CLI entrypoint
│   └── engine/                         loader · orchestrator · graders · judge · reporter · lint · static
│       ├── entrypoints/                surface system prompts (none ship — see its README)
│       └── harnesses/                  runtimes: claude_code · codex (seam)
└── tests/                              stdlib unittest, no live calls — beside scripts/, not in it
```

## Running the engine's tests

```bash
cd plugins/100xeval/skills/100xeval
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

`tests/` deliberately sits *beside* `scripts/` rather than inside it: `scripts/` is the
runtime payload — it ships with the plugin as-is and is the directory Claude invokes — so the
suite has no business being in there. Tests import `engine.*` absolutely, which is what
`PYTHONPATH=scripts` resolves. No live model or MCP calls; the suite runs offline.

## See also

* [Check IDs](check-ids.md) - adding a static check
* [Harness](harness.md) - the runtime seam
