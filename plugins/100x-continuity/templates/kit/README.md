# {{KIT_NAME}}

Hand a Claude session to a colleague, and pick up one they handed to you.

Built for {{ORG}} by [100x-continuity]({{FACTORY_URL}}) {{FACTORY_VERSION}} on
{{EMITTED_AT}}. It is tailored to how {{TEAM}} works — where sessions are kept is already
set, so there is nothing to configure.

## Using it

Two skills, both in ordinary words:

| Say something like | What happens |
| --- | --- |
| "hand this over to Dana" | The conversation and the files you name are packaged, scrubbed of anything credential-shaped, and filed. You get back one short code to send. |
| "pick up what Dana sent me — `<code>`" | That code is opened, checked, and read back: what the work was, where it stopped, and the files that came with it. |

{{STORE_SENTENCE}}

## How a handoff actually moves

{{ARCHITECTURE}}

## What travels, and what doesn't

**Travels:** the conversation, a readable summary of it, and the files named at handoff.

**Does not travel:** anything credential-shaped, which is removed on the way out; and
everything the host knows that isn't the conversation — what it cost, which tools were
enabled, what the system prompt said. That is deliberate. A handoff is a record of the
conversation, not of the machine it ran on.

Removal is pattern-based. It catches keys, tokens and passwords in the shapes they
usually take. **It does not catch a secret written out in ordinary prose**, so treat a
handoff as visible to everyone who can reach {{TEAM}}'s copies.

## Updating it

This plugin was generated. Edits here are kept only until the next time someone re-runs
the 100x-continuity factory against this repo, which rewrites it in place. Changes worth
keeping belong in the factory's answers, not in this directory.

## Checking it works

```bash
python3 tests/contract_test.py     # deterministic, free, no model — run this one
python3 scripts/run.py where       # where handoffs go, and which setting decided it
```

The contract test packs a synthetic session, scrubs it, files it, reads it back, and
refuses damaged bytes — everything this plugin promises that does not need a person. It
never touches a real conversation. Run it after any change, and when somebody reports that
handing over or picking up is broken.

`evals/` holds the cases checking what the *model* does with the two skills. They need a
model and cost money, so they gate nothing; see that directory's README.
