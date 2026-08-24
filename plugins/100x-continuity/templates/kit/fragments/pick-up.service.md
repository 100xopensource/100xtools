Two steps: ask the server for the contents, then open them.

Call `resolve_publication` on the `{{SERVICE_NAME}}` server with the code they sent. It
answers with a one-time address to read from and the digest to expect. Save that answer
to a file, then:

```bash
python3 "$OPEN" fetch --mint-file <the saved answer> --out /tmp/incoming.zip
python3 "$OPEN" open --bundle /tmp/incoming.zip
```

`fetch` refuses anything whose contents don't match the digest the server named, so what
`open` reads is what your colleague sent. The folder it unpacked into comes back as
`unpacked_to`.

If the server says you're not allowed to read that code, it means the person who sent it
hasn't shared it with you yet — that's a message to them, not something to work around.
