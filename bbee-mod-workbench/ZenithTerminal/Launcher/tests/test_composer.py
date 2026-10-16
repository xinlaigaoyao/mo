"""Regression tests use synthetic data; never import the game's loader entry point."""
import copy
import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from composer_core import ComposeError, compose_table, apply_js_replacements, depends_on
from prepare_cache import needs_prepare, mark_prepared
import prepare_cache


class TableTests(unittest.TestCase):
    def compose(self, base, changes, keys=("Id",), mods=None):
        report = []
        result = compose_table("Fixture", base, keys, changes, mods or {"a": {}, "b": {}, "c": {}}, report)
        return result, report

    def test_baseline_not_mutated(self):
        base = [{"Id": 1, "Values": [1]}]
        original = copy.deepcopy(base)
        changed, report = self.compose(base, [("a", [{"Id": 1, "Values": [2]}])])
        self.assertEqual(base, original)
        self.assertEqual(changed[0]["Values"], [2])
        self.assertFalse(report)

    def test_skilldamage_ambiguous_key_is_not_last_row_wins(self):
        base = [{"ActorId": 1, "HitTimes": 1, "Action": action, "Damage": 10} for action in ("a", "b")]
        with self.assertRaisesRegex(ComposeError, "ambiguous"):
            self.compose(base, [("a", [{"ActorId": 1, "HitTimes": 1, "Damage": 12}])], ("ActorId", "HitTimes"))
        result, report = self.compose(base, [("a", [{"ActorId": 1, "HitTimes": 1,
                                                   "$match": {"Action": "a"}, "Damage": 12}])], ("ActorId", "HitTimes"))
        self.assertEqual([r["Damage"] for r in result], [12, 10])
        self.assertFalse(report)

    def test_append_updates_index_and_owns_inserted_fields(self):
        result, report = self.compose([], [("a", [{"$append": True, "Id": 3, "Value": 1}, {"Id": 3, "Value": 2}]),
                                          ("b", [{"Id": 3, "Value": 4}])])
        self.assertEqual(result, [{"Id": 3, "Value": 2}])
        self.assertEqual(len(report), 1)
        self.assertIn("a vs b", report[0])

    def test_append_preserves_published_multirow_semantics(self):
        result, report = self.compose([], [("a", [{"$append": True, "ActorId": 1, "HitTimes": 1, "Action": action}
                                                  for action in ("a", "b")])], ("ActorId", "HitTimes"))
        self.assertEqual([r["Action"] for r in result], ["a", "b"])
        self.assertFalse(report)
        with self.assertRaisesRegex(ComposeError, "ambiguous"):
            self.compose(result, [("a", [{"ActorId": 1, "HitTimes": 1, "Damage": 2}])], ("ActorId", "HitTimes"))

    def test_new_duplicate_rejected_after_append(self):
        with self.assertRaisesRegex(ComposeError, "duplicate key"):
            self.compose([], [("a", [{"$append": True, "Id": 3}, {"$new": True, "Id": 3}])])

    def test_copy_rows_requires_actual_source(self):
        with self.assertRaisesRegex(ComposeError, "found no rows"):
            self.compose([{ "Id": 1}], [("a", [{"$copyRows": {"where": {"Id": 2}, "set": {"Id": 3}}}])])

    def test_copy_rows_tracks_owned_result(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"$copyRows": {"where": {"Id": 1}, "set": {"Id": 2}}}]),
            ("b", [{"Id": 2, "Value": 3}])])
        self.assertEqual(result[1]["Value"], 1)
        self.assertEqual(len(report), 1)

    def test_copy_rows_duplicate_requires_explicit_permission(self):
        base = [{"Id": 1, "Action": "a"}, {"Id": 1, "Action": "b"}]
        spec = {"where": {"Id": 1}, "set": {"Id": 2}}
        with self.assertRaisesRegex(ComposeError, "duplicate key"):
            self.compose(base, [("a", [{"$copyRows": spec}])])
        spec["allowDuplicateKeys"] = True
        result, report = self.compose(base, [("a", [{"$copyRows": spec}])])
        self.assertEqual(len(result), 4)
        self.assertFalse(report)

    def test_copy_setwhere_and_idoffset(self):
        result, report = self.compose([{ "Id": 1, "Value": "old"}], [("a", [{"$copyRows": {
            "where": {"Id": 1}, "setWhere": [{"match": {"Value": "old"}, "set": {"Value": "new"}}],
            "idOffset": 10}}])])
        self.assertEqual(result[1], {"Id": 11, "Value": "new"})
        self.assertFalse(report)

    def test_replace_conflicts_with_any_prior_field(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"Id": 1, "Value": 2}]), ("b", [{"$replace": True, "Id": 1, "Value": 3}])])
        self.assertEqual(result[0]["Value"], 2)
        self.assertEqual(len(report), 1)

    def test_replace_owns_whole_row_and_new_fields(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"$replace": True, "Id": 1, "Value": 2}]), ("b", [{"Id": 1, "Other": 3}])])
        self.assertNotIn("Other", result[0])
        self.assertEqual(len(report), 1)

    def test_replace_reindexes_changed_key_using_match(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [("a", [
            {"$replace": True, "$match": {"Id": 1}, "Id": 2, "Value": 2}, {"Id": 2, "Value": 3}])])
        self.assertEqual(result, [{"Id": 2, "Value": 3}])
        self.assertFalse(report)

    def test_delete_conflicts_with_prior_write(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"Id": 1, "Value": 2}]), ("b", [{"$delete": True, "Id": 1}])])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(report), 1)

    def test_key_changing_replace_reserves_removed_key_against_independent_recreation(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"$replace": True, "$match": {"Id": 1}, "Id": 2, "Value": 2}]),
            ("b", [{"$new": True, "Id": 1, "Value": 3}])])
        self.assertEqual(result, [{"Id": 2, "Value": 2}])
        self.assertEqual(len(report), 1)

    def test_delete_then_recreate_by_independent_author_is_conflict(self):
        result, report = self.compose([{ "Id": 1, "Value": 1}], [
            ("a", [{"$delete": True, "Id": 1}]), ("b", [{"$new": True, "Id": 1, "Value": 2}])])
        self.assertEqual(result, [])
        self.assertEqual(len(report), 1)

    def test_dependencies_allow_insert_replace_delete_and_transitive_edit(self):
        mods = {"a": {}, "b": {"dependencies": ["a"]}, "c": {"dependencies": ["b"]}}
        result, report = self.compose([], [("a", [{"$new": True, "Id": 1, "Value": 1}]),
                                          ("b", [{"$replace": True, "Id": 1, "Value": 2}]),
                                          ("c", [{"$delete": True, "Id": 1}])], mods=mods)
        self.assertEqual(result, [])
        self.assertFalse(report)
        self.assertTrue(depends_on(mods, "c", "a"))

    def test_idempotent_writer_cannot_launder_original_owner(self):
        mods = {"a": {}, "b": {}, "c": {"dependencies": ["b"]}}
        result, report = self.compose([{ "Id": 1, "Value": 0}], [
            ("a", [{"Id": 1, "Value": 1}]), ("b", [{"Id": 1, "Value": 1}]),
            ("c", [{"Id": 1, "Value": 2}])], mods=mods)
        self.assertEqual(result[0]["Value"], 1)
        self.assertEqual(len(report), 1)

    def test_independent_disjoint_fields_are_allowed(self):
        result, report = self.compose([{ "Id": 1, "A": 0, "B": 0}], [
            ("a", [{"Id": 1, "A": 1}]), ("b", [{"Id": 1, "B": 1}])])
        self.assertEqual(result, [{"Id": 1, "A": 1, "B": 1}])
        self.assertFalse(report)


class JsTests(unittest.TestCase):
    def replace(self, source, entries, options=None):
        report = []
        result = apply_js_replacements(source, entries, "a", "fixture", report, {}, {}, r"E:\work", options)
        return result, report

    def test_unique_anchor_replaces_and_expands_root(self):
        result, report = self.replace("anchor", [["anchor", "@ROOT@/file"]])
        self.assertEqual(result, "E:/work/file")
        self.assertFalse(report)

    def test_missing_anchor_is_error_even_when_multiple_allowed(self):
        result, report = self.replace("data", [["anchor", "x"]], {"allowMultiple": True})
        self.assertEqual(result, "data")
        self.assertIn("matched 0", report[0])

    def test_implicit_multi_match_is_error_without_editing(self):
        result, report = self.replace("a a", [["a", "b"]])
        self.assertEqual(result, "a a")
        self.assertIn("matched 2, expected 1", report[0])

    def test_explicit_expected_count_accepted_and_drift_rejected(self):
        result, report = self.replace("a a", [{"old": "a", "new": "b", "expectedCount": 2}])
        self.assertEqual(result, "b b")
        self.assertFalse(report)
        result, report = self.replace("a a a", [["a", "b", {"expectedCount": 2}]])
        self.assertEqual(result, "a a a")
        self.assertTrue(report)

    def test_script_level_allow_multiple_and_count_map(self):
        for options in ({"allowMultiple": True}, {"expectedCount": {"a": 2}}):
            result, report = self.replace("a a", [["a", "b"]], options)
            self.assertEqual(result, "b b")
            self.assertFalse(report)

    def test_empty_anchor_rejected(self):
        with self.assertRaisesRegex(ComposeError, "nonempty"):
            self.replace("a", [["", "b"]])


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / "mod"
        (self.mod / "nested").mkdir(parents=True)
        (self.mod / "build.py").write_text("pass", encoding="utf-8")
        (self.mod / "mod.json").write_text("{}", encoding="utf-8")
        self.asset = self.mod / "nested" / "asset.png"
        self.asset.write_bytes(b"asset")
        self.build = self.root / "game_build.txt"
        self.build.write_text("123", encoding="utf-8")

    def check(self, first=False):
        return needs_prepare(str(self.mod), ["mod/build.py"], str(self.root), [str(self.build)], first)

    def mark(self):
        return mark_prepared(str(self.mod), ["mod/build.py"], str(self.root), [str(self.build)])

    def test_absent_cache_rebuilds_once_then_is_stable(self):
        self.assertTrue(self.check())
        self.mark()
        self.assertFalse(self.check())
        self.assertTrue(self.check(first=True))

    def test_nested_change_with_unchanged_mtime_rebuilds(self):
        self.mark()
        before = self.asset.stat()
        self.asset.write_bytes(b"other")
        os.utime(self.asset, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertTrue(self.check())

    def test_nested_addition_and_deletion_rebuilds(self):
        self.mark()
        extra = self.mod / "nested" / "new.txt"
        extra.write_text("new", encoding="utf-8")
        self.assertTrue(self.check())
        self.mark()
        extra.unlink()
        self.assertTrue(self.check())

    def test_changed_game_baseline_rebuilds(self):
        self.mark()
        self.build.write_text("124", encoding="utf-8")
        self.assertTrue(self.check())

    def test_generated_descriptor_and_python_cache_do_not_loop(self):
        self.mark()
        (self.mod / "mod.json").write_text('{"changed":true}', encoding="utf-8")
        cache = self.mod / "nested" / "__pycache__"
        cache.mkdir()
        (cache / "ignored.pyc").write_bytes(b"compiled")
        self.assertFalse(self.check())

    def test_missing_descriptor_never_marked_successful(self):
        (self.mod / "mod.json").unlink()
        with self.assertRaisesRegex(ValueError, "without creating"):
            self.mark()
        self.assertTrue(self.check())


class PrepareQueueTests(unittest.TestCase):
    """Execute the actual GUI queue methods without requiring a Qt installation."""
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / "Gui" / "zenith_gui" / "controller.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        controller = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Controller")
        selected = [node for node in controller.body if isinstance(node, ast.FunctionDef)
                    and node.name in {"_install_job", "_needs_prepare", "_prepare_dependencies", "_next", "_ended"}]
        class Signal:
            def connect(self, callback):
                self.callback = callback
            def emit(self):
                pass
        class Process:
            ProcessChannelMode = type("Channel", (), {"MergedChannels": 1})
            ProcessError = type("Error", (), {"FailedToStart": 1})
            def __init__(self, parent):
                self.readyReadStandardOutput, self.finished, self.errorOccurred = Signal(), Signal(), Signal()
            def setProcessEnvironment(self, value):
                self.environment = value
            def setWorkingDirectory(self, value):
                self.directory = value
            def setProcessChannelMode(self, value):
                pass
            def start(self, executable, args):
                self.started = (executable, args)
        class Environment:
            @staticmethod
            def systemEnvironment():
                return Environment()
            def insert(self, name, value):
                pass
        cls.Signal = Signal
        namespace = {"REBUILD_STEPS": [], "REBUILD_MARKS": [], "INSTALL_STEPS": [],
                     "INSTALL_MARKS": [], "PREPARE_STEP": "prepare", "QProcess": Process,
                     "QProcessEnvironment": Environment, "os": os}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
        cls.methods = {node.name: namespace[node.name] for node in selected}

    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        folder = root / "mod"
        folder.mkdir()
        (folder / "build.py").write_text("pass", encoding="utf-8")
        (folder / "mod.json").write_text("{}", encoding="utf-8")
        mod = {"title": "Fixture", "folder": str(folder), "prepare": ["mod/build.py"]}
        cls = type("QueueFixture", (), self.methods)
        obj = cls()
        obj.launcher = str(root)
        obj._state = "changes"
        obj._work = lambda *parts: str(root.joinpath(*parts))
        obj._wanted = lambda: [mod]
        obj._run = lambda title, steps, marks, queue, done, after: setattr(obj, "_queue", queue)
        obj._finish = lambda ok, message: setattr(obj, "finished", (ok, message))
        obj._done_text = "done"
        obj._running = True
        obj.profile_root = None
        obj._prep_step = obj._step = 0
        obj.busyChanged = self.Signal()
        obj._python = lambda: sys.executable
        obj._line = lambda line: None
        return obj, folder

    def test_profile_prepare_cli_precedes_install_without_gui_cache_mark(self):
        obj, folder = self.fixture()
        obj._install_job("title", "done")
        self.assertEqual([item[0] for item in obj._queue], ["@prepare", "install"])
        self.assertFalse((folder / prepare_cache.STATE_NAME).exists())
        obj._next()
        self.assertEqual(obj._proc.started, (sys.executable, ["-E", "-s", "-u", os.path.join(obj.launcher, "prepare_mods.py")]))
        self.assertFalse((folder / prepare_cache.STATE_NAME).exists())
        self.assertEqual(obj._queue, [["install"]])

    def test_setup_precedes_one_profile_prepare_even_without_visible_generators(self):
        obj, folder = self.fixture()
        obj._state = "setup"
        obj._wanted = lambda: []
        obj._install_job("title", "done")
        self.assertEqual([item[0] for item in obj._queue], ["setup", "@prepare", "install"])

    def test_failed_prepare_discards_mark_and_install(self):
        obj, folder = self.fixture()
        obj._install_job("title", "done")
        obj._queue.pop(0)  # this script is the active failed process
        obj._problem = ["prepare failed"]
        obj._log = []
        obj._ended(1, None)
        self.assertEqual(obj._queue, [])
        self.assertFalse(obj.finished[0])
        self.assertFalse((folder / prepare_cache.STATE_NAME).exists())


if __name__ == "__main__":
    unittest.main()
