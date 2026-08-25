## Verification, and the two ways a read goes wrong

Every file is checked against the digest the manifest recorded for it, so a bad read is
named rather than silently accepted as a shorter conversation.

- **Not materialized yet** — the archive is in the shared folder but its bytes are not on
  this machine. Sync clients reclaim disk by dropping file contents while leaving names in
  place, and a plain read returns short or empty bytes with no error. Let the client finish
  downloading, then retry. Never read it as an empty session, and never hand anything over
  the top of it — that would replace a placeholder and lose the copy still in the cloud.
- **Damaged** — right length, wrong bytes. Waiting will not fix this one. Ask them to send
  it again; it costs them nothing, and an unchanged resend is recognised as the same
  handoff rather than filed twice.

The distinction is real here because a sync client is what went wrong, and the two causes
have different remedies. Telling them apart is why every read is verified rather than
trusted.
