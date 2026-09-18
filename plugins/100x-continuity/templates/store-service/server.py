"""A continuity store, as an MCP server you run.

This is a **starting point to own**, not a product. It implements the small contract
100x-continuity's service store needs, and nothing beyond it:

    mint_publication_upload   the publisher asks for somewhere to put a bundle
    resolve_publication       a reader asks for the bundle they were handed
    list_publications         what this caller owns, and what was shared with them
    set_publication_access    the owner changes who may read one

The bundle bytes never pass through MCP. They ride a presigned URL straight to object
storage, so a model turn only ever carries ids and URLs.

Read every line before you run it. The parts that decide who can read whose session
are marked, and they are the parts not to loosen:

1. **The principal comes from the verified request, never from an argument.** A client
   that could name its own identity could publish into anyone's history and read
   anyone's session.
2. **The object key is chosen here.** Never accept a client-supplied path, or one
   caller can write over another's object.
3. **A publication a caller may not read answers exactly like one that does not
   exist.** An id that leaks should not confirm that something is behind it.
4. **Length and checksum are bound into the signature.** The object store then rejects
   a body that does not match, which is what makes the publisher's 2xx meaningful.

Run it:

    export CONTINUITY_BUCKET=my-continuity-bucket
    export CONTINUITY_DB=./continuity-store.sqlite3
    uv run --with fastmcp --with boto3 python server.py

Then connect it as an MCP server in Claude Code, and set the plugin's store to
`service` with that server's name.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import os
import re
import secrets
import sqlite3
import urllib.parse
from typing import Any

import boto3
from botocore.config import Config
from fastmcp import FastMCP

# --- configuration -----------------------------------------------------------

BUCKET = os.environ.get("CONTINUITY_BUCKET", "")
PREFIX = os.environ.get("CONTINUITY_PREFIX", "continuity")
DB_PATH = os.environ.get("CONTINUITY_DB", "continuity-store.sqlite3")
UPLOAD_TTL = int(os.environ.get("CONTINUITY_UPLOAD_TTL", "600"))
DOWNLOAD_TTL = int(os.environ.get("CONTINUITY_DOWNLOAD_TTL", "600"))
MAX_BUNDLE_BYTES = int(os.environ.get("CONTINUITY_MAX_BYTES", str(512 * 1024 * 1024)))

# Development only. With no verified identity available and this unset, every call is
# refused — the server fails closed rather than treating an anonymous caller as
# somebody. Remove it once your auth is wired up.
DEV_PRINCIPAL_ENV = "CONTINUITY_DEV_PRINCIPAL"

_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_PUBLICATION_ID = re.compile(r"\Apub_[0-9a-f]{32}\Z")

mcp = FastMCP("continuity-store")


class Refused(Exception):
    """Something the caller may not do, phrased so it leaks nothing."""


# --- identity: the one thing you must wire up --------------------------------


def principal() -> str:
    """The verified identity of this caller, lowercased.

    **Replace the body, not the contract.** Whatever authenticates your MCP server —
    an OIDC token, an API gateway, a reverse proxy — put the identity *it* verified
    here. It must never come from a tool argument.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
    except Exception:  # noqa: BLE001 - no verified identity is available at all
        token = None

    if token is not None:
        claims = getattr(token, "claims", None) or {}
        for claim in ("email", "sub", "client_id"):
            value = claims.get(claim)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()

    development = os.environ.get(DEV_PRINCIPAL_ENV, "").strip().lower()
    if development:
        return development
    raise Refused(
        "this server has no verified identity for the caller; wire up authentication "
        f"or set {DEV_PRINCIPAL_ENV} for local development only"
    )


def owner_hash(who: str) -> str:
    """A stable, non-reversible directory for one owner's objects."""
    return hashlib.sha256(who.encode("utf-8")).hexdigest()[:32]


# --- storage -----------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS publications (
    publication_id TEXT PRIMARY KEY,
    owner          TEXT NOT NULL,
    object_key     TEXT NOT NULL,
    session_id     TEXT,
    sha256         TEXT NOT NULL,
    size           INTEGER NOT NULL,
    published_at   TEXT NOT NULL
);
-- Read access is a row per (publication, reader), so revoking one person touches one
-- row and "who can read this" is a query rather than a guess.
CREATE TABLE IF NOT EXISTS readers (
    publication_id TEXT NOT NULL,
    reader         TEXT NOT NULL,
    granted_at     TEXT NOT NULL,
    PRIMARY KEY (publication_id, reader)
);
-- Append-only, so a resolve is auditable after the fact. Never consulted to decide
-- access.
CREATE TABLE IF NOT EXISTS reads (
    publication_id TEXT NOT NULL,
    reader         TEXT NOT NULL,
    read_at        TEXT NOT NULL
);
"""


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def s3():
    # The endpoint URL is what makes this work against MinIO, R2, or B2 as well as AWS.
    # SigV4 is pinned rather than left to botocore's default: presigning falls back to
    # SigV2 in some endpoint/region combinations, and R2 refuses SigV2 outright with a
    # 401 that reads like a bad credential and is not one. Every vendor here speaks V4.
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("CONTINUITY_S3_ENDPOINT") or None,
        config=Config(signature_version="s3v4"),
    )


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def require_config() -> None:
    if not BUCKET:
        raise Refused("this server has no CONTINUITY_BUCKET configured")
    _check_endpoint(os.environ.get("CONTINUITY_S3_ENDPOINT", ""))


def _check_endpoint(endpoint: str) -> None:
    """An endpoint must be a bare host. A path on it silently misfiles everything.

    boto3 treats a path on the endpoint as a prefix, so with
    `https://<account>.r2.cloudflarestorage.com/my-bucket` every object is written to
    `my-bucket/continuity/...` instead of `continuity/...`. Nothing reports it —
    `put_object` returns 200 either way — so a whole team's handoffs can land where no
    correctly-configured server will ever look for them. Found against real R2, after
    the objects were already stranded.

    Refused rather than stripped: this is config somebody wrote on purpose, and a guard
    that silently changes behaviour is the same class of thing as the bug.
    """
    if not endpoint:
        return
    path = urllib.parse.urlsplit(endpoint).path
    if path and path != "/":
        raise Refused(
            f"CONTINUITY_S3_ENDPOINT must be a bare host, and this one carries the path "
            f"{path!r}. Every object would be written under that path as a prefix and "
            f"nothing would report it. For Cloudflare R2 the endpoint is "
            f"https://<account-id>.r2.cloudflarestorage.com with no bucket on the end — "
            f"the bucket is CONTINUITY_BUCKET"
        )


# --- tools -------------------------------------------------------------------


@mcp.tool
def mint_publication_upload(
    sha256: str,
    size: int,
    session_id: str | None = None,
    readers: list[str] | None = None,
) -> dict[str, Any]:
    """Mint a presigned upload for one bundle, and record who may read it.

    `sha256` and `size` describe the bundle the publisher just packed — they are bound
    into the signature, so the object store refuses anything else.
    """
    require_config()
    who = principal()
    if not _SHA256.match(sha256 or ""):
        raise Refused("sha256 must be a lowercase hex digest")
    if not isinstance(size, int) or not 0 < size <= MAX_BUNDLE_BYTES:
        raise Refused(f"size must be between 1 and {MAX_BUNDLE_BYTES} bytes")

    publication_id = f"pub_{secrets.token_hex(16)}"
    # Server-chosen, owner-namespaced, unique per publication — so it can never be
    # overwritten, and one caller can never address another's object.
    key = f"{PREFIX}/{owner_hash(who)}/{publication_id}.zip"
    checksum = base64.b64encode(binascii.unhexlify(sha256)).decode("ascii")

    url = s3().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ChecksumSHA256": checksum,
            "ContentLength": size,
            "ContentType": "application/zip",
        },
        ExpiresIn=UPLOAD_TTL,
    )

    with db() as connection:
        connection.execute(
            "INSERT INTO publications (publication_id, owner, object_key, session_id,"
            " sha256, size, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (publication_id, who, key, session_id, sha256, size, now()),
        )
        for reader in _clean(readers):
            connection.execute(
                "INSERT OR IGNORE INTO readers (publication_id, reader, granted_at)"
                " VALUES (?, ?, ?)",
                (publication_id, reader, now()),
            )

    return {
        "publication_id": publication_id,
        "url": url,
        # Sent verbatim by the plugin. These are the headers the signature commits to,
        # so do not reorder or add to them.
        "required_headers": {
            "Content-Length": str(size),
            "Content-Type": "application/zip",
            "x-amz-checksum-sha256": checksum,
        },
        "expires_in": UPLOAD_TTL,
    }


@mcp.tool
def resolve_publication(publication_id: str) -> dict[str, Any]:
    """Resolve a publication this caller is allowed to read.

    A publication that exists but is not theirs answers exactly like one that does not
    exist. That is deliberate: an id that leaks must not confirm anything.
    """
    require_config()
    who = principal()
    if not _PUBLICATION_ID.match(publication_id or ""):
        raise Refused("that is not a publication id")

    with db() as connection:
        row = connection.execute(
            "SELECT * FROM publications WHERE publication_id = ?", (publication_id,)
        ).fetchone()
        allowed = row is not None and (
            row["owner"] == who
            or connection.execute(
                "SELECT 1 FROM readers WHERE publication_id = ? AND reader = ?",
                (publication_id, who),
            ).fetchone()
            is not None
        )
        if not allowed:
            raise Refused("no publication is available to you with that id")
        connection.execute(
            "INSERT INTO reads (publication_id, reader, read_at) VALUES (?, ?, ?)",
            (publication_id, who, now()),
        )

    # A row is written when the upload is minted, before any bytes exist, so an
    # abandoned publish leaves an id that would otherwise resolve to a URL that 404s.
    # The reader then sees a download failure and reads it as the sender's fault. One
    # HEAD makes the refusal precise and costs nothing beside fetching the bundle.
    client = s3()
    try:
        client.head_object(Bucket=BUCKET, Key=row["object_key"])
    except client.exceptions.ClientError as exc:
        raise Refused(
            "that publication was started but its bytes were never uploaded, so there "
            "is nothing to read"
        ) from exc

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": row["object_key"]},
        ExpiresIn=DOWNLOAD_TTL,
    )
    return {
        "publication_id": publication_id,
        "url": url,
        "required_headers": {},
        # The reader checks the bytes against this, which is what turns "whatever
        # answered the URL" into "the publication I was pointed at".
        "sha256": row["sha256"],
        "size": row["size"],
        "session_id": row["session_id"],
        "published_at": row["published_at"],
        "expires_in": DOWNLOAD_TTL,
    }


@mcp.tool
def list_publications() -> dict[str, Any]:
    """What this caller owns, and what has been shared with them."""
    who = principal()
    with db() as connection:
        mine = connection.execute(
            "SELECT publication_id, session_id, size, published_at FROM publications"
            " WHERE owner = ? ORDER BY published_at DESC",
            (who,),
        ).fetchall()
        shared = connection.execute(
            "SELECT p.publication_id, p.session_id, p.size, p.published_at, p.owner"
            " FROM publications p JOIN readers r"
            " ON r.publication_id = p.publication_id"
            " WHERE r.reader = ? AND p.owner != ? ORDER BY p.published_at DESC",
            (who, who),
        ).fetchall()
    return {
        "mine": [dict(row) for row in mine],
        "shared_with_me": [dict(row) for row in shared],
    }


@mcp.tool
def set_publication_access(publication_id: str, readers: list[str]) -> dict[str, Any]:
    """Replace who may read one publication. Owner only.

    Replacing rather than adding is what makes revoking possible at all: an add-only
    list cannot express "not them any more".
    """
    who = principal()
    wanted = _clean(readers)
    with db() as connection:
        row = connection.execute(
            "SELECT owner FROM publications WHERE publication_id = ?", (publication_id,)
        ).fetchone()
        if row is None or row["owner"] != who:
            raise Refused("no publication is available to you with that id")
        connection.execute("DELETE FROM readers WHERE publication_id = ?", (publication_id,))
        for reader in wanted:
            connection.execute(
                "INSERT INTO readers (publication_id, reader, granted_at) VALUES (?, ?, ?)",
                (publication_id, reader, now()),
            )
    return {"publication_id": publication_id, "readers": wanted}


def _clean(readers: list[str] | None) -> list[str]:
    return sorted({entry.strip().lower() for entry in (readers or []) if entry.strip()})


if __name__ == "__main__":
    # stdio when you are poking at it locally, http when it is hosted. An MCP server the
    # Operator adds to their org has to be reachable over http — stdio only works for a
    # client that can start the process itself, which a hosted one cannot.
    transport = os.environ.get("CONTINUITY_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport=transport,
            host=os.environ.get("CONTINUITY_HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "8080")),
        )
