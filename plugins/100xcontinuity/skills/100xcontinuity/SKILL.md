---
name: 100xcontinuity
description: Save artifacts and conversation records from a Claude session so a later session can pick them back up, and restore them by name. Use when someone says "save this for later", "keep this session", "pick up where we left off", "restore my last session", or wants work to survive past the end of a conversation. Do NOT use for ordinary file writes that belong in the working directory.
---

# 100xcontinuity — carry work across sessions

Save an artifact into a **session**, and load it back in a later session. The store is
either a plain directory — typically one a sync client already watches, which is how the
data reaches the cloud — or an S3-compatible bucket.

**Resolve the engine entrypoint once**, then use `$RUN` below (works whether this skill is
loaded as a plugin or run from a clone of the repo):

```bash
RUN="${CLAUDE_PLUGIN_ROOT:-plugins/100xcontinuity}/skills/100xcontinuity/scripts/run.py"
```

Every command prints JSON on stdout and exits non-zero on failure, so parse the result
rather than reading it as prose. A failure carries `ok: false` and a `hint` naming the
remedy.

---

## 1) Save something

```bash
python3 "$RUN" save --name summary.md --file ./summary.md --media-type text/markdown
```

Reads stdin when `--file` is omitted, which is the usual way to save something you just
composed:

```bash
printf '%s' "$SUMMARY" | python3 "$RUN" save --name summary.md
```

`--name` is the handle a later session uses to get it back. Saving the same name twice is
normal and expected — the newer save wins on read, and the older one stays in the history
rather than being destroyed.

**Save the record of the conversation the same way.** There is no separate command for it:
write what matters to a file or stdin and give it a name like `conversation.md`. What
belongs in it is a judgment call — the decisions reached, what was tried and rejected, and
the state a later session would otherwise have to reconstruct.

## 2) See what a session holds

```bash
python3 "$RUN" list            # what is current
python3 "$RUN" list --history  # every save, oldest first
```

`artifacts` is the current state, one record per name. `damaged` names entries that could
not be read; a session with damaged entries still returns everything else, so report them
rather than treating the session as lost.

## 3) Load something back

```bash
python3 "$RUN" load --name summary.md              # bytes to stdout
python3 "$RUN" load --name summary.md --out ./summary.md
```

With `--out` the result is JSON describing the write. Without it, the raw bytes go to
stdout and nothing else does — that form is for piping, not for parsing.

## 4) Check the configuration

```bash
python3 "$RUN" where
```

Reports the backend, the resolved root, whether it exists yet, and the path this session
maps to. It has no side effects — it will not create the store. Run it first when a save
seems to have gone somewhere unexpected.

---

## Sessions, and what happens when the id is missing

A session is identified by `CLAUDE_SESSION_ID`, or by `--session`. When neither resolves,
the artifact is **still saved** — it lands in a shared `unattributed` slot and the result
says `session_resolved: false` with a hint. Nothing is lost, but a later session cannot
tell those artifacts apart from anyone else's unattributed ones.

**Surface that hint to the user rather than swallowing it.** A store quietly filling with
unattributed artifacts is the failure mode this design has: everything succeeds, nothing
errors, and the work cannot be found again.

To attribute past saves, pass the same `--session` value when loading.

## Configuration

Flag beats environment beats default.

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| Backend | `--backend` | `CONTINUITY_BACKEND` | `local` |
| Store root | `--root` | `CONTINUITY_ROOT` | `~/Continuity` |
| Namespace | `--namespace` | `CONTINUITY_NAMESPACE` | `default` |
| Session | `--session` | `CLAUDE_SESSION_ID` | unattributed |

A **namespace** separates unrelated projects that share one store. Two namespaces never see
each other's sessions, so use one per project rather than one per person.

**Backend status:** `local` is implemented. The S3-compatible backend is declared in the
seam but not yet wired — selecting it fails with a clear message rather than silently
writing nowhere.

## When the store is a synced folder

The ordinary setup points `--root` at a folder inside iCloud Drive, OneDrive, Google Drive,
or Dropbox, and lets that client do the uploading. The plugin never syncs anything itself,
which means **a successful save proves the bytes reached local disk, not the cloud.** Say
so if a user asks whether their work is backed up; there is no completion signal to check.

Three failures are worth recognising by name:

- **`ObjectNotMaterialized`** — the artifact exists but its bytes are not on this machine,
  because a sync client evicted them to reclaim space. Every read is verified against the
  digest the key carries, so this is caught whichever client did it and whether the file
  came back empty or part-way. The remedy is to let the sync client finish downloading,
  then retry. **Never treat it as an empty artifact, and never re-save over it** — that
  replaces a placeholder with new bytes and loses the copy still in the cloud.
- **"is corrupt: its bytes hash to … but the entry names …"** — same length, wrong content.
  Waiting will not fix this one; the stored object no longer matches what was saved.
- **Nothing found in a session you know you saved to** — usually the session id did not
  resolve on one of the two runs. Compare `session_digest` from `where` across both.

A `list` reporting entries under `damaged` means those records cannot be honoured. The rest
of the session is unaffected, so report them rather than treating the session as lost.

Read `references/synced-folders.md` before advising anyone on which folder to use, and
`references/storage-layout.md` before interpreting what is on disk or debugging a store by
hand.
