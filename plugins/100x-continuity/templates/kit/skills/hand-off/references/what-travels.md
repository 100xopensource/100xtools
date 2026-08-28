# What travels, and what does not

One handoff is one archive plus a small record beside it. The archive:

```
manifest.json                     written last — the marker that says it is complete
transcript/session-digest.md      the readable page a continuing session starts from
transcript/session-record.jsonl   every transcript record, redacted, one per line
artifacts/<path>                  the files this session chose to include
```

And beside it, wherever it is filed, a small record — the code it is known by, when it was
sent, the digest and size of the archive, the counts, and how the conversation was
chosen. That record is what makes a store browsable without opening a single archive,
and its presence is what marks the handoff as finished.

## The manifest describes content, and nothing else

No publish timestamp, no source path, no store. Those are facts about a *publication*,
not about a bundle, and keeping them out has a practical payoff: the same conversation
and the same files pack to **byte-identical bundles** on two machines. So a second handoff of
unchanged work is recognisable as the one already sent instead of filing a second copy
of it, and two people can compare what they received.

The manifest also carries the digest of every file in the archive. Extraction checks
each one, which is how an evicted or truncated archive is caught rather than read as a
shorter conversation.

## The digest is a page, not a dump

Roughly 6 KB from a 5 MB transcript, measured. It holds what was asked, the last thing
this session concluded, the tools used and how often, the files touched, timings, token
totals, and any open threads. It is what the other person reads first, and often all
they need.

Two details behind it that look arbitrary and are not:

- **Prompts are filtered to what a human actually said** — but only when the session's
  records carry that distinction at all. A `user` record is not the same thing as a
  prompt: tool results and injected skill bodies share the type, and an invoked slash
  command was appearing as a sixty-line question the user never asked. The field is not
  a published contract, so filtering unconditionally would summarise some builds as
  having been asked nothing.
- **The digest is redacted field by field, before it is rendered.** Redacting the
  rendered markdown instead read the report's own headings as content, and published
  `- Tokens: [redacted] 10`.

## What is deliberately not read

A publication is a complete record of the **conversation**, not of everything the host
knows. Two files are never touched, and both omissions are deliberate:

- **`audit.jsonl`** — the host's signed per-session log: cost, token usage, rate
  limits, permission decisions. Every row is HMAC-signed, so a redacted copy would
  fail its own signature check.
- **The session metadata file** — the assembled system prompt, thousands of characters
  of it, plus a map of every enabled connector and tool. Publishing it would put a
  vendor's prompt and a connector inventory into a shared folder, and redaction matches
  credential *shapes*; it would not stop prose.

Never describe a handoff as everything this machine knew.

## Exactly what redaction does

It removes **credential-shaped values**: key prefixes, `Authorization` headers, JWTs,
PEM blocks, and any value whose key names it a secret. That is the whole of it.

It cannot recognise:

- a credential that reads like prose ("the password is the dog's name backwards"),
- an internal hostname, a customer name, a ticket id,
- personal data someone typed into a prompt,
- a secret inside a file that was included as an artifact — those are scanned and
  refused, not rewritten.

Which is why the count is reported *with* the caveat, and why a handoff is never
described as safe, clean, sanitised, or free of secrets. Zero redactions means
the scrubber matched nothing. It does not mean there was nothing to find.

The one place recall is preferred over precision is here rather than in a linter: the
cost of redacting a placeholder is nothing, and the cost of missing a credential is
everything.

## Artifacts are the exception, on purpose

Files travel **verbatim**. They are content a person composed, and rewriting one would
corrupt something nobody asked us to touch. So the boundary fails closed instead:

- a filename that usually holds credentials — `.env`, `*.pem`, `id_rsa`, `.netrc` —
  is refused unless explicitly allowed,
- a credential-shaped value found *inside* a text file stops the handoff and names it,
- a file that is not text is reported as unscanned rather than as clean, because
  "nothing found" about bytes nobody could read is the more dangerous answer.

Overriding either refusal is a real decision with a real reason, not a step to take by
reflex when a command fails.
