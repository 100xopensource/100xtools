"""Identity, canonical serialization, and the names a publication is filed under.

Pure functions over strings and JSON values — no I/O, no config, no clock. That
matters twice over here: every digest has to come out the same on the machine that
publishes and the machine that reads, and a test has to be able to fix the time by
passing it rather than by patching a clock.

**Normalizing a session id.** A caller that cannot resolve its own session id still
publishes something; it just passes a sentinel. `normalize_session_id` maps every
known sentinel to `None`, so an unresolved session is filed under one explicit
`unattributed` slot instead of one slot per spelling of "I don't know".

**Names, not digests.** A publication is meant to be found by a human reading a
shared folder — the recipient is handed a path and has to recognise it. So a session
directory carries a readable name with a short digest suffix, and a publication is
named for the moment it was published plus the digest of its own bytes. Nothing here
is reversible-secret: a folder store shows what it holds to anyone who can see it,
which is a property of the folder and is stated as such in the skills.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Sentinels meaning "the session id did not resolve". A caller that cannot expand
# its session id emits one of these rather than inventing an id; they normalize to
# None so unresolved sessions land in an explicit slot instead of colliding under a
# shared literal. Compared case-folded after trimming.
#
# `${claude_session_id}` is here because that is the shape an *unsubstituted* skill
# placeholder arrives in: Claude Code expands `${CLAUDE_SESSION_ID}` in a skill's
# markdown, but a body that reaches the model as literal text leaves the placeholder
# intact, and it would otherwise become a directory named after the variable.
UNRESOLVED_SESSION_IDS = frozenset(
    {
        "",
        "none",
        "null",
        "unknown",
        "unknown-session",
        "${claude_session_id}",
        "$claude_session_id",
    }
)

# Where an unresolved session's publications land. A real, visible slot rather than
# a sentinel that leaks into a path: nothing downstream needs a special case, and it
# stays obvious when browsing the store by eye.
UNATTRIBUTED = "unattributed"

# Anything outside this set is percent-escaped out of a namespace before it becomes
# a directory, so a namespace can never introduce a path separator, traverse a
# directory, or collide with a sibling by case on a case-insensitive filesystem.
# `.` is deliberately NOT safe: allowing it lets `..` through intact, and a
# namespace is a short label that loses nothing by escaping dots.
_NAMESPACE_SAFE = re.compile(r"[^a-z0-9_-]")

# Characters kept verbatim in a human-browsable directory name.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

# A publication id: the UTC stamp it was published at, then 12 hex of the bundle's
# own digest. Anchored, and used to validate an id that arrived from outside — a
# recipient pastes one, so it is untrusted input that becomes a path segment.
PUBLICATION_ID_RE = re.compile(r"\A\d{8}T\d{6}Z-[0-9a-f]{12}\Z")


def normalize_session_id(session_id: str | None) -> str | None:
    """Trim a session id and drop unresolved sentinels; `None` if nothing is left.

    The single normalization every caller runs, so a padded id and a clean one
    agree by construction and no sentinel ever reaches a path.
    """
    if session_id is None:
        return None
    trimmed = session_id.strip()
    if trimmed.lower() in UNRESOLVED_SESSION_IDS:
        return None
    return trimmed


def normalize_namespace(namespace: str | None) -> str:
    """Fold a namespace to a safe path segment, defaulting to `default`.

    A namespace separates unrelated projects sharing one store. It is
    caller-supplied text, so it is lowercased and escaped down to `[a-z0-9_-]`
    before it can become a directory: no separators, no traversal, and no two
    namespaces differing only by case addressing one slot on a case-insensitive
    filesystem.
    """
    if namespace is None:
        return "default"
    folded = namespace.strip().lower()
    if not folded:
        return "default"
    # Percent-escape rather than strip, so two distinct namespaces cannot fold onto
    # each other by having their unsafe characters silently deleted.
    return _NAMESPACE_SAFE.sub(lambda m: f"%{ord(m.group()):02x}", folded)


def session_slot(session_id: str | None) -> str:
    """The directory one session's publications live in.

    A readable prefix so a person scanning a shared folder recognises it, plus a
    digest suffix so two ids that escape to the same prefix stay apart.
    """
    resolved = normalize_session_id(session_id)
    if resolved is None:
        return UNATTRIBUTED
    readable = _SAFE_NAME.sub("_", resolved).strip("._-")[:80] or "session"
    return f"{readable}-{hashlib.sha256(resolved.encode('utf-8')).hexdigest()[:12]}"


def publication_id(stamp: str, bundle_sha256: str) -> str:
    """Name one publication: when it was published, and what it contains.

    Both halves earn their place. The stamp sorts chronologically and is what a
    person reads; the digest means republishing changed bytes never overwrites the
    earlier publication, so nothing in a synced folder is ever rewritten and a sync
    client has no two versions to reconcile.
    """
    require_digest(bundle_sha256, "bundle_sha256")
    if not re.fullmatch(r"\d{8}T\d{6}Z", stamp or ""):
        raise ValueError(f"stamp must look like 20260820T140311Z, got {stamp!r}")
    return f"{stamp}-{bundle_sha256[:12]}"


def canonical_json(value: Any) -> bytes:
    """Serialize deterministically: sorted keys, no spaces, no NaN, UTF-8.

    Every digest in the engine is taken over this encoding, so the same logical
    record hashes identically across machines and across runs. `allow_nan=False`
    matters: JSON has no NaN/Infinity, and letting Python's non-standard spelling
    through would produce a manifest other readers reject.
    """
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def readable_json(value: Any) -> bytes:
    """The same value, indented, for a file a person is expected to open.

    A manifest is read by hand when something looks wrong, so it is stored
    indented. Digests are never taken over this form — `canonical_json` is.
    """
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def reject_nonfinite_json(value: str) -> None:
    """`json.load` hook that refuses `NaN`/`Infinity` on the way in.

    Paired with `canonical_json`'s `allow_nan=False`, so a non-finite number can
    neither enter a manifest nor be written back out of one.
    """
    raise ValueError(f"non-finite number {value}")


def content_digest(data: bytes) -> str:
    """The sha256 of some bytes — their identity and how a reader verifies them."""
    return hashlib.sha256(data).hexdigest()


def integrity_hash(value: Any) -> str:
    """A prefixed digest over a JSON value, for recording alongside the value."""
    return f"sha256:{hashlib.sha256(canonical_json(value)).hexdigest()}"


def stable_event_id(
    *, source: str, session_id: str, source_cursor: dict[str, Any]
) -> str:
    """The idempotency key for one transcript record.

    Identity is the *source position*, not the moment of reading: publishing one
    transcript twice must produce the same ids, which is what lets a reader compare
    two published copies of a session instead of diffing noise.
    """
    identity = {
        "source": source,
        "session_id": session_id,
        "source_cursor": source_cursor,
    }
    return f"evt_{hashlib.sha256(canonical_json(identity)).hexdigest()}"


def require_digest(value: str, field: str) -> None:
    """Reject anything that is not a lowercase hex sha256.

    Digests are joined into paths and compared against stored ones, so a non-digest
    is the one input that could introduce a separator or a traversal. Checked at the
    seam rather than trusted from the caller.
    """
    if not _HEX64.match(value or ""):
        raise ValueError(f"{field} must be a lowercase hex sha256, got {value!r}")


def require_publication_id(value: str) -> str:
    """Reject anything that is not a publication id, and return it if it is.

    A recipient pastes this in, so it arrives as untrusted text and then becomes a
    path segment. Validating the shape is what stops `../..` from being one.
    """
    if not PUBLICATION_ID_RE.match(value or ""):
        raise ValueError(
            f"{value!r} is not a publication id — expected one like "
            "20260820T140311Z-9f2c1ab4d0e5"
        )
    return value
