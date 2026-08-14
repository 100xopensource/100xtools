# 100xcontinuity

Save artifacts and conversation records from a Claude session so a later session can pick
them back up.

A session ends and its context goes with it. This plugin gives Claude somewhere durable to
put the things worth keeping — a summary, a draft, the decisions reached — and a way to
load them back by name later. The store is a plain directory or an S3-compatible bucket.

**Status: in development.** The local backend and the full save/load path work. The
S3-compatible backend and the MCP surface are landing next; see [Roadmap](#roadmap).

## Install

```
/plugin marketplace add 100xopensource/100xtools
/plugin install 100xcontinuity@100xtools
```

Or run it straight from a clone — Python 3.11+, no dependencies, no build step:

```bash
python3 plugins/100xcontinuity/skills/100xcontinuity/scripts/run.py where
```

## Use

Point it at a folder and go:

```bash
export CONTINUITY_ROOT="$HOME/Continuity"

printf '%s' "what we decided today" | \
  python3 .../scripts/run.py save --name summary.md

python3 .../scripts/run.py list
python3 .../scripts/run.py load --name summary.md
```

In Claude, ask for it in words — "save this for later", "pick up where we left off" — and
the skill drives the same commands.

## Getting it into the cloud

The plugin never syncs anything and holds no credentials for any cloud service. To get
artifacts off one machine, point the root at a folder a sync client already watches:

```bash
export CONTINUITY_ROOT="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Continuity"
```

iCloud Drive, OneDrive, a synced SharePoint library, Google Drive, and Dropbox all work.
The client does the uploading, which means **a successful save proves the bytes reached
local disk, not the cloud** — there is no completion signal to wait on.

That setup has sharp edges that show up days later (evicted files, conflict copies, sync
lag). The store is built to survive them, and
[`skills/100xcontinuity/references/synced-folders.md`](skills/100xcontinuity/references/synced-folders.md)
explains which folder to pick and what to expect.

## How the store works

Two ideas, both chosen because the store may live in a folder a sync client is actively
rewriting:

- **Artifact bytes are named by their own sha256.** Identical content saved twice is one
  file, so two machines cannot produce diverging versions of it.
- **The log of saves is append-only.** Nothing is ever rewritten, so a sync client never
  has two versions of a file to reconcile and never forks a conflict copy.

Reading a session means folding its log: last entry per name wins, history intact. The full
layout, including how to read a store by hand, is in
[`skills/100xcontinuity/references/storage-layout.md`](skills/100xcontinuity/references/storage-layout.md).

## Configuration

Flag beats environment beats default.

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| Backend | `--backend` | `CONTINUITY_BACKEND` | `local` |
| Store root | `--root` | `CONTINUITY_ROOT` | `~/Continuity` |
| Namespace | `--namespace` | `CONTINUITY_NAMESPACE` | `default` |
| Session | `--session` | `CLAUDE_SESSION_ID` | unattributed |

A namespace separates unrelated projects sharing one store — one per project, not one per
person.

When no session id resolves, artifacts are **still saved**, into a shared `unattributed`
slot, and the result says so. Nothing is lost, but sessions cannot be told apart until an
id is supplied.

## Tests

Offline; no model, no network, no third-party packages.

```bash
cd plugins/100xcontinuity/skills/100xcontinuity
PYTHONPATH=scripts python3 -m unittest discover -s tests -p 'test_*.py'
```

## Roadmap

| | Status |
| --- | --- |
| Local backend, save / load / list / where | Done |
| S3-compatible backend | Not started — the seam is in place, the backend is not. Selecting `--backend s3` fails with a clear message rather than writing nowhere |
| Custom MCP surface for fetching sessions | Not started |
| Using an existing Google Drive or SharePoint MCP to read the store | Not started — no setup steps are written yet |

Until the S3 backend lands there is nothing to switch *to*: `--backend` accepts `local`
alone, and no bucket, endpoint, or credential setting exists. The documentation for
switching arrives with the backend.

## Licence

Apache-2.0.
