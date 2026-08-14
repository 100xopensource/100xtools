"""The storage seam and the local backend's synced-folder behaviour."""

import pathlib
import tempfile
import unittest

from engine import keys, store


SHA_A = "a" * 64
SHA_B = "b" * 64


class LocalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name) / "continuity"
        self.store = store.LocalStore(self.root)
        self.digest = keys.session_digest("reports", "session-1")

    def test_satisfies_the_protocol(self) -> None:
        # The seam is what lets the S3 backend drop in without touching callers.
        self.assertIsInstance(self.store, store.ObjectStore)

    def test_round_trip(self) -> None:
        key = keys.blob_key(self.digest, SHA_A)
        self.store.put(key, b"artifact bytes")
        self.assertEqual(self.store.get(key), b"artifact bytes")

    def test_root_is_created(self) -> None:
        self.assertTrue(self.root.is_dir())

    def test_user_expansion(self) -> None:
        # Users configure a synced folder as ~/... — an unexpanded tilde would
        # silently create a literal "~" directory in the working directory.
        expanded = store.LocalStore(self.root / "sub").root
        self.assertNotIn("~", str(expanded))

    def test_missing_object_raises_not_found(self) -> None:
        with self.assertRaises(store.ObjectNotFound):
            self.store.get(keys.blob_key(self.digest, SHA_A))

    def test_exists_tracks_writes(self) -> None:
        key = keys.blob_key(self.digest, SHA_A)
        self.assertFalse(self.store.exists(key))
        self.store.put(key, b"x")
        self.assertTrue(self.store.exists(key))

    def test_genuinely_empty_object_round_trips(self) -> None:
        # Zero bytes is a legitimate artifact; only an evicted file is an error.
        key = keys.blob_key(self.digest, SHA_A)
        self.store.put(key, b"")
        self.assertEqual(self.store.get(key), b"")

    def test_key_escaping_the_root_is_refused(self) -> None:
        for hostile in ("../outside", "sessions/../../outside"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    self.store.put(hostile, b"x")

    def test_repeat_put_of_identical_bytes_does_not_rewrite(self) -> None:
        # Rewriting an unchanged file gives the sync client a pointless upload.
        key = keys.blob_key(self.digest, SHA_A)
        self.store.put(key, b"same")
        path = self.root / key
        before = path.stat().st_mtime_ns
        self.store.put(key, b"same")
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_no_partial_file_is_left_behind(self) -> None:
        # A sync client watching the folder must never see a half-written file,
        # so writes land via a temp file that is renamed into place.
        key = keys.blob_key(self.digest, SHA_A)
        self.store.put(key, b"payload")
        leftovers = [p.name for p in (self.root / key).parent.iterdir()
                     if p.name.startswith(".tmp-")]
        self.assertEqual(leftovers, [])


class EvictedFileTests(unittest.TestCase):
    """iCloud Drive replaces an evicted file's bytes with a placeholder."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.store = store.LocalStore(self.root)
        self.digest = keys.session_digest("reports", "session-1")
        self.key = keys.blob_key(self.digest, SHA_A)

    def _evict(self) -> pathlib.Path:
        """Reproduce an eviction: contents gone, placeholder sibling present."""
        path = self.root / self.key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        (path.parent / f".{path.name}.icloud").write_bytes(b"")
        return path

    def test_evicted_file_raises_rather_than_returning_empty(self) -> None:
        # The bug this prevents: handing back zero bytes as if the artifact were
        # empty, so a restore silently produces nothing.
        self._evict()
        with self.assertRaises(store.ObjectNotMaterialized):
            self.store.get(self.key)

    def test_eviction_is_distinct_from_absence(self) -> None:
        # Different remedies: wait for the sync client vs. save it again.
        self._evict()
        self.assertNotIsInstance(
            self._raised(self.key), store.ObjectNotFound
        )

    def test_placeholders_are_not_listed_as_objects(self) -> None:
        self._evict()
        listed = self.store.list(keys.session_prefix(self.digest))
        self.assertTrue(all(not k.endswith(".icloud") for k in listed))

    def _raised(self, key: str) -> BaseException:
        try:
            self.store.get(key)
        except BaseException as exc:  # noqa: BLE001 - the assertion is the type
            return exc
        self.fail("expected get() to raise")


class ListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.store = store.LocalStore(self.root)
        self.digest = keys.session_digest("reports", "session-1")

    def test_empty_prefix_lists_nothing(self) -> None:
        self.assertEqual(self.store.list(keys.session_prefix(self.digest)), [])

    def test_listing_is_sorted_and_scoped(self) -> None:
        other = keys.session_digest("reports", "session-2")
        self.store.put(keys.blob_key(self.digest, SHA_B), b"b")
        self.store.put(keys.blob_key(self.digest, SHA_A), b"a")
        self.store.put(keys.blob_key(other, SHA_A), b"elsewhere")
        listed = self.store.list(keys.session_prefix(self.digest))
        self.assertEqual(listed, sorted(listed))
        self.assertEqual(len(listed), 2)

    def test_entries_are_append_only_across_writers(self) -> None:
        # Two machines saving to one session at the same instant: both entries
        # must survive, which is what keeps a sync client from forking the log.
        stamp = "2026-08-13T09-00-00Z"
        self.store.put(keys.entry_key(self.digest, stamp, SHA_A), b"{}")
        self.store.put(keys.entry_key(self.digest, stamp, SHA_B), b"{}")
        entries = [
            k for k in self.store.list(keys.session_prefix(self.digest))
            if "/entries/" in k
        ]
        self.assertEqual(len(entries), 2)


class SelectorTests(unittest.TestCase):
    def test_local_backend_is_built(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsInstance(store.get_store("local", root=tmp), store.LocalStore)

    def test_local_backend_needs_a_root(self) -> None:
        with self.assertRaises(ValueError):
            store.get_store("local")

    def test_unknown_backend_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as caught:
            store.get_store("gdrive")
        self.assertIn("gdrive", str(caught.exception))

    def test_s3_backend_is_declared_but_not_yet_wired(self) -> None:
        with self.assertRaises(NotImplementedError):
            store.get_store("s3")


if __name__ == "__main__":
    unittest.main()
