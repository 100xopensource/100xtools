# The service store

A service store is object storage the Operator owns, reached through an MCP server the
Operator runs. **A Kit never holds a credential**, never signs a request, and knows
nothing about any provider. It does exactly one thing that needs no authority: send
bytes to, or read bytes from, a URL that already carries its own authorisation.

## Why it is shaped this way

A Kit runs as the Teammate, on their machine, inside a session that can be steered by
content it reads. Three consequences settle the design:

- **A long-lived cloud credential in that position is a liability.** It would sit in an
  environment variable readable by every process, in a config file a sync client might
  upload, and in scope for any prompt injection that reaches the session.
- **Signing is not the Kit's business.** Request signing needs a credential to sign
  with, which returns us to the first point.
- **Whoever owns the bucket owns the access rules.** Only they can decide which key a
  given user may write, how long a URL lives, and who may read it back.

There is deliberately no `s3` store kind. This engine addresses a store it can list,
read back, and verify; a presigned PUT can do none of those. Modelling one as a store
would promise operations it cannot perform.

## The contract the server has to meet

Two tools. Everything else is the operator's business.

**Mint an upload.** Takes the session's identity plus the bundle's `sha256` and `size`.
Returns:

```json
{
  "url": "https://<host>/<bucket>/<key>?<signature>",
  "required_headers": {
    "Content-Length": "20480",
    "x-amz-checksum-sha256": "<base64 sha256 of the body>"
  }
}
```

**Resolve a download.** Takes a publication id. Returns the same shape, signed for
`GET`, plus the `sha256` the server recorded — which is what lets the reader verify it
got the publication it asked for rather than whatever answered the URL.

Rules the Kit enforces on both, so build to them:

| Rule | Why |
| --- | --- |
| `https` only | refused before any bytes move |
| no credentials in the URL | a `user:pass@host` URL is refused outright |
| no redirects | never followed — on the way up it would replay prompts to a host nobody signed for; on the way down it would accept a bundle from a host the operator never named |
| headers used verbatim | a presigned URL commits to the headers it was signed with; adding or reordering one invalidates the signature |

Optionally pin the hosts you expect, so a mint result naming an unexpected destination
is refused rather than sent to:

```bash
export CONTINUITY_ALLOWED_HOSTS="s3.eu-west-1.amazonaws.com,my-account.r2.cloudflarestorage.com"
```

Unset means "trust the mint", which is the default because a Kit cannot know the
operator's bucket host.

## The governance pattern

`templates/continuity-store/` is a working FastMCP server implementing the two tools
above. It is a starting point to own, not a product — read it before running it. The
pattern it follows is worth keeping whatever else changes:

- **Ownership comes from the verified caller, never from the payload.** The principal
  on the authenticated request is recorded as the owner the first time a session is
  published, and only the owner may add to it. A client that could name its own owner
  could publish into anyone's history.
- **Keys are chosen server-side.** Derive the object key from the owner and the
  publication id; never accept a client-supplied path, or one user can write over
  another's object.
- **Read access is a list on the publication's owner-scoped record.** One allowlist,
  edited in one place, so "who can read this" is answerable and revocable. A reader not
  on it gets the same answer as for a publication that does not exist — an id that
  leaks should not confirm that something is there.
- **Only ids and URLs cross MCP.** The bundle rides the presigned side channel, so
  session content never passes through a model turn or a tool result.
- **Bind length and checksum into the signature.** The object store then rejects any
  body that does not match, which is what makes a 2xx meaningful.
- **Keep URLs short-lived**, minutes not hours, and log resolves so reads are auditable.

## What the Operator still has to do

None of this is done for the Operator, and none of it is specific to this factory.

1. **A bucket with public access blocked**, encryption on, and versioning if recovery
   from a bad publish matters.
2. **A lifecycle rule.** Publications accumulate forever otherwise. Decide the retention
   period deliberately — these objects hold redacted prompts, and redacted is not safe.
3. **An IAM policy for the server** allowing exactly the operations it mints for, on
   exactly its own prefix.
4. **Authentication in front of the server**, giving it the verified principal the
   ownership rule depends on.
5. **Egress**, if their Claude deployment restricts it: the storage host has to be
   reachable from wherever the session runs.

## What is being shipped when a publication goes up

The full transcript record, redacted. Redaction removes **credential-shaped values
only**: key prefixes, `Authorization` headers, JWTs, PEM blocks, and values whose key
names them a secret. It cannot recognise a credential that reads like prose, an
internal hostname, a customer name, or personal data someone typed into a prompt.

So decide what the destination is cleared for before pointing a mint at it. Publishing
without the full record is a much smaller surface — a summary of what was asked and
touched, rather than every tool payload — and is the right call when the record is not
needed off-machine.
