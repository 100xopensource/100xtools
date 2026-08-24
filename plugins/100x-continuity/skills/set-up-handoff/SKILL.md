---
name: set-up-handoff
description: Builds this team a session-handoff plugin — interviews you, writes a plan you approve, generates the plugin into your repo with its marketplace row, then proves it works. Use when someone wants to give their team a way to hand Claude sessions to each other, set up session handoff, or change how an existing handoff plugin is configured.
---

# Build this team their handoff plugin

The person here is an Operator: they run tooling for a team, and they want their
Teammates to be able to hand a Claude session to each other. This works out what to
build, gets an explicit yes, writes it into their repository, and proves it runs.

One skill, because they asked for a plugin — not for a plan, and not for an emit.

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
and how to put the choice without steering. For a folder: the root path and a group name. For a service: the name the MCP
server is registered under, which is the only way a Teammate's Claude finds it.

If they pick a service and no server exists yet, say that `store-service` builds one and
that the Kit cannot be proven end to end until it is registered. Do not stop — carry on and
emit; a Kit waiting on a server is still worth having on disk.

## 3. Write the plan, and get one yes

Write `continuity-plan.md` into the target repo: what it will be called and where it goes;
its two skills and one line each on what a Teammate says; where handoffs go and **who can
read them**; what will be created or overwritten; and for a service store, that the server
must exist and be registered first.

Show it and ask in the chat — not a pop-up, which invites a click. This is the gate.

## 4. Write it

```bash
python3 "$FACTORY/scripts/emit.py" \
  --into <repo>/plugins/<kit-name> --name <kit-name> \
  --team "<who it is for>" --org "<organisation>" \
  --store folder --root '<the synced directory>' --namespace <group> \
  --marketplace <repo>/.claude-plugin/marketplace.json
```

For a service store, swap the store flags for `--store service --service-name <registered
name>`. Add `--dry-run` first if the target already holds files, and show what `overwrote`
names before doing it for real.

The script owns four rules so you don't have to: placeholders are all-or-nothing, a Kit
describes one store, the marketplace `source` is repo-root relative, and a non-empty
directory with no `kit.json` is refused. Read [references/kit-layout.md](references/kit-layout.md)
for what each emitted file is, and how re-emitting treats a repo that has diverged.

## 5. Prove it, now

Run the `verify` skill. Do not end the turn having only named it — an emitted Kit that has
never round-tripped is a plausible-looking directory, and "shall I verify?" is how a team
ends up shipping one that was never run.

## 6. Say what happened

Where it landed, what its skills are called, what `verify` proved and what it could not.
Then: nothing was committed or pushed — for most orgs a merge to the marketplace repo's
main branch is the release, and that is theirs.

## Self-check

- [ ] Facts that could be looked up were looked up, not asked.
- [ ] An existing `kit.json` was found and used as defaults, not overwritten blind.
- [ ] The access consequence of the store choice was said before it was chosen.
- [ ] The plan was written to a file and approved in the chat.
- [ ] The target is the Operator's repo, never this factory's own.
- [ ] `verify` was actually run, not offered.
- [ ] Nothing was branched, committed, or pushed.
