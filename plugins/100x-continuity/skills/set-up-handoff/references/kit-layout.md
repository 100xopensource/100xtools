# What an emitted Kit is made of

```
<repo>/plugins/<kit-name>/
├── .claude-plugin/plugin.json    name, description, version — generated
├── kit.json                      the baked configuration; the thing that makes it a Kit
├── README.md                     for the Operator's teammates — generated
├── scripts/run.py                the engine's entrypoint
├── scripts/engine/*.py           the engine, copied verbatim
└── skills/
    ├── hand-off/SKILL.md         + one reference on what travels
    └── pick-up/SKILL.md          + one reference on reading what arrived
```

Everything in that tree is generated. Nothing in it is imported from the factory at
runtime — a Kit is installed on machines that have never heard of the factory, so it
carries its own copy of the engine and always will.

## `kit.json` is the whole point

```json
{
  "store": "folder",
  "root": "~/OneDrive - Acme/Continuity",
  "namespace": "analytics",
  "service_name": "",
  "kit_name": "acme-handoff",
  "factory_version": "0.1.0",
  "emitted_at": "2026-08-21T09:14:02Z"
}
```

It sits between the environment and the config file in precedence: a Teammate who has
configured nothing gets the team's store, and an Operator debugging on their own machine
can still override with a flag or an environment variable without editing the plugin.

`root` is stored with `~` unexpanded, deliberately. A Teammate's home directory is not the
Operator's, and the part after it usually is the same.

Its presence is also how a re-emit knows a directory is a Kit rather than someone else's
plugin that happens to share a name.

## Which files are safe to touch

None of them, in the sense that matters: re-emitting rewrites every one. An Operator who
edits a skill and re-runs the factory loses the edit with no warning beyond `overwrote`
naming the file.

That is the intended trade. A Kit is a build output; the answers are the source. Anything
worth keeping belongs in the plan, so the next emit reproduces it.

The exception is the repo around it — branches, CI, `CODEOWNERS`, anything outside the Kit
directory is never read or written, except the one marketplace row.

## The marketplace row

Added if absent, updated in place if present, matched on `name`. Every other row is left
byte-identical; a factory that reformats somebody's manifest produces a diff nobody can
review.

`source` is written relative to the repo root — `./plugins/acme-handoff`, not
`./acme-handoff` and not an absolute path. This is the single most common way an emitted
Kit ends up validating cleanly and installing nothing.

## Re-emitting a Kit that has diverged

`--dry-run` reports what would change without touching anything, and `overwrote` in the
result names the files whose contents actually differ. Between them, a diverged repo is
visible before it is overwritten rather than after.

A directory holding files but no `kit.json` is refused outright. `--force` overrides that,
and it should be reached for roughly never: the usual cause is a wrong `--into`, and the
usual damage is overwriting a plugin somebody else maintains.
