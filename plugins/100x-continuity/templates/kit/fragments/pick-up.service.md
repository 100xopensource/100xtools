Two steps: ask the server for the contents, then open them.

Before either, satisfy yourself the server is reachable at all — there should be a tool
whose name *ends* with `__resolve_publication`, most often written
`{{TOOL_PREFIX}}resolve_publication`. The leading part varies with how your team added the
server; the ending does not.

Nothing to match means this Claude has no connection to your team's store, which is not
the same as a bad code and is not something to work around. Say that plainly and ask them
to have it connected, then stop.

When it is there, call `resolve_publication` on the `{{SERVICE_NAME}}` server with the
code they sent. It answers with a one-time address to read from and the digest to expect.
Save that answer to a file, then:

```bash
python3 "$OPEN" fetch --mint-file <the saved answer> --out /tmp/incoming.zip
python3 "$OPEN" open --bundle /tmp/incoming.zip
```

`fetch` refuses anything whose contents don't match the digest the server named, so what
`open` reads is what your colleague sent. The folder it unpacked into comes back as
`unpacked_to`.

If the server says you're not allowed to read that code, it means the person who sent it
hasn't shared it with you yet — that's a message to them, not something to work around.
