# Reading what a colleague sent

A handoff is one archive and a small record beside it. Opening it verifies the
archive, unpacks it, and hands back the parts:

```
transcript/session-digest.md      start here — the readable page
transcript/session-record.jsonl   every record of the conversation, redacted
artifacts/<path>                  files that travelled with it
manifest.json                     what is inside, with a digest for each file
```

## Start with the digest, and read it properly

It is a page, not a dump — roughly 6 KB from a transcript that may have been megabytes.
It carries what was asked, the last thing that session concluded, which tools ran and
how often, the files it touched, when it started and stopped, and any threads left
open.

That is usually enough to continue. Skim it and you will miss the two things it exists
to tell you: what was already decided, and what was deliberately left undone.

## When to open the full record

`session-record.jsonl` is one JSON object per line, each wrapping a transcript record
in an envelope carrying its position and a content digest. Open it for:

- the exact wording of a decision the digest paraphrased,
- a tool call's actual arguments,
- the order things happened in, when that matters,
- anything the digest says it omitted — it reports what it dropped.

Do not read it front to back. Search it for what you need. And note that a record's
integrity digest describes the record **before** redaction, so verifying a published
record against that value is expected to fail — that failure is how a transformed copy
is told from an original, not a sign of damage.

## When the digest seems to be missing something

Three ordinary explanations before assuming damage:

1. **They sent it without the full record.** The digest is there and
   `session-record.jsonl` is not. The manifest says which was included.
2. **Subagent traffic is not there.** A fan-out run's subagent transcripts are never
   published: the parent turn is what a continuing session needs, and including them
   makes the prompt list read as though the user said things they never said.
3. **A `[redacted]` is not content.** A credential shape was removed on the way in.
   There is nothing to recover and nothing to look for.

## What was never in it at all

A handoff is a complete record of the **conversation**, and nothing more. The
sending host's assembled system prompt, its map of enabled connectors and tools, and
its signed audit log of cost and permission decisions were all deliberately never read.

So never answer "what was their setup" from a handoff. It cannot say.

{{BAD_READ}}

{{CODE_SHAPE}}

## What you are inheriting

Someone else's working session, mid-thought, with credential shapes removed. Sending
it did not end it — if something looks half-finished it may still be in flight. Where a
decision looks final but reads oddly, ask rather than assume; the person who sent the
code is usually one message away.
