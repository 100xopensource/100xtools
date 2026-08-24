# 100x-continuity

Carrying a piece of work from the person who did it to the person who continues it, and
giving a team a system of their own for doing that.

## Language

### The two sides of the product

**Factory**:
What this repository ships. An Operator installs it in Claude Code, is interviewed by it,
and it emits a Kit. It is never the thing a Teammate uses.
_Avoid_: the plugin (ambiguous — there are two), the generator, the tool.

**Kit**:
What the Factory emits: one tailored plugin, written into the Operator's own repository,
plus the Store service scaffold when there is one. Each Kit knows its own store because
the Factory baked it in. "The Kit does X" is a claim about *every* emitted Kit, so it is a
promise the Factory has to keep.
_Avoid_: end-plugin, generated plugin, output.

**Emit**:
Writing a Kit into the Operator's repository. Re-emitting updates the Kit that is already
there; it never produces a second one.
_Avoid_: generate, install, scaffold (scaffolding is what the Store service gets).

**Plan**:
What the Factory proposes before it writes anything, and what the Operator approves. Every
question the interview settled, in one place.

### The people

**Operator**:
Runs the Factory in Claude Code. Owns a repository, an org plugin marketplace, and — if
there is one — the Store service. A developer; may be shown paths, flags and file lists.
_Avoid_: user (ambiguous), admin, installer.

**Teammate**:
Uses a Kit in Cowork. Never sees a path, a flag, or a repository — says what they want in
their own words and gets a plain answer. Every Teammate-facing surface is written for this
person.
_Avoid_: user (ambiguous), recipient, reader, end user.

### The four moments

**Plan**:
The Factory's interview, and the document it writes. Approved by the Operator before
anything is written into their repo. A *phase* of `set-up-handoff`, not a thing anyone
types — the Operator asked for a handoff plugin, not for a plan.
_Avoid_: config, spec, setup, wizard.

**Emit**:
Writing a Kit into the Operator's repository. Re-emitting *updates* that Kit; it never
produces a second one. Also a phase rather than a skill; `emit.py` is what performs it.
_Avoid_: generate, scaffold, install, deploy.

**Hand off**:
What a Teammate does at the end of a piece of work. `hand-off` is the Kit skill.
_Avoid_: publish, save, upload, share (to a Teammate — those words are internal).

**Pick up**:
What the receiving Teammate does with a Handle. `pick-up` is the Kit skill.
_Avoid_: continue, resume, restore, import.

### Proving it works

**Contract test**:
A deterministic check of the engine and the Store, with no model in the loop — a Bundle
reaches the Store, a Handle opens for a second person, damaged bytes are refused. Ships
inside every Kit, free to re-run, and it is what gates a release.
_Avoid_: unit test (it crosses process and network boundaries), smoke test, eval.

**Eval case**:
A check on what the *model* does with a Kit's skills — whether `hand-off` fires on the
right words, stays quiet on the wrong ones, and keeps internal vocabulary out of the
chat. Costs money and needs a model, so it never gates anything a Contract test can.
_Avoid_: test (ambiguous here), behavioural test.

### The work being carried

**Publication**:
One session, published: immutable, verifiable, and complete on its own. Publishing the
same work twice recognises the first publication rather than making a second.
_Avoid_: snapshot, save, backup, export.

**Handle**:
The one string a Teammate sends someone so they can pick the work up. The whole handoff is
this string.
_Avoid_: link, id, key, token.

**Bundle**:
A Publication's bytes: one zip holding the conversation, the artifacts, and a manifest
naming and digesting every file in it. Readable by a person who has no Claude at all.
_Avoid_: archive, package, payload.

**Artifact**:
A file a Teammate chose to send along with the conversation. Travels verbatim — it is
content a person composed, so it is scanned and refused, never rewritten.
_Avoid_: attachment, output, asset.

**Digest**:
The readable page a Publication opens with — what was asked, what was decided, what was
touched, what is still open. What a Teammate picking the work up reads first.
_Avoid_: summary, report, transcript (a Digest is not the conversation, it is the account
of it).

### Where a Publication lives

**Store**:
Where Publications go. Every Kit has exactly one, chosen by the Operator and baked in at
emit time — a Kit never asks a Teammate where things are kept and never goes looking.
_Avoid_: backend, storage, destination.

**Folder store**:
A directory a sync client already watches. Works in Cowork and in Claude Code. Has no
per-person access control: whoever can open the folder reads every Publication in it.
_Avoid_: local store, synced store.

**Store service**:
An MCP server the Operator hosts, which mints short-lived presigned URLs against their own
object storage. The only Store with per-person access control, and the only reason to
accept the cost of running something.
_Avoid_: server, backend, API, S3.

### What the product does and does not claim

**Handoff**:
One person's work reaching another person's Claude. The thing this product is for.

**Object delivery**:
Delivering a thing — a report, an analysis, a deck — with a way to reopen the work behind
it. Built by an Operator *on top of* a Kit; the Kit supplies the mechanism (publish, hand
over a Handle, fetch artifacts and session by id) and never a delivery channel.
_Avoid_: continuity (means a disclosure level in other systems; do not use it for this)
