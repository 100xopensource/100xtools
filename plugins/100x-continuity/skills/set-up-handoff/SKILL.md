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

## 3. Write the plan, and get one yes

Write `continuity-plan.md` into the target repo: what it will be called and where it goes;
its two skills and one line each on what a Teammate says; where handoffs go and **who can
read them**; and what will be created or overwritten, including the marked section this
adds to the repo's `CLAUDE.md`. For a service store, add the three answers above.

Show it and ask in the chat — not a pop-up, which invites a click. This is the gate.

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

## 5. Stand the server up, if the plan chose one

Service store only, and it belongs here rather than earlier: the registered name is settled
now, so the server can be built to answer to it. Run the `store-service` skill. It copies
the template out, gets it running on the Operator's own credentials, and checks it answers.

This is a step inside this run, not homework to hand back. If the Kit carries its own
`.mcp.json`, re-run the emit command with `--server-url <the address>` once there is one —
the Kit is a build output, so it is regenerated rather than edited.

## 6. Prove it, now

Run the `verify` skill. Do not end the turn having only named it — an emitted Kit that has
never round-tripped is a plausible-looking directory, and "shall I verify?" is how a team
ends up shipping one that was never run.

## 7. Say what happened, and where the rest of it is written

Where the Kit landed, what its skills are called, what `verify` proved and what it could
not. Then point at the marked section in their `CLAUDE.md`: it lists what is still theirs —
releasing it, sharing the folder or registering the server, telling the team the two
sentences that drive it. That file is the handover, because this runs once and this
conversation ends.

Nothing was committed or pushed. For most orgs a merge to the marketplace repo's main
branch is the release, and that call is theirs.

## Self-check

- [ ] Facts that could be looked up were looked up, not asked.
- [ ] An existing `kit.json` was found and used as defaults, not overwritten blind.
- [ ] The access consequence of the store choice was said before it was chosen.
- [ ] For a service store, the registered name was chosen before anything was emitted.
- [ ] The plan was written to a file and approved in the chat.
- [ ] The target is the Operator's repo, never this factory's own.
- [ ] `store-service` was run in this same turn when the plan chose a service store.
- [ ] `verify` was actually run, not offered.
- [ ] The Operator was pointed at the notes in their `CLAUDE.md`, not told it all in chat.
- [ ] Nothing was branched, committed, or pushed.
