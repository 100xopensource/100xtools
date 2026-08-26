"""Emitting a Kit — the one thing here that writes into somebody else's repository."""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import emit as emit_mod  # noqa: E402


def _args(**overrides):
    base = {
        "into": None,
        "name": "acme-handoff",
        "team": "the Acme analytics team",
        "org": "Acme",
        "store": "folder",
        "root": "~/OneDrive - Acme/Continuity",
        "namespace": "analytics",
        "service_name": None,
        "server_route": "org",
        "server_url": None,
        "server_location": None,
        "description": None,
        "kit_version": "0.1.0",
        "marketplace": None,
        "repo": None,
        "force": False,
        "dry_run": False,
    }
    base.update(overrides)
    import argparse

    return argparse.Namespace(**base)


class EmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _emit(self, **overrides):
        into = overrides.pop("into", self.root / "plugins" / "acme-handoff")
        return emit_mod.emit(_args(into=str(into), **overrides)), pathlib.Path(into)

    def test_writes_a_complete_kit(self):
        result, kit = self._emit()
        self.assertTrue(result["ok"])
        for rel in (
            ".claude-plugin/plugin.json",
            "kit.json",
            "README.md",
            "scripts/run.py",
            "scripts/engine/cli.py",
            "skills/hand-off/SKILL.md",
            "skills/pick-up/SKILL.md",
        ):
            self.assertTrue((kit / rel).is_file(), rel)

    def test_no_placeholder_survives(self):
        """An unfilled placeholder still loads and still instructs the model."""
        for store, extra in (("folder", {}), ("service", {"service_name": "continuity-store"})):
            with self.subTest(store=store):
                target = self.root / store / "kit"
                self._emit(into=target, store=store, root=None if store == "service" else "~/x", **extra)
                for path in target.rglob("*"):
                    if path.is_file() and path.suffix in {".md", ".json"}:
                        self.assertNotIn("{{", path.read_text(encoding="utf-8"), str(path))

    def test_fragments_are_rendered_not_just_spliced(self):
        """Substitution is one pass, so a value carried in by a fragment must be filled here."""
        _, kit = self._emit(store="service", root=None, service_name="continuity-store")
        body = (kit / "skills" / "hand-off" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("continuity-store", body)
        self.assertNotIn("{{SERVICE_NAME}}", body)

    def test_a_kit_describes_only_its_own_store(self):
        _, folder = self._emit()
        _, service = self._emit(
            into=self.root / "svc", store="service", root=None, service_name="continuity-store"
        )
        folder_body = (folder / "skills" / "pick-up" / "SKILL.md").read_text(encoding="utf-8")
        service_body = (service / "skills" / "pick-up" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("mint", folder_body)
        self.assertIn("resolve_publication", service_body)
        self.assertNotIn("resolve_publication", folder_body)

    def test_kit_config_carries_the_baked_store(self):
        result, kit = self._emit()
        stored = json.loads((kit / "kit.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, result["kit_config"])
        self.assertEqual(stored["store"], "folder")
        self.assertEqual(stored["namespace"], "analytics")
        # Unexpanded on purpose: a teammate's home is not the operator's.
        self.assertTrue(stored["root"].startswith("~"))

    def test_folder_kit_needs_a_root(self):
        with self.assertRaises(emit_mod.EmitError) as caught:
            self._emit(root=None)
        self.assertIn("--root", str(caught.exception))

    def test_service_kit_needs_a_registered_name(self):
        with self.assertRaises(emit_mod.EmitError) as caught:
            self._emit(store="service", root=None)
        self.assertIn("--service-name", str(caught.exception))

    def test_refuses_to_write_inside_the_factory(self):
        with self.assertRaises(emit_mod.EmitError) as caught:
            self._emit(into=emit_mod.FACTORY_ROOT / "plugins" / "oops")
        self.assertIn("inside the factory", str(caught.exception))

    def test_refuses_a_foreign_directory(self):
        target = self.root / "someone-elses-plugin"
        target.mkdir(parents=True)
        (target / "README.md").write_text("not ours", encoding="utf-8")
        with self.assertRaises(emit_mod.EmitError):
            self._emit(into=target)
        self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "not ours")

    def test_force_overrides_a_foreign_directory(self):
        target = self.root / "someone-elses-plugin"
        target.mkdir(parents=True)
        (target / "README.md").write_text("not ours", encoding="utf-8")
        result, _ = self._emit(into=target, force=True)
        self.assertTrue(result["ok"])

    def test_re_emitting_reports_the_update(self):
        _, kit = self._emit()
        result, _ = self._emit(into=kit, team="a renamed team")
        self.assertTrue(result["updated"])
        self.assertIn("README.md", result["overwrote"])

    def test_dry_run_writes_nothing(self):
        target = self.root / "plugins" / "acme-handoff"
        result, _ = self._emit(into=target, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(target.exists())
        self.assertTrue(result["files"])

    def test_only_a_kit_carrying_its_own_server_gets_an_mcp_json(self):
        """Two declarations of one server, and the placeholder one is what answers."""
        _, org = self._emit(
            into=self.root / "org", store="service", root=None, service_name="acme-store"
        )
        _, carried = self._emit(
            into=self.root / "carried",
            store="service",
            root=None,
            service_name="acme-store",
            server_route="mcp-json",
        )
        self.assertFalse((org / ".mcp.json").exists())
        declared = json.loads((carried / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(list(declared["mcpServers"]), ["acme-store"])
        # RFC 2606 reserves example.com, so an unfinished Kit points at nobody's host.
        self.assertIn("example.com", declared["mcpServers"]["acme-store"]["url"])

    def test_a_known_server_url_replaces_the_placeholder(self):
        _, kit = self._emit(
            store="service",
            root=None,
            service_name="acme-store",
            server_route="mcp-json",
            server_url="https://store.acme.example.net/mcp",
        )
        declared = json.loads((kit / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(
            declared["mcpServers"]["acme-store"]["url"], "https://store.acme.example.net/mcp"
        )

    def test_tool_names_are_hinted_per_route(self):
        """An org connector arrives slugified and infixed; a carried one does not."""
        self.assertEqual(
            emit_mod.tool_prefix("service", "org", "acme store"), "mcp__claude_ai_acme_store__"
        )
        self.assertEqual(emit_mod.tool_prefix("service", "mcp-json", "acme-store"), "mcp__acme-store__")
        self.assertEqual(emit_mod.tool_prefix("folder", "org", None), "")

    def test_the_skills_match_on_how_a_tool_name_ends(self):
        """The full spelling is a hint; a Kit that matched it exactly would miss."""
        _, kit = self._emit(store="service", root=None, service_name="acme-store")
        body = (kit / "skills" / "hand-off" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("__mint_publication_upload", body)
        self.assertIn("mcp__claude_ai_acme_store__", body)

    def test_a_kit_only_carries_the_eval_cases_it_can_run(self):
        """A folder Kit scoring an unreachable-server case would be scoring nothing."""
        case = "hand-off-stops-when-the-store-is-unreachable"
        _, folder = self._emit()
        _, service = self._emit(
            into=self.root / "svc", store="service", root=None, service_name="acme-store"
        )
        self.assertFalse((folder / "evals" / case / "case.yaml").exists())
        self.assertTrue((service / "evals" / case / "case.yaml").is_file())
        listed = (folder / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(case, listed)
        self.assertIn(case, (service / "evals" / "README.md").read_text(encoding="utf-8"))

    def test_the_readme_draws_this_kit_s_store_and_no_other(self):
        """A diagram of a server this team never ran is a diagram of somebody else's system."""
        _, folder = self._emit()
        _, service = self._emit(
            into=self.root / "svc", store="service", root=None, service_name="acme-store"
        )
        drawn = (folder / "README.md").read_text(encoding="utf-8")
        self.assertIn("```mermaid", drawn)
        self.assertIn("the cloud drive moves it", drawn)
        self.assertNotIn("acme-store", drawn)
        drawn = (service / "README.md").read_text(encoding="utf-8")
        self.assertIn("```mermaid", drawn)
        self.assertIn("acme-store", drawn)
        self.assertNotIn("cloud drive", drawn)
        # Raw newlines inside a quoted mermaid label do not parse; `<br/>` does.
        for kit in (folder, service):
            body = (kit / "README.md").read_text(encoding="utf-8")
            block = body.split("```mermaid", 1)[1].split("```", 1)[0]
            for line in block.splitlines():
                self.assertEqual(line.count('"') % 2, 0, line)

    def test_the_eval_command_carries_what_it_needs_to_run(self):
        """A documented command that fails on the first try reads as a broken plugin."""
        _, folder = self._emit()
        _, service = self._emit(
            into=self.root / "svc", store="service", root=None, service_name="acme-store"
        )
        listed = (folder / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("CLAUDE_CODE_WALNUT_SPIRE=1", listed)
        self.assertIn("CLAUDE_CODE_ENTRYPOINT=remote_cowork", listed)
        # Bash and Write are gated. Without the grant the skills are refused the tool they
        # need to reach their own engine, and the cases pass having tested nothing.
        self.assertIn("--allow-tools Bash Write", listed)
        self.assertNotIn("mcp__", listed)
        listed = (service / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("CLAUDE_CODE_WALNUT_SPIRE=1", listed)
        self.assertIn("--allow-tools Bash Write 'mcp__*'", listed)

    def test_the_engine_is_findable_without_anything_set(self):
        """Two of the three rungs need an env var. The third is derived from the file."""
        _, kit = self._emit()
        for name in ("hand-off", "pick-up"):
            body = (kit / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            # A suffix strip rather than `../..`: no relative traversal for a reader
            # (or a linter) to squint at, and it does not care how deep the skill sits.
            self.assertIn('${SKILL_BASE_DIR%/skills/*}/scripts/run.py', body, name)
            # One ordered list, not three near-identical guards for a model to skim.
            self.assertIn("for candidate in", body, name)

    def test_kit_config_says_nothing_about_the_operators_machine(self):
        """kit.json ships to every Teammate; where the Operator keeps the server is theirs."""
        result, _ = self._emit(
            store="service",
            root=None,
            service_name="acme-store",
            server_location="~/infra/acme-store",
            server_url="https://store.acme.example.net/mcp",
        )
        self.assertEqual(
            set(result["kit_config"]),
            {"store", "root", "namespace", "service_name", "kit_name", "factory_version",
             "emitted_at"},
        )
        self.assertNotIn("acme-store/mcp", json.dumps(result["kit_config"]))

    def test_render_refuses_a_missing_value(self):
        with self.assertRaises(emit_mod.EmitError) as caught:
            emit_mod.render("hello {{NOBODY}}", {"TEAM": "x"})
        self.assertIn("NOBODY", str(caught.exception))


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "acme-plugins"
        (self.repo / ".claude-plugin").mkdir(parents=True)
        self.manifest = self.repo / ".claude-plugin" / "marketplace.json"
        self.manifest.write_text(
            json.dumps({"name": "acme", "plugins": [{"name": "other", "source": "./plugins/other"}]}),
            encoding="utf-8",
        )
        self.addCleanup(self.tmp.cleanup)

    def _emit(self, **overrides):
        into = self.repo / "plugins" / "acme-handoff"
        return emit_mod.emit(_args(into=str(into), marketplace=str(self.manifest), **overrides))

    def test_source_is_relative_to_the_repo_root(self):
        result = self._emit()
        self.assertEqual(result["marketplace_entry"]["source"], "./plugins/acme-handoff")

    def test_other_rows_are_left_alone(self):
        self._emit()
        rows = json.loads(self.manifest.read_text(encoding="utf-8"))["plugins"]
        self.assertEqual(rows[0], {"name": "other", "source": "./plugins/other"})
        self.assertEqual(len(rows), 2)

    def test_re_emitting_updates_the_row_in_place(self):
        self._emit()
        self._emit(description="a new line")
        rows = json.loads(self.manifest.read_text(encoding="utf-8"))["plugins"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["description"], "a new line")

    def test_a_kit_outside_the_repo_is_refused(self):
        outside = pathlib.Path(self.tmp.name) / "elsewhere" / "kit"
        with self.assertRaises(emit_mod.EmitError) as caught:
            emit_mod.emit(_args(into=str(outside), marketplace=str(self.manifest)))
        self.assertIn("outside", str(caught.exception))

    def test_unparseable_manifest_is_left_untouched(self):
        self.manifest.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(emit_mod.EmitError):
            self._emit()
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), "{ not json")



class BoardNoteTests(unittest.TestCase):
    """The notes may only send a reader to a board the run actually left."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_repo_with_no_board_is_told_nothing_about_one(self):
        self.assertEqual(emit_mod.board_note(self.repo), "")
        self.assertEqual(emit_mod.board_note(None), "")

    def test_a_repo_with_a_board_is_pointed_at_it(self):
        (self.repo / "status").mkdir()
        (self.repo / "status" / "tasks.json").write_text("{}", encoding="utf-8")
        self.assertIn("board.html", emit_mod.board_note(self.repo))

    def test_the_notes_carry_it_only_when_it_exists(self):
        market = self.repo / ".claude-plugin" / "marketplace.json"
        market.parent.mkdir(parents=True)
        market.write_text(
            json.dumps({"name": "p", "owner": {"name": "Acme"}, "plugins": []}),
            encoding="utf-8",
        )
        args = _args(
            into=str(self.repo / "plugins" / "acme-handoff"), marketplace=str(market)
        )
        emit_mod.emit(args)
        self.assertNotIn("board.html", (self.repo / "CLAUDE.md").read_text(encoding="utf-8"))

        (self.repo / "status").mkdir()
        (self.repo / "status" / "tasks.json").write_text("{}", encoding="utf-8")
        emit_mod.emit(args)
        self.assertIn("board.html", (self.repo / "CLAUDE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class OperatorNotesTests(unittest.TestCase):
    """The Factory runs once, so what is left over has to outlive the conversation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "acme-plugins"
        (self.repo / ".claude-plugin").mkdir(parents=True)
        self.manifest = self.repo / ".claude-plugin" / "marketplace.json"
        self.manifest.write_text(json.dumps({"name": "acme", "plugins": []}), encoding="utf-8")
        self.notes = self.repo / "CLAUDE.md"
        self.addCleanup(self.tmp.cleanup)

    def _emit(self, **overrides):
        into = self.repo / "plugins" / "acme-handoff"
        return emit_mod.emit(_args(into=str(into), marketplace=str(self.manifest), **overrides))

    def test_written_where_the_next_person_will_read_them(self):
        result = self._emit()
        self.assertEqual(result["operator_notes"]["action"], "created")
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn("acme-handoff", body)
        # Created about the handoff plugin, not titled as if it described the whole repo.
        self.assertTrue(body.startswith("# CLAUDE.md"), body[:40])
        self.assertNotIn("# acme-plugins", body)
        begin, end = emit_mod.notes_markers("acme-handoff")
        self.assertIn(begin, body)
        self.assertIn(end, body)

    def test_somebody_elses_guidance_is_kept(self):
        self.notes.write_text("# acme-plugins\n\nOur own rules.\n", encoding="utf-8")
        result = self._emit()
        self.assertEqual(result["operator_notes"]["action"], "appended")
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn("Our own rules.", body)
        self.assertIn(emit_mod.notes_markers("acme-handoff")[0], body)

    def test_re_emitting_rewrites_only_its_own_section(self):
        self.notes.write_text("# acme-plugins\n\nOur own rules.\n", encoding="utf-8")
        self._emit()
        self.notes.write_text(
            self.notes.read_text(encoding="utf-8") + "\nA later note of ours.\n", encoding="utf-8"
        )
        result = self._emit(team="a renamed team")
        self.assertEqual(result["operator_notes"]["action"], "updated")
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn("Our own rules.", body)
        self.assertIn("A later note of ours.", body)
        self.assertIn("a renamed team", body)
        self.assertEqual(body.count(emit_mod.notes_markers("acme-handoff")[0]), 1)

    def test_a_second_kit_does_not_eat_the_first_ones_notes(self):
        """One repository can ship two Kits, and each owns its own section."""
        self._emit()
        emit_mod.emit(
            _args(
                into=str(self.repo / "plugins" / "acme-support"),
                name="acme-support",
                marketplace=str(self.manifest),
            )
        )
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn(emit_mod.notes_markers("acme-handoff")[0], body)
        self.assertIn(emit_mod.notes_markers("acme-support")[0], body)

    def test_a_folder_kit_is_told_to_share_the_folder(self):
        self._emit()
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn("~/OneDrive - Acme/Continuity", body)
        self.assertIn("Release it", body)

    def test_a_service_kit_is_told_to_register_the_planned_name(self):
        self._emit(store="service", root=None, service_name="acme-store")
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn("acme-store", body)
        self.assertIn("connectors", body)

    def test_a_carried_server_is_told_to_replace_the_placeholder(self):
        self._emit(
            store="service", root=None, service_name="acme-store", server_route="mcp-json"
        )
        body = self.notes.read_text(encoding="utf-8")
        self.assertIn(emit_mod.PLACEHOLDER_SERVER_URL, body)
        self.assertIn("./plugins/acme-handoff/.mcp.json", body)

    def test_dry_run_leaves_the_file_alone(self):
        result = self._emit(dry_run=True)
        self.assertEqual(result["operator_notes"]["action"], "skipped-dry-run")
        self.assertFalse(self.notes.exists())

    def test_no_repo_root_means_no_notes_rather_than_a_guess(self):
        into = pathlib.Path(self.tmp.name) / "loose" / "kit"
        result = emit_mod.emit(_args(into=str(into)))
        self.assertEqual(result["operator_notes"]["action"], "skipped")
