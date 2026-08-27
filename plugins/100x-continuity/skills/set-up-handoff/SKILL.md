---
name: set-up-handoff
description: Builds this team a session-handoff plugin — interviews you, writes a plan you approve, generates the plugin into your repo with its marketplace row, then proves it works. Use when someone wants to give their team a way to hand Claude sessions to each other, set up session handoff, or change how an existing handoff plugin is configured.
---

# Build this team their handoff plugin

The person here is an Operator: they run tooling for a team, and they want their
Teammates to be able to hand a Claude session to each other. This works out what to
build, gets an explicit yes, writes it into their repository, and proves it runs.

One skill, because they asked for a plugin — not for a plan, and not for an emit. It runs
once. When it ends, everything still outstanding is written down in their repository
rather than left in this conversation.

## How to work

The Operator is technical. Say what things are, not what they feel like. But this is an
interview, not a form:

- **Ask in batches, with `AskUserQuestion`.** Everything that doesn't depend on an earlier
  answer goes in one round, recommended option first with the reason in a short clause.
- **Look before you ask.** Which repo they're in, what's in `.claude-plugin/`, which cloud
  drives exist here, whether a Kit already exists — all findable. Asking for a fact you
  could have read is the fastest way to feel like a form.
- **Carry on to the end.** Approval is the one place a human is needed. Everything after
  it is yours to finish — do not stop and offer to continue.

## 1. Read what is already there

```bash
FACTORY="${CLAUDE_PLUGIN_ROOT}"
```

Then look at the Operator's side:

- Are they in a plugin repository? A `.claude-plugin/marketplace.json` at the root says
  yes, and its rows say what naming they already use.
- Is there a Kit here — a plugin directory holding `kit.json`? If so this is an **update**:
  read it, treat every value as the default, ask only about what they want changed.
- Which synced folders exist (`~/OneDrive*`, `~/Library/Mobile Documents/com~apple~CloudDocs`,
  `~/Google Drive`, `~/Dropbox`)? Offer what exists.

## 2. Ask, in two rounds

**Round one — what it is and where it ships.** The plugin's **name**; the **repo directory**
to write into (default to the plugin repo you are standing in — if that is this factory's
own repo, say so and ask, because writing a Kit there helps nobody); and **who it is for**
in the words their Teammates would use, which becomes the plugin's own language.

**Round two — where handoffs are kept.** Read [references/storage-choices.md](references/storage-choices.md)
before asking: it carries the access consequence, the four sharp edges of a synced folder,
where a store server belongs, and how to put the choice without steering. For a folder, one
more answer: the root path and a group name.

For a service, three more, and settle all three **now** rather than after a server exists:

- **The name the server will be registered under.** They choose it here and register to
  match later. A Kit built against `acme-store` and a server registered `Acme Store` never
  meet, and nothing reports it — asking for the name after the fact is how that happens.
- **How Teammates reach it**: an organisation connector, which every Teammate then has
  without installing anything, or a `.mcp.json` carried inside the Kit. Recommend the
  connector. The `.mcp.json` route is for a team with no way to register one org-wide.
- **Where the server's source will live** — a directory *outside* this plugin repo. Offer
  a sibling of the repo. The reason is in the reference and is worth saying out loud.

If no server exists yet, say that `store-service` builds one later in this same run, and
that the Kit cannot be proven end to end until it is registered. Do not stop — a Kit
waiting on a server is still worth having on disk.

## 3. Write the plan, put the board up, and get one yes

**Display the plan file. Do not retype it into the chat.** Writing it and then saying it
again is the same document twice, and the second copy is the one nobody reads. The same
goes for the board: it is a file and a page, not something to paste.

Write `continuity-plan.md` into the target repo: what it will be called and where it goes;
its two skills and one line each on what a Teammate says; where handoffs go and **who can
read them**; and what will be created or overwritten, including the marked section this
adds to the repo's `CLAUDE.md`. For a service store, add the three answers above.

Then put the whole run on a board, while everything on it is still a plan:

```bash
python3 "$FACTORY/scripts/board.py" init --into <repo> --name <kit-name> \
  --store folder --root '<the synced directory>' --kit-source plugins/<kit-name> \
  --subtitle '<one line: what this is and where it keeps things>'
```

Swap in `--store service --service-name <the chosen name> --server-route <org|mcp-json>
--server-location <where its source will live>` for a service store, and the board grows
the tasks only a server has. It writes `status/board.html` and `status/tasks.json`. Say
where it is and how to watch it, in one line, rather than listing what is on it:

```bash
cd <repo>/status && python3 -m http.server 4173    # then open localhost:4173/board.html
```

`board.py show` prints it if you need to read the state back yourself. That output is for
you, not for the chat.

Every task carries a `key`. Mark one off the moment it lands, never in a batch at the
end, and give it the evidence that convinced you rather than the word *done*:

```bash
python3 "$FACTORY/scripts/board.py" set --into <repo> read-the-repo \
  --status done --proof proven --evidence '<what you actually found>'
```

`--proof proven` means it was proven here; `--proof stand-in` means something stood in
for the real thing, which is the honest label for anything a synthetic session or a local
process satisfied. Anything the run turns up that no plan predicted goes on with `add`.

Mark `read-the-repo` now, with what reading the repo actually turned up. Then display
`continuity-plan.md` and ask in the chat — not a pop-up, which invites a click. This is
the gate. Their yes is what marks `plan`.

## 4. Write it

```bash
python3 "$FACTORY/scripts/emit.py" \
  --into <repo>/plugins/<kit-name> --name <kit-name> \
  --team "<who it is for>" --org "<organisation>" \
  --store folder --root '<the synced directory>' --namespace <group> \
  --marketplace <repo>/.claude-plugin/marketplace.json
```

For a service store, swap the store flags for `--store service --service-name <the name
they chose>`, and add `--server-route org` or `--server-route mcp-json`, plus
`--server-location "<where its source will live>"` so the notes can say where it is.

Two things it writes besides the plugin: the marketplace row, and a marked section in the
repo's `CLAUDE.md` saying what the Kit is and what is still theirs to do. Read
[references/kit-layout.md](references/kit-layout.md) for what each emitted file is, how the
notes are merged rather than replaced, and how re-emitting treats a repo that has diverged.

The script owns five rules so you don't have to: placeholders are all-or-nothing, a Kit
describes one store, the marketplace `source` is repo-root relative, a non-empty directory
with no `kit.json` is refused, and only the text between its own markers in `CLAUDE.md` is
ever rewritten. Add `--dry-run` first if the target already holds files, and show what
`overwrote` names before doing it for real.

Then mark `emit` and `marketplace` off — the file count and whatever `overwrote` named,
and the row as it was written.

## 5. Stand the server up, if the plan chose one

Service store only, and it belongs here rather than earlier: the registered name is settled
now, so the server can be built to answer to it. Run the `store-service` skill. It copies
the template out, gets it running on the Operator's own credentials, and checks it answers.

This is a step inside this run, not homework to hand back. If the Kit carries its own
`.mcp.json`, re-run the emit command with `--server-url <the address>` once there is one —
the Kit is a build output, so it is regenerated rather than edited.

Three tasks are waiting on it: `copy-store-service`, `credential-uncommittable` and
`server-answers`. Mark each as it lands. A server proven against a local process is
`stand-in`, not `proven`, however green it looked.

## 6. Prove it, now

Run the `verify` skill. Do not end the turn having only named it — an emitted Kit that has
never round-tripped is a plausible-looking directory, and "shall I verify?" is how a team
ends up shipping one that was never run.

It settles three more: `contract-test`, `baked-config` and `round-trip`. A task that
failed is marked `blocked` with what it said, not quietly left in `todo`.

## 7. Say what happened, and where the rest of it is written

Close the board first. Set the verdict to the one true sentence about the state of this
thing — what works, and what is not yet reachable by anybody else:

```bash
python3 "$FACTORY/scripts/board.py" verdict --into <repo> --state blocked \
  --line '<what works, and what nobody else can do yet>'
```

`--state ok` only when nothing stands between a Teammate and a handoff. A Kit whose store
is not shared or whose server is not registered is `blocked`, and saying otherwise is the
one thing the board exists to prevent.

Then say where the Kit landed, what its skills are called, and what `verify` proved and
what it could not. Point at two files. `status/board.html` is what is left and who each
piece is waiting on. The marked section in their `CLAUDE.md` says what the Kit is and how
to drive it from their own code. Between them they are the handover, because this runs
once and this conversation ends.

Nothing was committed or pushed. For most orgs a merge to the marketplace repo's main
branch is the release, and that call is theirs.

## Self-check

- [ ] Facts that could be looked up were looked up, not asked.
- [ ] An existing `kit.json` was found and used as defaults, not overwritten blind.
- [ ] The access consequence of the store choice was said before it was chosen.
- [ ] For a service store, the registered name was chosen before anything was emitted.
- [ ] The plan was written to a file, displayed rather than restated, and approved in
      the chat with the board already up beside it.
- [ ] Every task was marked as it happened, with evidence, and nothing that stood in for
      the real thing was marked `proven`.
- [ ] The target is the Operator's repo, never this factory's own.
- [ ] `store-service` was run in this same turn when the plan chose a service store.
- [ ] `verify` was actually run, not offered.
- [ ] The verdict says what nobody else can do yet, rather than that it all works.
- [ ] The Operator was pointed at the board and the notes in their `CLAUDE.md`, not told
      it all in chat.
- [ ] Nothing was branched, committed, or pushed.
