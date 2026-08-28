**Check the server is there before you package anything.** Look for a tool whose name
*ends* with `__mint_publication_upload`. It usually reads
`{{TOOL_PREFIX}}mint_publication_upload`, but the exact spelling depends on how your team
added the server, which is why you match on the ending rather than the whole name.

If no tool matches, stop here. Say one line — *"I can't reach where your team keeps these,
so I haven't sent anything. Whoever set this up needs to connect it to this Claude first."*
— and leave it there. Do not file the copy somewhere else instead: a handoff nobody else
can open is worse than saying it did not happen.

With the tool there, three steps, because the bytes are prepared here and only then sent up.

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
