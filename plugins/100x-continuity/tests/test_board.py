"""The board a setup run is watched on.

Two things here are worth more than the rest: that the Operator's half of the board and
the checklist in their `CLAUDE.md` come from one list, and that the page and the script
still agree about the shape of `tasks.json`. Both are contracts split across two files,
and both fail silently — a board that renders with empty cards, or two lists of leftovers
that quietly stop matching.
"""

import argparse
import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import board as board_mod  # noqa: E402
import emit as emit_mod  # noqa: E402


def _args(**overrides):
    base = {
        "into": None,
        "name": "acme-handoff",
        "store": "folder",
        "root": "~/OneDrive - Acme/Continuity",
        "service_name": None,
        "server_route": "org",
        "server_location": None,
        "kit_source": "plugins/acme-handoff",
        "label": None,
        "subtitle": None,
        "restart": False,
        "force": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _service(**overrides):
    return _args(
        store="service",
        root=None,
        service_name="acme-store",
        server_location="../acme-store",
        **overrides,
    )


class PrefixTests(unittest.TestCase):
    def test_three_letters_of_the_name(self):
        self.assertEqual(board_mod.id_prefix("acme-handoff"), "ACM")
        self.assertEqual(board_mod.id_prefix("yoda-session-handoff"), "YOD")

    def test_a_name_with_too_few_letters_still_draws_a_board(self):
        self.assertEqual(board_mod.id_prefix("x-1"), "KIT")


class SeedTests(unittest.TestCase):
    def test_a_folder_board_carries_no_server_work(self):
        keys = {t["key"] for t in board_mod.seed(_args())["tasks"]}
        self.assertIn("share-the-folder", keys)
        self.assertNotIn("copy-store-service", keys)
        self.assertNotIn("register", keys)

    def test_a_service_board_names_the_registered_name(self):
        tasks = board_mod.seed(_service())["tasks"]
        register = next(t for t in tasks if t["key"] == "register")
        self.assertIn("acme-store", register["title"])
        self.assertNotIn("share-the-folder", {t["key"] for t in tasks})

    def test_the_operator_half_is_the_notes_checklist(self):
        """One list, so the board and their CLAUDE.md cannot come to disagree.

        Checked against the rendered checklist rather than against `operator_items`,
        which the board is built from: comparing a function to itself would pass
        whatever anybody did to it. This fails the moment a leftover is written out by
        hand here instead of coming from there.
        """
        for args in (_args(), _service()):
            with self.subTest(store=args.store):
                checklist = emit_mod.operator_todo(args, args.kit_source)
                mine = [
                    t for t in board_mod.seed(args)["tasks"] if t["assignee"] == "operator"
                ]
                self.assertTrue(mine)
                for task in mine:
                    self.assertIn(task["title"], checklist)

    def test_the_factory_s_own_steps_open_as_todo(self):
        """A sequence filed as blocked is not a plan anybody can read."""
        mine = [t for t in board_mod.seed(_service())["tasks"] if t["assignee"] == "claude"]
        self.assertTrue(mine)
        self.assertEqual({t["status"] for t in mine}, {"todo"})
        self.assertEqual([t["blockedBy"] for t in mine], [[] for _ in mine])

    def test_blockers_are_ids_that_exist_on_the_board(self):
        tasks = board_mod.seed(_service())["tasks"]
        ids = {t["id"] for t in tasks}
        blockers = {b for t in tasks for b in t["blockedBy"]}
        self.assertTrue(blockers)
        self.assertLessEqual(blockers, ids)


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _init(self, **overrides):
        return board_mod.cmd_init(_args(into=str(self.repo), **overrides))

    def _tasks(self):
        return json.loads((self.repo / "status" / "tasks.json").read_text(encoding="utf-8"))

    def test_it_writes_the_page_beside_the_data(self):
        self._init()
        page = self.repo / "status" / "board.html"
        self.assertEqual(page.read_bytes(), board_mod.BOARD_TEMPLATE.read_bytes())

    def test_a_second_run_is_refused_rather_than_wiping_the_first(self):
        self._init()
        board_mod.cmd_set(
            argparse.Namespace(
                into=str(self.repo), task="emit", status="done",
                proof=None, evidence=None, body=None,
            )
        )
        with self.assertRaises(board_mod.BoardError):
            self._init()
        self._init(restart=True)  # asked for, so allowed
        emitted = next(t for t in self._tasks()["tasks"] if t["key"] == "emit")
        self.assertEqual(emitted["status"], "todo")

    def test_somebody_else_s_status_directory_is_refused(self):
        (self.repo / "status").mkdir()
        (self.repo / "status" / "notes.md").write_text("ours", encoding="utf-8")
        with self.assertRaises(board_mod.BoardError):
            self._init()

    def test_a_task_is_addressed_by_key_or_by_the_id_on_its_card(self):
        self._init()
        data = board_mod.load(self.repo)
        by_key = board_mod.find(data, "round-trip")
        self.assertIs(board_mod.find(data, by_key["id"].lower()), by_key)
        with self.assertRaises(board_mod.BoardError):
            board_mod.find(data, "no-such-task")

    def test_evidence_carrying_a_credential_is_redacted_and_reported(self):
        """The board is written into a repo other people clone."""
        self._init()
        leak = "=".join(["AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI" + "K7MDENGbPxRfiCYEXAMPLEKEY"])
        result = board_mod.cmd_set(
            argparse.Namespace(
                into=str(self.repo), task="emit", status="done",
                proof="proven", evidence=leak, body=None,
            )
        )
        self.assertTrue(result["redacted"])
        written = next(t for t in self._tasks()["tasks"] if t["key"] == "emit")
        self.assertNotIn("wJalrXUtnFEMI", written["evidence"])
        self.assertIn("[redacted:", written["evidence"])

    def test_finishing_a_blocker_releases_what_waited_on_it(self):
        board_mod.cmd_init(_service(into=str(self.repo)))
        waiting = next(t for t in self._tasks()["tasks"] if t["key"] == "tell-the-team")
        self.assertEqual(waiting["status"], "blocked")
        board_mod.cmd_set(
            argparse.Namespace(
                into=str(self.repo), task="release", status="done",
                proof=None, evidence=None, body=None,
            )
        )
        waiting = next(t for t in self._tasks()["tasks"] if t["key"] == "tell-the-team")
        self.assertEqual(waiting["status"], "todo")

    def test_a_task_somebody_parked_stays_parked(self):
        """`needsyou` is a decision waiting on a person, not a blocker to clear."""
        self._init()
        board_mod.cmd_set(
            argparse.Namespace(
                into=str(self.repo), task="teammate-pick-up", status="needsyou",
                proof=None, evidence=None, body=None,
            )
        )
        data = board_mod.load(self.repo)
        board_mod.relieve(data)
        parked = next(t for t in data["tasks"] if t["key"] == "teammate-pick-up")
        self.assertEqual(parked["status"], "needsyou")

    def test_what_a_run_turns_up_gets_the_next_id(self):
        self._init()
        added = board_mod.cmd_add(
            argparse.Namespace(
                into=str(self.repo), title="Delete the test object?", body=None,
                key="cleanup", labels="store,cleanup", assignee="operator",
                priority="medium", status="needsyou", blocked_by=["release"],
            )
        )["task"]
        ids = [t["id"] for t in self._tasks()["tasks"]]
        self.assertEqual(ids[-1], added["id"])
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(added["blockedBy"], [board_mod.find(board_mod.load(self.repo), "release")["id"]])

    def test_show_names_every_task_once(self):
        self._init()
        data = board_mod.load(self.repo)
        text = board_mod.render(data)
        for task in data["tasks"]:
            self.assertEqual(text.count(task["id"] + " "), 1, task["id"])


class PageContractTests(unittest.TestCase):
    """`board.html` and `board.py` are one contract split across two files."""

    def setUp(self):
        self.page = board_mod.BOARD_TEMPLATE.read_text(encoding="utf-8")

    def test_the_page_reads_no_field_the_script_never_writes(self):
        data = board_mod.seed(_service())
        fields = {key for task in data["tasks"] for key in task}
        # Set later, by `set`, on tasks that have something to show for themselves.
        fields |= {"proof", "evidence"}
        reads = set(re.findall(r"\bt\.([a-zA-Z]+)", self.page))
        self.assertTrue(reads)
        self.assertEqual(sorted(reads - fields), [])

    def test_the_page_draws_every_column_the_script_can_set(self):
        for status in board_mod.STATUSES:
            self.assertIn(f"{status}:{{", self.page.replace(" ", ""))

    def test_every_assignee_has_a_colour_and_a_filter(self):
        """An avatar with no rule behind it renders as an unlabelled white circle."""
        for who in board_mod.ASSIGNEES:
            self.assertIn(f".who.{who}{{", self.page)
            self.assertIn(f'data-who="{who}"', self.page)

    def test_the_template_names_no_project_and_fetches_nothing(self):
        """It is copied into somebody else's repo and opened from their disk."""
        self.assertNotIn("https://", self.page.split("<script>")[0])
        self.assertIn('const SRC = "./tasks.json"', self.page)


class KitTests(unittest.TestCase):
    def test_no_board_is_ever_copied_into_a_kit(self):
        """It is the Operator's record of one run. Teammates install the Kit."""
        for store in ("folder", "service"):
            for route in emit_mod.SERVER_ROUTES:
                files = emit_mod._plan_files(store, route)
                self.assertEqual([r for _, r in files if "board" in r or "status" in r], [])


if __name__ == "__main__":
    unittest.main()
