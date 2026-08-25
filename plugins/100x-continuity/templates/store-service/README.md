# A continuity store you run

`server.py` is a working MCP server that gives 100x-continuity a **service store**: object
storage where you decide who may read which published session. It is a starting point
to own and adapt, not a product to deploy as-is.

The plugin never holds a credential. It asks this server for a short-lived presigned
URL, sends or receives the bundle bytes on that URL, and that is the whole of its
access to your storage.

## What it implements

| Tool | Who may call it | What it does |
| --- | --- | --- |
| `mint_publication_upload` | any authenticated caller | records a publication owned by the caller, returns a presigned `PUT` |
| `resolve_publication` | the owner, or a listed reader | returns a presigned `GET` plus the digest to verify against |
| `list_publications` | any authenticated caller | what they own, and what was shared with them |
| `set_publication_access` | the owner | replaces the reader list, which is what makes revoking possible |

## Running it locally

```bash
export CONTINUITY_BUCKET=my-continuity-bucket
export CONTINUITY_S3_ENDPOINT=http://localhost:9000     # MinIO; omit for AWS
export CONTINUITY_DEV_PRINCIPAL=you@example.com         # local development ONLY
uv run --with fastmcp --with boto3 python server.py
```

Then add it as an MCP server in Claude Code, and point the plugin at it:

```bash
python3 /path/to/plugins/100x-continuity/scripts/run.py config \
  --set-store service --set-service continuity-store
```

With no verified identity available and `CONTINUITY_DEV_PRINCIPAL` unset, every call is
refused. That is deliberate: the server fails closed rather than treating an anonymous
caller as somebody.

| Variable | Default | What it is |
| --- | --- | --- |
| `CONTINUITY_BUCKET` | — | required; the bucket publications live in |
| `CONTINUITY_S3_ENDPOINT` | AWS | set for MinIO, R2, or B2 |
| `CONTINUITY_PREFIX` | `continuity` | key prefix inside the bucket |
| `CONTINUITY_DB` | `./continuity-store.sqlite3` | the ownership and access index |
| `CONTINUITY_UPLOAD_TTL` / `CONTINUITY_DOWNLOAD_TTL` | `600` | seconds a URL stays valid |
| `CONTINUITY_MAX_BYTES` | 512 MiB | largest bundle accepted |
| `CONTINUITY_DEV_PRINCIPAL` | unset | local development identity; remove in production |

## Before this is production

Four things, in order of how badly they bite.

**1. Wire up authentication.** `principal()` is the whole authorization model: it must
return an identity your infrastructure verified. Until it does, the dev fallback is the
only identity there is, and everyone is the same person. Replace the body, keep the
contract — and never take the identity from a tool argument.

**2. Lock down the bucket.** Public access blocked, encryption on, versioning if you
want to recover from a bad publish. The server's IAM policy should allow exactly
`PutObject` and `GetObject` on exactly its own prefix, and nothing else.

**3. Set a retention policy.** Publications accumulate forever otherwise. These objects
hold redacted prompts and whatever files people chose to include, and redacted is not
the same as safe — so decide the retention period deliberately rather than inheriting
"never delete" by default.

**4. Move the index off SQLite** if more than one instance will ever run. The schema is
three small tables and ports to Postgres unchanged; the file-backed default is here so
the template runs with nothing else installed.

## The rules worth keeping when you rewrite it

Whatever else changes, these are the parts that make the store trustworthy:

- **Ownership is recorded from the verified caller** the first time a publication is
  minted, and only the owner may change its access.
- **The object key is chosen server-side**, derived from the owner and a freshly minted
  publication id, so it is unique per publication and one caller can never address
  another's object.
- **A publication a caller may not read answers exactly like one that does not exist.**
  An id that leaks must not confirm that something is behind it.
- **Length and checksum are bound into the upload signature**, so the object store
  itself rejects a body that does not match — which is what makes the publisher's 2xx
  mean the right bytes landed.
- **The download response carries the digest**, so the reader can tell the publication
  it asked for from whatever answered the URL.
- **Reads are logged, and the log never decides access.** It is there to answer "who
  opened this", after the fact.
- **Only ids and URLs cross MCP.** Session content must never pass through a tool
  result.

## Compatibility notes

`ChecksumSHA256` in a presigned `PUT` is supported by AWS S3 and by current MinIO. If
your store rejects it, drop that parameter and the `x-amz-checksum-sha256` header
together — the signature and the headers must always agree — and accept that the 2xx
then proves only that *something* of the right length arrived. The reader still
verifies the digest, so the failure surfaces there rather than never.
