"""Session identity and the content-addressed key scheme.

Two jobs, both pure functions over strings — no I/O, no config, so every storage
backend derives identical keys for identical inputs.

**Normalizing a session id.** A caller that cannot resolve its own session id
still saves something; it just passes a sentinel. `normalize_session_id` maps
every known sentinel to `None` so an unresolved session is stored under an
explicit "unattributed" slot rather than silently colliding with every *other*
unresolved session under one shared literal. Comparison is case-folded and
whitespace-trimmed, so a padded id and a clean one address the same session.

**Addressing an object.** Artifact bytes are keyed by their own sha256, which is
what makes the local backend safe inside a folder a consumer sync client watches
(iCloud Drive, OneDrive, Google Drive). Two machines saving identical bytes
produce the same key and the same file, so a sync client has nothing to fork a
conflict copy over. Nothing is ever rewritten in place — see `store.py`, whose
entry log is append-only for the same reason.
"""

from __future__ import annotations

import hashlib
import re

# Sentinels meaning "the session id did not resolve". A caller that cannot expand
# its session id emits one of these rather than inventing an id; they normalize to
# None so unresolved sessions land in an explicit bucket instead of colliding
# under a shared literal. Compared case-folded after trimming.
UNRESOLVED_SESSION_IDS = frozenset(
    {
        "",
        "none",
        "null",
        "unknown",
        "unknown-session",
        "${claude_session_id}",
    }
)

# Where an unresolved session's objects land. A real slot, not a sentinel that
# leaks into a key: it is a digest like any other, so nothing downstream needs a
# special case, and it stays visibly distinct when browsing the store by eye.
UNATTRIBUTED = "unattributed"

# Anything outside this set is percent-escaped out of a namespace before it
# reaches a key, so a namespace can never introduce a path separator, traverse a
# directory, or collide with a sibling by case on a case-insensitive filesystem.
# `.` is deliberately NOT safe: allowing it lets `..` through intact, and a
# namespace is a short label that loses nothing by escaping dots.
_NAMESPACE_SAFE = re.compile(r"[^a-z0-9_-]")

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def normalize_session_id(session_id: str | None) -> str | None:
    """Trim a session id and drop unresolved sentinels; `None` if it resolves to nothing.

    The single normalization every caller runs before digesting, so a padded id
    and a clean one agree by construction and no sentinel ever reaches a key.
    """
    if session_id is None:
        return None
    trimmed = session_id.strip()
    if trimmed.lower() in UNRESOLVED_SESSION_IDS:
        return None
    return trimmed


def normalize_namespace(namespace: str | None) -> str:
    """Fold a namespace to a safe key segment, defaulting to `default`.

    A namespace separates unrelated projects that share one bucket or one synced
    folder. It is caller-supplied text, so it is lowercased and escaped down to
    `[a-z0-9_-]` before it can reach a key: no separators, no traversal, and no
    two namespaces differing only by case addressing different slots on a
    case-insensitive filesystem.
    """
    if namespace is None:
        return "default"
    folded = namespace.strip().lower()
    if not folded:
        return "default"
    # Percent-escape rather than strip, so two distinct namespaces cannot fold
    # onto each other by having their unsafe characters silently deleted.
    return _NAMESPACE_SAFE.sub(lambda m: f"%{ord(m.group()):02x}", folded)


def session_digest(namespace: str | None, session_id: str | None) -> str:
    """The per-namespace-per-session digest that scopes every key.

    An unresolved session id digests under `UNATTRIBUTED` instead of its raw
    value, so unresolved sessions stay grouped and inspectable rather than
    scattered across one slot per sentinel spelling.
    """
    resolved = normalize_session_id(session_id) or UNATTRIBUTED
    ns = normalize_namespace(namespace)
    return hashlib.sha256(f"{ns}:{resolved}".encode()).hexdigest()


def content_digest(data: bytes) -> str:
    """The sha256 of an artifact's bytes — its identity and its key."""
    return hashlib.sha256(data).hexdigest()


def blob_key(session_digest_hex: str, content_sha256: str) -> str:
    """Key for one artifact's bytes: content-addressed under its session.

    Identical bytes saved twice — from two machines, or one machine twice —
    produce one key and one file, which is what keeps a synced folder free of
    conflict copies.
    """
    _require_digest(session_digest_hex, "session_digest_hex")
    _require_digest(content_sha256, "content_sha256")
    return f"sessions/{session_digest_hex}/blobs/{content_sha256}"


def entry_key(session_digest_hex: str, ordinal: str, entry_sha256: str) -> str:
    """Key for one append-only log entry describing a save.

    `ordinal` sorts the log (an ISO-8601 UTC stamp from the caller — the clock is
    never read in here, so keys stay reproducible in a test). The entry's own
    digest is the tiebreaker, so two machines writing at the same instant produce
    two distinct entries instead of one overwriting the other.
    """
    _require_digest(session_digest_hex, "session_digest_hex")
    _require_digest(entry_sha256, "entry_sha256")
    if not ordinal or "/" in ordinal:
        raise ValueError(f"ordinal must be a non-empty path segment, got {ordinal!r}")
    return f"sessions/{session_digest_hex}/entries/{ordinal}-{entry_sha256[:12]}.json"


def session_prefix(session_digest_hex: str) -> str:
    """Everything belonging to one session, for a prefix listing."""
    _require_digest(session_digest_hex, "session_digest_hex")
    return f"sessions/{session_digest_hex}/"


def _require_digest(value: str, field: str) -> None:
    """Reject anything that is not a lowercase hex sha256.

    Keys are built by joining these into a path, so a non-digest here is the one
    input that could introduce a separator or a traversal. Checked at the seam
    rather than trusted from the caller.
    """
    if not _HEX64.match(value or ""):
        raise ValueError(f"{field} must be a lowercase hex sha256, got {value!r}")
