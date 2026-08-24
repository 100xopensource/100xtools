---
name: hand-off
description: Hands this session to someone else — the conversation, and any files worth sending — and gives back one short code to pass on. Use when someone says to hand this over, send this to a colleague, pass this on, share this session, or wants another person to carry this work on. Do NOT use for ordinary file writes that belong in the working folder.
---

# Hand this session over

Someone wants a colleague to carry this work on. Package up what happened here, put it
where {{TEAM}} can reach it, and give back the one short code they pass to that person.

Everything about where things are kept is already decided — don't ask, and don't look.

## How to work

- **Say very little.** Two lines in the chat: one before you start, one when it's done.
- **Ask with a pop-up, not a question in the chat.** Use `AskUserQuestion` when there's a
  real choice, with the sensible option first and why in a short clause.
- **Settle what you can settle yourself.** You know which files this session touched.
  Don't ask them to list what you already saw.
- **Plain words only.** They're handing work to a colleague. Never say bundle, publish,
  store, namespace, redact, transcript, mount, or handle — say *"a copy of this session"*,
  *"the code to send them"*, *"where your team keeps these"*.

## 1. Find the tools

```bash
CARRY="${CLAUDE_PLUGIN_ROOT:-}/scripts/run.py"
if [ ! -f "$CARRY" ]; then
  ID=$(printf '%s' "$SKILL_BASE_DIR" | tr '/' '\n' | grep -m1 '^plugin_')
  CARRY="$HOME/mnt/.remote-plugins/$ID/scripts/run.py"
fi
SESSION="${CLAUDE_SESSION_ID}"
```

The first path is the ordinary one. The second is for a session where the folder this
skill is told it lives in doesn't resolve — the files are reachable under
`~/mnt/.remote-plugins/plugin_<id>/` instead. Search only inside that folder if you have
to look; searching all of `~/mnt` is slow, because the team's shared folders are under
there too.

Results come back as JSON. A failure exits non-zero and carries two strings: **`say`**
is one plain sentence written for the person in front of you — repeat that one.
**`hint`** is the engine talking to whoever maintains it, and it uses words like
*transcript* and *bundle*; never put it in the chat.

## 2. Check you're packaging the right conversation

```bash
python3 "$CARRY" sessions --session "$SESSION"
```

Read `current.turns` and `current.title` and see that they match what actually happened
here. If they don't, stop and say so — packaging the wrong conversation would send a
colleague somebody else's work.

## 3. Decide what goes with it

The conversation always goes. Files go only if you name them: the note that was just
written, the spreadsheet, the draft — what the next person actually needs. Not everything
in the folder, not build output, not something that was only read.

If it's genuinely unclear which files matter, that's a pop-up with two or three named
options — never an open question.

## 4. Send it

{{HANDOFF_STEPS}}

## 5. Say one line

Give them the code and who to send it to, in plain words — *"Done. Send Dana this:
`<code>` — she can open it in her Claude and pick up where this left off."*

Then two things you must not skip, said simply:

- If anything couldn't be included — a file that moved, a part of the conversation too
  long to keep whole — say it in the same breath. It never stops the handoff.
- Never say the copy is safe, clean, or has no secrets in it. Keys and passwords are
  stripped out on the way, and that is what you can say; anything written out in
  ordinary words is still in there.

## If something stops you

- **A file that looks like it holds a password or a key** — this one stops, and it is
  the clearest case for a pop-up there is. Put it to them with `AskUserQuestion`, naming
  the file, with three options: take the value out first, leave that file behind, or send
  it as it stands. Do not ask this one in the chat — it is a decision with a consequence,
  and a question in the chat gets skimmed.
- **Anything else** — a file that vanished, a piece that was too big — never stops the
  handoff. Note it in your final line and carry on.

## Before you decide what to leave out

Read [references/what-travels.md](references/what-travels.md) before you override any
refusal. It carries what a handoff contains, what is deliberately never looked at, exactly
what the scrubber removes and what it cannot, and why files travel verbatim rather than
being rewritten.

## Self-check

- [ ] The conversation checked out as this one before anything was packaged.
- [ ] Files were chosen deliberately, by name.
- [ ] The code was given exactly as it came back, with who to send it to.
- [ ] Anything that couldn't be included was mentioned in the same message.
- [ ] Nothing was described as safe or clean.
- [ ] A file that looked like it held a key stopped things and got a pop-up, not a shrug.
- [ ] The chat got two lines, not a running commentary.
