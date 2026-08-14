# Synced folders — picking one, and what it does to your data

The local backend is a plain directory. It becomes a *cloud* backend when you point it at a
folder a consumer sync client already watches. The plugin does no syncing and has no
credentials for any of these services — the client that is already running does the work.

This is the cheapest way to get session artifacts off one machine, and it is why the store
is built the way it is. It also has sharp edges that only appear days later, so they are
worth knowing before you choose a folder.

## Where the folder usually lives

| Client | Typical root | Notes |
| --- | --- | --- |
| iCloud Drive | `~/Library/Mobile Documents/com~apple~CloudDocs/` | Evicts file contents — see below |
| OneDrive / SharePoint | `~/OneDrive/`, or `~/OneDrive - <Org>/` | A synced SharePoint library works the same way |
| Google Drive | `~/Google Drive/My Drive/` | Streaming mode behaves like iCloud eviction |
| Dropbox | `~/Dropbox/` | Smart Sync behaves like iCloud eviction |

Set it once:

```bash
export CONTINUITY_ROOT="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Continuity"
```

There is no auto-detection, deliberately. Guessing wrong means writing a user's work into a
folder that is not backed up while reporting success, and the guess would have to be
re-made on every machine.

## The four sharp edges

**1. Files get evicted.** iCloud Drive, Dropbox Smart Sync, and Google Drive streaming all
reclaim disk by dropping a file's contents while leaving its name in place. Reading one
returns empty bytes and *no error*. The store detects this and raises
`ObjectNotMaterialized` instead of handing back a truncated artifact — but the remedy is to
let the client download the file, not to save it again.

**2. Sync is not instant and gives no completion signal.** A save that returns `ok: true`
means the bytes are on local disk. Whether they have left the machine is between the user
and their sync client, and nothing here can observe it. Do not describe a save as "backed
up"; describe it as saved.

**3. Two machines editing one session used to mean conflict copies.** Sync clients resolve
a simultaneous edit by forking the file — `notes (conflicted copy).md`, `notes 2.md` — and
whichever half a reader opens is a coin flip. The store avoids the situation entirely
rather than resolving it: artifact bytes are named by their own sha256, and the log of
saves is append-only. No file is ever rewritten, so there is nothing for a client to fork.

**4. A save can outrun its own directory.** Writing a file while a client uploads the
folder can expose a half-written file. Every write lands in a temporary file in the
destination directory and is then renamed into place, so a watcher sees the whole file or
nothing.

## What not to point it at

- **A repository working tree.** Session artifacts are not source, and they will be
  committed by accident.
- **A folder shared with people who should not read the sessions.** There is no per-object
  access control here; the folder's sharing *is* the access control.
- **A network mount that is not a sync client** (SMB, NFS). The atomic rename the store
  relies on is not reliably atomic across all network filesystems.

## When you outgrow it

Move to the S3-compatible backend when you need more than one person writing to one store,
access control per bucket, or a store that is not tied to somebody's laptop. The key
layout is identical across backends, so a store copied into a bucket keeps working.
