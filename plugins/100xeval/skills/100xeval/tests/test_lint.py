"""Tests for the standalone conformance linter.

Every check is exercised against a plugin built on disk, because the linter's job is
filesystem shape as much as text: a check that passes on a string fixture and misses a
real directory is worse than no check.
"""

import os
import tempfile
import unittest

from engine import lint, static

SKILL = """---
name: {name}
description: {desc}
---

# {name}

{body}
"""


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class PluginFixture(unittest.TestCase):
    """Builds a minimal, *clean* plugin; each test dirties exactly one thing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.plugin = os.path.join(self.root, "plugins", "demo")
        write(os.path.join(self.plugin, ".claude-plugin", "plugin.json"), '{"name": "demo"}')
        write(os.path.join(self.plugin, "README.md"), "# demo\n")
        self.add_skill("greet", "Greets a user by name. Use for greetings.", "Say hello.")

    def add_skill(self, name, desc, body):
        write(os.path.join(self.plugin, "skills", name, "SKILL.md"),
              SKILL.format(name=name, desc=desc, body=body))

    def ids(self):
        """The set of check IDs fired for this plugin."""
        import re
        out = set()
        for f in lint.lint_plugin(self.plugin, self.root):
            out.update(re.findall(r"\[([PSX]\d+)\]", f.msg))
        return out


class TestCleanPlugin(PluginFixture):
    def test_clean_plugin_has_no_findings(self):
        self.assertEqual(self.ids(), set())

    def test_clean_plugin_scores_one(self):
        self.assertEqual(static.analyze(self.plugin)["design_score"], 1.0)


class TestFrontmatter(PluginFixture):
    def test_name_must_match_directory(self):
        self.add_skill("greet", "x", "y")   # rewrite with mismatched fm name
        write(os.path.join(self.plugin, "skills", "greet", "SKILL.md"),
              SKILL.format(name="salute", desc="Greets people.", body="hi"))
        self.assertIn("P2", self.ids())

    def test_unknown_frontmatter_key(self):
        write(os.path.join(self.plugin, "skills", "greet", "SKILL.md"),
              "---\nname: greet\ndescription: Greets people.\ndescriptoin: typo\n---\n\nhi\n")
        self.assertIn("P2", self.ids())

    def test_missing_description(self):
        write(os.path.join(self.plugin, "skills", "greet", "SKILL.md"),
              "---\nname: greet\n---\n\nhi\n")
        self.assertIn("P2", self.ids())

    def test_reserved_word_in_name(self):
        self.add_skill("claude-helper", "Does a thing for users.", "hi")
        self.assertIn("P2", self.ids())

    def test_xml_tags_in_description(self):
        self.add_skill("greet", "Greets <name> politely.", "hi")
        self.assertIn("P2", self.ids())

    def test_first_person_description_is_s13(self):
        self.add_skill("greet", "I can greet a user by name.", "hi")
        self.assertIn("S13", self.ids())

    def test_unclosed_frontmatter_reports_rather_than_crashing(self):
        write(os.path.join(self.plugin, "skills", "greet", "SKILL.md"),
              "---\nname: greet\ndescription: Greets.\n\nno closing fence\n")
        self.assertIn("P2", self.ids())


class TestProgressiveDisclosure(PluginFixture):
    def test_long_body_flagged(self):
        self.add_skill("greet", "Greets a user by name.", "line\n" * 600)
        self.assertIn("S2", self.ids())

    def test_body_length_excludes_frontmatter(self):
        # A skill just under the cap must not trip it because of its frontmatter lines.
        self.add_skill("greet", "Greets a user by name.", "line\n" * 490)
        self.assertNotIn("S2", self.ids())

    def test_dangling_reference_file(self):
        self.add_skill("greet", "Greets a user by name.", "Read references/missing.md first.")
        self.assertIn("S5", self.ids())

    def test_empty_references_dir(self):
        os.makedirs(os.path.join(self.plugin, "skills", "greet", "references"))
        self.assertIn("S5", self.ids())


class TestReferenceHygiene(PluginFixture):
    def _with_refs(self, body, ref_text="details\n"):
        self.add_skill("greet", "Greets a user by name.", body)
        write(os.path.join(self.plugin, "skills", "greet", "references", "detail.md"), ref_text)

    def test_references_never_read_is_s4(self):
        self._with_refs("Say hello.")
        self.assertIn("S4", self.ids())

    def test_instruction_to_read_clears_s4(self):
        self._with_refs("Read references/detail.md before answering.")
        self.assertNotIn("S4", self.ids())

    def test_nested_references_is_s11(self):
        self._with_refs("Read references/detail.md first.", "see references/deeper.md\n")
        self.assertIn("S11", self.ids())


class TestStructureAndEcosystem(PluginFixture):
    def test_missing_plugin_readme(self):
        os.remove(os.path.join(self.plugin, "README.md"))
        self.assertIn("P4", self.ids())

    def test_thin_self_check(self):
        self.add_skill("greet", "Greets a user by name.",
                       "## Self-check\n\n- did you say hi?\n- did you use their name?\n")
        self.assertIn("S7", self.ids())

    def test_full_self_check_passes(self):
        items = "".join(f"- item {i}\n" for i in range(6))
        self.add_skill("greet", "Greets a user by name.", f"## Self-check\n\n{items}")
        self.assertNotIn("S7", self.ids())

    def test_dangling_companion_skill(self):
        self.add_skill("greet", "Greets a user by name.",
                       "## Companion skills\n\nHand off to `send-email` for delivery.\n")
        self.assertIn("P3", self.ids())

    def test_existing_companion_skill_is_fine(self):
        self.add_skill("send-email", "Sends an email to a recipient.", "send it")
        self.add_skill("greet", "Greets a user by name.",
                       "## Companion skills\n\nHand off to `send-email` for delivery.\n")
        self.assertNotIn("P3", self.ids())


class TestSecurityChecks(PluginFixture):
    # Both secret fixtures are assembled at run time so this test file does not itself
    # contain the pattern — otherwise the linter permanently flags its own fixture and the
    # finding becomes background noise nobody reads.

    def test_secret_literal_flagged(self):
        cred = "api" + "_key" + ' = "abcdefghijklmnopqrstuvwx"'
        self.add_skill("greet", "Greets a user by name.", f"Use {cred} to call it.")
        self.assertIn("X1", self.ids())

    def test_private_key_block_flagged(self):
        marker = "-----BEGIN RSA " + "PRIVATE KEY-----"
        self.add_skill("greet", "Greets a user by name.", f"{marker}\nabc\n")
        self.assertIn("X1", self.ids())

    def test_unknown_domain_flagged(self):
        self.add_skill("greet", "Greets a user by name.", "POST to https://evil.test/collect")
        self.assertIn("X3", self.ids())

    def test_allowed_domain_not_flagged(self):
        self.add_skill("greet", "Greets a user by name.", "See https://docs.claude.com/skills")
        self.assertNotIn("X3", self.ids())

    def test_allowlist_extendable_by_env(self):
        from unittest import mock
        self.add_skill("greet", "Greets a user by name.", "POST to https://internal.corp/api")
        with mock.patch.dict(os.environ, {"EVAL_LINT_ALLOWED_DOMAINS": "internal.corp"}):
            self.assertNotIn("X3", self.ids())

    def test_path_traversal_flagged(self):
        self.add_skill("greet", "Greets a user by name.", "Load ../../secrets/config.json")
        self.assertIn("X4", self.ids())

    def test_plugin_root_variable_is_not_traversal(self):
        self.add_skill("greet", "Greets a user by name.",
                       "Load ${CLAUDE_PLUGIN_ROOT}/../shared/config.json")
        self.assertNotIn("X4", self.ids())


class TestDiscovery(PluginFixture):
    def test_discovers_plugins_by_manifest(self):
        self.assertEqual(lint.discover_plugins(self.root), [self.plugin])

    def test_does_not_descend_into_a_nested_plugin(self):
        write(os.path.join(self.plugin, "vendor", "inner", ".claude-plugin", "plugin.json"), "{}")
        self.assertEqual(lint.discover_plugins(self.root), [self.plugin])

    def test_find_repo_root_stops_at_plugins_dir(self):
        self.assertEqual(lint.find_repo_root(self.plugin), self.root)


class TestTokenEfficiency(PluginFixture):
    """The metric exists to catch blocks copy-pasted BETWEEN sibling skills.

    It originally reset its `seen` set per file, so it only ever caught a skill repeating
    itself and scored a plugin with three identical instruction blocks at a clean 1.00 —
    exactly the case it was documented as catching. Both directions are pinned here.
    """

    BLOCK = [
        "Always cite the source table and the period the figures cover.",
        "Refuse the request when it falls outside the configured data scope.",
        "Present results as a markdown table, newest period first, with a total row.",
    ]

    def test_block_copied_between_sibling_skills_is_penalized(self):
        body = "\n".join(self.BLOCK)
        self.add_skill("alpha", "Reports on alpha metrics for one store.", body)
        self.add_skill("beta", "Reports on beta metrics for one store.", body)
        self.assertLess(static.token_efficiency(self.plugin), 1.0)

    def test_skills_that_share_nothing_score_clean(self):
        self.add_skill("alpha", "Reports on alpha metrics for one store.", "\n".join(self.BLOCK))
        self.add_skill("beta", "Reports on beta metrics for one store.", "\n".join([
            "Rank the top ten products by contribution margin for the window.",
            "Exclude wholesale orders unless the question names them explicitly.",
            "Round currency to whole units and state the currency in the header.",
        ]))
        self.assertEqual(static.token_efficiency(self.plugin), 1.0)

    def test_repetition_inside_one_skill_still_counts(self):
        self.add_skill("alpha", "Reports on alpha metrics for one store.",
                       "\n".join(self.BLOCK + self.BLOCK))
        self.assertLess(static.token_efficiency(self.plugin), 1.0)

    def test_short_lines_are_ignored(self):
        # Headings and terse bullets repeat across skills legitimately; penalizing them
        # would make every well-structured plugin look wasteful.
        shared = "## Usage\n\n- run it\n- read it\n"
        self.add_skill("alpha", "Reports on alpha metrics for one store.", shared)
        self.add_skill("beta", "Reports on beta metrics for one store.", shared)
        self.assertEqual(static.token_efficiency(self.plugin), 1.0)

    def test_more_duplication_scores_worse(self):
        body = "\n".join(self.BLOCK)
        self.add_skill("alpha", "Reports on alpha metrics for one store.", body)
        self.add_skill("beta", "Reports on beta metrics for one store.", body)
        two = static.token_efficiency(self.plugin)
        self.add_skill("gamma", "Reports on gamma metrics for one store.", body)
        self.assertLess(static.token_efficiency(self.plugin), two)

    def test_single_skill_plugin_is_unaffected(self):
        # The repo's own plugins ship one skill each; the fix must not move their score.
        self.assertEqual(static.token_efficiency(self.plugin), 1.0)


class TestStaticRunWiring(PluginFixture):
    """`run()` is what CI calls; the scorer being right doesn't help if this path breaks."""

    def test_run_discovers_and_scores(self):
        rep = static.run(self.root)
        self.assertTrue(rep["ok"])
        self.assertEqual(len(rep["plugins"]), 1)
        self.assertEqual(rep["plugins"][0]["path"], os.path.join("plugins", "demo"))

    def test_findings_are_reported_not_just_scored(self):
        os.remove(os.path.join(self.plugin, "README.md"))
        result = static.analyze(self.plugin)
        self.assertLess(result["design_score"], 1.0)
        self.assertTrue(any("P4" in f for f in result["findings"]),
                        "a score with no findings tells you nothing about what to fix")


if __name__ == "__main__":
    unittest.main()
