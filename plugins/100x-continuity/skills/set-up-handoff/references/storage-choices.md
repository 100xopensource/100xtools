# Choosing where the Kit files things

Two kinds exist, and the Kit is built for exactly one of them — this choice is baked
in at emit time and cannot be changed by a Teammate later. They differ in one thing that
matters more than everything else about them: **who can read a session someone hands
over.**

## The folder store

A directory the Kit writes handoffs into. It becomes a *shared* store when it
sits inside a folder a consumer sync client already watches, and the client does the
uploading — the Kit syncs nothing and holds no credential for any service.

Where those folders usually are:

| Client | Typical root | Worth knowing |
| --- | --- | --- |
| iCloud Drive | `~/Library/Mobile Documents/com~apple~CloudDocs/` | evicts file contents; leaves a marker |
| OneDrive / SharePoint | `~/OneDrive/`, `~/OneDrive - <Org>/` | a synced SharePoint library behaves the same |
| Google Drive | `~/Google Drive/My Drive/` | streaming mode evicts like iCloud |
| Dropbox | `~/Dropbox/` | Smart Sync evicts like iCloud |

Inside a Cowork session the Teammate's granted folders appear under `~/mnt/`, which is
how a synced drive reaches a sandbox at all. The sandbox's own home does not outlive the
session, so a root under it disappears exactly when someone tries to pick up from it —
which is why the Operator names a real synced path here rather than the Kit guessing one
per machine.

**Do not auto-detect and proceed.** Offer what exists on the Operator's machine and let
them choose. Guessing wrong bakes a folder nothing is backing up into every Teammate's
plugin, while reporting success.

The path has to be right on the *Teammate's* machine, not only on the Operator's. Ask
whether their people mount the shared drive at the same place — for OneDrive and
SharePoint under a single tenant they usually do; for iCloud and Dropbox the home
directory differs but the part after it does not, which is why the root is stored with
`~` rather than expanded.

### The four sharp edges

**1. There is no access control.** Anyone who can open the folder reads every handoff
in it. Sharing one session with one person is not something a folder can do; sharing the
folder shares all of it, past and future. This is the single reason to prefer a service
store, and the Operator has to hear it before choosing, not after.

**2. Files get evicted.** iCloud Drive, Dropbox Smart Sync, and Google Drive streaming
all reclaim disk by dropping a file's contents while leaving its name in place.
Reading one returns short or empty bytes and *no error*. Only iCloud leaves a marker
behind, so marker-spotting alone is not enough: every read is verified against
the digest recorded when the handoff was written, which catches it whichever
client did it. Short bytes report as "not materialized yet" — wait for the client.
Full-length wrong bytes report as corruption, which waiting will not fix.

**3. A successful handoff is not a backup.** It proves the bytes reached local disk.
The client uploads on its own schedule and offers no completion signal the Kit can check.
A Teammate who hands off and closes the laptop in the same minute may have sent nothing
yet.

**4. Sharing has to actually be set up.** A recipient who cannot see the folder cannot
open a code from it, and the failure looks like a bad code. Shared-folder setup is per
client and per person; it is the Operator's job to do it once for the team, and it is not
something the Kit can check.

### Why it is append-only anyway

The obvious design is one mutable index per store. It fails in exactly this
environment: two machines editing one file inside a synced folder produce a conflict
copy, and a reader gets whichever half the client picked.

So nothing is ever rewritten. A handoff is named for the moment it was sent plus the
digest of its own bytes, so a second one lands beside the first rather than over it, and a sync client never has two versions of anything to reconcile.
Conflict copies are structurally impossible rather than resolved after the fact. The
cost is that a store grows monotonically — which also means a bad publish can be
inspected instead of only overwritten.

## The service store

Object storage — S3, R2, MinIO, B2 — reached through an MCP server the Operator runs
and adds to their organisation, so every Teammate has it without installing anything. The
server holds the storage credential, decides who may read which handoff, and hands the
Kit nothing but a short-lived URL.

Choose it when any of these is true:

- One session needs to go to one person, not to everyone with folder access.
- Handoffs must outlive the machines that made them, under a retention policy rather
  than a laptop's disk.
- The people picking the work up are outside the folder-sharing arrangement entirely.

The cost is honest: the Operator has to run a server, hold credentials, and own the
access rules. `store-service` scaffolds a working one and the contract it has to meet is
small — but it is real infrastructure with an on-call cost, and nobody should be talked
into it who only needed a shared folder.

## How to put it to the Operator

One question, two options, a recommendation. Something like: *"Where should handoffs go
— a folder your cloud drive already syncs, or object storage behind an MCP server you
run? The folder works today and anyone with folder access can read everything in it. The
server is real setup and is the only way to hand one session to one person."*

Take a "just do the simple one" as the folder, and state the access consequence in the
same breath rather than leaving it to be discovered. Do not present the service store as
the better answer; present it as the answer to a specific need.

Whichever they pick, it is fixed for that Kit. Changing it later means re-running the
factory and re-releasing the plugin — cheap, but not nothing, and worth saying now so
the choice gets thirty seconds of thought.
