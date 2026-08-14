# Storage layout — what is on disk, and why

Read this before debugging a store by hand or interpreting a directory listing. The layout
is identical for every backend, so a store copied from a folder into a bucket keeps
working.

## The shape

```
<root>/
  sessions/
    <session_digest>/
      entries/
        2026-08-13T09-14-02-118431Z-65cd9d8a30e5.json
        2026-08-13T11-40-55-903712Z-f2cdb2361262.json
      blobs/
        4519dac9d5e955b0a33a3f679a16f2840aa3de1d0a4bac3dcb754cdb75dc9d76
        770516662a6aa8106529459aa99dd5447ba7d9b98c6ac3a97b28fd6322c7aa6d
```

**`session_digest`** is `sha256("<namespace>:<session_id>")`. It is not reversible, so a
listing shows which sessions exist and how big they are, but not what they were called.
`where` prints the digest for the current configuration when you need to find one.

**`blobs/<sha256>`** holds artifact bytes, named by the digest of those bytes. Identical
content saved twice — from two machines, or twice on one — is one file. This is what keeps
a synced folder free of conflict copies.

**`entries/<stamp>-<digest12>.json`** is one record per save, naming a blob. The leading
UTC stamp sorts chronologically; the digest suffix keeps two saves in the same microsecond
distinct. Time separators are hyphens because a colon is not portable in a filename across
every filesystem this may sync to.

## Reading a session by hand

An entry is a small flat JSON object:

```json
{
  "name": "summary.md",
  "sha256": "4519dac9...",
  "size": 13,
  "media_type": "text/markdown",
  "saved_at": "2026-08-13T11-40-55-903712Z",
  "session_id": "0f9c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8",
  "namespace": "reports",
  "resolved": true
}
```

To reconstruct what a session currently holds: sort the entries by filename, and for each
`name` keep the last one. Its `sha256` is the filename under `blobs/`. That is the whole
fold — there is no index to rebuild and no state outside these two directories.

`resolved: false` means the session id did not resolve when this was saved, and the
artifact is in the shared `unattributed` slot rather than its own.

## Why append-only

The obvious design is one mutable manifest per session. It fails in exactly the environment
this is built for: two machines editing one manifest inside a synced folder produce a
conflict copy, and a reader gets whichever half the client picked.

Append-only removes the situation rather than resolving it. No file is ever rewritten after
it is created, so a sync client never has two versions of anything to reconcile. The cost
is that a session's history grows monotonically — an overwrite adds an entry rather than
replacing one — which is a price worth paying, and which also means a bad save can be
inspected instead of only overwritten.

## Things that look wrong but are not

- **More blobs than artifacts.** Every version ever saved is still there. The fold only
  surfaces the newest per name.
- **A blob with no entry naming it.** A save writes its blob first so that a crash between
  the two writes loses a save rather than leaving an entry pointing at bytes that are not
  there. The orphan is harmless.
- **`.tmp-*` files.** An interrupted write. They are excluded from listings and can be
  deleted.
- **A `sessions/` directory with one digest you do not recognise.** Usually the
  `unattributed` slot. Check it with `where` when no session id is set.

## Deleting things

There is no delete command. Remove a session by deleting its `<session_digest>` directory;
remove one version by deleting its entry file. Deleting a blob that an entry still names
turns a later load into a "not found" — prune blobs only when no entry references them.
