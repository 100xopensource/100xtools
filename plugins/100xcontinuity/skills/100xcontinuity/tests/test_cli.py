"""The command-line surface: JSON contract, config precedence, exit codes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

from engine import cli


class _CliFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = str(pathlib.Path(self._tmp.name) / "store")
        self.base = ["--root", self.root, "--namespace", "t", "--session", "s1"]

    def run_cli(self, *args: str, stdin: bytes = b"") -> tuple[int, str]:
        out = io.StringIO()
        buffer = io.BytesIO()
        out.buffer = buffer  # type: ignore[attr-defined]
        stdin_stream = io.StringIO()
        stdin_stream.buffer = io.BytesIO(stdin)  # type: ignore[attr-defined]
        with contextlib.redirect_stdout(out):
            with unittest.mock.patch("sys.stdin", stdin_stream):
                code = cli.main(list(args))
        return code, out.getvalue() or buffer.getvalue().decode("utf-8", "replace")

    def json_cli(self, *args: str, stdin: bytes = b"") -> dict:
        code, text = self.run_cli(*args, stdin=stdin)
        self.assertEqual(code, 0, text)
        return json.loads(text)


class SaveAndLoadTests(_CliFixture):
    def test_save_then_list(self) -> None:
        self.json_cli("save", *self.base, "--name", "a.txt", stdin=b"hello")
        listed = self.json_cli("list", *self.base)
        self.assertEqual([a["name"] for a in listed["artifacts"]], ["a.txt"])

    def test_save_from_a_file(self) -> None:
        src = pathlib.Path(self._tmp.name) / "in.txt"
        src.write_bytes(b"from disk")
        saved = self.json_cli(
            "save", *self.base, "--name", "b.txt", "--file", str(src)
        )
        self.assertEqual(saved["saved"]["size"], 9)

    def test_load_to_a_file_round_trips(self) -> None:
        self.json_cli("save", *self.base, "--name", "a.txt", stdin=b"payload")
        dest = pathlib.Path(self._tmp.name) / "out" / "a.txt"
        self.json_cli("load", *self.base, "--name", "a.txt", "--out", str(dest))
        self.assertEqual(dest.read_bytes(), b"payload")

    def test_load_to_stdout_emits_raw_bytes(self) -> None:
        # The bytes are the point here, so no JSON envelope wraps them.
        self.json_cli("save", *self.base, "--name", "a.txt", stdin=b"raw output")
        code, text = self.run_cli("load", *self.base, "--name", "a.txt")
        self.assertEqual(code, 0)
        self.assertEqual(text, "raw output")

    def test_media_type_is_recorded(self) -> None:
        saved = self.json_cli(
            "save", *self.base, "--name", "c.png", "--media-type", "image/png",
            stdin=b"\x89PNG",
        )
        self.assertEqual(saved["saved"]["media_type"], "image/png")


class OutputContractTests(_CliFixture):
    def test_every_result_is_json(self) -> None:
        for cmd in (("list",), ("where",)):
            with self.subTest(cmd=cmd):
                _, text = self.run_cli(*cmd, *self.base)
                json.loads(text)  # raises if the command printed prose

    def test_missing_artifact_exits_nonzero_with_a_hint(self) -> None:
        code, text = self.run_cli("load", *self.base, "--name", "nope.txt")
        self.assertEqual(code, 1)
        payload = json.loads(text)
        self.assertFalse(payload["ok"])
        self.assertIn("nope.txt", payload["hint"])

    def test_unknown_backend_exits_nonzero(self) -> None:
        code, text = self.run_cli("list", "--backend", "gdrive", "--root", self.root)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)["ok"])

    def test_no_command_prints_help_and_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main([]), 2)

    def test_empty_session_lists_cleanly(self) -> None:
        listed = self.json_cli("list", *self.base)
        self.assertEqual(listed["artifacts"], [])
        self.assertEqual(listed["damaged"], [])


class ConfigPrecedenceTests(_CliFixture):
    def test_flag_beats_environment(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"CONTINUITY_NAMESPACE": "from-env"}
        ):
            where = self.json_cli("where", *self.base)
        self.assertEqual(where["namespace"], "t")

    def test_environment_is_used_when_no_flag(self) -> None:
        with unittest.mock.patch.dict(
            os.environ,
            {"CONTINUITY_ROOT": self.root, "CONTINUITY_NAMESPACE": "from-env"},
        ):
            where = self.json_cli("where", "--session", "s1")
        self.assertEqual(where["namespace"], "from-env")

    def test_session_falls_back_to_the_claude_variable(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"CLAUDE_SESSION_ID": "from-claude", "CONTINUITY_ROOT": self.root}
        ):
            where = self.json_cli("where", "--namespace", "t")
        self.assertTrue(where["session_resolved"])

    def test_defaults_apply_with_nothing_set(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            where = self.json_cli("where")
        self.assertEqual(where["backend"], "local")
        self.assertIn("Continuity", where["root"])


class UnresolvedSessionTests(_CliFixture):
    def test_unresolved_session_still_succeeds_but_says_so(self) -> None:
        # Silence here is how someone ends up with a store full of artifacts they
        # cannot find again.
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            saved = self.json_cli(
                "save", "--root", self.root, "--name", "a.txt", stdin=b"x"
            )
        self.assertFalse(saved["session_resolved"])
        self.assertIn("--session", saved["hint"])

    def test_resolved_session_carries_no_hint(self) -> None:
        saved = self.json_cli("save", *self.base, "--name", "a.txt", stdin=b"x")
        self.assertTrue(saved["session_resolved"])
        self.assertNotIn("hint", saved)


class WhereTests(_CliFixture):
    def test_where_reports_the_resolved_path(self) -> None:
        where = self.json_cli("where", *self.base)
        self.assertTrue(where["session_path"].startswith(self.root))
        self.assertIn(where["session_digest"], where["session_path"])

    def test_where_does_not_create_the_root(self) -> None:
        # A diagnostic command must not have a side effect, or "where is my
        # store" silently answers "here now".
        self.json_cli("where", *self.base)
        self.assertFalse(pathlib.Path(self.root).exists())

    def test_where_reports_whether_the_root_exists(self) -> None:
        self.assertFalse(self.json_cli("where", *self.base)["root_exists"])
        self.json_cli("save", *self.base, "--name", "a.txt", stdin=b"x")
        self.assertTrue(self.json_cli("where", *self.base)["root_exists"])


if __name__ == "__main__":
    unittest.main()
