**Check the place exists first.** `python3 "$CARRY" where` names the folder this Kit
files into. If that folder is not on this machine, stop and say the shared drive is not
set up here yet, and that nothing was sent. Creating the folder yourself would file the
handoff somewhere nobody syncs, and it would look like it worked.

Then one command does the whole thing — package it, strip out anything credential-shaped, and
file it where {{TEAM}} can reach it:

```bash
python3 "$CARRY" publish --session "$SESSION" \
  --artifact <each file, repeated> \
  --confirm "<a distinctive phrase from this conversation>"
```

`--confirm` is worth the effort: it checks that phrase really appears near the end of the
conversation being packaged, which is the only thing that catches the wrong session
before it's sent rather than after.

Read `handle` from the result — that is the code to pass on. If `already_published` comes
back true, nothing changed since last time and the same code still works; say so rather
than sending a second one.
