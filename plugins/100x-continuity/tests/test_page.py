"""The landing page: what a person sees when they open the zip with no Claude."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
import zipfile

import fixtures
from engine import bundle, digest, page


def _rendered(rows=None) -> tuple[str, dict]:
    built = bundle.write(
        pathlib.Path(tempfile.mkdtemp()) / bundle.BUNDLE_NAME,
        fixtures.records(rows),
        session={"id": fixtures.SESSION, "outer_id": None},
    )
    with zipfile.ZipFile(built.path) as archive:
        return archive.read(bundle.LANDING_PAGE).decode("utf-8"), built.manifest


class ContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html, self.manifest = _rendered()

    def test_it_is_a_whole_document(self) -> None:
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn("</html>", self.html)

    def test_the_title_and_the_work_are_there(self) -> None:
        self.assertIn("Importer flags", self.html)
        self.assertIn("Wire the importer up", self.html)
        self.assertIn("store 41 still open", self.html)

    def test_it_lists_what_came_with_the_session(self) -> None:
        self.assertIn(bundle.DIGEST_FILE, self.html)
        self.assertIn(bundle.RECORD_FILE, self.html)

    def test_it_states_the_redaction_position(self) -> None:
        # The reader has to learn what redaction did and did not do without opening
        # anything else — this page may be all they ever look at.
        self.assertIn("credential-shaped value", self.html)
        self.assertIn("cannot recognise", self.html)

    def test_nothing_is_fetched_from_the_network(self) -> None:
        # It has to render on a laptop with no internet, and it must not phone home
        # about a session somebody was handed.
        for hostile in ("http://", "https://", "<script", "src="):
            with self.subTest(hostile=hostile):
                self.assertNotIn(hostile, self.html)


class EscapingTests(unittest.TestCase):
    def test_a_session_about_html_does_not_rewrite_the_page(self) -> None:
        # Everything on this page came out of somebody's conversation. A prompt is
        # untrusted input to the renderer, exactly like a bundle is to the extractor.
        rows = fixtures.rows(prompt="<script>alert('x')</script> and <b>bold</b>")
        html, _ = _rendered(rows)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_a_hostile_title_is_escaped_too(self) -> None:
        rows = fixtures.rows(title='"><script>alert(1)</script>')
        html, _ = _rendered(rows)
        self.assertNotIn("<script>alert(1)", html)


class EmptinessTests(unittest.TestCase):
    def test_a_session_with_no_title_still_renders(self) -> None:
        rows = [row for row in fixtures.rows() if row.get("type") != "ai-title"]
        html, _ = _rendered(rows)
        self.assertIn("<h1>Session</h1>", html)

    def test_missing_pieces_are_said_rather_than_left_blank(self) -> None:
        summary = digest.Digest(session_id="s1")
        html = page.render(summary, {"files": [], "redacted": {}, "session": {}})
        self.assertIn("No prompts were captured", html)
        self.assertIn("unattributed", html)


class InTheBundleTests(unittest.TestCase):
    def test_the_manifest_records_the_page_like_any_other_file(self) -> None:
        # Derived or not, it is bytes in the zip, so a reader can verify it.
        _, manifest = _rendered()
        entry = [f for f in manifest["files"] if f["path"] == bundle.LANDING_PAGE]
        self.assertEqual(len(entry), 1)
        self.assertRegex(entry[0]["sha256"], r"\A[0-9a-f]{64}\Z")

    def test_the_manifest_is_still_the_last_member(self) -> None:
        built = bundle.write(
            pathlib.Path(tempfile.mkdtemp()) / bundle.BUNDLE_NAME,
            fixtures.records(),
            session={"id": fixtures.SESSION},
        )
        with zipfile.ZipFile(built.path) as archive:
            self.assertEqual(archive.namelist()[-1], bundle.MANIFEST_NAME)


if __name__ == "__main__":
    unittest.main()
