---
name: verify
description: Proves an emitted handoff plugin actually works — runs its contract test, hands a session through it, opens it back, and reports which facts are proven and which cannot be yet. Use after building a kit, before anyone ships one to their team, or when a teammate reports that handing off or picking up is failing.
---

# Prove the Kit works

An emitted Kit is a directory of plausible-looking files until something has gone through
it and come back out. This always produces a result — never a question about whether to
try — and it is explicit about the difference between *proven*, *proven against a stand-in*,
and *cannot be proven yet*.

That last category is real and small: for a service store, nothing can exercise the
org-registered server until it is registered. Everything else is testable today.

## 1. Read what the Kit thinks it is

```bash
KIT=<the emitted plugin directory>
cat "$KIT/kit.json"
python3 "$KIT/scripts/run.py" where
```

Check the store kind matches the plan, the root or server name is what the team uses, and
the source says `kit`. Anything else means an environment variable or a config file on
*this* machine is shadowing the baked value — so what you are about to test is not what a
Teammate gets. Say so and unset it.

For a folder Kit, confirm the root exists and is writable. A path that is right in spirit
and absent on disk is the most common failure, and emitting cannot catch it.

## 2. Run the contract test

```bash
cd "$KIT" && python3 tests/contract_test.py
```

This is the backbone: deterministic, no model, no money, and it runs against a synthetic
session in a throwaway home rather than anyone's real conversation. It covers packing,
redaction, reproducibility, the credential refusal, reading back, and both damage kinds —
and for a service Kit, that a download is checked against the digest the server reported.

Read the skips. They are not failures; they say which half of the contract this Kit's store
does not have.

If it fails, stop and report that. Everything below assumes the mechanics hold.

## 3. Hand a real session through it

The contract test uses a synthetic conversation on purpose. This step uses the actual one,
which is the only way to prove that discovery finds a real session on this machine:

```bash
python3 "$KIT/scripts/run.py" publish --session "${CLAUDE_SESSION_ID}" \
  --artifact <a small file written for the purpose> \
  --confirm "<a distinctive phrase from this conversation>"
```

For a service Kit this is `pack`, then the server's `mint_publication_upload`, then
`upload --bundle`. If the server is not registered yet, say so plainly and skip **this step
only** — it is a missing prerequisite, not a failure, and the contract test has already
covered everything up to the network.

Then open it again with the handle, and check the digest reads as this conversation, the
artifact is intact, and the session id is real rather than `unattributed`.

## 4. The receiving half

The part nobody tests. A handoff works when *the other person* can open it, and for a
folder store that depends on sharing arranged outside this plugin.

Ask the Operator to open the same handle from a second machine or a colleague's account. If
they cannot right now, name the receiving half as **unverified** — never report a green
round-trip over it. A Kit that only works for its author is the failure this step exists to
catch.

## 5. Report in three buckets

Say it in this shape, because "it works" hides exactly the thing that bites later:

- **Proven** — what actually ran here, with the contract test's count.
- **Proven against a stand-in** — the synthetic session, and for a service store anything
  checked without the live server.
- **Not proven yet** — the registered server, the receiving half, anything skipped, and why.

Then one sentence: ready to ship, or not. Never report a pass over a step that was skipped.

## Self-check

- [ ] `where` was read and the source confirmed as `kit`, not a local override.
- [ ] The contract test ran, and its skips were read rather than ignored.
- [ ] A real session went through, or the reason it could not was named.
- [ ] The redaction count was reported with its caveat, never as a safety claim.
- [ ] The receiving half was tested or explicitly listed as unproven.
- [ ] The report separates proven, stand-in, and not-yet — not one word for all three.
- [ ] The verdict is one sentence, and it is not a pass over a skipped step.
