"""Saving into a session and folding it back out."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from engine import keys, session, store  # noqa: F401 - store used by subclasses


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.store = store.LocalStore(self.root)
        self.ns = "reports"
        self.sid = "session-1"

    def save(self, name: str, data: bytes, stamp: str | None = None, **kw):
        return session.save_artifact(
            self.store,
            namespace=self.ns,
            session_id=self.sid,
            name=name,
            data=data,
            stamp=stamp,
            **kw,
        )

    def read(self):
        return session.read_session(
            self.store, namespace=self.ns, session_id=self.sid
        )


class SaveTests(_Fixture):
    def test_save_then_read_back(self) -> None:
        self.save("summary.md", b"# what happened")
        state = self.read()
        self.assertIn("summary.md", state["artifacts"])
        self.assertEqual(
            session.load_artifact(
                self.store, namespace=self.ns, session_id=self.sid, name="summary.md"
            ),
            b"# what happened",
        )

    def test_entry_records_size_and_digest(self) -> None:
        entry = self.save("a.txt", b"12345")
        self.assertEqual(entry["size"], 5)
        self.assertEqual(entry["sha256"], keys.content_digest(b"12345"))

    def test_media_type_is_carried(self) -> None:
        entry = self.save("chart.png", b"\x89PNG", media_type="image/png")
        self.assertEqual(entry["media_type"], "image/png")

    def test_identical_bytes_share_one_blob(self) -> None:
        # The property that keeps a synced folder small and conflict-free.
        self.save("a.txt", b"same", stamp="2026-08-13T09-00-00-000000Z")
        self.save("b.txt", b"same", stamp="2026-08-13T09-00-01-000000Z")
        blobs = [
            k for k in self.store.list(
                keys.session_prefix(keys.session_digest(self.ns, self.sid))
            )
            if "/blobs/" in k
        ]
        self.assertEqual(len(blobs), 1)

    def test_empty_name_is_refused(self) -> None:
        with self.assertRaises(session.SessionError):
            self.save("", b"x")

    def test_multiline_name_is_refused(self) -> None:
        with self.assertRaises(session.SessionError):
            self.save("a\nb", b"x")

    def test_oversized_entry_is_refused(self) -> None:
        # Entries name bytes; they must not become a second place bytes live.
        with self.assertRaises(session.SessionError):
            self.save("a.txt", b"x", media_type="m" * session.MAX_ENTRY_BYTES)

    def test_blob_lands_before_its_entry(self) -> None:
        # An entry naming absent bytes would read as corruption, not a lost save.
        self.save("a.txt", b"payload")
        state = self.read()
        entry = state["artifacts"]["a.txt"]
        self.assertTrue(
            self.store.exists(keys.blob_key(state["session_digest"], entry["sha256"]))
        )


class FoldTests(_Fixture):
    def test_latest_entry_for_a_name_wins(self) -> None:
        self.save("draft.md", b"v1", stamp="2026-08-13T09-00-00-000000Z")
        self.save("draft.md", b"v2", stamp="2026-08-13T10-00-00-000000Z")
        self.assertEqual(
            session.load_artifact(
                self.store, namespace=self.ns, session_id=self.sid, name="draft.md"
            ),
            b"v2",
        )

    def test_history_keeps_every_save(self) -> None:
        # Append-only: an overwrite must not erase what it replaced.
        self.save("draft.md", b"v1", stamp="2026-08-13T09-00-00-000000Z")
        self.save("draft.md", b"v2", stamp="2026-08-13T10-00-00-000000Z")
        self.assertEqual(len(self.read()["history"]), 2)

    def test_history_is_chronological(self) -> None:
        self.save("a.txt", b"late", stamp="2026-08-13T18-00-00-000000Z")
        self.save("a.txt", b"early", stamp="2026-08-13T06-00-00-000000Z")
        stamps = [e["saved_at"] for e in self.read()["history"]]
        self.assertEqual(stamps, sorted(stamps))

    def test_empty_session_reads_clean(self) -> None:
        state = self.read()
        self.assertEqual(state["artifacts"], {})
        self.assertEqual(state["history"], [])
        self.assertEqual(state["damaged"], [])

    def test_sessions_are_isolated(self) -> None:
        self.save("a.txt", b"mine")
        other = session.read_session(
            self.store, namespace=self.ns, session_id="session-2"
        )
        self.assertEqual(other["artifacts"], {})

    def test_namespaces_are_isolated(self) -> None:
        self.save("a.txt", b"mine")
        other = session.read_session(
            self.store, namespace="audits", session_id=self.sid
        )
        self.assertEqual(other["artifacts"], {})

    def test_missing_artifact_raises(self) -> None:
        with self.assertRaises(session.SessionError):
            session.load_artifact(
                self.store, namespace=self.ns, session_id=self.sid, name="nope.txt"
            )


class DamagedEntryTests(_Fixture):
    def test_one_bad_entry_does_not_sink_the_session(self) -> None:
        # A truncated sync, a half-written file from an older version: the other
        # artifacts must still come back.
        self.save("good.txt", b"intact", stamp="2026-08-13T09-00-00-000000Z")
        digest = keys.session_digest(self.ns, self.sid)
        self.store.put(
            keys.entry_key(digest, "2026-08-13T10-00-00-000000Z", "c" * 64),
            b"{not json",
        )
        state = self.read()
        self.assertIn("good.txt", state["artifacts"])
        self.assertEqual(len(state["damaged"]), 1)

    def test_damaged_entries_are_named(self) -> None:
        digest = keys.session_digest(self.ns, self.sid)
        bad = keys.entry_key(digest, "2026-08-13T10-00-00-000000Z", "c" * 64)
        self.store.put(bad, b"\xff\xfe not utf-8")
        self.assertEqual(self.read()["damaged"], [bad])


class VerifiesBytesOnReadTests(_Fixture):
    """Reads verify against the digest the key already carries.

    This is the real eviction guarantee. Only iCloud leaves a marker a store can
    spot; Dropbox and Google Drive evict silently, so a store-level check cannot
    cover them and a digest check can.
    """

    def setUp(self) -> None:
        super().setUp()
        self.save("a.txt", b"hello world", stamp="2026-08-13T09-00-00-000000Z")
        digest = keys.session_digest(self.ns, self.sid)
        self.blob = self.root / keys.blob_key(digest, keys.content_digest(b"hello world"))

    def load(self) -> bytes:
        return session.load_artifact(
            self.store, namespace=self.ns, session_id=self.sid, name="a.txt"
        )

    def test_healthy_bytes_still_load(self) -> None:
        self.assertEqual(self.load(), b"hello world")

    def test_eviction_without_a_marker_is_caught(self) -> None:
        # Dropbox and Google Drive leave no .icloud sibling. Before the digest
        # check this returned b"" as a successful empty artifact.
        self.blob.write_bytes(b"")
        with self.assertRaises(store.ObjectNotMaterialized):
            self.load()

    def test_partial_materialization_is_caught(self) -> None:
        # A file part-way through downloading is readable and wrong.
        self.blob.write_bytes(b"hel")
        with self.assertRaises(store.ObjectNotMaterialized):
            self.load()

    def test_full_length_mismatch_is_corruption_not_eviction(self) -> None:
        # Same length, different bytes: waiting for a sync client will not fix
        # this, so it must not borrow the eviction error or its advice.
        self.blob.write_bytes(b"HELLO WORLD")
        with self.assertRaises(session.SessionError) as caught:
            self.load()
        self.assertNotIsInstance(caught.exception, store.ObjectNotMaterialized)
        self.assertIn("corrupt", str(caught.exception))


class DamagedEntryShapeTests(_Fixture):
    """An entry that parses but cannot be honoured is damaged, not healthy."""

    def _write_entry(self, payload: bytes) -> str:
        digest = keys.session_digest(self.ns, self.sid)
        key = keys.entry_key(digest, "2026-08-13T09-00-00-000000Z", "c" * 64)
        self.store.put(key, payload)
        return key

    def test_entry_without_a_digest_is_damaged(self) -> None:
        # It used to fold in as a healthy artifact and crash on read instead.
        key = self._write_entry(b'{"name":"a.txt"}')
        state = self.read()
        self.assertEqual(state["damaged"], [key])
        self.assertEqual(state["artifacts"], {})

    def test_entry_without_a_name_is_damaged(self) -> None:
        key = self._write_entry(b'{"sha256":"' + b"a" * 64 + b'"}')
        self.assertEqual(self.read()["damaged"], [key])

    def test_loading_a_damaged_entry_raises_session_error_not_keyerror(self) -> None:
        # The CLI only models StoreError/SessionError/ValueError/OSError, so a
        # KeyError here escaped as a traceback and broke the JSON contract.
        self._write_entry(b'{"name":"a.txt"}')
        with self.assertRaises(session.SessionError):
            session.load_artifact(
                self.store, namespace=self.ns, session_id=self.sid, name="a.txt"
            )

    def test_a_damaged_entry_does_not_sink_its_healthy_siblings(self) -> None:
        self.save("good.txt", b"intact", stamp="2026-08-13T08-00-00-000000Z")
        self._write_entry(b'{"name":"bad.txt"}')
        state = self.read()
        self.assertIn("good.txt", state["artifacts"])
        self.assertEqual(len(state["damaged"]), 1)


class UnresolvedSessionTests(_Fixture):
    def test_unresolved_session_still_saves(self) -> None:
        # Losing the artifact because the id did not expand would be the worst
        # outcome; it lands in the unattributed slot instead.
        entry = session.save_artifact(
            self.store,
            namespace=self.ns,
            session_id="${CLAUDE_SESSION_ID}",
            name="a.txt",
            data=b"x",
        )
        self.assertFalse(entry["resolved"])

    def test_unresolved_saves_are_readable_together(self) -> None:
        for sentinel in ("unknown", "unknown-session"):
            session.save_artifact(
                self.store,
                namespace=self.ns,
                session_id=sentinel,
                name=f"{sentinel}.txt",
                data=sentinel.encode(),
            )
        state = session.read_session(
            self.store, namespace=self.ns, session_id=keys.UNATTRIBUTED
        )
        self.assertEqual(len(state["artifacts"]), 2)

    def test_resolved_flag_is_true_for_a_real_id(self) -> None:
        self.assertTrue(self.save("a.txt", b"x")["resolved"])


class StampTests(unittest.TestCase):
    def test_stamp_sorts_lexically(self) -> None:
        import datetime as dt

        early = session.utc_stamp(dt.datetime(2026, 8, 13, 6, tzinfo=dt.timezone.utc))
        late = session.utc_stamp(dt.datetime(2026, 8, 13, 18, tzinfo=dt.timezone.utc))
        self.assertLess(early, late)

    def test_stamp_has_no_colons(self) -> None:
        # Colons are not portable in a filename across every filesystem this may
        # sync to.
        self.assertNotIn(":", session.utc_stamp())

    def test_naive_and_aware_times_agree(self) -> None:
        import datetime as dt

        aware = dt.datetime(2026, 8, 13, 12, tzinfo=dt.timezone.utc)
        self.assertEqual(session.utc_stamp(aware)[:13], "2026-08-13T12")


class EncodingTests(_Fixture):
    def test_entry_encoding_is_deterministic(self) -> None:
        # The entry's digest is part of its key, so an unstable encoding would
        # scatter one logical entry across several files.
        entry = {"b": 2, "a": 1}
        self.assertEqual(session._encode_entry(entry), session._encode_entry(entry))

    def test_entry_is_valid_json(self) -> None:
        payload = session._encode_entry({"name": "a.txt"})
        self.assertEqual(json.loads(payload)["name"], "a.txt")


if __name__ == "__main__":
    unittest.main()
