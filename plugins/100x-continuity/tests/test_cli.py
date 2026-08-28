"""The command surface, driven the way a skill drives it: argv in, JSON out."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import tempfile
import unittest
import unittest.mock

import fixtures
from engine import bundle, cli, config, keys, store

PHRASE = "flags file"


class _CliCase(unittest.TestCase):
    """A private HOME, a clean environment, and one seeded transcript."""

    def setUp(self) -> None:
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}))
        for name in (
            config.STORE_KIND_ENV,
            config.STORE_ROOT_ENV,
            config.NAMESPACE_ENV,
            config.SERVICE_ENV,
            config.CONFIG_ENV,
            config.SESSION_ENV,
        ):
            os.environ.pop(name, None)
        self.root = self.home / "Store"
        self.transcript = fixtures.write_transcript(self.home)

    def run_cli(self, *argv: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())

    def publish(self, *extra: str) -> tuple[int, dict]:
        return self.run_cli(
            "publish", "--root", str(self.root), "--session", fixtures.SESSION, *extra
        )


class WhereTests(_CliCase):
    def test_it_reports_what_it_searched_and_creates_nothing(self) -> None:
        code, result = self.run_cli("where", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(result["store"], "folder")
        self.assertFalse(result["root_exists"])
        self.assertFalse(self.root.exists())
        self.assertTrue(result["config_searched"])
        self.assertEqual(result["sources"]["root"], "flag")

    def test_it_names_the_transcript_it_would_read(self) -> None:
        _, result = self.run_cli("where", "--session", fixtures.SESSION)
        self.assertEqual(result["transcript"], str(self.transcript))
        self.assertTrue(result["transcript_roots"])

    def test_an_unresolved_session_is_flagged_before_anything_is_written(self) -> None:
        _, result = self.run_cli("where", "--session", "${CLAUDE_SESSION_ID}")
        self.assertFalse(result["session_resolved"])
        self.assertEqual(result["session_slot"], keys.UNATTRIBUTED)


class SessionsTests(_CliCase):
    def test_it_shows_this_session_and_an_empty_store(self) -> None:
        # Both halves: "is there a record here" and "can anyone else find it" are
        # different questions, and one without the other reads as a broken plugin.
        _, result = self.run_cli("sessions", "--root", str(self.root))
        self.assertTrue(result["current"]["found"])
        self.assertEqual(result["current"]["inner_id"], fixtures.SESSION)
        self.assertEqual(result["current"]["turns"], 1)
        self.assertEqual(result["published"], [])

    def test_a_published_session_appears(self) -> None:
        self.publish()
        _, result = self.run_cli("sessions", "--root", str(self.root))
        self.assertEqual(len(result["published"]), 1)
        self.assertEqual(result["published"][0]["session_id"], fixtures.SESSION)

    def test_no_transcript_anywhere_says_what_was_searched(self) -> None:
        self.transcript.unlink()
        _, result = self.run_cli("sessions", "--root", str(self.root))
        self.assertFalse(result["current"]["found"])
        self.assertTrue(result["current"]["notes"])

    def test_a_service_store_is_not_listed_from_here(self) -> None:
        _, result = self.run_cli("sessions", "--store", "service")
        self.assertIsNone(result["published"])
        self.assertIn("MCP", result["note"])


class PublishTests(_CliCase):
    def test_it_files_the_session_and_hands_back_a_handle(self) -> None:
        code, result = self.publish()
        self.assertEqual(code, 0)
        self.assertTrue(result["filed"])
        namespace, _slot, publication = result["handle"].split("/")
        self.assertEqual(namespace, "default")
        self.assertEqual(publication, result["publication_id"])
        self.assertTrue(pathlib.Path(result["path"], bundle.BUNDLE_NAME).is_file())

    def test_it_reports_redaction_on_every_publish(self) -> None:
        # Including when the count is zero: that means the scrubber matched
        # nothing, not that there was nothing to find.
        _, result = self.publish()
        self.assertIn("redacted", result)
        self.assertTrue(result["redaction_caveat"])

    def test_the_session_id_comes_from_the_records(self) -> None:
        _, result = self.publish()
        self.assertEqual(result["manifest"]["session"]["id"], fixtures.SESSION)
        self.assertEqual(result["source"]["selected_by"], "session-id")

    def test_republishing_unchanged_work_is_recognised(self) -> None:
        first = self.publish()[1]
        second = self.publish()[1]
        self.assertTrue(second["already_published"])
        self.assertEqual(first["publication_id"], second["publication_id"])

    def test_without_a_session_id_the_guess_is_stated(self) -> None:
        _, result = self.run_cli("publish", "--root", str(self.root))
        self.assertEqual(result["source"]["selected_by"], "most-recent")
        self.assertTrue(any("most recently written" in note for note in result["notes"]))

    def test_a_confirmed_phrase_settles_it(self) -> None:
        _, result = self.run_cli(
            "publish", "--root", str(self.root), "--confirm", PHRASE
        )
        self.assertTrue(result["source"]["confirmed"])

    def test_a_phrase_that_is_absent_publishes_nothing(self) -> None:
        # The failure this exists to prevent is publishing somebody else's
        # conversation, so it stops rather than warns.
        code, result = self.run_cli(
            "publish", "--root", str(self.root), "--confirm", "a phrase never said"
        )
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(store.publications(self.root), [])

    def test_an_unresolved_session_still_publishes_and_says_where(self) -> None:
        # Losing the work would be worse than filing it imprecisely.
        _, result = self.run_cli(
            "publish", "--root", str(self.root), "--session", "unknown"
        )
        self.assertTrue(result["filed"])
        self.assertFalse(result["session_resolved"])
        self.assertIn(keys.UNATTRIBUTED, result["hint"])

    def test_a_service_store_is_sent_to_pack(self) -> None:
        code, result = self.run_cli("publish", "--store", "service")
        self.assertEqual(code, 1)
        self.assertIn("pack", result["error"]["hint"])

    def test_no_transcript_is_an_error_that_says_what_was_searched(self) -> None:
        self.transcript.unlink()
        code, result = self.publish()
        self.assertEqual(code, 1)
        self.assertIn("no transcript found", result["error"]["hint"])


class ArtifactTests(_CliCase):
    def setUp(self) -> None:
        super().setUp()
        self.work = self.home / "work"
        (self.work / "docs").mkdir(parents=True)
        self.note = self.work / "docs" / "handover.md"
        self.note.write_text("pick up at store 41\n", encoding="utf-8")

    def test_a_staged_file_travels_with_the_session(self) -> None:
        _, published = self.publish(
            "--artifact", str(self.note), "--artifact-root", str(self.work)
        )
        _, opened = self.run_cli("open", "--handle", published["path"])
        self.assertEqual(opened["artifacts"], ["artifacts/docs/handover.md"])
        self.assertEqual(
            pathlib.Path(opened["unpacked_to"], "artifacts/docs/handover.md").read_text(),
            "pick up at store 41\n",
        )

    def test_a_directory_of_files_can_be_staged(self) -> None:
        _, published = self.publish(
            "--artifacts-from-dir", str(self.work), "--artifact-root", str(self.work)
        )
        self.assertEqual(published["manifest"]["artifacts"]["count"], 1)

    def test_a_credential_shaped_name_stops_the_publish(self) -> None:
        (self.work / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
        code, result = self.publish("--artifact", str(self.work / ".env"))
        self.assertEqual(code, 1)
        self.assertIn(".env", result["error"]["hint"])
        self.assertEqual(store.publications(self.root), [])

    def test_a_credential_inside_an_artifact_stops_the_publish(self) -> None:
        # Assembled at run time so the fixture is not itself a committed secret.
        self.note.write_text("key AKIA" + "W" * 16 + "\n", encoding="utf-8")
        code, result = self.publish("--artifact", str(self.note))
        self.assertEqual(code, 1)
        self.assertIn("handover.md", result["error"]["hint"])

    def test_it_can_be_included_deliberately(self) -> None:
        self.note.write_text("key AKIA" + "W" * 16 + "\n", encoding="utf-8")
        code, result = self.publish(
            "--artifact", str(self.note), "--allow-flagged-artifacts"
        )
        self.assertEqual(code, 0)
        self.assertTrue(result["notes"])


class PackTests(_CliCase):
    def test_it_builds_the_bundle_without_filing_it(self) -> None:
        out = self.home / "staging"
        code, result = self.run_cli(
            "pack", "--session", fixtures.SESSION, "--out", str(out)
        )
        self.assertEqual(code, 0)
        self.assertFalse(result["filed"])
        self.assertTrue(pathlib.Path(result["bundle"]).is_file())
        self.assertFalse(self.root.exists())

    def test_it_reports_what_the_mint_needs(self) -> None:
        # The server has to bind these before it can sign an upload URL.
        _, result = self.run_cli("pack", "--session", fixtures.SESSION)
        self.assertRegex(result["sha256"], r"\A[0-9a-f]{64}\Z")
        self.assertGreater(result["size"], 0)
        self.assertIn("upload", result["next_step"])

    def test_it_names_the_configured_service(self) -> None:
        _, result = self.run_cli(
            "pack", "--store", "service", "--session", fixtures.SESSION
        )
        self.assertFalse(result["filed"])


class OpenTests(_CliCase):
    def setUp(self) -> None:
        super().setUp()
        self.published = self.publish()[1]

    def test_a_handle_returns_the_digest_to_read(self) -> None:
        _, result = self.run_cli(
            "open", "--handle", self.published["handle"], "--root", str(self.root)
        )
        self.assertIn("flags file", result["digest"])
        self.assertEqual(result["session_id"], fixtures.SESSION)
        self.assertEqual(result["title"], "Importer flags")

    def test_a_path_works_as_well_as_a_handle(self) -> None:
        _, result = self.run_cli("open", "--handle", self.published["path"])
        self.assertEqual(result["session_id"], fixtures.SESSION)

    def test_the_full_record_is_named_when_it_is_there(self) -> None:
        _, result = self.run_cli("open", "--handle", self.published["path"])
        self.assertTrue(pathlib.Path(result["record"]).is_file())

    def test_the_caveat_is_carried_to_the_reader(self) -> None:
        # Whoever continues the work needs to know what redaction did and did not do.
        _, result = self.run_cli("open", "--handle", self.published["path"])
        self.assertTrue(result["redaction_caveat"])

    def test_an_unknown_handle_says_what_to_check(self) -> None:
        code, result = self.run_cli(
            "open", "--handle", "default/nobody/20260820T140311Z-abcabcabcabc",
            "--root", str(self.root),
        )
        self.assertEqual(code, 1)
        self.assertIn("where", result["error"]["hint"])

    def test_neither_handle_nor_bundle_is_a_usage_error(self) -> None:
        code, result = self.run_cli("open")
        self.assertEqual(code, 1)
        self.assertIn("--handle", result["error"]["hint"])

    def test_an_evicted_bundle_is_not_read_as_a_short_session(self) -> None:
        pathlib.Path(self.published["path"], bundle.BUNDLE_NAME).write_bytes(b"")
        code, result = self.run_cli("open", "--handle", self.published["path"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["exception"], "ObjectNotMaterialized")
        self.assertEqual(result["error"]["code"], "session.not_materialized")


class UploadGuardTests(_CliCase):
    def test_something_that_is_not_a_bundle_is_not_sent(self) -> None:
        # Uploading unopenable bytes would only fail for whoever tried to continue
        # from them, long after the receipt said it worked.
        not_a_bundle = self.home / "notes.txt"
        not_a_bundle.write_text("hello\n", encoding="utf-8")
        mint = self.home / "mint.json"
        mint.write_text('{"url": "https://store.example.com/k"}', encoding="utf-8")
        code, result = self.run_cli(
            "upload", "--bundle", str(not_a_bundle), "--mint-file", str(mint)
        )
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["exception"], "BundleError")
        self.assertEqual(result["error"]["code"], "input.not_a_bundle")


class ConfigCommandTests(_CliCase):
    def test_showing_reports_without_writing(self) -> None:
        code, result = self.run_cli("config")
        self.assertEqual(code, 0)
        self.assertFalse(result["wrote"])
        self.assertIsNone(result["config_path"])

    def test_writing_persists_the_answers(self) -> None:
        code, result = self.run_cli(
            "config", "--set-store", "folder", "--set-root", str(self.root),
            "--set-namespace", "reports",
        )
        self.assertEqual(code, 0)
        self.assertTrue(result["wrote"])
        _, shown = self.run_cli("where")
        self.assertEqual(shown["root"], str(self.root))
        self.assertEqual(shown["namespace"], "reports")
        self.assertEqual(shown["sources"]["root"], "config-file")

    def test_the_root_is_not_created_by_configuring_it(self) -> None:
        # A store root brought into existence by a diagnostic is how work ends up
        # in a directory nobody is syncing.
        self.run_cli("config", "--set-root", str(self.root))
        self.assertFalse(self.root.exists())

    def test_a_service_store_is_recorded_with_its_server(self) -> None:
        _, result = self.run_cli(
            "config", "--set-store", "service", "--set-service", "my-store"
        )
        self.assertEqual(result["config"]["service_name"], "my-store")
        self.assertNotIn("root", result["config"])

    def test_a_store_this_build_cannot_use_is_refused(self) -> None:
        code, result = self.run_cli("config", "--set-store", "s3")
        self.assertEqual(code, 1)
        self.assertIn("service", result["error"]["hint"])


class RoundTripTests(_CliCase):
    def test_publish_then_open_carries_the_work_across(self) -> None:
        # The whole product in one test: one session publishes, another reads it
        # back from nothing but the handle.
        note = self.home / "handover.md"
        note.write_text("store 41 still open\n", encoding="utf-8")
        _, published = self.publish("--artifact", str(note), "--artifact-root", str(self.home))

        _, opened = self.run_cli(
            "open", "--handle", published["handle"], "--root", str(self.root)
        )
        self.assertEqual(opened["session_id"], fixtures.SESSION)
        self.assertIn("Importer flags", opened["digest"])
        self.assertIn("artifacts/handover.md", opened["artifacts"])
        self.assertEqual(opened["published_at"], published["publication_id"].split("-")[0])


if __name__ == "__main__":
    unittest.main()


class PlainErrorTests(_CliCase):
    """Every failure carries a sentence a teammate can read.

    A Kit relays what the engine says, so the engine must offer a string it is safe to
    relay. `hint` is written for whoever debugs this engine and uses words like
    `transcript` and `bundle`; `say` is for the person handing work to a colleague.
    """

    #: Words the Kit's skills are told never to put in front of a person.
    INTERNAL = ("bundle", "transcript", "namespace", "publication", "redact", "digest")

    def test_a_failure_carries_the_facts_a_caller_acts_on(self) -> None:
        code, result = self.run_cli("open", "--handle", "nope/nope/nope")
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        error = result["error"]
        self.assertEqual(error["op"], "open")
        self.assertEqual(error["code"], "handle.unknown")
        self.assertTrue(error["hint"], "the precise wording must survive for debugging")
        self.assertNotEqual(error["remedy"], error["hint"])

    def test_the_remedy_keeps_internal_words_out(self) -> None:
        for argv in (
            ("open", "--handle", "nope/nope/nope"),
            ("publish", "--session", "no-such-session-at-all"),
            ("upload", "--bundle", str(self.home / "not-a-bundle.zip"), "--mint-file", "/dev/null"),
        ):
            with self.subTest(argv=argv[0]):
                _, result = self.run_cli(*argv)
                if result.get("ok"):
                    continue
                spoken = (result["error"]["remedy"] or "").lower()
                for word in self.INTERNAL:
                    self.assertNotIn(word, spoken, f"{argv[0]} said {word!r} to a person")

    def test_a_receiving_failure_never_claims_nothing_was_sent(self) -> None:
        """The defect this shape exists for. Found against real R2.

        The old single fallback said "nothing was sent" for everything it did not
        recognise, so a reader whose download failed was told the *sender* had failed.
        """
        for code, (_origin, _fix_by, remedy) in cli.ERROR_CODES.items():
            with self.subTest(code=code):
                self.assertNotIn("nothing was sent", (remedy or "").lower())
                self.assertNotIn("nothing arrived", (remedy or "").lower())

    def test_an_unrecognised_failure_promises_nothing(self) -> None:
        described = cli.describe(Exception("disk on fire"), "open")
        self.assertEqual(described["code"], cli.FALLBACK_CODE)
        self.assertIsNone(described["remedy"])


class FetchDigestTests(_CliCase):
    """`fetch` checks the bytes against the digest the store reported.

    It used to honour `--sha256` alone, which nothing passed — so the reading skill
    promised a check that never ran, and a URL answering with someone else's bytes was
    written to disk without complaint.
    """

    def _mint(self, **overrides) -> pathlib.Path:
        mint = {"url": "https://example.net/x", "required_headers": {}}
        mint.update(overrides)
        path = self.home / "mint.json"
        path.write_text(json.dumps(mint), encoding="utf-8")
        return path

    def test_the_digest_comes_from_the_mint_when_no_flag_is_given(self) -> None:
        captured: dict = {}

        def fake_download(out, mint, *, expected_sha256=None):
            captured["expected"] = expected_sha256
            return {"path": str(out), "bytes": 0, "sha256": expected_sha256}

        with unittest.mock.patch.object(cli.download_mod, "download", fake_download):
            code, result = self.run_cli(
                "fetch", "--out", str(self.home / "b.zip"),
                "--mint-file", str(self._mint(sha256="a" * 64)),
            )
        self.assertEqual(code, 0)
        self.assertEqual(captured["expected"], "a" * 64)
        self.assertEqual(result["digest_source"], "mint")
        self.assertNotIn("note", result)

    def test_an_explicit_flag_still_wins(self) -> None:
        captured: dict = {}

        def fake_download(out, mint, *, expected_sha256=None):
            captured["expected"] = expected_sha256
            return {"path": str(out), "bytes": 0}

        with unittest.mock.patch.object(cli.download_mod, "download", fake_download):
            _, result = self.run_cli(
                "fetch", "--out", str(self.home / "b.zip"),
                "--mint-file", str(self._mint(sha256="a" * 64)), "--sha256", "b" * 64,
            )
        self.assertEqual(captured["expected"], "b" * 64)
        self.assertEqual(result["digest_source"], "flag")

    def test_a_store_that_reports_no_digest_says_so(self) -> None:
        def fake_download(out, mint, *, expected_sha256=None):
            return {"path": str(out), "bytes": 0}

        with unittest.mock.patch.object(cli.download_mod, "download", fake_download):
            _, result = self.run_cli(
                "fetch", "--out", str(self.home / "b.zip"), "--mint-file", str(self._mint()),
            )
        self.assertIsNone(result["digest_source"])
        self.assertIn("not checked", result["note"])


class ErrorContractTests(unittest.TestCase):
    """The failure payload is a contract, so the registry cannot rot quietly."""

    def test_every_registered_code_is_complete(self):
        for code, row in cli.ERROR_CODES.items():
            origin, fix_by, remedy = row
            self.assertIn(origin, {"input", "store", "network", "engine"}, code)
            self.assertIn(fix_by, {"user", "sender", "operator", "nobody"}, code)
            self.assertTrue(remedy is None or remedy.strip(), code)

    def test_every_transfer_code_maps_to_a_registered_one(self):
        for wire_code, code in cli._TRANSFER_CODES.items():
            self.assertIn(code, cli.ERROR_CODES, wire_code)

    def test_no_transfer_code_falls_through_unmapped(self):
        """A new `TransferError` code must be mapped, not left to the catch-all.

        Read out of the source rather than a hand-kept list, so adding one to `wire.py`
        or `download.py` is what fails this — which is the moment to decide what it is.
        """
        source = "".join(
            path.read_text(encoding="utf-8")
            for path in (pathlib.Path(cli.__file__).parent).glob("*.py")
        )
        raised = set(re.findall(r'TransferError\(\s*"([a-z_]+)"', source))
        raised |= set(re.findall(r'return "([a-z_]+)"', source)) & {
            "target_missing", "url_expired_or_forbidden", "body_too_large",
            "store_unavailable", "not_accepted",
        }
        self.assertTrue(raised)
        self.assertEqual(sorted(raised - set(cli._TRANSFER_CODES)), [])

    def test_a_remedy_never_carries_the_engine_s_own_vocabulary(self):
        for code, (_o, _f, remedy) in cli.ERROR_CODES.items():
            for word in ("bundle", "transcript", "namespace", "publication", "manifest"):
                self.assertNotIn(word, (remedy or "").lower(), code)

    def test_an_unregistered_code_raises_rather_than_shipping(self):
        original = cli._CODE_RULES
        cli._CODE_RULES = ((re.compile("boom"), "nope.not.a.code"),)
        self.addCleanup(setattr, cli, "_CODE_RULES", original)
        with self.assertRaises(cli.UnknownCode):
            cli.describe(ValueError("boom"), "pack")

    def test_the_catch_all_promises_nothing(self):
        """Its remedy was a sentence about sending, on failures that were receiving."""
        self.assertIsNone(cli.ERROR_CODES[cli.FALLBACK_CODE][2])
