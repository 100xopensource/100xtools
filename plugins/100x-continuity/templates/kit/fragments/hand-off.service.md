Three steps, because the bytes are prepared here and only then sent up.

**Package it**, without filing it anywhere yet:

```bash
python3 "$CARRY" pack --session "$SESSION" \
  --artifact <each file, repeated> \
  --confirm "<a distinctive phrase from this conversation>" \
  --out /tmp/handoff
```

`--confirm` is worth the effort: it checks that phrase really appears near the end of the
conversation being packaged, which is the only thing that catches the wrong session
before it's sent rather than after. Keep `bundle`, `sha256` and `size` from the result.

**Ask for a place to put it.** Call `mint_publication_upload` on the `{{SERVICE_NAME}}`
server with that `sha256` and `size`. It answers with a one-time address and the code the
publication will be known by. Save its whole answer to a file:

```bash
python3 "$CARRY" upload --bundle <bundle> --mint-file <the saved answer>
```

**Read the code** the server gave back — that is what gets passed on. If the server says
this exact content is already up there, nothing changed since last time and the existing
code still works; say so rather than sending a second one.
