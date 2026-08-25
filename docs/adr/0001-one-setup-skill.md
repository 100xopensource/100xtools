# 1. One set-up skill, with the approval gate inside it

Date: 2026-08-24

## Status

Accepted.

## Context

100x-continuity started with the work split across two Operator-facing skills: `plan`
interviewed and wrote `continuity-plan.md`; `emit` turned that into a plugin. `verify`
was a third, and `store-service` a fourth. The split matched how the repo's other
generator, 100xdrift-check, exposes two separate installer skills, and it made the
approval gate its own visible act: you ran `plan`, you read what came back, you ran
`emit`.

The first real run showed what that costs. Across 648 records the Operator typed 13
times, and three of those turns were spent restarting a chain that had stalled:

- `verify` was named four times and never invoked — *"say so and I'll drive a real
  round-trip"*, then again two more times.
- The Operator asked `"how can we test this?"` about facts the `verify` skill exists to
  establish.
- Then `/wait-what` — *"try explaining to me again"* — because by then the session had
  drifted into debugging a testing harness.

A model that has finished `emit` has finished the thing it was asked to do. Naming the
next skill reads as a complete, well-mannered handoff back to the human. It is also
exactly where the work stops.

## Decision

One entry point, `set-up-handoff`, running interview → plan → approval → write → verify.
`plan` and `emit` stop being skills; the Plan document and `emit.py` both remain, and
`CONTEXT.md` keeps both as concepts. The skill's self-check asserts that `verify` was
*run*, not offered.

`verify` stays separately invokable. It has a second audience — a Teammate reporting that
picking up is broken — and re-interviewing that person about their storage would be
absurd. `store-service` stays separate for the same reason: it is only reached by teams
that chose a service store, and it is run again whenever that server changes.

## Consequences

The approval gate is no longer visible in the skill list. It is one question in the middle
of one skill, and if that question is ever skipped, a plugin lands in somebody's repo
without a human reading what it will be. The self-check names it; nothing enforces it.

`set-up-handoff` is a longer skill than either half was, and closer to the body-length cap
that `PD1` enforces. Detail that would previously have gone in prose has to go to
`references/`.

Reversing this means renaming again, after Operators have muscle memory and after emitted
Kits carry a README mentioning the name.

We accept those because the alternative failed in the only real trial it had, and it
failed silently — the split produced a green-looking session with an unverified plugin in
a repo, which is worse than a visibly incomplete one.
