```bash
python3 "$OPEN" open --handle "<the code they sent>"
```

Paste the code exactly as it arrived. The tool finds it, checks the contents are whole
and unaltered, and unpacks them — the folder it used comes back as `unpacked_to`.

It resolves the code against this team's own store, which is already configured: a
{{SYNC_CLIENT}} folder whose root ends in `{{NAMESPACE}}`. There is nothing to locate, so
a code that finds nothing is a fact about the code or about syncing, never a reason to go
hunting through the drive. Under Cowork that same drive arrives beneath `~/mnt/`.
