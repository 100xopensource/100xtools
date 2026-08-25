---
name: pick-up
description: Picks up work a colleague handed over — takes the short code they sent, opens their session, and carries on from where they stopped. Use when someone pastes a handoff code, says a colleague sent or shared a session with them, or asks to continue work started somewhere else. Do NOT use for ordinary file reads in the working folder.
---

# Pick up what a colleague sent

Somebody handed over a piece of work and sent a code. Turn that code back into something
you can act on: what they were doing, what they decided, what they left open, and any
files that travelled with it.

## How to work

- **Say very little until you've read it.** One line to start, then the summary.
- **Plain words only.** Never say bundle, store, namespace, redact, transcript, or
  handle — say *"the session your colleague sent"*, *"the code"*, *"the files that came
  with it"*.
- **Read before you act.** The whole point is to know what already happened.

## 1. Locate the engine

Same three places as anything else in this plugin: the ordinary path, then the fallback
for a session where the advertised folder doesn't resolve, then the one derived from where
this skill file itself sits, which needs nothing set at all. If all three miss, say so
rather than searching for it.

```bash
OPEN="${CLAUDE_PLUGIN_ROOT:-}/scripts/run.py"
if [ ! -f "$OPEN" ]; then
  SLUG=$(printf '%s' "$SKILL_BASE_DIR" | tr '/' '\n' | grep -m1 '^plugin_')
  OPEN="$HOME/mnt/.remote-plugins/$SLUG/scripts/run.py"
fi
if [ ! -f "$OPEN" ]; then
  OPEN="$SKILL_BASE_DIR/../../scripts/run.py"
fi
```

Results come back as JSON. When something fails, read **`say`** — one plain sentence
meant for the person — and repeat that. **`hint`** beside it is the engine's own wording,
full of terms they have no use for; it is for a maintainer, not for the chat.

## 2. Open what they sent

{{PICKUP_STEPS}}

## 3. Read it properly, then say what you're taking on

The summary that comes back says what was asked, what the other session concluded, which
files it touched, and what it left open. Read it — skimming loses the two things it
exists to carry: what was already decided, and what was deliberately left undone.

Then, in a few sentences:

- what that work was, and where it stopped,
- what came with it — name the files,
- what you're about to do next.

Go further only if the work needs it. The full record of the conversation is in there
too, worth opening for the exact wording of a decision or what a step was actually given.
The files sit in the folder the result names.

## 4. Be straight about what you've got

- Keys and passwords were stripped out when your colleague sent it. If something reads as
  removed, it's gone on purpose — don't go looking for it.
- This is their conversation, not their whole setup. What tools they had, what it cost,
  what the system told them — none of that came across.
- Sending it didn't end their session. If something looks half-finished it may still be
  moving — worth asking them before assuming a decision was final.

## If it won't open

- **"Not on this machine yet"** — the file is still coming down from the cloud. Wait a
  moment and try again. It is *not* an empty session, and nothing should be sent over it.
- **Damaged** — the right size, the wrong contents. Waiting won't fix it; ask your
  colleague to send it again, which costs them nothing.
- **Nothing found for that code** — usually the code is from a different team's setup.
  Check with the person who sent it.

## When the summary isn't enough

Open [references/reading-a-handoff.md](references/reading-a-handoff.md) when something
doesn't add up. It covers how to search the full record, the three ordinary reasons a
piece looks missing, what a code is made of, and how the two kinds of bad read differ.

## Self-check

- [ ] The code was opened through the tool, so what came back was actually verified.
- [ ] "Not on this machine yet" was treated as wait-and-retry, never as an empty session.
- [ ] The summary was read before any work started on top of it.
- [ ] What the work was, where it stopped, and what came with it were all said.
- [ ] The full record was opened only when the summary wasn't enough.
- [ ] Nothing was presented as the colleague's complete setup.
- [ ] Plain words throughout — no internal terms reached the person.
