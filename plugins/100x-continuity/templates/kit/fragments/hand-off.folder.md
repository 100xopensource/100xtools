Handoffs for {{TEAM}} are filed under {{SYNC_CLIENT}}, here:

```
{{STORE_ROOT}}/{{NAMESPACE}}/
```

That is baked into this plugin. Don't search for it and don't ask about it — if the path
is not on this machine, the shared drive is not set up here yet. Say that, say nothing was
sent, and stop. Creating the folder yourself files the handoff where nobody syncs, and it
looks exactly like success.

{{SYNC_NOTE}}

Inside Cowork the same drive is mounted under `~/mnt/` instead, so the beginning of that
path differs there while the end of it does not.

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
