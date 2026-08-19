import unittest

from engine import static


class TestStaticScorer(unittest.TestCase):
    def test_clean_plugin_scores_high(self):
        r = static.score_from_findings([], token_efficiency=1.0)
        self.assertEqual(r["design_score"], 1.0)
        self.assertEqual(r["flags"], 0)

    def test_findings_lower_score(self):
        clean = static.score_from_findings([], 1.0)["design_score"]
        dirty = static.score_from_findings(
            ["[PD1] SKILL.md over 500 lines", "[PD2] missing reference file"], 1.0
        )["design_score"]
        self.assertLess(dirty, clean)

    def test_id_maps_to_subcheck(self):
        r = static.score_from_findings(["[RH1] ships references/ nobody is told to read"], 1.0)
        self.assertLess(r["sub_scores"]["reference_hygiene"], 1.0)
        self.assertEqual(r["sub_scores"]["security"], 1.0)  # untouched

    def test_security_weighted_and_penalized(self):
        r = static.score_from_findings(["[SEC1] hardcoded secret"], 1.0)
        self.assertLess(r["sub_scores"]["security"], 1.0)
        self.assertEqual(r["flags"], 1)

    def test_untagged_findings_ignored(self):
        r = static.score_from_findings(["a plain note with no id"], 1.0)
        self.assertEqual(r["flags"], 0)
        self.assertEqual(r["design_score"], 1.0)

    def test_token_efficiency_flows_through(self):
        low = static.score_from_findings([], token_efficiency=0.0)
        high = static.score_from_findings([], token_efficiency=1.0)
        self.assertLess(low["design_score"], high["design_score"])
        self.assertEqual(low["sub_scores"]["token_efficiency"], 0.0)

    def test_repeating_one_check_is_one_problem(self):
        """Scored on distinct IDs. Counting occurrences made the score track plugin size:
        a 30-skill plugin floored at 0.16 while a 31-skill one scored far higher."""
        once = static.score_from_findings(["[PD1] x"], 1.0)
        fifty = static.score_from_findings(["[PD1] x"] * 50, 1.0)
        self.assertEqual(once["design_score"], fifty["design_score"])
        self.assertEqual(fifty["flags"], 1)
        self.assertEqual(fifty["occurrences"], 50)

    def test_distinct_checks_do_accumulate(self):
        one = static.score_from_findings(["[PD1] x"], 1.0)["design_score"]
        two = static.score_from_findings(["[PD1] x", "[PD2] y"], 1.0)["design_score"]
        self.assertLess(two, one)



class TestStaticGrader(unittest.TestCase):
    """`type: static` was described in the design doc but never registered, so a case
    using it scored "unknown grader type" instead of a design-quality gate."""

    def test_static_is_a_registered_grader_type(self):
        from engine import graders
        self.assertIn("static", graders._GRADERS)

    def _case(self, tmp):
        import os
        from engine.models import Case
        os.makedirs(os.path.join(tmp, "plug"), exist_ok=True)
        return Case(name="c", prompt="p", path=tmp, plugins=["plug"])

    def test_passes_when_design_score_meets_min(self):
        import tempfile
        from unittest import mock
        from engine import graders
        from engine.models import Grader, RunResult
        g = Grader("static", "design", params={"min_score": 0.5})
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("engine.static.analyze",
                            return_value={"design_score": 0.8, "sub_scores": {}}):
                out = graders.grade(g, RunResult(), {"case": self._case(tmp)})
        self.assertTrue(out.passed)
        self.assertIn("0.80", out.detail)

    def test_failure_names_the_weakest_subscores(self):
        import tempfile
        from unittest import mock
        from engine import graders
        from engine.models import Grader, RunResult
        g = Grader("static", "design", params={"min_score": 0.9})
        subs = {"security": 1.0, "progressive_disclosure": 0.0, "ecosystem_coherence": 0.25,
                "reference_hygiene": 0.5, "frontmatter_quality": 1.0}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("engine.static.analyze",
                            return_value={"design_score": 0.4, "sub_scores": subs}):
                out = graders.grade(g, RunResult(), {"case": self._case(tmp)})
        self.assertFalse(out.passed)
        self.assertIn("progressive_disclosure 0.00", out.detail)   # actionable, not just a number
        self.assertNotIn("security", out.detail)                   # only the worst three

    def test_needs_a_case_with_plugins(self):
        from engine import graders
        from engine.models import Grader, RunResult
        out = graders.grade(Grader("static", "design"), RunResult(), {})
        self.assertFalse(out.passed)
        self.assertIn("plugins", out.detail)


class TestStaticOnlyWritesReports(unittest.TestCase):
    """CI runs `--static-only --report static.md` then cats the file. `--report` was
    accepted and silently ignored in this mode, so the next step died on a missing file."""

    def _args(self, **kw):
        import argparse
        base = dict(report=None, json_path=None, html_path=None, comment_path=None)
        base.update(kw)
        return argparse.Namespace(**base)

    REPORT = {"plugins": [{"path": "plugins/x", "design_score": 0.68,
                           "sub_scores": {"security": 0.75, "reference_hygiene": 1.0}}], "ok": True}

    def test_report_flag_writes_markdown(self):
        import os
        import tempfile
        from engine import cli
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "static.md")
            cli._emit_static(self.REPORT, self._args(report=path))
            self.assertTrue(os.path.isfile(path), "--static-only --report must write the file CI cats")
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        self.assertIn("plugins/x", body)
        self.assertIn("0.68", body)

    def test_comment_flag_writes_the_pr_comment(self):
        import os
        import tempfile
        from engine import cli
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "comment.md")
            cli._emit_static(self.REPORT, self._args(comment_path=path))
            self.assertTrue(os.path.isfile(path), "--static-only --comment must write the file CI posts")
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        self.assertIn("plugins/x", body)
        self.assertIn("0.68", body)
        # The comment is a different shape from --report, not a copy of it.
        self.assertIn("| Plugin | design_score |", body)

    def test_json_and_html_flags_also_write(self):
        import json as _json
        import os
        import tempfile
        from engine import cli
        with tempfile.TemporaryDirectory() as tmp:
            j, h = os.path.join(tmp, "s.json"), os.path.join(tmp, "s.html")
            cli._emit_static(self.REPORT, self._args(json_path=j, html_path=h))
            with open(j, encoding="utf-8") as fh:
                self.assertEqual(_json.load(fh)["plugins"][0]["design_score"], 0.68)
            with open(h, encoding="utf-8") as fh:
                html = fh.read()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("http://", html)      # self-contained, no external assets

    def test_no_flags_still_just_prints(self):
        from engine import cli
        cli._emit_static(self.REPORT, self._args())   # must not raise

class TestInitSubstitutesPlugin(unittest.TestCase):
    """`init --plugin` was accepted and ignored, so every scaffolded case shipped the
    literal `<plugin>` placeholder and failed to load until hand-edited."""

    def _init(self, tmp, plugin):
        """Scaffold the way it is really used: cwd = repo root, root = `evals`,
        --plugin given repo-relative. A --plugin in a different tree than the case dir
        legitimately yields a long ../.. path; that is not the scenario under test."""
        import argparse
        import contextlib
        import os
        from engine import cli
        args = argparse.Namespace(root="evals", name="mycase", plugin=plugin, tag="t",
                                  prompt="q", force=True)
        with contextlib.chdir(tmp):
            self.assertEqual(cli._cmd_init(args), 0)
            with open(os.path.join("evals", "mycase", "case.yaml"), encoding="utf-8") as fh:
                return fh.read()

    def test_plugin_path_is_resolved_relative_to_the_case_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            body = self._init(tmp, "plugins/acme-analytics")
        self.assertIn('["../../plugins/acme-analytics"]', body)
        self.assertNotIn("<plugin>", body)

    def test_scaffolded_case_loads(self):
        import contextlib
        import os
        import tempfile
        from engine import loader
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "plugins", "demo"))
            self._init(tmp, "plugins/demo")
            with contextlib.chdir(tmp):
                cases, errors = loader.load_all("evals")
        self.assertEqual(errors, [], "a freshly scaffolded case must load")
        self.assertEqual(cases[0].plugins, ["../../plugins/demo"])

    def test_placeholder_kept_when_no_plugin_given(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            body = self._init(tmp, "<plugin>")
        self.assertIn("<plugin>", body)


if __name__ == "__main__":
    unittest.main()


class TestScoringVersion(unittest.TestCase):
    """A score is only comparable within a scoring version, so reports must carry it.

    The semantics moved several times before the first release — weights, what counts as a
    finding, occurrence vs distinct counting. Without a version on the output, a threshold
    pinned in someone's CI cannot be traced to the rules that produced it.
    """

    def test_run_reports_the_scoring_version(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            plug = os.path.join(tmp, "plugins", "demo")
            os.makedirs(os.path.join(plug, ".claude-plugin"))
            with open(os.path.join(plug, ".claude-plugin", "plugin.json"), "w") as fh:
                fh.write('{"name": "demo"}')
            rep = static.run(tmp)
        self.assertEqual(rep["scoringVersion"], static.SCORING_VERSION)

    def test_the_rendered_report_shows_it(self):
        from engine import cli
        rendered = cli.static_render({"scoringVersion": 7, "plugins": [], "ok": True})
        self.assertIn("scoring v7", rendered)

    def test_version_is_documented_in_the_changelog(self):
        import os
        # Walk up rather than counting dirnames — a miscount makes this skip silently,
        # which is the same as not having the test.
        cur = os.path.dirname(os.path.abspath(__file__))
        while cur != os.path.dirname(cur):
            path = os.path.join(cur, "CHANGELOG.md")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    self.assertIn(f"Scoring version **{static.SCORING_VERSION}**", fh.read())
                return
            cur = os.path.dirname(cur)
        self.skipTest("CHANGELOG.md not found (plugin installed without the repo)")
