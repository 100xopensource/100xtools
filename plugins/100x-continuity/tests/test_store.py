"""The folder store: what gets written, in what order, and how a bad read is named."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

import fixtures
from engine import bundle, keys, store

STAMP = "20260820T140311Z"
LATER = "20260821T090000Z"


def _built(tmp: pathlib.Path, *, prompt: str = "Wire the importer up.") -> bundle.Built:
    return bundle.write(
        tmp / bundle.BUNDLE_NAME,
        fixtures.records(fixtures.rows(prompt=prompt)),
        session={"id": fixtures.SESSION, "outer_id": "local_1111"},
    )


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "Continuity"
        self.built = _built(self.tmp)
        self.record = store.install(
            self.root,
            self.built,
            namespace="reports",
            session_id=fixtures.SESSION,
            stamp=STAMP,
        )

    def test_the_handle_is_readable_and_three_parts(self) -> None:
        namespace, slot, publication = self.record["handle"].split("/")
        self.assertEqual(namespace, "reports")
        self.assertTrue(slot.startswith(fixtures.SESSION[:12]))
        self.assertEqual(publication, self.record["publication_id"])

    def test_both_files_land(self) -> None:
        directory = pathlib.Path(self.record["path"])
        self.assertTrue((directory / bundle.BUNDLE_NAME).is_file())
        self.assertTrue((directory / store.MARKER_NAME).is_file())

    def test_the_marker_carries_what_a_listing_needs(self) -> None:
        # So the store can be browsed without opening a single archive.
        self.assertEqual(self.record["bundle"]["sha256"], self.built.sha256)
        self.assertEqual(self.record["published_at"], STAMP)
        self.assertEqual(self.record["session"]["id"], fixtures.SESSION)
        self.assertIn("turns", self.record["transcript"])

    def test_no_temporary_marker_is_left_behind(self) -> None:
        names = {entry.name for entry in pathlib.Path(self.record["path"]).iterdir()}
        self.assertEqual(names, {bundle.BUNDLE_NAME, store.MARKER_NAME})

    def test_republishing_the_same_work_is_recognised(self) -> None:
        again = store.install(
            self.root,
            _built(pathlib.Path(tempfile.mkdtemp())),
            namespace="reports",
            session_id=fixtures.SESSION,
            stamp=LATER,
        )
        self.assertTrue(again["already_published"])
        self.assertEqual(again["publication_id"], self.record["publication_id"])
        session_dir = pathlib.Path(self.record["path"]).parent
        self.assertEqual(len(list(session_dir.iterdir())), 1)

    def test_changed_work_lands_beside_it_rather_than_over_it(self) -> None:
        other = _built(pathlib.Path(tempfile.mkdtemp()), prompt="A different session.")
        second = store.install(
            self.root,
            other,
            namespace="reports",
            session_id=fixtures.SESSION,
            stamp=LATER,
        )
        self.assertFalse(second["already_published"])
        session_dir = pathlib.Path(self.record["path"]).parent
        self.assertEqual(len(list(session_dir.iterdir())), 2)

    def test_an_unresolved_session_is_filed_visibly(self) -> None:
        record = store.install(
            self.root,
            _built(pathlib.Path(tempfile.mkdtemp()), prompt="No id here."),
            namespace="reports",
            session_id="${CLAUDE_SESSION_ID}",
            stamp=STAMP,
        )
        self.assertIn(f"/{keys.UNATTRIBUTED}/", record["handle"] + "/")
        self.assertFalse(record["session"]["resolved"])


class ListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "Continuity"
        for index, stamp in enumerate((STAMP, LATER)):
            store.install(
                self.root,
                _built(pathlib.Path(tempfile.mkdtemp()), prompt=f"Session {index}."),
                namespace="reports",
                session_id=f"session-{index}",
                stamp=stamp,
            )

    def test_newest_first(self) -> None:
        found = store.publications(self.root)
        self.assertEqual([item["published_at"] for item in found], [LATER, STAMP])

    def test_a_namespace_sees_only_itself(self) -> None:
        store.install(
            self.root,
            _built(pathlib.Path(tempfile.mkdtemp()), prompt="Elsewhere."),
            namespace="audits",
            session_id="session-9",
            stamp=STAMP,
        )
        self.assertEqual(len(store.publications(self.root, namespace="reports")), 2)
        self.assertEqual(len(store.publications(self.root, namespace="audits")), 1)
        self.assertEqual(len(store.publications(self.root)), 3)

    def test_an_unfinished_publish_is_skipped_not_fatal(self) -> None:
        # A directory with no marker is an interrupted write. It must not break the
        # listing, and it must not be offered as a publication.
        (self.root / "reports" / "half" / "20260822T000000Z-abcabcabcabc").mkdir(parents=True)
        self.assertEqual(len(store.publications(self.root)), 2)

    def test_a_foreign_marker_is_skipped(self) -> None:
        directory = self.root / "reports" / "foreign" / "20260822T000000Z-abcabcabcabc"
        directory.mkdir(parents=True)
        (directory / store.MARKER_NAME).write_text('{"layout": "something/else@1"}')
        self.assertEqual(len(store.publications(self.root)), 2)

    def test_a_missing_root_lists_nothing_rather_than_raising(self) -> None:
        self.assertEqual(store.publications(self.tmp / "not-here"), [])


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "Continuity"
        self.record = store.install(
            self.root,
            _built(self.tmp),
            namespace="reports",
            session_id=fixtures.SESSION,
            stamp=STAMP,
        )

    def test_a_publication_directory_resolves(self) -> None:
        found = store.resolve(self.record["path"])
        self.assertEqual(found["publication_id"], self.record["publication_id"])

    def test_the_bundle_file_itself_resolves(self) -> None:
        # People paste what they clicked on, and in a file browser that is the archive.
        found = store.resolve(str(pathlib.Path(self.record["path"]) / bundle.BUNDLE_NAME))
        self.assertEqual(found["publication_id"], self.record["publication_id"])

    def test_a_three_part_handle_resolves_against_the_root(self) -> None:
        found = store.resolve(self.record["handle"], root=self.root)
        self.assertEqual(found["publication_id"], self.record["publication_id"])

    def test_a_traversing_handle_is_refused(self) -> None:
        for hostile in ("../../etc/passwd", "reports/../../../etc", "a/b/../../../c"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(store.PublicationNotFound):
                    store.resolve(hostile, root=self.root)

    def test_a_handle_whose_id_is_not_an_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            store.resolve("reports/some-session/latest", root=self.root)

    def test_an_unfinished_publication_says_so(self) -> None:
        directory = self.root / "reports" / "half"
        directory.mkdir(parents=True)
        with self.assertRaises(store.PublicationNotFound) as caught:
            store.resolve(str(directory))
        self.assertIn(store.MARKER_NAME, str(caught.exception))

    def test_nothing_at_all_is_refused_with_the_forms_named(self) -> None:
        with self.assertRaises(store.PublicationNotFound) as caught:
            store.resolve("   ")
        self.assertIn("handle", str(caught.exception))


class ReadingTests(unittest.TestCase):
    """Telling an evicted file apart from a corrupt one. Only one is fixed by waiting."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "Continuity"
        self.built = _built(self.tmp)
        self.record = store.install(
            self.root,
            self.built,
            namespace="reports",
            session_id=fixtures.SESSION,
            stamp=STAMP,
        )
        self.archive = pathlib.Path(self.record["path"]) / bundle.BUNDLE_NAME

    def test_a_good_publication_reads(self) -> None:
        self.assertEqual(store.bundle_path(self.record), self.archive)

    def test_short_bytes_read_as_not_yet_materialized(self) -> None:
        self.archive.write_bytes(b"")
        with self.assertRaises(store.ObjectNotMaterialized) as caught:
            store.bundle_path(self.record)
        self.assertIn("downloading", str(caught.exception))

    def test_an_icloud_marker_reads_as_not_yet_materialized(self) -> None:
        self.archive.unlink()
        (self.archive.parent / f".{self.archive.name}.icloud").write_bytes(b"")
        with self.assertRaises(store.ObjectNotMaterialized):
            store.bundle_path(self.record)

    def test_full_length_wrong_bytes_read_as_corruption(self) -> None:
        # Same size, different content: waiting will not fix this, so it must not
        # be reported as a sync client still working.
        self.archive.write_bytes(b"x" * self.record["bundle"]["size"])
        with self.assertRaises(store.StoreError) as caught:
            store.bundle_path(self.record)
        self.assertIn("corrupt", str(caught.exception))
        self.assertNotIsInstance(caught.exception, store.ObjectNotMaterialized)

    def test_a_missing_archive_is_a_missing_publication(self) -> None:
        self.archive.unlink()
        with self.assertRaises(store.PublicationNotFound):
            store.bundle_path(self.record)


if __name__ == "__main__":
    unittest.main()
