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
        "description": None,
        "kit_version": "0.1.0",
        "marketplace": None,
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


if __name__ == "__main__":
    unittest.main()
