"""Cases run in parallel under ONE shared run budget (`--concurrency`).

Two contracts are pinned here:

1. `--concurrency` caps the plugin runs in flight across the WHOLE suite, not per case.
   That is the resource that actually binds (one `claude -p` subprocess per run, each
   hitting the API and the plugin's MCP), so overlapping cases must not multiply peak load.
2. The report stays deterministic: cards come back in case order however the runs
   interleave — otherwise the same suite would produce a differently-ordered scorecard
   on every invocation.
"""

import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from engine import cli
from engine.harnesses.base import register_harness
from engine.models import Case, Grader, RunResult


class ConcurrencyProbe:
    """Harness that records the peak number of overlapping `run` calls."""

    name = "fake_probe"

    def __init__(self, name="fake_probe", hold_s=0.05):
        self.name = name
        self._hold_s = hold_s
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        self.started = []

    def supports(self, grader_type):
        return True

    def preflight(self, case):
        pass

    def run(self, case, model, workspace=None):
        with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self.started.append(case.name)
        try:
            time.sleep(self._hold_s)
            return RunResult(final_text="Source: X", tool_calls=[], cost_usd=0.0, duration_ms=1)
        finally:
            with self._lock:
                self.in_flight -= 1


def _case(name, harness, runs=3):
    return Case(name=name, prompt="p", harness=harness, runs=runs,
                graders=[Grader("regex", "cite", params={"pattern": "Source:"})])


class TestSharedRunBudget(unittest.TestCase):
    def test_semaphore_caps_runs_across_concurrent_cases(self):
        probe = ConcurrencyProbe("fake_budget")
        register_harness(probe)
        slots = threading.BoundedSemaphore(2)

        # Three cases × 3 runs = 9 runs, all racing for 2 slots.
        cases = [_case(f"c{i}", "fake_budget") for i in range(3)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(
                lambda c: cli.run_case(c, threshold=1.0, concurrency=4, run_slots=slots),
                cases,
            ))

        self.assertEqual(probe.peak, 2, f"peak {probe.peak} exceeded the 2-slot budget")
        self.assertEqual(len(probe.started), 9)

    def test_without_a_semaphore_runs_are_unbounded_by_this_mechanism(self):
        # Backwards compatibility: run_slots=None must not throw (nullcontext path).
        probe = ConcurrencyProbe("fake_nobudget")
        register_harness(probe)
        card = cli.run_case(_case("solo", "fake_nobudget", runs=2), threshold=1.0)
        self.assertTrue(card.passed)
        self.assertEqual(len(probe.started), 2)


CASE_YAML = """
name: {name}
tags: [par]
runs: 2
execution:
  prompt: "q"
  harness: {harness}
graders:
  - {{type: regex, name: cite, pattern: "Source:"}}
"""


class TestCliRunsCasesInParallel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.probe = ConcurrencyProbe("fake_cli", hold_s=0.1)
        register_harness(self.probe)
        # Written out of alphabetical order to prove ordering comes from the load order,
        # not from whichever case finishes first.
        for name in ("aaa", "bbb", "ccc"):
            d = os.path.join(self.root, name)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "case.yaml"), "w", encoding="utf-8") as fh:
                fh.write(CASE_YAML.format(name=name, harness="fake_cli"))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *extra):
        # Artifacts default to `.runs/` at the invocation cwd, so the test names its own
        # location rather than depending on where it happens to be run from.
        runs = os.path.join(self.root, "artifacts")
        rc = cli.main(["eval", "--cases-dir", self.root, "--runs-dir", runs,
                       "--skip-static", *extra])
        run_dirs = sorted(os.listdir(runs))
        with open(os.path.join(runs, run_dirs[-1], "report.json"), encoding="utf-8") as fh:
            return rc, json.load(fh)

    def test_cases_overlap_and_report_stays_in_case_order(self):
        rc, report = self._run("--concurrency", "4")
        self.assertEqual(rc, 0)
        self.assertEqual([c["name"] for c in report["cases"]], ["aaa", "bbb", "ccc"])
        # 3 cases × 2 runs under a 4-slot budget: more than one case must have overlapped,
        # and the budget must still have been respected.
        self.assertGreater(self.probe.peak, 2)
        self.assertLessEqual(self.probe.peak, 4)

    def test_concurrency_one_is_fully_sequential(self):
        rc, report = self._run("--concurrency", "1")
        self.assertEqual(rc, 0)
        self.assertEqual([c["name"] for c in report["cases"]], ["aaa", "bbb", "ccc"])
        self.assertEqual(self.probe.peak, 1)


if __name__ == "__main__":
    unittest.main()


class TestDefaultRunsDir(unittest.TestCase):
    """Artifacts default to `.runs/` at the cwd, not inside the cases directory.

    The old default wrote to `<cases-dir>/runs`, which put machine-specific transcripts
    inside a tracked tree and made staying out of git depend on every case root being
    separately ignored. One of those got committed before this changed.
    """

    def test_default_is_dot_runs_at_cwd(self):
        import contextlib
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = os.path.join(tmp, "cases", "c1")
            os.makedirs(case_dir)
            with open(os.path.join(case_dir, "case.yaml"), "w", encoding="utf-8") as fh:
                fh.write(CASE_YAML.format(name="c1", harness="fake_cli"))
            with contextlib.chdir(tmp):
                cli.main(["eval", "--cases-dir", "cases", "--skip-static"])
                self.assertTrue(os.path.isdir(".runs"), "expected .runs/ at the cwd")
                self.assertFalse(os.path.isdir(os.path.join("cases", "runs")),
                                 "must not write inside the cases directory")
