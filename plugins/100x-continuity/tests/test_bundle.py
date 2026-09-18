"""The bundle: what goes in, what is refused, and what a reader can trust."""

from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
import zipfile

import fixtures
from engine import bundle, keys


def _build(tmp: pathlib.Path, **kwargs) -> bundle.Built:
    return bundle.write(
        tmp / bundle.BUNDLE_NAME,
        fixtures.records(),
        session={"id": fixtures.SESSION, "outer_id": "local_1111"},
        **kwargs,
    )


class LayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.built = _build(self.tmp)

    def _names(self) -> list[str]:
        with zipfile.ZipFile(self.built.path) as archive:
            return archive.namelist()

    def test_the_two_transcript_files_are_there(self) -> None:
        self.assertIn(bundle.DIGEST_FILE, self._names())
        self.assertIn(bundle.RECORD_FILE, self._names())

    def test_the_manifest_is_written_last(self) -> None:
        # Its position IS the commit marker: a reader that finds it knows every
        # other member was already written.
        self.assertEqual(self._names()[-1], bundle.MANIFEST_NAME)

    def test_the_manifest_names_every_file_with_its_digest(self) -> None:
        recorded = {entry["path"]: entry for entry in self.built.manifest["files"]}
        self.assertIn(bundle.DIGEST_FILE, recorded)
        self.assertRegex(recorded[bundle.DIGEST_FILE]["sha256"], r"\A[0-9a-f]{64}\Z")

    def test_no_record_leaves_the_digest_alone(self) -> None:
        built = _build(pathlib.Path(tempfile.mkdtemp()), include_record=False)
        with zipfile.ZipFile(built.path) as archive:
            names = archive.namelist()
        self.assertIn(bundle.DIGEST_FILE, names)
        self.assertNotIn(bundle.RECORD_FILE, names)
        self.assertFalse(built.manifest["transcript"]["record_included"])

    def test_an_empty_transcript_is_refused(self) -> None:
        with self.assertRaises(bundle.BundleError):
            bundle.write(self.tmp / "empty.zip", [], session={"id": fixtures.SESSION})


class ReproducibilityTests(unittest.TestCase):
    def test_the_same_session_packs_to_the_same_bytes(self) -> None:
        # What lets a store recognise a republish of unchanged work instead of
        # filing a second copy of it.
        first = _build(pathlib.Path(tempfile.mkdtemp()))
        second = _build(pathlib.Path(tempfile.mkdtemp()))
        self.assertEqual(first.sha256, second.sha256)

    def test_changed_content_changes_the_digest(self) -> None:
        first = _build(pathlib.Path(tempfile.mkdtemp()))
        other = bundle.write(
            pathlib.Path(tempfile.mkdtemp()) / bundle.BUNDLE_NAME,
            fixtures.records(fixtures.rows(prompt="Something else entirely.")),
            session={"id": fixtures.SESSION},
        )
        self.assertNotEqual(first.sha256, other.sha256)


class RedactionTests(unittest.TestCase):
    def test_a_credential_in_a_prompt_does_not_reach_the_bundle(self) -> None:
        # Assembled at run time so this fixture is not itself a committed secret.
        secret = "AKIA" + "V" * 16
        built = bundle.write(
            pathlib.Path(tempfile.mkdtemp()) / bundle.BUNDLE_NAME,
            fixtures.records(fixtures.rows(secret=secret)),
            session={"id": fixtures.SESSION},
        )
        with zipfile.ZipFile(built.path) as archive:
            blob = b"".join(archive.read(name) for name in archive.namelist())
        self.assertNotIn(secret.encode(), blob)
        self.assertGreater(sum(built.redacted.values()), 0)

    def test_the_caveat_travels_with_the_bundle(self) -> None:
        # A reader of the manifest alone must still learn that redaction removes
        # credential shapes and nothing else.
        built = _build(pathlib.Path(tempfile.mkdtemp()))
        self.assertTrue(built.manifest["redaction_caveat"])


class ArtifactPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "docs").mkdir()
        self.note = self.tmp / "docs" / "handover.md"
        self.note.write_text("what is left to do\n", encoding="utf-8")

    def test_a_path_under_the_root_keeps_its_shape(self) -> None:
        artifacts, _ = bundle.plan_artifacts([str(self.note)], root=str(self.tmp))
        self.assertEqual([a.arcname for a in artifacts], ["docs/handover.md"])

    def test_a_path_outside_the_root_is_reduced_to_its_name(self) -> None:
        # So a bundle never carries a stranger's directory layout.
        artifacts, _ = bundle.plan_artifacts([str(self.note)], root=str(self.tmp / "docs" / "x"))
        self.assertEqual([a.arcname for a in artifacts], ["handover.md"])

    def test_a_directory_is_walked_only_when_asked(self) -> None:
        with self.assertRaises(bundle.BundleError):
            bundle.plan_artifacts([str(self.tmp / "docs")], root=str(self.tmp))
        artifacts, _ = bundle.plan_artifacts(
            [], from_dirs=[str(self.tmp / "docs")], root=str(self.tmp)
        )
        self.assertEqual([a.arcname for a in artifacts], ["docs/handover.md"])

    def test_a_missing_file_is_refused(self) -> None:
        with self.assertRaises(bundle.BundleError):
            bundle.plan_artifacts([str(self.tmp / "nope.md")], root=str(self.tmp))

    def test_two_files_colliding_on_one_name_are_refused(self) -> None:
        # Silently keeping one of them would publish half of what was asked for.
        other = self.tmp / "elsewhere"
        other.mkdir()
        (other / "handover.md").write_text("different\n", encoding="utf-8")
        with self.assertRaises(bundle.BundleError):
            bundle.plan_artifacts(
                [str(self.note), str(other / "handover.md")], root=str(other / "x")
            )

    def test_a_credential_shaped_filename_is_refused_by_default(self) -> None:
        env = self.tmp / ".env"
        env.write_text("TOKEN=whatever\n", encoding="utf-8")
        with self.assertRaises(bundle.BundleError):
            bundle.plan_artifacts([str(env)], root=str(self.tmp))
        artifacts, _ = bundle.plan_artifacts(
            [str(env)], root=str(self.tmp), allow_sensitive_names=True
        )
        self.assertEqual(len(artifacts), 1)

    def test_an_oversized_file_is_refused(self) -> None:
        big = self.tmp / "big.bin"
        big.write_bytes(b"0")
        original = bundle.MAX_ARTIFACT_BYTES
        bundle.MAX_ARTIFACT_BYTES = 0
        try:
            with self.assertRaises(bundle.BundleError):
                bundle.plan_artifacts([str(big)], root=str(self.tmp))
        finally:
            bundle.MAX_ARTIFACT_BYTES = original


class ArtifactScanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_a_credential_in_an_artifact_stops_the_publish(self) -> None:
        # Artifacts are included verbatim, so the boundary here fails closed
        # instead of rewriting a file nobody asked us to touch.
        leaky = self.tmp / "notes.md"
        leaky.write_text("aws key AKIA" + "W" * 16 + "\n", encoding="utf-8")
        artifacts, _ = bundle.plan_artifacts([str(leaky)], root=str(self.tmp))
        with self.assertRaises(bundle.BundleError) as caught:
            _build(self.tmp, artifacts=artifacts)
        self.assertIn("notes.md", str(caught.exception))

    def test_it_can_be_included_deliberately(self) -> None:
        leaky = self.tmp / "notes.md"
        leaky.write_text("aws key AKIA" + "W" * 16 + "\n", encoding="utf-8")
        artifacts, _ = bundle.plan_artifacts([str(leaky)], root=str(self.tmp))
        built = _build(self.tmp, artifacts=artifacts, allow_flagged_artifacts=True)
        self.assertIn("notes.md", built.manifest["artifacts"]["flagged"])
        self.assertTrue(built.notes)

    def test_a_clean_artifact_rides_along_unchanged(self) -> None:
        note = self.tmp / "handover.md"
        note.write_text("pick up at store 41\n", encoding="utf-8")
        artifacts, _ = bundle.plan_artifacts([str(note)], root=str(self.tmp))
        built = _build(self.tmp, artifacts=artifacts)
        out = bundle.extract(built.path, self.tmp / "out")
        self.assertEqual(
            (self.tmp / "out" / bundle.ARTIFACT_DIR / "handover.md").read_text(),
            "pick up at store 41\n",
        )
        self.assertEqual(built.manifest["artifacts"]["count"], 1)
        self.assertIn(f"{bundle.ARTIFACT_DIR}/handover.md", out["files"])

    def test_binary_artifacts_are_reported_as_unscanned(self) -> None:
        # "Nothing found" about a file nobody could read is the more dangerous answer.
        blob = self.tmp / "chart.png"
        blob.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
        artifacts, _ = bundle.plan_artifacts([str(blob)], root=str(self.tmp))
        built = _build(self.tmp, artifacts=artifacts)
        self.assertEqual(built.manifest["artifacts"]["unscanned"], ["chart.png"])


class ReadingIsUntrustedInputTests(unittest.TestCase):
    """A bundle arrives from someone else, so extraction refuses before it writes."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def _hostile(self, names: list[str], bodies: list[bytes], *, mode: int = 0o644) -> pathlib.Path:
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for name, body in zip(names, bodies):
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                archive.writestr(info, body)
        path = self.tmp / "hostile.zip"
        path.write_bytes(raw.getvalue())
        return path

    def test_a_traversing_member_is_refused(self) -> None:
        path = self._hostile(["../../evil.sh"], [b"rm -rf /\n"])
        with self.assertRaises(bundle.BundleError):
            bundle.extract(path, self.tmp / "out")
        self.assertFalse((self.tmp.parent / "evil.sh").exists())

    def test_an_absolute_member_is_refused(self) -> None:
        path = self._hostile(["/etc/cron.d/evil"], [b"x\n"])
        with self.assertRaises(bundle.BundleError):
            bundle.extract(path, self.tmp / "out")

    def test_a_symlink_member_is_refused(self) -> None:
        # A zip stores unix modes in external_attr, symlinks included — the one member
        # shape that escapes the destination without ever containing a `..`.
        path = self._hostile(
            [f"{bundle.ARTIFACT_DIR}/link"], [b"/etc/passwd"], mode=0o120777
        )
        with self.assertRaises(bundle.BundleError):
            bundle.extract(path, self.tmp / "out")

    def test_a_windows_path_shape_is_refused(self) -> None:
        for hostile in ("artifacts\\evil.txt", "C:/artifacts/evil.txt"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(bundle.BundleError):
                    bundle.extract(self._hostile([hostile], [b"x\n"]), self.tmp / "out")

    def test_a_member_outside_the_layout_is_refused(self) -> None:
        path = self._hostile(["somewhere/else.txt"], [b"x\n"])
        with self.assertRaises(bundle.BundleError):
            bundle.extract(path, self.tmp / "out")

    def test_a_bundle_with_no_manifest_is_refused(self) -> None:
        # The manifest is written last, so its absence means an unfinished write.
        path = self._hostile([bundle.DIGEST_FILE], [b"# notes\n"])
        with self.assertRaises(bundle.BundleError) as caught:
            bundle.read_manifest(path)
        self.assertIn(bundle.MANIFEST_NAME, str(caught.exception))

    def test_something_that_is_not_an_archive_is_refused(self) -> None:
        path = self.tmp / "not-a-bundle.zip"
        path.write_bytes(b"just some text")
        with self.assertRaises(bundle.BundleError):
            bundle.read_manifest(path)


class VerifyingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.built = _build(self.tmp)

    def test_a_good_bundle_round_trips(self) -> None:
        out = bundle.extract(self.built.path, self.tmp / "out", expected_sha256=self.built.sha256)
        self.assertEqual(out["sha256"], self.built.sha256)
        self.assertIn(bundle.DIGEST_FILE, out["files"])
        self.assertTrue((self.tmp / "out" / bundle.DIGEST_FILE).read_text())

    def test_the_wrong_digest_stops_the_read(self) -> None:
        with self.assertRaises(bundle.BundleError):
            bundle.extract(self.built.path, self.tmp / "out", expected_sha256="a" * 64)

    def test_a_tampered_member_is_caught_against_the_manifest(self) -> None:
        # Repack the same manifest over changed content: the outer digest is not
        # what catches this, the per-file digests are.
        with zipfile.ZipFile(self.built.path) as archive:
            members = [(name, archive.read(name)) for name in archive.namelist()]
        swapped = [
            (name, b"# tampered\n" if name == bundle.DIGEST_FILE else body)
            for name, body in members
        ]
        forged = self.tmp / "forged.zip"
        forged.write_bytes(bundle._pack(swapped))
        with self.assertRaises(bundle.BundleError) as caught:
            bundle.extract(forged, self.tmp / "out2")
        self.assertIn("manifest", str(caught.exception))

    def test_a_foreign_layout_version_is_refused(self) -> None:
        manifest = dict(self.built.manifest, layout="somebody-else/bundle@9")
        forged = self.tmp / "foreign.zip"
        forged.write_bytes(
            bundle._pack(
                [
                    (bundle.DIGEST_FILE, b"# notes\n"),
                    (bundle.MANIFEST_NAME, keys.readable_json(manifest)),
                ]
            )
        )
        with self.assertRaises(bundle.BundleError):
            bundle.read_manifest(forged)


if __name__ == "__main__":
    unittest.main()


class EnvVariantTests(unittest.TestCase):
    """Every `.env` flavour, not only the bare name.

    A store service is configured by `.env`, so the file most likely to be sitting in
    the working directory of a session about handoffs is exactly this one — and the
    variants hold the same thing the bare name does.
    """

    def test_every_env_flavour_is_refused(self) -> None:
        for name in (".env", ".env.local", ".env.production", ".env.staging", ".ENV.Local"):
            with self.subTest(name=name):
                self.assertTrue(bundle._looks_sensitive(name), name)

    def test_an_ordinary_file_is_not(self) -> None:
        for name in ("notes.md", "chart.png", "environment.md", "env-setup.md"):
            with self.subTest(name=name):
                self.assertFalse(bundle._looks_sensitive(name), name)
