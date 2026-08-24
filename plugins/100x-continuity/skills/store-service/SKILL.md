---
name: store-service
description: Stands up the MCP server that holds handoffs in object storage — copies the FastMCP template, walks you through getting credentials for your storage vendor, runs it locally from your own .env, and checks it answers. Use when the plan chose a service store, or when an existing store server needs checking.
---

# Stand up the store service

A service store is object storage the Operator owns, reached through an MCP server they
run. This copies out a working one, gets it running on their machine with their own
credentials, and checks it answers. It does not deploy anything and never handles a
credential itself — where it runs and who holds the keys are theirs.

Only needed if the plan chose a service store. A folder Kit never talks to a server.

## What it buys, and what it costs

One thing a folder cannot do: hand one session to one person. The server holds the storage
credential, decides who may read which handoff, and gives the Kit nothing but a short-lived
URL.

If the Operator is here because a service store sounded more serious, say the cost out
loud — a process to keep up, a credential to hold, access rules to own — and that a shared
folder is a complete answer for a team that trusts everyone in it.

## 1. Copy it out

```bash
cp -R "${CLAUDE_PLUGIN_ROOT}/templates/store-service" <where they want it>
```

Five files: `server.py`, `pyproject.toml`, a `Dockerfile`, `.env.example`, and a README.
Two things to point out as you hand it over:

- **`principal()` fails closed.** With no verified caller identity it refuses rather than
  treating anonymous as somebody. Whatever else they change, this must not become lenient —
  an access-controlled store that answers a caller it cannot name is a public store with
  extra steps.
- **The access table is SQLite** and the container runs one process against it. Fine for a
  team, wrong for a fleet; scaling means a real database, not more copies.

## 2. Ask which storage they use, then help them get in

One pop-up: AWS S3, Cloudflare R2, Backblaze B2, MinIO, or one already set up. Then
read [references/getting-credentials.md](references/getting-credentials.md) and give them
the commands for **their** vendor — bucket creation, blocking public access, and the credential,
with the quirk that actually trips people on that one.

**Never ask them to paste a secret into the chat.** They fill `.env` themselves, from
`.env.example`. You read the file to run the server and never echo what is in it.

Check `.env` is ignored by git before anything else happens in that directory. A credential
committed to a repo is a worse outcome than no store at all.

## 3. Run it here

```bash
cd <where they put it> && set -a && . ./.env && set +a && python3 server.py
```

Then check it answers on the port `.env` names, and that the four tools are listed. What
this proves is that their credentials work and the code runs — not that the deployed one
will, and say so in those words.

For a single-machine check the template accepts `CONTINUITY_DEV_PRINCIPAL`, which skips the
authentication gate. Say plainly that it must never be set anywhere a second person can
reach: it turns "nobody" into "somebody" and the whole access model rests on that
distinction.

## 4. Register it, and get the name exactly right

Deploying is theirs — the Dockerfile builds it and they will have opinions about where it
runs. Registration is the step that matters to the Kit: the Operator adds the server to
their organisation's connectors under a name, and **that name is baked into the Kit**. A
Kit emitted against `acme-store` and a server registered as `Acme Store` never meet.

Get the exact registered name and use it verbatim. Then run `verify`, which is the only
thing that proves the two halves actually found each other.

If they adapted the template, check it still meets what a Kit expects — the four tools and
what each must return are in [references/service-contract.md](references/service-contract.md),
and a renamed field surfaces as a Teammate who cannot hand anything over.

## Self-check

- [ ] The cost of running a server was stated before it was copied out.
- [ ] The vendor was asked, and the commands given were that vendor's.
- [ ] No secret was requested in the chat, and `.env` was confirmed git-ignored.
- [ ] The server was actually started and checked, not just described.
- [ ] The dev principal escape hatch was named as local-only.
- [ ] The exact registered server name was obtained, not guessed.
- [ ] Nothing was deployed, and no credential was echoed.
