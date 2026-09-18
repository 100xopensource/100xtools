## Verification, and what a bad read means

Every file is checked against the digest the manifest recorded for it, so a bad read is
named rather than silently accepted as a shorter conversation. `fetch` checks the whole
archive against the digest the server reported before `open` ever looks inside it.

There is **one** failure here, not two: the bytes do not match what the server said it
holds. Both a truncated download and a corrupted one come back the same way, as a digest
mismatch, and neither is fixed by waiting — nothing is syncing in the background, because
the bytes came straight off the server.

So the remedy is always the same: try once more in case the transfer was interrupted, and
if it fails again ask them to send it again. Do not tell the person it is "still
downloading" — that is a shared-folder situation and this is not one.
