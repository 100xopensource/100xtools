"""The folder store: publications on a disk somebody else can also see.

```
<root>/<namespace>/<session>/<publication-id>/
    bundle.zip          written first
    publication.json    written last — the marker that says this one is complete
```

The whole design answers one question: **a person is handed a path and has to be
able to act on it.** So nothing here is content-addressed into opacity, nothing is
rewritten in place, and every directory name is something a human can read in a file
browser and match against what they were told.

Four properties, each bought deliberately:

- **Nothing is ever rewritten.** A publication id carries the digest of its own
  bundle, so a second publish of changed work lands beside the first rather than over
  it. A sync client therefore never has two versions of one file to reconcile, and
  conflict copies are structurally impossible rather than resolved after the fact.
- **A republish of unchanged work is recognised, not duplicated.** Bundles are
  reproducible, so an identical bundle already in the session's directory is reported
  as the publication it is.
- **`publication.json` last.** An interrupted publish leaves a directory with no
  marker, which every reader here skips. Half a publication is never mistaken for a
  small one.
- **Bytes are verified against the digest in the marker.** A synced folder can
  evict a file's contents while leaving its name in place, and a read then returns
  short or empty bytes with *no error*. Short is `ObjectNotMaterialized` (wait for the
  client); full-length-but-wrong is corruption, a different problem with a different
  remedy.

**There is no access control here, and the skills say so.** A folder store is exactly
as private as the folder: anyone who can open it reads every publication in it.
Redaction is the only boundary on that path. Per-recipient access is what the
`service` store is for, where the operator's own server decides who may read what.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from engine import bundle as bundle_mod, keys

LAYOUT = "100x-continuity/publication@1"
MARKER_NAME = "publication.json"

# iCloud is the one client that leaves a marker behind when it evicts a file's
# contents. Spotting it is a fast path to a better message; the digest check below is
# what actually catches an eviction, whichever client did it.
_EVICTED_SUFFIX = ".icloud"


class StoreError(Exception):
    """The store could not be read or written."""


class PublicationNotFound(StoreError):
    """Nothing at that handle."""


class ObjectNotMaterialized(StoreError):
    """The publication exists, but a sync client has not put its bytes here yet."""


def install(
    root: str | pathlib.Path,
    built: bundle_mod.Built,
    *,
    namespace: str | None,
    session_id: str | None,
    stamp: str,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """File a built bundle as a publication, and return its record.

    `stamp` is passed in rather than read from a clock here, so a caller — or a test
    — decides what time it is exactly once per publish.
    """
    base = pathlib.Path(root).expanduser()
    ns = keys.normalize_namespace(namespace)
    slot = keys.session_slot(session_id)
    session_dir = base / ns / slot

    existing = _same_bundle(session_dir, built.sha256)
    if existing is not None:
        return {**existing, "already_published": True}

    publication_id = keys.publication_id(stamp, built.sha256)
    target = session_dir / publication_id
    target.mkdir(parents=True, exist_ok=True)

    record = {
        "layout": LAYOUT,
        "publication_id": publication_id,
        "handle": f"{ns}/{slot}/{publication_id}",
        "published_at": stamp,
        "namespace": ns,
        "session": {
            **built.manifest.get("session", {}),
            "slot": slot,
            "resolved": keys.normalize_session_id(session_id) is not None,
        },
        "bundle": {
            "name": bundle_mod.BUNDLE_NAME,
            "sha256": built.sha256,
            "size": built.size,
        },
        "transcript": built.manifest.get("transcript", {}),
        "artifacts": built.manifest.get("artifacts", {}),
        "redacted": built.redacted,
        "source": source or {},
    }

    # Bundle first, marker last. A crash between the two leaves an unmarked
    # directory, which reads as an interrupted publish rather than as a publication
    # naming bytes that are not there.
    (target / bundle_mod.BUNDLE_NAME).write_bytes(built.path.read_bytes())
    _write_marker(target, record)
    return {**record, "path": str(target), "already_published": False}


def _write_marker(target: pathlib.Path, record: dict[str, Any]) -> None:
    scratch = target / f".tmp-{MARKER_NAME}"
    scratch.write_bytes(keys.readable_json(record))
    scratch.replace(target / MARKER_NAME)


def _same_bundle(session_dir: pathlib.Path, sha256: str) -> dict[str, Any] | None:
    """An existing publication in this session holding exactly these bytes."""
    for record in _read_session(session_dir):
        if record.get("bundle", {}).get("sha256") == sha256:
            return record
    return None


def _read_session(session_dir: pathlib.Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not session_dir.is_dir():
        return out
    for entry in sorted(session_dir.iterdir()):
        record = read_marker(entry)
        if record is not None:
            out.append({**record, "path": str(entry)})
    return out


def read_marker(publication_dir: pathlib.Path) -> dict[str, Any] | None:
    """One publication's record, or None when this is not a finished publication.

    Returning None rather than raising is the point: a store is browsed by
    directory listing, and an in-progress or foreign directory beside real
    publications must not make the whole listing fail.
    """
    marker = publication_dir / MARKER_NAME
    try:
        raw = marker.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, OSError):
        return None
    try:
        record = json.loads(raw, parse_constant=keys.reject_nonfinite_json)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("layout") != LAYOUT:
        return None
    return record


def publications(
    root: str | pathlib.Path, *, namespace: str | None = None
) -> list[dict[str, Any]]:
    """Every finished publication under `root`, newest first.

    Listed by walking, never by reading an index: an index in a synced folder is one
    more file two machines can disagree about, and the directory tree already holds
    the answer.
    """
    base = pathlib.Path(root).expanduser()
    if not base.is_dir():
        return []
    wanted = keys.normalize_namespace(namespace) if namespace else None
    found: list[dict[str, Any]] = []
    for ns_dir in sorted(entry for entry in base.iterdir() if entry.is_dir()):
        if wanted and ns_dir.name != wanted:
            continue
        for session_dir in sorted(e for e in ns_dir.iterdir() if e.is_dir()):
            found.extend(_read_session(session_dir))
    found.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    return found


def resolve(
    handle: str, *, root: str | pathlib.Path | None = None
) -> dict[str, Any]:
    """Find one publication from whatever the recipient was given.

    Three forms are accepted, because all three are things a person actually pastes:
    a path to the publication directory, a path to the `bundle.zip` inside it, and a
    `<namespace>/<session>/<publication-id>` handle to look up under the configured
    root. Anything else is refused with the forms named, rather than guessed at.
    """
    text = (handle or "").strip()
    if not text:
        raise PublicationNotFound("no handle was given")

    candidate = pathlib.Path(text).expanduser()
    if candidate.name == bundle_mod.BUNDLE_NAME and candidate.is_file():
        candidate = candidate.parent
    if candidate.is_dir():
        record = read_marker(candidate)
        if record is None:
            raise PublicationNotFound(
                f"{candidate} holds no {MARKER_NAME}, so it is not a finished "
                "publication — the publish may have been interrupted"
            )
        return {**record, "path": str(candidate)}

    parts = [part for part in pathlib.PurePosixPath(text).parts if part not in (".", "/")]
    if root and len(parts) == 3 and ".." not in parts:
        keys.require_publication_id(parts[2])
        target = pathlib.Path(root).expanduser() / parts[0] / parts[1] / parts[2]
        record = read_marker(target)
        if record is not None:
            return {**record, "path": str(target)}
        raise PublicationNotFound(
            f"no publication at {target}. Check the store root and the handle with "
            "`where`, and check the folder has finished syncing"
        )
    raise PublicationNotFound(
        f"{text!r} is not a handle this can resolve. Pass a path to a publication "
        "directory, a path to its bundle.zip, or "
        "<namespace>/<session>/<publication-id> with the store root configured"
    )


def bundle_path(record: dict[str, Any]) -> pathlib.Path:
    """The verified path to a publication's bundle, or a named reason it is not readable.

    This is where an evicted file is told apart from a corrupt one. Both look like
    "the read went wrong"; only one of them is fixed by waiting.
    """
    location = record.get("path")
    if not location:
        raise StoreError("this publication record carries no path")
    path = pathlib.Path(location) / str(
        record.get("bundle", {}).get("name") or bundle_mod.BUNDLE_NAME
    )
    expected_size = record.get("bundle", {}).get("size")
    expected_sha = record.get("bundle", {}).get("sha256")

    if not path.exists():
        if (path.parent / f".{path.name}{_EVICTED_SUFFIX}").exists():
            raise ObjectNotMaterialized(
                f"{path.name} is in the cloud but not on this machine yet — iCloud has "
                "evicted it. Open the folder to make the client download it, then retry"
            )
        raise PublicationNotFound(f"{path} is missing from a publication that names it")

    size = path.stat().st_size
    if isinstance(expected_size, int) and size < expected_size:
        raise ObjectNotMaterialized(
            f"{path.name} is {size} of {expected_size} bytes — a sync client is still "
            "downloading it. Wait for it to finish and retry; do not republish over it"
        )
    if isinstance(expected_sha, str) and expected_sha:
        actual = keys.content_digest(path.read_bytes())
        if actual != expected_sha:
            raise StoreError(
                f"{path.name} is corrupt: its bytes hash to {actual[:12]}… but the "
                f"publication names {expected_sha[:12]}…. Waiting will not fix this"
            )
    return path
