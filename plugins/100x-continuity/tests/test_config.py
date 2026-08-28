"""Configuration precedence, where the file lives, and what `setup` writes."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

from engine import config

STAMP = "2026-08-20T14:03:11Z"


class _EnvCase(unittest.TestCase):
    """Base that isolates the environment and gives each test a fresh home.

    A developer's own `CONTINUITY_*` exports would otherwise decide the outcome of
    every precedence test here. `patch.dict` restores them on the way out.
    """

    def setUp(self) -> None:
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.enterContext(unittest.mock.patch.dict(os.environ, {}, clear=False))
        for name in (
            config.STORE_KIND_ENV,
            config.STORE_ROOT_ENV,
            config.NAMESPACE_ENV,
            config.SERVICE_ENV,
            config.CONFIG_ENV,
        ):
            os.environ.pop(name, None)

    def write_config(self, values: object) -> pathlib.Path:
        path = self.home / config.CONFIG_PATHS[1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values), encoding="utf-8")
        return path


class DefaultsTests(_EnvCase):
    def test_a_bare_host_defaults_to_a_visible_folder(self) -> None:
        # Not a dot-directory: the folder store is meant to be opened, pointed at by
        # a sync client, and shared with whoever continues the work.
        root = config.default_root(base=self.home)
        self.assertEqual(root, str(self.home / config.DEFAULT_ROOT_NAME))

    def test_inside_cowork_the_default_lives_on_the_mount(self) -> None:
        # The sandbox home does not outlive the session, so a store written there
        # would be gone exactly when someone tried to continue from it.
        (self.home / config.MOUNT).mkdir(parents=True)
        self.assertEqual(
            config.default_root(base=self.home),
            str(self.home / config.MOUNT / config.DEFAULT_ROOT_NAME),
        )

    def test_the_config_file_follows_the_same_rule(self) -> None:
        self.assertEqual(
            config.default_config_path(base=self.home),
            self.home / config.CONFIG_PATHS[1],
        )
        (self.home / config.MOUNT).mkdir(parents=True)
        self.assertEqual(
            config.default_config_path(base=self.home),
            self.home / config.CONFIG_PATHS[0],
        )

    def test_the_mounted_config_is_searched_first(self) -> None:
        searched = config.config_paths(base=self.home)
        self.assertEqual(searched[0], self.home / config.CONFIG_PATHS[0])

    def test_defaults_when_nothing_is_configured(self) -> None:
        resolved = config.settings(base=self.home)
        self.assertEqual(resolved["store"], "folder")
        self.assertEqual(resolved["namespace"], "default")
        self.assertIsNone(resolved["config_path"])
        self.assertEqual(resolved["sources"]["root"], "default")


class PrecedenceTests(_EnvCase):
    def test_the_file_beats_the_default(self) -> None:
        self.write_config({"store": "folder", "root": "/tmp/from-file", "namespace": "reports"})
        resolved = config.settings(base=self.home)
        self.assertEqual(resolved["root"], "/tmp/from-file")
        self.assertEqual(resolved["namespace"], "reports")
        self.assertEqual(resolved["sources"]["root"], "config-file")

    def test_the_environment_beats_the_file(self) -> None:
        self.write_config({"root": "/tmp/from-file"})
        with unittest.mock.patch.dict(os.environ, {config.STORE_ROOT_ENV: "/tmp/from-env"}):
            resolved = config.settings(base=self.home)
        self.assertEqual(resolved["root"], "/tmp/from-env")
        self.assertEqual(resolved["sources"]["root"], "environment")

    def test_a_flag_beats_everything(self) -> None:
        self.write_config({"root": "/tmp/from-file"})
        with unittest.mock.patch.dict(os.environ, {config.STORE_ROOT_ENV: "/tmp/from-env"}):
            resolved = config.settings(root_flag="/tmp/from-flag", base=self.home)
        self.assertEqual(resolved["root"], "/tmp/from-flag")
        self.assertEqual(resolved["sources"]["root"], "flag")

    def test_an_explicit_config_path_is_searched_first(self) -> None:
        elsewhere = self.home / "somewhere" / "cont.json"
        elsewhere.parent.mkdir(parents=True)
        elsewhere.write_text(json.dumps({"namespace": "pinned"}), encoding="utf-8")
        with unittest.mock.patch.dict(os.environ, {config.CONFIG_ENV: str(elsewhere)}):
            resolved = config.settings(base=self.home)
        self.assertEqual(resolved["namespace"], "pinned")
        self.assertEqual(resolved["config_path"], str(elsewhere))


class BadFileTests(_EnvCase):
    def test_unparseable_config_raises_rather_than_falling_back(self) -> None:
        # It was written on purpose. Falling through to defaults would publish into
        # a store the user did not choose.
        path = self.home / config.CONFIG_PATHS[1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(config.ConfigError) as caught:
            config.settings(base=self.home)
        self.assertIn(str(path), str(caught.exception))

    def test_a_config_that_is_not_an_object_raises(self) -> None:
        self.write_config(["a", "list"])  # type: ignore[arg-type]
        with self.assertRaises(config.ConfigError):
            config.settings(base=self.home)

    def test_unknown_keys_are_reported_not_silently_dropped(self) -> None:
        self.write_config({"store": "folder", "bucket": "s3://nope"})
        resolved = config.settings(base=self.home)
        self.assertEqual(resolved["config_unknown_keys"], ["bucket"])


class StoreKindTests(unittest.TestCase):
    def test_the_two_kinds_pass(self) -> None:
        for kind in config.STORE_KINDS:
            self.assertEqual(config.check_store_kind(kind), kind)

    def test_s3_is_told_where_object_storage_actually_lives(self) -> None:
        # Someone will try it, and "unknown store" would read as a missing feature
        # rather than the wrong shape.
        with self.assertRaises(config.ConfigError) as caught:
            config.check_store_kind("s3")
        self.assertIn("service", str(caught.exception))

    def test_anything_else_names_the_two_that_exist(self) -> None:
        with self.assertRaises(config.ConfigError) as caught:
            config.check_store_kind("dropbox")
        self.assertIn("folder", str(caught.exception))


class WriteTests(_EnvCase):
    def test_a_folder_store_keeps_its_root(self) -> None:
        written = config.write(
            store="folder", root=str(self.home / "Shared"), namespace="reports",
            stamp=STAMP, base=self.home,
        )
        self.assertEqual(written["config"]["root"], str(self.home / "Shared"))
        self.assertEqual(json.loads(pathlib.Path(written["path"]).read_text())["namespace"], "reports")

    def test_a_service_store_is_given_no_root_at_all(self) -> None:
        # A plausible-looking directory in the file would have the next reader
        # believe publications are landing there.
        written = config.write(
            store="service", root=str(self.home / "Shared"), service_name="my-store",
            stamp=STAMP, base=self.home,
        )
        self.assertNotIn("root", written["config"])
        self.assertEqual(written["config"]["service_name"], "my-store")

    def test_it_is_written_whole_rather_than_merged(self) -> None:
        config.write(store="folder", root=str(self.home / "A"), stamp=STAMP, base=self.home)
        config.write(store="service", service_name="s", stamp=STAMP, base=self.home)
        stored = json.loads(config.default_config_path(base=self.home).read_text())
        self.assertEqual(stored["store"], "service")
        self.assertNotIn("root", stored)

    def test_no_temporary_file_is_left_beside_it(self) -> None:
        written = config.write(store="folder", stamp=STAMP, base=self.home)
        directory = pathlib.Path(written["path"]).parent
        self.assertEqual([p.name for p in directory.iterdir()], ["config.json"])

    def test_what_was_written_is_what_is_then_resolved(self) -> None:
        config.write(
            store="folder", root=str(self.home / "Shared"), namespace="reports",
            stamp=STAMP, base=self.home,
        )
        resolved = config.settings(base=self.home)
        self.assertEqual(resolved["root"], str(self.home / "Shared"))
        self.assertEqual(resolved["namespace"], "reports")

    def test_an_unusable_store_kind_is_refused_before_anything_is_written(self) -> None:
        with self.assertRaises(config.ConfigError):
            config.write(store="s3", stamp=STAMP, base=self.home)
        self.assertFalse(config.default_config_path(base=self.home).exists())


if __name__ == "__main__":
    unittest.main()


class KitTests(_EnvCase):
    """A Kit carries its own answers, because a Teammate has nowhere to put any."""

    def kit(self, values: object) -> pathlib.Path:
        root = self.home / "kit"
        root.mkdir(parents=True, exist_ok=True)
        (root / config.KIT_CONFIG_NAME).write_text(json.dumps(values), encoding="utf-8")
        return root

    def test_the_baked_answers_are_used(self) -> None:
        root = self.kit({"store": "folder", "root": "/mnt/Team/Continuity", "namespace": "acme"})
        resolved = config.settings(base=self.home, kit_root=root)
        self.assertEqual(resolved["root"], "/mnt/Team/Continuity")
        self.assertEqual(resolved["namespace"], "acme")
        self.assertEqual(resolved["sources"]["root"], "kit")

    def test_a_kit_beats_the_user_config_file(self) -> None:
        # The Operator's own machine may be configured for their own testing; a Kit
        # they installed must still publish where the Kit says.
        self.write_config({"root": "/tmp/operators-own", "namespace": "personal"})
        root = self.kit({"store": "folder", "root": "/mnt/Team/Continuity"})
        resolved = config.settings(base=self.home, kit_root=root)
        self.assertEqual(resolved["root"], "/mnt/Team/Continuity")

    def test_the_environment_still_wins_for_debugging(self) -> None:
        root = self.kit({"store": "folder", "root": "/mnt/Team/Continuity"})
        with unittest.mock.patch.dict(os.environ, {config.STORE_ROOT_ENV: "/tmp/debug"}):
            resolved = config.settings(base=self.home, kit_root=root)
        self.assertEqual(resolved["root"], "/tmp/debug")
        self.assertEqual(resolved["sources"]["root"], "environment")

    def test_provenance_travels_with_the_kit(self) -> None:
        # A Teammate reporting a problem names which Factory built their Kit without
        # having to know what a Factory is.
        root = self.kit(
            {"store": "folder", "kit_name": "acme-handoff", "factory_version": "0.2.0",
             "emitted_at": "2026-08-21T10:00:00Z"}
        )
        resolved = config.settings(base=self.home, kit_root=root)
        self.assertEqual(resolved["kit"]["name"], "acme-handoff")
        self.assertEqual(resolved["kit"]["factory_version"], "0.2.0")

    def test_not_being_a_kit_is_not_an_error(self) -> None:
        resolved = config.settings(base=self.home, kit_root=self.home / "nothing-here")
        self.assertIsNone(resolved["kit"]["path"])
        self.assertEqual(resolved["sources"]["root"], "default")

    def test_a_broken_kit_config_raises_rather_than_guessing(self) -> None:
        # It was written by the Factory. Falling back to defaults would publish a
        # Teammate's work somewhere nobody chose.
        root = self.home / "kit"
        root.mkdir(parents=True, exist_ok=True)
        (root / config.KIT_CONFIG_NAME).write_text("{not json", encoding="utf-8")
        with self.assertRaises(config.ConfigError) as caught:
            config.settings(base=self.home, kit_root=root)
        self.assertIn("emitted again", str(caught.exception))

    def test_the_engine_finds_its_own_plugin_root(self) -> None:
        # `<plugin>/scripts/engine/config.py` → `<plugin>`. Derived from the file's own
        # location because the variable that would name it is unreliable in Cowork.
        self.assertTrue((config.plugin_root() / "scripts" / "engine").is_dir())
