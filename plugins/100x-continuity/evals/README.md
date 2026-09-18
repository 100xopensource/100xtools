# Behavioral evals for 100x-continuity

Four cases: one on the factory, three on the Kit it emits.

| Case | What it holds the skill to |
| --- | --- |
| `emits-a-working-kit` | writes a usable plugin and a correct marketplace row into someone else's repo, with no placeholder surviving and nothing committed |
| `publishes-a-handoff` | hands a session over through the engine, files a complete bundle, keeps a credential out of it, and speaks to a teammate rather than an operator |
| `continues-from-a-handle` | opens a handoff somebody else made and reports what that session was actually doing, including what it left open |
| `evicted-bundle-is-not-an-empty-session` | calls a not-yet-downloaded archive what it is, and writes nothing over it |

**These are repo-only.** They need the sibling 100xeval plugin, so they are not part of
what a marketplace install operates. They cost money and are **not** in CI.

## Running them

```bash
python3 plugins/100x-continuity/evals/seed.py     # required first — see below
python3 plugins/100xeval/skills/100xeval/scripts/run.py eval \
  --cases-dir plugins/100x-continuity/evals
```

## Three cases run against an emitted Kit, not against this plugin

The factory ships no `hand-off` skill. Pointing a handoff case at `../..` would test a
plugin that structurally cannot do the thing, so the seed **emits a Kit** into each case
root and the case's `plugins:` points at that. Two consequences worth knowing:

- The seed is what proves the emitter still produces something operable. A hand-built
  fixture directory would keep passing after `emit.py` changed, which is the regression
  these cases are best positioned to catch.
- The Kit-facing prompts never name the store, because a real Teammate never would — it
  is baked into the Kit. A prompt that named it would be scoring a plugin nobody has.

## The seed is not optional

Every case starts from state a prompt cannot produce for itself: a session transcript
waiting to be handed over, a store already holding somebody else's handoff, a handoff
whose bytes a sync client evicted, and an otherwise-empty plugin repo with one unrelated
marketplace row in it. Without the seed the prompts point at nothing and the graders fail
for a reason that has nothing to do with the skill.

The seed prints the code it created. **If the fixture content changes, that code changes**
— a publication is named for its own digest — and the two cases carrying it in their
prompt have to be updated to match. That is the one maintenance cost of naming
publications by content, and it is worth it: it is also what makes a second handoff of
unchanged work recognisable.

## How they are graded

The graders read the **store and the emitted files**, not the model's reply. A skill that
reports success over an empty directory is exactly the failure worth catching, and it
reads identically to a real success in the transcript.

Each case also carries at least one **positive** assertion, not just absence checks. A run
that never happened would otherwise score well on "the secret is not in the store", "no
placeholder survived", and "nothing was written over the placeholder" — all trivially true
of a directory nobody touched.

One grader has no on-disk equivalent: `spoke-to-a-teammate-not-an-operator` reads the
reply for internal vocabulary. It is the only check on the half of this product that is
purely about how it sounds, and the Kit's skills are written to a hard rule there rather
than a preference.
