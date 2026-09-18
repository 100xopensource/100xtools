"""Pull a bundle back down from a URL someone else minted, and verify it.

The mirror of `upload.py`, and it exists for the same reason: the plugin holds no
credential, so the operator's own MCP server decides who may read a publication and
hands back a short-lived presigned `GET`. This module fetches those bytes and writes
them to a file.

What it adds over the upload side is **verification**, because a download is where
the interesting failures land:

- A size cap, enforced while reading rather than after, so an unexpectedly enormous
  or endless response is refused instead of filling the disk.
- A digest check against the sha256 the caller was told to expect. That check is the
  difference between "this is the bundle that was published" and "this is whatever
  answered the URL" — and the caller usually got that digest from the same server
  that minted the URL, so it is a consistency check, not a trust anchor.
- Writing through a temporary file and renaming, so an interrupted download never
  leaves a half file that reads as a short conversation.

Whether the *contents* can be trusted is a separate question, answered in
`bundle.py`: every member is checked before extraction, because a bundle is written
by someone else.
"""

from __future__ import annotations

import pathlib
import urllib.request
from typing import Any

from engine import bundle as bundle_mod, keys, wire

# The largest bundle this will pull down. Matches the bundle module's own total cap,
# so a body that could not have been produced here is refused before it is written.
MAX_BYTES = bundle_mod.MAX_TOTAL_BYTES

_CHUNK = 1024 * 256


def download(
    destination: str | pathlib.Path,
    mint: dict[str, Any],
    *,
    expected_sha256: str | None = None,
    max_bytes: int = MAX_BYTES,
    timeout: int = wire.DEFAULT_TIMEOUT_SECONDS,
    opener_factory=None,
) -> dict[str, Any]:
    """GET the minted URL into `destination`; return what landed.

    Raises `TransferError` for anything that stops the bytes arriving, including a
    digest that does not match — a wrong bundle written to the right filename is the
    one failure here that would otherwise look like success.
    """
    url, headers = wire.read_mint(mint)
    wire.validate_url(url)
    if expected_sha256:
        keys.require_digest(expected_sha256, "expected_sha256")

    request = urllib.request.Request(url, method="GET")
    for name, value in headers.items():
        request.add_header(name, value)

    def read(response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise wire.TransferError(
                    "body_too_large",
                    f"the response is over the {max_bytes}-byte cap; stopped reading",
                )
            chunks.append(chunk)
        return b"".join(chunks)

    status, body = wire.send(
        request, timeout=timeout, opener_factory=opener_factory, reader=read
    )
    body = body or b""
    if not body:
        raise wire.TransferError(
            "empty_body", "the store answered with no bytes, so there is nothing to read"
        )

    digest = keys.content_digest(body)
    if expected_sha256 and digest != expected_sha256:
        raise wire.TransferError(
            "digest_mismatch",
            f"the downloaded bytes hash to {digest[:12]}… but {expected_sha256[:12]}… "
            "was expected — this is not the publication you were pointed at",
        )

    target = pathlib.Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(f".tmp-{target.name}")
    scratch.write_bytes(body)
    scratch.replace(target)
    return {
        "ok": True,
        "receipt": "http_2xx",
        "status": status,
        "path": str(target),
        "bytes": len(body),
        "sha256": digest,
        "verified": bool(expected_sha256),
    }
