import unittest

from engine.orchestrator import run_case
from engine.harnesses.base import register_harness
from engine.models import Case, Grader, RunResult, ToolCall


class FakeHarness:
    """Deterministic in-memory harness for testing execution + scoring."""

    def __init__(self, name, final="Source: X", calls=None, supports_tool=True):
        self.name = name
        self._final = final
        self._calls = calls if calls is not None else [ToolCall("sql", "Eastern")]
        self._supports_tool = supports_tool

    def supports(self, grader_type):
        if grader_type == "tool_used":
            return self._supports_tool
        return True

    def preflight(self, case):
        pass

    def run(self, case, model, workspace=None):
        return RunResult(final_text=self._final, tool_calls=list(self._calls),
                         cost_usd=0.01, duration_ms=100)


def _case(harness, model=None, runs=2):
    return Case(
        name="c", prompt="p", harness=harness, model=model, runs=runs,
        graders=[
            Grader("tool_used", "q", params={"tool": "sql", "input_match": "Eastern", "min": 1}),
            Grader("regex", "cite", params={"pattern": "Source:"}),
        ],
    )


class TestExecutor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_harness(FakeHarness("fake"))
        register_harness(FakeHarness("fake_bad", final="no cite", calls=[]))
        register_harness(FakeHarness("fake_notool", supports_tool=False))

    def test_case_passes(self):
        card = run_case(_case("fake"), threshold=1.0)
        self.assertTrue(card.passed)
        self.assertEqual(card.score, 1.0)

    def test_card_records_its_harness_and_model(self):
        card = run_case(_case("fake", model="m1"), threshold=1.0)
        self.assertEqual(card.harness, "fake")
        self.assertEqual(card.model, "m1")
        self.assertEqual(card.label(), "fake/m1")

    def test_failing_harness_scores_zero(self):
        card = run_case(_case("fake_bad"), threshold=1.0)
        self.assertFalse(card.passed)
        self.assertEqual(card.score, 0.0)

    def test_passrate_over_runs(self):
        card = run_case(_case("fake", runs=3), threshold=1.0)
        for g in card.graders:
            self.assertEqual(g["passRate"], 1.0)
            self.assertEqual(len(g["runs"]), 3)

    def test_tool_unsupported_reported_not_crashed(self):
        card = run_case(_case("fake_notool"), threshold=1.0)
        tool_grader = next(g for g in card.graders if g["name"] == "q")
        self.assertEqual(tool_grader["passRate"], 0.0)
        self.assertIn("unsupported", tool_grader["runs"][0]["detail"])

    def test_codex_seam_aborts_with_guidance(self):
        # Registered but unimplemented: the case must fail with an actionable message,
        # not the generic "unknown harness" error.
        card = run_case(_case("codex"), threshold=1.0)
        self.assertFalse(card.passed)
        self.assertIn("not yet implemented", card.error)
        self.assertIn("claude_code", card.error)

    def test_unknown_harness_errors_the_case(self):
        card = run_case(_case("does_not_exist"), threshold=1.0)
        self.assertIsNotNone(card.error)
        self.assertFalse(card.passed)
        self.assertEqual(card.graders, [])

    def test_run_dir_persists_structured_files(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as run_dir:
            run_case(_case("fake", runs=2), threshold=1.0, run_dir=run_dir)
            # Flat: runs/<run_id>/<case>/ — no <harness>__<model> level.
            case_dir = os.path.join(run_dir, "c")
            self.assertTrue(os.path.isfile(os.path.join(case_dir, "scorecard.json")))
            r1 = os.path.join(case_dir, "run-1", "result.json")
            self.assertTrue(os.path.isfile(r1))
            self.assertTrue(os.path.isfile(os.path.join(case_dir, "run-2", "result.json")))
            import json

            def _read(path):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)

            keys = _read(r1).keys()
            for k in ("command", "returncode", "stderr", "debug_log"):
                self.assertIn(k, keys)   # debug capture persisted
            card = _read(os.path.join(case_dir, "scorecard.json"))
            self.assertEqual(card["harness"], "fake")
            self.assertEqual(len(card["executions"]), 2)



class TestDurationIsAveraged(unittest.TestCase):
    """Runs execute concurrently, so a SUM of run durations describes no elapsed time.
    The scorecard reports the mean per run; per-run figures stay in `executions`."""

    @classmethod
    def setUpClass(cls):
        register_harness(FakeHarness("fake_dur"))

    def test_scorecard_duration_is_the_mean_not_the_sum(self):
        card = run_case(_case("fake_dur", runs=3), threshold=1.0)
        # FakeHarness reports 100 ms per run: mean 100, not 300.
        self.assertEqual(card.duration_ms, 100)
        self.assertEqual(len(card.executions), 3)
        self.assertEqual(sum(e["duration_ms"] for e in card.executions), 300)

    def test_no_runs_does_not_divide_by_zero(self):
        card = run_case(_case("fake_dur", runs=0), threshold=1.0)
        self.assertEqual(card.duration_ms, 0)

if __name__ == "__main__":
    unittest.main()
