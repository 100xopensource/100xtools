"""Send a bundle to a URL someone else minted, and treat the 2xx as the receipt.

This is how the plugin reaches object storage **without ever holding a credential**.
It does not sign requests, does not know a bucket name, and has no notion of a
provider. Someone else — an MCP server the operator runs, under their own identity
and their own access rules — mints a short-lived presigned `PUT` and hands back the
URL plus whatever headers it bound. This module PUTs the bytes verbatim.

Two consequences of that split are worth stating plainly:

- **The store and this module are different things.** `store.py` addresses
  publications you can list, read back, and verify. A presigned `PUT` is a one-way
  transport: you cannot enumerate it, cannot read from it, and cannot re-derive its
  key. Modelling it as a store would promise operations it cannot perform, which is
  why object storage is a `service` store — a server that answers, not a directory.
- **The 2xx is the only proof.** There is no finalize step and nothing to poll. If
  the mint bound a content length or checksum, the object store itself rejects a body
  that does not match, so a success means those exact bytes landed.

The URL rules, the refusal to follow a redirect, and the optional host pin live in
`wire.py`, shared with the download side.
"""

from __future__ import annotations

import pathlib
import urllib.request
from typing import Any

from engine import keys, wire


def upload(
    payload: bytes | str | pathlib.Path,
    mint: dict[str, Any],
    *,
    timeout: int = wire.DEFAULT_TIMEOUT_SECONDS,
    opener_factory=None,
) -> dict[str, Any]:
    """PUT `payload` to the minted URL. Returns a receipt, or raises `TransferError`.

    `mint` is whatever the operator's tool returned; only `url` and
    `required_headers` are read.
    """
    url, headers = wire.read_mint(mint)
    body = _read_body(payload)
    if not body:
        raise wire.TransferError("empty_body", "refusing to upload zero bytes")
    wire.validate_url(url)

    request = urllib.request.Request(url, data=body, method="PUT")
    for name, value in headers.items():
        request.add_header(name, value)
    status, _ = wire.send(request, timeout=timeout, opener_factory=opener_factory)
    return {
        "ok": True,
        "receipt": "http_2xx",
        "status": status,
        "bytes": len(body),
        "sha256": keys.content_digest(body),
    }


def _read_body(payload: bytes | str | pathlib.Path) -> bytes:
    if isinstance(payload, bytes):
        return payload
    path = pathlib.Path(payload).expanduser()
    try:
        return path.read_bytes()
    except OSError as exc:
        raise wire.TransferError("body_unreadable", f"could not read {path}: {exc}") from exc
