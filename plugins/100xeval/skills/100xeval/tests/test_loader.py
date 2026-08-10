import os
import tempfile
import unittest

from engine import loader
from engine.loader import CaseError

GOOD = """
name: sample-case
plugins: ["plugin-a"]
tags: [asksales, smoke]
execution:
  prompt: "what were my slowest hours?"
  model: claude-sonnet-5
  allowed_tools: [Read, Skill]
graders:
  - {type: tool_used, name: queried, tool: some_tool, min: 1}
  - {type: llm, name: presentation, criteria: "cites source"}
"""


class TestLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # A case dir with a resolvable plugin dir next to it.
        self.case_dir = os.path.join(self.root, "sample-case")
        os.makedirs(os.path.join(self.case_dir, "plugin-a"))

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text, name="sample-case"):
        d = os.path.join(self.root, name)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "case.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_load_good_case(self):
        path = self._write(GOOD)
        case = loader.load_case(path)
        self.assertEqual(case.name, "sample-case")
        self.assertEqual(case.prompt, "what were my slowest hours?")
        self.assertEqual(case.model, "claude-sonnet-5")
        self.assertEqual(case.runs, 3)                      # default
        self.assertEqual(case.harness, "claude_code")       # default
        self.assertEqual(len(case.graders), 2)
        self.assertEqual(case.graders[0].params["tool"], "some_tool")
        self.assertEqual(case.graders[0].params["min"], 1)

    def test_execution_identity(self):
        case = loader.load_case(self._write(GOOD))
        self.assertEqual(case.harness, "claude_code")
        self.assertEqual(case.model, "claude-sonnet-5")
        self.assertEqual(case.label(), "claude_code/claude-sonnet-5")

    def test_explicit_harness(self):
        text = GOOD.replace("  model: claude-sonnet-5",
                            "  model: claude-sonnet-5\n  harness: codex")
        case = loader.load_case(self._write(text))
        self.assertEqual(case.harness, "codex")

    def test_surface_named_harnesses_rejected(self):
        # `harness` names a RUNTIME; these named surfaces. The error must point at the
        # runtime + entrypoint pair that replaces each.
        for bad, expected in (("cowork", "entrypoint: cowork"), ("claude_chat", "entrypoint: chat")):
            text = GOOD.replace("  model: claude-sonnet-5",
                                f"  model: claude-sonnet-5\n  harness: {bad}")
            with self.assertRaises(CaseError) as ctx:
                loader.load_case(self._write(text))
            self.assertIn("claude_code", str(ctx.exception))
            self.assertIn(expected, str(ctx.exception))

    def test_entrypoint_cowork_still_valid(self):
        # The rename touches `harness` only — `entrypoint: cowork` is still correct.
        text = GOOD.replace("  model: claude-sonnet-5",
                            "  model: claude-sonnet-5\n  entrypoint: cowork")
        case = loader.load_case(self._write(text))
        self.assertEqual(case.entrypoint, "cowork")
        self.assertEqual(case.harness, "claude_code")

    def test_retired_plural_fields_error(self):
        # The old matrix keys must fail loudly, not silently pick the first entry.
        for text in (
            GOOD.replace("  model: claude-sonnet-5", "  models: [claude-sonnet-5, claude-opus-4-8]"),
            GOOD.replace("  model: claude-sonnet-5",
                         "  model: claude-sonnet-5\n  harnesses: [claude_code, codex]"),
        ):
            with self.assertRaises(CaseError):
                loader.load_case(self._write(text))

    def test_as_dict_covers_every_case_field(self):
        # cases.json must stay a COMPLETE record of what ran. This fails if a field is
        # added to Case and not to as_dict(), which would silently drop it from the run.
        import dataclasses

        from engine.models import Case
        case = loader.load_case(self._write(GOOD))
        dumped = case.as_dict()
        flat = {k for k in dumped if k != "execution"} | set(dumped["execution"])
        missing = {f.name for f in dataclasses.fields(Case)} - flat
        self.assertEqual(missing, set(), f"Case fields missing from as_dict(): {missing}")

    def test_as_dict_round_trips_through_json(self):
        import json

        case = loader.load_case(self._write(GOOD))
        dumped = json.loads(json.dumps(case.as_dict()))   # must be JSON-serializable
        self.assertEqual(dumped["execution"]["prompt"], "what were my slowest hours?")
        self.assertEqual(dumped["execution"]["allowed_tools"], ["Read", "Skill"])
        self.assertEqual(dumped["plugins"], ["plugin-a"])
        # Graders keep their per-type params, not just type/name/weight.
        tool_grader = next(g for g in dumped["graders"] if g["name"] == "queried")
        self.assertEqual(tool_grader["tool"], "some_tool")
        self.assertEqual(tool_grader["min"], 1)

    def test_missing_prompt_errors(self):
        text = "name: x\ngraders:\n  - {type: regex, name: g, pattern: hi}\n"
        with self.assertRaises(CaseError):
            loader.load_case(self._write(text, name="nop"))

    def test_no_graders_errors(self):
        text = "name: x\nexecution:\n  prompt: hi\n"
        with self.assertRaises(CaseError):
            loader.load_case(self._write(text, name="nog"))

    def test_duplicate_grader_name_errors(self):
        text = (
            "name: x\nexecution:\n  prompt: hi\ngraders:\n"
            "  - {type: regex, name: dup, pattern: a}\n"
            "  - {type: regex, name: dup, pattern: b}\n"
        )
        with self.assertRaises(CaseError):
            loader.load_case(self._write(text, name="dup"))

    def test_unresolved_plugin_path_errors(self):
        text = GOOD.replace('["plugin-a"]', '["does-not-exist"]')
        with self.assertRaises(CaseError):
            loader.load_case(self._write(text, name="badplugin"))

    def test_select_by_tag_and_glob(self):
        self._write(GOOD, name="sample-case")
        cases, errors = loader.load_all(self.root, tags=["smoke"], case_glob="sample-*")
        self.assertEqual(errors, [])
        self.assertEqual(len(cases), 1)
        # A tag not present filters it out.
        cases2, _ = loader.load_all(self.root, tags=["nope"], case_glob=None)
        self.assertEqual(cases2, [])

    def test_malformed_case_isolated(self):
        self._write(GOOD, name="sample-case")
        self._write("name: broken\n:::not yaml", name="broken")
        cases, errors = loader.load_all(self.root)
        names = {c.name for c in cases}
        self.assertIn("sample-case", names)                 # good one still loads
        self.assertTrue(any("broken" in path for path, _ in errors))



class TestSkip(unittest.TestCase):
    """A case can be parked with a reason instead of deleted. Deleting loses the
    scenario; untagging hides it. `skip:` keeps both the case and the why."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text, name):
        import os
        d = os.path.join(self.root, name)
        os.makedirs(os.path.join(d, "plugin-a"), exist_ok=True)
        with open(os.path.join(d, "case.yaml"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_skipped_case_is_excluded_but_still_loadable(self):
        self._write(GOOD.replace("name: sample-case", "name: runs-me"), "runs-me")
        self._write(GOOD.replace("name: sample-case", 'name: parked\nskip: "too slow for now"'), "parked")
        cases, errors = loader.load_all(self.root)
        self.assertEqual(errors, [])
        self.assertEqual([c.name for c in cases], ["runs-me"])
        every, _ = loader.load_all(self.root, include_skipped=True)
        parked = next(c for c in every if c.name == "parked")
        self.assertEqual(parked.skip, "too slow for now")

    def test_skip_reason_is_recorded_in_cases_json(self):
        self._write(GOOD.replace("name: sample-case", 'name: parked\nskip: "why"'), "parked")
        every, _ = loader.load_all(self.root, include_skipped=True)
        self.assertEqual(every[0].as_dict()["skip"], "why")

    def test_absent_skip_means_it_runs(self):
        self._write(GOOD, "sample-case")
        cases, _ = loader.load_all(self.root)
        self.assertEqual(cases[0].skip, "")

if __name__ == "__main__":
    unittest.main()
