#!/usr/bin/env python3
"""What this plugin promises, checked without a model in the loop.

Run it any time. It costs nothing, needs no network unless your store is a service,
and never touches a real conversation — every check runs against a synthetic session
written into a throwaway home, because packing your actual conversation would put it
in the store.

    python3 tests/contract_test.py            # from the plugin directory
    python3 tests/contract_test.py -v         # naming each check

What it proves depends on where your handoffs go, and it says so rather than passing
quietly: a folder store can be exercised end to end here, while a service store's own
server is reached through MCP, which a shell cannot speak. The service checks therefore
cover everything up to and including the download digest, and stop at the one fact no
test can establish before you register the server.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
RUN = PLUGIN / "scripts" / "run.py"
KIT = json.loads((PLUGIN / "kit.json").read_text(encoding="utf-8"))
STORE_KIND = KIT.get("store", "folder")

SESSION = "contract-check"
CWD = "/repo/contract-check"

# Assembled rather than written out, so this file never itself contains a string that
# a secret scanner has to decide about.
PLANTED = "AKIA" + "Q" * 16
LABELLED = "DEPLOY_TOKEN=dpl_" + "a" * 20


def _records() -> list[dict]:
    """One short session: a prompt carrying two credential shapes, and an answer."""
    return [
        {"type": "ai-title", "aiTitle": "Contract check", "sessionId": SESSION},
        {
            "type": "user",
            "sessionId": SESSION,
            "origin": {"kind": "human"},
            "cwd": CWD,
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Ship it. Key is {PLANTED} and {LABELLED} if you need them.",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": SESSION,
            "cwd": CWD,
            "timestamp": "2026-01-01T00:01:00.000Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "content": [{"type": "text", "text": "Shipped. One thing is still open."}],
            },
        },
    ]


class _Contract(unittest.TestCase):
    """A private home holding one synthetic session, and a store beside it."""

    maxDiff = None

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="handoff-contract-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        projects = self.tmp / "home" / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
        projects.mkdir(parents=True)
        (projects / f"{SESSION}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in _records()), encoding="utf-8"
        )
        self.work = self.tmp / "work"
        self.work.mkdir()
        (self.work / "handover.md").write_text("# Handover\n\nOne open item.\n", encoding="utf-8")
        self.store = self.tmp / "store"

    def run_kit(self, *argv: str, expect_ok: bool = True) -> dict:
        """Drive the real command surface, the way the skills drive it."""
        env = {
            **os.environ,
            "HOME": str(self.tmp / "home"),
            # The store is overridden so a check never writes into the team's real one.
            "CONTINUITY_ROOT": str(self.store),
        }
        proc = subprocess.run(
            [sys.executable, str(RUN), *argv],
            capture_output=True, text=True, env=env, cwd=str(self.work),
        )
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:  # pragma: no cover - only on a broken build
            self.fail(f"the engine printed something that is not JSON:\n{proc.stdout}\n{proc.stderr}")
        if expect_ok:
            self.assertTrue(payload.get("ok"), f"{argv[0]} failed: {payload.get('hint')}")
        else:
            self.assertFalse(payload.get("ok"), f"{argv[0]} was expected to refuse, got {payload}")
        return payload

    def pack(self, *extra: str) -> dict:
        return self.run_kit(
            "pack", "--session", SESSION,
            "--artifact", str(self.work / "handover.md"), "--artifact-root", str(self.work),
            "--out", str(self.tmp / "staging"), *extra,
        )


class Packing(_Contract):
    def test_a_handoff_is_one_archive_with_the_manifest_last(self) -> None:
        built = self.pack()
        names = zipfile.ZipFile(built["bundle"]).namelist()
        self.assertIn("start-here.html", names)
        self.assertIn("artifacts/handover.md", names)
        self.assertTrue(any(n.startswith("transcript/") for n in names))
        self.assertEqual(
            names[-1], "manifest.json",
            "the manifest is the marker that the archive is complete, so it is written last",
        )

    def test_credential_shapes_do_not_travel(self) -> None:
        built = self.pack()
        with zipfile.ZipFile(built["bundle"]) as archive:
            blob = b"".join(archive.read(n) for n in archive.namelist())
        self.assertNotIn(PLANTED.encode(), blob, "an access key reached the archive")
        self.assertNotIn(b"dpl_" + b"a" * 20, blob, "a labelled token reached the archive")
        self.assertGreater(built["redaction_total"], 0)

    def test_a_file_a_person_wrote_travels_verbatim(self) -> None:
        built = self.pack()
        with zipfile.ZipFile(built["bundle"]) as archive:
            self.assertEqual(
                archive.read("artifacts/handover.md"),
                (self.work / "handover.md").read_bytes(),
            )

    def test_the_same_work_packs_to_the_same_bytes(self) -> None:
        """Reproducibility is what makes an unchanged resend recognisable."""
        first, second = self.pack()["sha256"], self.pack()["sha256"]
        self.assertEqual(first, second)

    def test_a_file_that_looks_like_a_credential_stops_it(self) -> None:
        (self.work / "deploy.env").write_text("API_KEY=zzzzzzzzzzzzzzzz\n", encoding="utf-8")
        self.run_kit(
            "pack", "--session", SESSION,
            "--artifact", str(self.work / "deploy.env"), "--artifact-root", str(self.work),
            "--out", str(self.tmp / "staging2"),
            expect_ok=False,
        )

    def test_a_failure_speaks_to_a_person_and_to_a_maintainer(self) -> None:
        result = self.run_kit("open", "--handle", "no/such/handle", expect_ok=False)
        self.assertTrue(result["say"], "nothing to tell the person")
        self.assertTrue(result["hint"], "nothing to tell whoever maintains this")
        for word in ("bundle", "transcript", "namespace", "publication"):
            self.assertNotIn(word, result["say"].lower())


class Reading(_Contract):
    def test_a_packed_handoff_opens_again(self) -> None:
        built = self.pack()
        opened = self.run_kit("open", "--bundle", built["bundle"], "--out", str(self.tmp / "opened"))
        self.assertEqual(opened["session_id"], SESSION)
        self.assertIn("artifacts/handover.md", opened["artifacts"])
        self.assertIn("Contract check", opened["digest"])

    def test_truncated_bytes_are_refused(self) -> None:
        built = self.pack()
        path = pathlib.Path(built["bundle"])
        path.write_bytes(path.read_bytes()[: len(path.read_bytes()) // 2])
        self.run_kit("open", "--bundle", str(path), "--out", str(self.tmp / "t"), expect_ok=False)

    def test_altered_bytes_are_refused(self) -> None:
        """Right length, wrong contents — the failure a length check cannot see."""
        built = self.pack()
        path = pathlib.Path(built["bundle"])
        raw = bytearray(path.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        path.write_bytes(bytes(raw))
        self.run_kit("open", "--bundle", str(path), "--out", str(self.tmp / "a"), expect_ok=False)


@unittest.skipUnless(STORE_KIND == "folder", "this Kit files into a service, not a folder")
class FolderStore(_Contract):
    def publish(self) -> dict:
        return self.run_kit(
            "publish", "--session", SESSION,
            "--artifact", str(self.work / "handover.md"), "--artifact-root", str(self.work),
        )

    def test_a_handoff_reaches_the_store(self) -> None:
        filed = self.publish()
        directory = pathlib.Path(filed["path"])
        self.assertTrue((directory / "bundle.zip").is_file())
        self.assertTrue((directory / "publication.json").is_file(), "the completion marker")

    def test_the_code_opens_it_again(self) -> None:
        filed = self.publish()
        opened = self.run_kit("open", "--handle", filed["handle"], "--out", str(self.tmp / "o"))
        self.assertEqual(opened["session_id"], SESSION)
        self.assertIn("artifacts/handover.md", opened["artifacts"])

    def test_handing_the_same_work_over_twice_is_recognised(self) -> None:
        first = self.publish()
        second = self.publish()
        self.assertTrue(second["already_published"])
        self.assertEqual(first["handle"], second["handle"])
        directories = [p for p in self.store.rglob("publication.json")]
        self.assertEqual(len(directories), 1, "an unchanged resend was filed twice")

    def test_a_placeholder_is_not_read_as_an_empty_session(self) -> None:
        """What a sync client leaves behind when it reclaims disk."""
        filed = self.publish()
        (pathlib.Path(filed["path"]) / "bundle.zip").write_bytes(b"")
        result = self.run_kit(
            "open", "--handle", filed["handle"], "--out", str(self.tmp / "e"), expect_ok=False
        )
        self.assertTrue(result["say"])


@unittest.skipUnless(STORE_KIND == "service", "this Kit files into a folder, not a service")
class ServiceStore(_Contract):
    """Everything up to and including the download digest.

    The store's own server is reached over MCP, which a shell cannot speak, so minting
    is not exercised here. What is exercised is the half that has actually been wrong:
    whether a download is checked against the digest the server reported. The transport
    is stubbed rather than served locally, because the engine refuses a plain-http URL
    and that refusal is itself worth keeping — see the first check below.
    """

    def test_a_plain_http_url_is_refused(self) -> None:
        """No downgrade, not even to localhost. A minted URL is https or it is nothing."""
        mint = self.tmp / "http-mint.json"
        mint.write_text(
            json.dumps({"url": "http://127.0.0.1:9/x.zip", "required_headers": {}}),
            encoding="utf-8",
        )
        result = self.run_kit(
            "fetch", "--mint-file", str(mint), "--out", str(self.tmp / "no.zip"),
            expect_ok=False,
        )
        self.assertIn("https", result["hint"])

    def _download(self, served: bytes, reported: str) -> None:
        """Call the engine's own download with the network stubbed out."""
        sys.path.insert(0, str(PLUGIN / "scripts"))
        from engine import download as download_mod, wire  # noqa: PLC0415

        original = wire.send
        wire.send = lambda *a, **k: (200, served)  # type: ignore[assignment]
        self.addCleanup(setattr, wire, "send", original)
        download_mod.download(
            str(self.tmp / "in.zip"),
            {"url": "https://example.net/bundle.zip", "required_headers": {}},
            expected_sha256=reported,
        )

    def test_bytes_matching_what_the_store_reported_are_accepted(self) -> None:
        body = pathlib.Path(self.pack()["bundle"]).read_bytes()
        self._download(body, hashlib.sha256(body).hexdigest())
        self.assertEqual((self.tmp / "in.zip").read_bytes(), body)

    def test_bytes_that_do_not_match_are_refused(self) -> None:
        """The check the reading skill promises. As invoked, it once never ran."""
        body = pathlib.Path(self.pack()["bundle"]).read_bytes()
        wrong = bytearray(body)
        wrong[len(wrong) // 2] ^= 0xFF
        with self.assertRaises(Exception):
            self._download(bytes(wrong), hashlib.sha256(body).hexdigest())

    def test_the_reading_skill_passes_the_reported_digest_through(self) -> None:
        """The defect was here: `fetch` honoured only --sha256, which nothing passed."""
        mint = self.tmp / "mint.json"
        mint.write_text(
            json.dumps({
                "url": "https://example.net/x.zip",
                "required_headers": {},
                "sha256": "a" * 64,
            }),
            encoding="utf-8",
        )
        result = self.run_kit(
            "fetch", "--mint-file", str(mint), "--out", str(self.tmp / "x.zip"),
            expect_ok=False,
        )
        self.assertNotIn(
            "not checked", json.dumps(result),
            "the digest in the mint answer was ignored, so nothing verified the bytes",
        )


class DocumentedLimits(_Contract):
    """Pinned so nobody reads a green suite as proof a handoff is clean."""

    def test_a_labelled_credential_is_removed(self) -> None:
        sys.path.insert(0, str(PLUGIN / "scripts"))
        from engine import redact  # noqa: PLC0415 - the plugin's own copy

        self.assertTrue(redact.redact_text("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI7MD").counts)

    def test_a_secret_written_as_prose_is_not(self) -> None:
        sys.path.insert(0, str(PLUGIN / "scripts"))
        from engine import redact  # noqa: PLC0415

        prose = "the password is the dog's name backwards"
        self.assertFalse(
            redact.redact_text(prose).counts,
            "if this now passes, the documented limit changed and the skills should say so",
        )


if __name__ == "__main__":
    print(f"contract: {KIT.get('kit_name')} filing into a {STORE_KIND} store\n")
    unittest.main(verbosity=2)
