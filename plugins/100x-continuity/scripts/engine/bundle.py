"""The bundle: one publication's bytes, in a layout every reader can rely on.

```
start-here.html                     what a person sees when they open the zip
manifest.json                       written last inside the archive
transcript/session-digest.md        the readable page
transcript/session-record.jsonl     every transcript record, redacted
artifacts/<path>                    files the publishing session chose to include
```

**It is a zip, and that is a product decision rather than a technical one.** The person
who receives a handoff is a person before they are a session: a zip opens with a
double-click on every operating system they might be using, and `start-here.html` inside
it means the work is legible with no Claude, no engine, and nothing installed. A tarball
would have been marginally smaller and a support ticket on Windows.

Three decisions in that shape are load-bearing.

**The manifest describes content and nothing else.** No publish timestamp, no source
path, no store. Those are facts about a *publication* and live beside the archive
(see `store.py`), which is what makes the bundle a portable object: the same
conversation and the same files produce byte-identical bundles on two machines, so a
republish of unchanged work is recognisable as the same bundle rather than a second
one.

**Everything from the conversation is redacted on the way in; artifacts are not.**
The digest and the record cross the boundary through `redact.py` — the only path
into a bundle for anything the session said. Artifacts are files a person composed
and asked to include, so transforming them would corrupt content nobody asked us to
touch. Instead they are *scanned*, and a credential-shaped hit refuses the publish
by name. That fails closed without rewriting anyone's file.

**Reading a bundle is reading untrusted input.** A bundle arrives from someone else,
so every member is checked before extraction: inside the known layout, no absolute
paths, no `..`, no Windows separators or drive letters, no symlinks, and under the size
and count caps below. A zip is not safer than a tar here — it can carry all the same
hostile shapes, including a unix symlink in its external attributes — so nothing is
delegated to the library.
"""

from __future__ import annotations

import dataclasses
import io
import json
import pathlib
import stat
import zipfile
from typing import Any

from engine import digest as digest_mod, keys, page, redact

LAYOUT = "100x-continuity/bundle@1"

MANIFEST_NAME = "manifest.json"
LANDING_PAGE = "start-here.html"
TRANSCRIPT_DIR = "transcript"
ARTIFACT_DIR = "artifacts"
DIGEST_FILE = f"{TRANSCRIPT_DIR}/session-digest.md"
RECORD_FILE = f"{TRANSCRIPT_DIR}/session-record.jsonl"
BUNDLE_NAME = "bundle.zip"

# Caps. A bundle is written by us and read from anywhere, so the read side needs a
# bound it can refuse at rather than a promise the writer behaved.
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 5000

# Names that are almost never something to hand another person. Refused unless the
# caller says otherwise, because a staged `.env` is the one mistake here that cannot
# be walked back once the folder has synced.
SENSITIVE_NAMES = frozenset(
    {".env", ".netrc", ".npmrc", ".pgpass", "credentials", "id_rsa", "id_ed25519"}
)
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")

# Fixed member timestamp so identical content yields identical bytes. The real moment
# lives on the publication, which is where a reader looks for it anyway. 1980-01-01 is
# the zip format's own epoch — the earliest value it can store.
_EPOCH = (1980, 1, 1, 0, 0, 0)


class BundleError(Exception):
    """A bundle could not be built, or cannot be trusted to be read."""


@dataclasses.dataclass(frozen=True)
class Artifact:
    """One file staged for inclusion, and the name it will carry inside the bundle."""

    arcname: str
    source: pathlib.Path
    size: int


@dataclasses.dataclass(frozen=True)
class Built:
    """A written bundle: where it is, what it hashes to, and what went into it."""

    path: pathlib.Path
    sha256: str
    size: int
    manifest: dict[str, Any]
    redacted: dict[str, int]
    notes: tuple[str, ...] = ()


def plan_artifacts(
    paths: list[str],
    *,
    from_dirs: list[str] | None = None,
    root: str | None = None,
    allow_sensitive_names: bool = False,
) -> tuple[list[Artifact], list[str]]:
    """Resolve what to include, and the name each file takes inside the bundle.

    A name is the path relative to `root` when the file is under it, and the bare
    filename otherwise — so a bundle never carries a stranger's directory layout,
    and never carries an absolute path that an extractor would have to strip.

    Returns the artifacts and any notes worth reporting. Raises on the cases where
    continuing would publish something the caller did not mean to: a sensitive-looking
    filename, an oversized file, a path that is not a regular file.
    """
    base = pathlib.Path(root or ".").expanduser().resolve()
    selected: dict[str, Artifact] = {}
    notes: list[str] = []
    total = 0

    candidates: list[pathlib.Path] = [pathlib.Path(p).expanduser() for p in paths]
    for directory in from_dirs or []:
        top = pathlib.Path(directory).expanduser()
        if not top.is_dir():
            raise BundleError(f"--artifacts-from-dir {top} is not a directory")
        candidates.extend(sorted(entry for entry in top.rglob("*") if entry.is_file()))

    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.exists():
            raise BundleError(f"artifact {candidate} does not exist")
        if not resolved.is_file():
            raise BundleError(
                f"artifact {candidate} is not a regular file — only files are included, "
                "so pass --artifacts-from-dir for a directory"
            )
        name = _arcname(resolved, base)
        if not allow_sensitive_names and _looks_sensitive(resolved.name):
            raise BundleError(
                f"refusing to include {candidate}: its name is one that usually holds "
                "credentials. Include it deliberately with --allow-sensitive-names, or "
                "leave it out"
            )
        size = resolved.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise BundleError(
                f"artifact {candidate} is {size} bytes, over the "
                f"{MAX_ARTIFACT_BYTES}-byte per-file cap"
            )
        total += size
        if total > MAX_TOTAL_BYTES:
            raise BundleError(
                f"the staged artifacts exceed the {MAX_TOTAL_BYTES}-byte total cap"
            )
        if name in selected and selected[name].source != resolved:
            raise BundleError(
                f"two different files would both be included as {name!r} "
                f"({selected[name].source} and {resolved}) — pass --artifact-root so "
                "their paths stay distinct"
            )
        selected[name] = Artifact(arcname=name, source=resolved, size=size)

    if len(selected) > MAX_MEMBERS:
        raise BundleError(f"{len(selected)} artifacts is over the {MAX_MEMBERS} cap")
    return [selected[name] for name in sorted(selected)], notes


def _arcname(path: pathlib.Path, base: pathlib.Path) -> str:
    try:
        relative = path.relative_to(base)
    except ValueError:
        return path.name
    return relative.as_posix()


def _looks_sensitive(name: str) -> bool:
    lowered = name.lower()
    if lowered in SENSITIVE_NAMES or lowered.endswith(SENSITIVE_SUFFIXES):
        return True
    # Every `.env` variant, not just the bare name. `.env.local`, `.env.production`
    # and `.env.staging` hold exactly what `.env` holds, and a store service is
    # configured by one of them — so the file most likely to be sitting in the working
    # directory of a session about handoffs was the one name not covered.
    return lowered == ".env" or lowered.startswith(".env.")


def scan_artifacts(artifacts: list[Artifact]) -> dict[str, Any]:
    """Look for credential shapes in each artifact, without changing any of them.

    Text is scanned with the same patterns the transcript is redacted with. Bytes
    that are not text are reported as unscanned rather than guessed at — saying
    "nothing found" about a file nobody could read would be the more dangerous
    answer.
    """
    flagged: dict[str, dict[str, int]] = {}
    unscanned: list[str] = []
    for artifact in artifacts:
        raw = artifact.source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            unscanned.append(artifact.arcname)
            continue
        result = redact.redact_text(text)
        if not result.clean:
            flagged[artifact.arcname] = dict(result.counts)
    return {"flagged": flagged, "unscanned": unscanned}


def crossing(
    records: list[dict[str, Any]],
    *,
    include_record: bool = True,
) -> tuple[digest_mod.Digest, list[tuple[str, bytes]], dict[str, int]]:
    """Turn transcript records into the redacted files that may leave the machine.

    The whole boundary transform in one place: summarize, scrub the digest
    field-by-field, scrub every record, and report what was removed. It reads no
    configuration and writes nothing, so there is exactly one implementation of
    "redact, then render" and no second path that could quietly stop scrubbing.
    """
    if not records:
        raise BundleError(
            "the transcript holds no records, so there is nothing to publish — this "
            "may be a brand-new session"
        )
    summary = digest_mod.summarize(records)
    safe, counts = _redact_digest(summary)
    counts = dict(counts)

    files: list[tuple[str, bytes]] = [
        (DIGEST_FILE, safe.to_markdown().encode("utf-8"))
    ]
    if include_record:
        scrubbed = redact.redact_records(records)
        body = b"".join(
            keys.canonical_json(record) + b"\n" for record in scrubbed.value
        )
        files.append((RECORD_FILE, body))
        for name, hits in scrubbed.counts.items():
            counts[name] = counts.get(name, 0) + hits
    return safe, files, counts


# The captured text inside a digest. Everything else it carries — counts, tool
# names, timestamps, token totals — is this plugin's own scaffolding and is
# trustworthy by construction.
_CAPTURED_DIGEST_FIELDS = (
    "title",
    "prompts",
    "last_assistant_text",
    "files",
    "cwd",
    "git_branch",
    "open_notes",
)


def _redact_digest(
    summary: digest_mod.Digest,
) -> tuple[digest_mod.Digest, dict[str, int]]:
    """Scrub the captured text in a digest, leaving its own structure alone.

    Redacting the *rendered markdown* instead was the first attempt, and it read the
    digest's own headings as content: the `Tokens:` line matched the rule for a
    labelled credential and published `- Tokens: [redacted] 10`. Scrubbing the
    fields before rendering keeps recall on the parts that came from the session and
    stops the report from redacting itself.
    """
    scrubbed = redact.redact_value(
        {field: getattr(summary, field) for field in _CAPTURED_DIGEST_FIELDS}
    )
    return dataclasses.replace(summary, **scrubbed.value), scrubbed.counts


def write(
    out_path: str | pathlib.Path,
    records: list[dict[str, Any]],
    *,
    session: dict[str, Any],
    artifacts: list[Artifact] | None = None,
    include_record: bool = True,
    allow_flagged_artifacts: bool = False,
) -> Built:
    """Build the bundle at `out_path` and return what it is.

    `manifest.json` is added **last**, after every other member, so an archive
    interrupted mid-write cannot be mistaken for a complete bundle: a reader looks
    for the manifest first and refuses a bundle without one.
    """
    artifacts = artifacts or []
    safe, transcript_files, counts = crossing(records, include_record=include_record)
    scan = scan_artifacts(artifacts)
    if scan["flagged"] and not allow_flagged_artifacts:
        named = ", ".join(sorted(scan["flagged"]))
        raise BundleError(
            f"credential-shaped values were found in staged artifacts ({named}); the "
            "transcript is redacted but artifacts are included verbatim. Remove the "
            "value, drop the file, or pass --allow-flagged-artifacts to include it as "
            "it stands"
        )

    members: list[tuple[str, bytes]] = list(transcript_files)
    for artifact in artifacts:
        members.append(
            (f"{ARTIFACT_DIR}/{artifact.arcname}", artifact.source.read_bytes())
        )

    manifest = {
        "layout": LAYOUT,
        "session": {
            "id": session.get("id"),
            "outer_id": session.get("outer_id"),
            "title": safe.title,
        },
        "transcript": {
            "records": safe.records,
            "turns": safe.turns,
            "started_at": safe.started_at,
            "ended_at": safe.ended_at,
            "record_included": include_record,
        },
        "redacted": counts,
        "redaction_caveat": redact.CAVEAT,
        "artifacts": {
            "count": len(artifacts),
            "unscanned": sorted(scan["unscanned"]),
            "flagged": {name: dict(hits) for name, hits in scan["flagged"].items()},
        },
        "files": [
            {"path": name, "sha256": keys.content_digest(data), "size": len(data)}
            for name, data in sorted(members)
        ],
    }

    # The landing page is rendered from the manifest, so it is added after it exists and
    # then recorded in it — which is why it cannot list itself. Everything a reader needs
    # to verify is still covered: the page carries a digest like every other member.
    landing = page.render(safe, manifest).encode("utf-8")
    members.append((LANDING_PAGE, landing))
    manifest["files"].append(
        {"path": LANDING_PAGE, "sha256": keys.content_digest(landing), "size": len(landing)}
    )
    manifest["files"].sort(key=lambda entry: entry["path"])
    members.append((MANIFEST_NAME, keys.readable_json(manifest)))

    data = _pack(members)
    target = pathlib.Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    notes = []
    if scan["flagged"]:
        notes.append(
            "included artifacts holding credential-shaped values: "
            + ", ".join(sorted(scan["flagged"]))
        )
    if scan["unscanned"]:
        notes.append(
            f"{len(scan['unscanned'])} artifact(s) are not text and were not scanned"
        )
    return Built(
        path=target,
        sha256=keys.content_digest(data),
        size=len(data),
        manifest=manifest,
        redacted=counts,
        notes=tuple(notes),
    )


def _pack(members: list[tuple[str, bytes]]) -> bytes:
    """Zip `members`, in the order given, reproducibly.

    Fixed timestamps and fixed permissions, so two machines packing the same content
    produce the same bytes. That is what lets a store notice a republish of unchanged
    work instead of filing a second copy of it.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=_EPOCH)
            # Unix mode in the high half, where zip keeps it — with the regular-file
            # bits set, so a reader checking the file type finds one.
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return out.getvalue()


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Every member, refusing anything a bundle has no business containing.

    This runs before a single byte is written to disk. A bundle comes from another
    person, so the archive is untrusted input: a member escaping the destination, a
    symlink pointing at the reader's own files, or a name that only misbehaves on
    Windows are all things an extractor must refuse rather than sanitise.
    """
    out: list[zipfile.ZipInfo] = []
    total = 0
    for info in archive.infolist():
        name = info.filename
        if len(out) >= MAX_MEMBERS:
            raise BundleError(f"the bundle holds more than {MAX_MEMBERS} files")
        if info.is_dir():
            continue
        # Zip stores unix modes in the top half of external_attr, symlinks included.
        # Extracting one would write a link into the reader's tree pointing wherever
        # its target says — the one member shape that reaches outside the destination
        # without ever containing a `..`.
        # A zip written by a DOS tool carries no unix mode at all, and plenty of unix
        # tools store permissions without the type bits. Absent type bits mean "a
        # plain member"; only a type that is present and *not* a regular file is the
        # thing to refuse.
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind and kind != stat.S_IFREG:
            raise BundleError(
                f"{name!r} in the bundle is a link or device, not a file — refusing to "
                "extract it"
            )
        if "\\" in name or (len(name) > 1 and name[1] == ":"):
            raise BundleError(
                f"{name!r} uses a Windows path shape; a bundle's names are always POSIX"
            )
        path = pathlib.PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise BundleError(f"{name!r} in the bundle is not a safe path")
        head = path.parts[0]
        if not (
            name in (MANIFEST_NAME, LANDING_PAGE) or head in (TRANSCRIPT_DIR, ARTIFACT_DIR)
        ):
            raise BundleError(
                f"{name!r} is outside a bundle's layout — expected {MANIFEST_NAME}, "
                f"{LANDING_PAGE}, {TRANSCRIPT_DIR}/ or {ARTIFACT_DIR}/"
            )
        if info.file_size > MAX_ARTIFACT_BYTES:
            raise BundleError(f"{name!r} is {info.file_size} bytes, over the per-file cap")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise BundleError("the bundle's contents exceed the total size cap")
        out.append(info)
    if not out:
        raise BundleError("the bundle is empty")
    return out


def read_manifest(path: str | pathlib.Path) -> dict[str, Any]:
    """The manifest out of a bundle, without extracting anything else.

    Refuses a bundle with no manifest: the manifest is written last, so its absence
    means the archive was never finished and its contents are not a publication.
    """
    with _open(path) as archive:
        _safe_members(archive)
        try:
            raw = archive.read(MANIFEST_NAME)
        except KeyError as exc:
            raise BundleError(
                f"the bundle has no {MANIFEST_NAME} — it was written by something else, "
                "or the write was interrupted before it finished"
            ) from exc
    try:
        manifest = json.loads(raw.decode("utf-8"), parse_constant=keys.reject_nonfinite_json)
    except ValueError as exc:
        raise BundleError(f"the bundle's {MANIFEST_NAME} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("layout") != LAYOUT:
        raise BundleError(
            f"the bundle declares layout {manifest.get('layout')!r} when this build "
            f"reads {LAYOUT!r}"
        )
    return manifest


def extract(
    path: str | pathlib.Path,
    dest: str | pathlib.Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify a bundle and unpack it into `dest`; return what was written.

    Every file is checked against the digest the manifest recorded for it, so a
    bundle that a sync client evicted, truncated, or corrupted is reported as such
    rather than read as a shorter conversation.
    """
    source = pathlib.Path(path).expanduser()
    data = source.read_bytes()
    actual = keys.content_digest(data)
    if expected_sha256 and actual != expected_sha256:
        raise BundleError(
            f"{source.name} hashes to {actual[:12]}… but was expected to be "
            f"{expected_sha256[:12]}… — {len(data)} bytes read. If this store is a "
            "synced folder, the client may not have finished downloading it"
        )
    manifest = read_manifest(source)
    recorded = {entry["path"]: entry for entry in manifest.get("files", [])}

    target = pathlib.Path(dest).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with _open(source) as archive:
        members = _safe_members(archive)
        for info in members:
            body = archive.read(info)
            name = info.filename
            if name in recorded:
                if keys.content_digest(body) != recorded[name].get("sha256"):
                    raise BundleError(
                        f"{name!r} does not match the digest in the manifest — the "
                        "bundle is corrupt, and waiting will not fix it"
                    )
            out = target / pathlib.PurePosixPath(name)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(body)
            written.append(name)

    missing = sorted(set(recorded) - set(written))
    if missing:
        raise BundleError(
            f"the manifest names {len(missing)} file(s) the bundle does not hold: "
            + ", ".join(missing[:4])
        )
    return {
        "path": str(target),
        "sha256": actual,
        "size": len(data),
        "manifest": manifest,
        "files": sorted(written),
    }


def _open(path: str | pathlib.Path) -> zipfile.ZipFile:
    """Open a bundle for reading, or say plainly that it is not one."""
    try:
        return zipfile.ZipFile(pathlib.Path(path).expanduser(), mode="r")
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise BundleError(f"{path} is not a readable bundle archive: {exc}") from exc
