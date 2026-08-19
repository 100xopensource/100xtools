import unittest

from engine.harnesses import claude_code

# A representative Claude Code session transcript (.jsonl) with two tool_use blocks.
TRANSCRIPT = """
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"slowest hours?"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Let me query."},{"type":"tool_use","name":"mcp__Acme__run_query","input":{"sql":"SELECT hour FROM sales WHERE store='Eastern'"}}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Read","input":{"file":"x.md"}}]}}
not-json-garbage-line
{"type":"result"}
"""

CLI_JSON = '{"type":"result","subtype":"success","result":"Source: Acme\\n| hour | sales |","session_id":"abc-123","total_cost_usd":0.0421,"duration_ms":8123}'


class TestCoworkParse(unittest.TestCase):
    def test_parse_transcript_tool_calls(self):
        calls = claude_code.parse_transcript_tool_calls(TRANSCRIPT)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].name, "mcp__Acme__run_query")
        self.assertIn("Eastern", calls[0].input_str)
        self.assertEqual(calls[1].name, "Read")

    def test_parse_cli_json(self):
        final, session, cost, duration = claude_code.parse_cli_json(CLI_JSON)
        self.assertIn("Source: Acme", final)
        self.assertEqual(session, "abc-123")
        self.assertAlmostEqual(cost, 0.0421)
        self.assertEqual(duration, 8123)

    def test_parse_cli_json_non_json_fallback(self):
        final, session, cost, duration = claude_code.parse_cli_json("plain text answer")
        self.assertEqual(final, "plain text answer")
        self.assertIsNone(session)

    def test_harness_capabilities(self):
        h = claude_code.ClaudeCodeHarness()
        self.assertTrue(h.supports("tool_used"))
        self.assertTrue(h.supports("llm"))
        self.assertFalse(h.supports("nonexistent"))

    def test_default_entrypoint_is_none_and_loads_empty(self):
        # The default emulates no surface on purpose: no entrypoint file ships, so the
        # run uses the harness's own system prompt. `_load_entrypoint` returning "" is
        # what makes the harness omit --system-prompt entirely.
        from engine.models import Case
        self.assertEqual(Case(name="c", prompt="p").entrypoint, "none")
        self.assertEqual(claude_code._load_entrypoint(Case(name="c", prompt="p")), "")

    def test_unknown_entrypoint_resolves_to_none(self):
        from engine.models import Case
        self.assertIsNone(claude_code._entrypoint_path(Case(name="c", prompt="p", entrypoint="nope")))

    def test_redact_cmd_hides_system_prompt(self):
        cmd = ["claude", "-p", "q", "--system-prompt", "X" * 9000, "--output-format", "json"]
        red = claude_code._redact_cmd(cmd)
        self.assertNotIn("X" * 9000, red)
        self.assertIn("<9000 chars>", red)
        self.assertIn("--system-prompt", red)      # flag kept, value redacted
        self.assertIn("--output-format", red)       # everything else intact



class TestEngineGapFixes(unittest.TestCase):
    """Three knobs that were parsed but did nothing (or failed silently)."""

    def test_max_turns_reaches_the_cli(self):
        # Was parsed into Case and written to cases.json, but never passed to `claude`,
        # so raising it bought a long report build exactly nothing.
        import os
        import tempfile
        from unittest import mock

        from engine.models import Case
        with tempfile.TemporaryDirectory() as tmp:
            case = Case(name="c", prompt="q", path=tmp, max_turns=60)
            h = claude_code.ClaudeCodeHarness()
            captured = {}

            def fake_run(cmd, **kw):
                captured["cmd"] = cmd
                import subprocess
                return subprocess.CompletedProcess(cmd, 0, stdout='{"result":"ok"}', stderr="")

            with mock.patch.object(claude_code.subprocess, "run", side_effect=fake_run):
                h.run(case, model=None, workspace=os.path.join(tmp, "ws"))
        cmd = captured["cmd"]
        self.assertIn("--max-turns", cmd)
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "60")

    def test_missing_entrypoint_aborts_instead_of_running_promptless(self):
        # Naming a surface with no file used to return None -> empty system prompt ->
        # the run emulated NO surface, silently, while still producing a score.
        from engine.harnesses.base import Abort
        from engine.models import Case
        with self.assertRaises(Abort) as ctx:
            claude_code.verify_entrypoint(Case(name="c", prompt="q", entrypoint="does-not-exist"))
        self.assertIn("does-not-exist", str(ctx.exception))

    def test_default_none_passes_preflight_without_a_file(self):
        # No entrypoint files ship, so the default must not abort — otherwise a clean
        # clone cannot run a single case.
        from engine.models import Case
        claude_code.verify_entrypoint(Case(name="c", prompt="q"))   # entrypoint: none

    def test_added_entrypoint_is_discovered(self):
        # Surface prompts are supplied by the user, so `available_entrypoints` must pick
        # up whatever is dropped into entrypoints/ rather than a hardcoded list.
        import os
        from unittest import mock
        d = os.path.join(os.path.dirname(os.path.dirname(claude_code.__file__)), "entrypoints")
        with mock.patch("os.path.isdir", return_value=True), \
             mock.patch("os.listdir", return_value=["README.md", "my-surface.md"]) as ls:
            names = claude_code.available_entrypoints()
        ls.assert_called_once_with(d)
        self.assertEqual(names, ["my-surface"])   # README.md is not a surface

if __name__ == "__main__":
    unittest.main()


class TestTokenUsage(unittest.TestCase):
    """Cost alone hid WHY a run was expensive — cache creation dwarfs plain input."""

    SAMPLE = ('{"result":"ok","total_cost_usd":0.42,"usage":{"input_tokens":2,'
              '"output_tokens":97,"cache_read_input_tokens":15743,'
              '"cache_creation_input_tokens":40826}}')

    def test_parses_the_four_counters(self):
        u = claude_code.parse_usage(self.SAMPLE)
        self.assertEqual(u["input_tokens"], 2)
        self.assertEqual(u["output_tokens"], 97)
        self.assertEqual(u["cache_read_input_tokens"], 15743)
        self.assertEqual(u["cache_creation_input_tokens"], 40826)

    def test_missing_or_unparseable_usage_is_zeros_not_a_crash(self):
        for bad in ("not json", '{"result":"ok"}', '{"result":"ok","usage":null}'):
            u = claude_code.parse_usage(bad)
            self.assertEqual(set(u), set(claude_code.TOKEN_FIELDS))
            self.assertEqual(sum(u.values()), 0)

    def test_add_tokens_sums_elementwise(self):
        a = {"input_tokens": 1, "output_tokens": 2,
             "cache_read_input_tokens": 3, "cache_creation_input_tokens": 4}
        total = claude_code.add_tokens(a, a, None, {})
        self.assertEqual(total["input_tokens"], 2)
        self.assertEqual(total["cache_creation_input_tokens"], 8)

    def test_run_result_carries_usage(self):
        import os
        import tempfile
        from unittest import mock
        from engine.models import Case
        with tempfile.TemporaryDirectory() as tmp:
            case = Case(name="c", prompt="q", path=tmp)
            completed = __import__("subprocess").CompletedProcess([], 0, stdout=self.SAMPLE, stderr="")
            with mock.patch.object(claude_code.subprocess, "run", return_value=completed):
                res = claude_code.ClaudeCodeHarness().run(case, None, os.path.join(tmp, "ws"))
        self.assertEqual(res.tokens["cache_creation_input_tokens"], 40826)
        self.assertAlmostEqual(res.cost_usd, 0.42)
