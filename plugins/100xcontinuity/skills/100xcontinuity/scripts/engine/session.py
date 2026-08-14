"""Saving artifacts into a session, and folding a session back out.

A session is an **append-only log plus a set of content-addressed blobs**. Saving
writes one blob (the bytes) and one entry (a small JSON record naming them).
Nothing is ever rewritten, which is what lets two machines write to one session
inside a synced folder without a sync client forking a conflict copy.

Restoring folds the log: entries are read in key order — which is chronological,
because the ordinal leading each key is a UTC timestamp — and the last entry for
a given name wins. The full history stays readable, so a save that turned out to
be wrong can be inspected rather than only overwritten.

The clock is read exactly once per save, in `save_artifact`, and threaded down as
`stamp`. Everything below it is a pure function of its arguments, so a test fixes
the time by passing it.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from engine import keys
from engine.store import ObjectNotFound, ObjectNotMaterialized, ObjectStore


# Entry records are small by contract: they name bytes, they never carry them.
# A record over this size means a caller is trying to smuggle content into the
# log, where it would defeat the content-addressing the blobs provide.
MAX_ENTRY_BYTES = 16 * 1024


class SessionError(Exception):
    """A session could not be saved or read back."""


def utc_stamp(now: dt.datetime | None = None) -> str:
    """A sortable UTC ordinal for an entry key.

    Colons are not portable inside a filename on every filesystem this may sync
    to, so the time separators are hyphens. Lexical order still matches
    chronological order, which is what the fold relies on.
    """
    moment = now or dt.datetime.now(dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def save_artifact(
    store: ObjectStore,
    *,
    namespace: str | None,
    session_id: str | None,
    name: str,
    data: bytes,
    media_type: str | None = None,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Write one artifact into a session; return the entry that was recorded.

    Two writes of identical bytes under the same name are not an error and cost
    one blob between them — the blob key is the content digest, so the second
    write finds it already present.
    """
    if not name or "\n" in name:
        raise SessionError(f"artifact name must be a non-empty single line, got {name!r}")

    digest = keys.session_digest(namespace, session_id)
    sha = keys.content_digest(data)
    ordinal = stamp or utc_stamp()

    entry = {
        "name": name,
        "sha256": sha,
        "size": len(data),
        "media_type": media_type,
        "saved_at": ordinal,
        # The id as the caller gave it. The digest above is what addresses the
        # session; this is here so an unattributed save can still be traced back
        # to whatever the caller thought its session was.
        "session_id": session_id,
        "namespace": keys.normalize_namespace(namespace),
        "resolved": keys.normalize_session_id(session_id) is not None,
    }
    payload = _encode_entry(entry)

    # Blob first: an entry naming bytes that are not there yet would make a
    # crash between the two writes look like corruption instead of a lost save.
    store.put(keys.blob_key(digest, sha), data)
    store.put(keys.entry_key(digest, ordinal, keys.content_digest(payload)), payload)
    return entry


def read_session(
    store: ObjectStore, *, namespace: str | None, session_id: str | None
) -> dict[str, Any]:
    """Fold a session's log into its current state.

    Returns the artifacts live now (last entry per name wins), the full history in
    chronological order, and any entries that could not be parsed. A damaged
    entry is reported rather than raised on: one bad record must not make the
    other artifacts in a session unrecoverable.
    """
    digest = keys.session_digest(namespace, session_id)
    entry_prefix = f"{keys.session_prefix(digest)}entries/"

    history: list[dict[str, Any]] = []
    sound_keys: list[str] = []
    damaged: list[str] = []
    for key in store.list(entry_prefix):
        try:
            record = json.loads(store.get(key).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ObjectNotFound):
            damaged.append(key)
            continue
        history.append(record)
        sound_keys.append(key)

    # An entry that parses as JSON but does not describe an artifact is damaged
    # too. Counting only unparseable ones let a record with no `sha256` through
    # as a healthy artifact, and the failure surfaced later as a crash on read
    # rather than here, where the caller is already being told what is wrong.
    artifacts: dict[str, dict[str, Any]] = {}
    for entry, key in zip(history, sound_keys):
        if _describes_an_artifact(entry):
            artifacts[entry["name"]] = entry
        else:
            damaged.append(key)

    return {
        "session_digest": digest,
        "namespace": keys.normalize_namespace(namespace),
        "resolved": keys.normalize_session_id(session_id) is not None,
        "artifacts": artifacts,
        "history": history,
        "damaged": damaged,
    }


def load_artifact(
    store: ObjectStore, *, namespace: str | None, session_id: str | None, name: str
) -> bytes:
    """Return the current bytes of one named artifact, verified against its digest.

    The verification is the real eviction guarantee. A sync client that reclaims
    disk leaves a file readable but short or empty, and only iCloud leaves a
    marker a store could spot — Dropbox and Google Drive do not. Here the
    expected digest is known, so bytes that do not hash to it are rejected
    whichever client did it, and truncation is caught for free.

    Empty or short bytes read as an eviction (`ObjectNotMaterialized`: wait for
    the sync client). A full-length mismatch is corruption, which is a different
    problem with a different remedy, so it does not borrow that name.
    """
    state = read_session(store, namespace=namespace, session_id=session_id)
    entry = state["artifacts"].get(name)
    if entry is None:
        raise SessionError(f"no artifact named {name!r} in this session")

    expected = entry.get("sha256")
    if not isinstance(expected, str):
        raise SessionError(
            f"the entry for {name!r} names no sha256, so its bytes cannot be located "
            "or verified — the entry is damaged"
        )
    try:
        blob_key = keys.blob_key(state["session_digest"], expected)
    except ValueError as exc:
        raise SessionError(f"the entry for {name!r} is damaged: {exc}") from exc

    data = store.get(blob_key)
    actual = keys.content_digest(data)
    if actual == expected:
        return data
    if len(data) < entry.get("size", len(data) + 1):
        raise ObjectNotMaterialized(
            f"{name!r} is in the cloud but not fully on this machine yet — "
            f"got {len(data)} of {entry.get('size')} bytes. Ask the sync client to "
            "download it and retry; do not re-save, which would overwrite the copy "
            "the client still holds"
        )
    raise SessionError(
        f"{name!r} is corrupt: its bytes hash to {actual[:12]}… but the entry names "
        f"{expected[:12]}…. The stored object no longer matches what was saved"
    )


def _describes_an_artifact(entry: Any) -> bool:
    """Whether a parsed entry carries the two fields a read actually needs.

    A name to look it up by, and a digest to locate and verify its bytes with.
    Anything missing either is a record that cannot be honoured, and saying so
    at fold time is what keeps `load_artifact` from failing on a `KeyError`.
    """
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and bool(entry.get("name"))
        and isinstance(entry.get("sha256"), str)
        and bool(entry.get("sha256"))
    )


def _encode_entry(entry: dict[str, Any]) -> bytes:
    """Serialize an entry deterministically, refusing an oversized record.

    Sorted keys and a fixed separator so the same entry always encodes to the
    same bytes — the entry's own digest is part of its key, and an unstable
    encoding would scatter one logical entry across several.
    """
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_ENTRY_BYTES:
        raise SessionError(
            f"entry record is {len(payload)} bytes, over the {MAX_ENTRY_BYTES} limit — "
            "entries name artifacts, they do not carry them"
        )
    return payload
