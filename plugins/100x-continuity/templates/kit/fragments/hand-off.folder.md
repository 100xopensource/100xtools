One command does the whole thing — package it, strip out anything credential-shaped, and
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
