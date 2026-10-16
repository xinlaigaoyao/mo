"""Lock/cache/baseline regression tests use only isolated temporary folders."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_mods
from prepare_mods import PrepareError, prepare_profile
from prepare_cache import STATE_NAME


class PrepareProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("inspect", "decoded/tables", "decoded/data/js/core", "extracted_raw", "shared/sdk", "mods/generated"):
            (self.root / folder).mkdir(parents=True)
        for filename in ("bbmod.py", "make_patch.py", "bbchar.py", "validation_tables.py", "composer_core.py", "native_table_keys.py", "prepare_cache.py"):
            (self.root / filename).write_text("# common generator import\n", encoding="utf-8")
        self.table = self.root / "decoded/tables/Fixture.json"
        self.script = self.root / "decoded/data/js/core/Fixture.js"
        self.table.write_text('[{"Id":1,"Value":"baseline"}]', encoding="utf-8")
        self.script.write_text("exports.value='baseline';", encoding="utf-8")
        self.originals = [Path(str(self.table) + ".orig"), Path(str(self.script) + ".orig")]
        for path in self.originals:
            path.write_bytes(Path(str(path).removesuffix(".orig")).read_bytes())
        self.raw = self.root / "extracted_raw/fixture.bin"
        self.raw.write_bytes(b"immutable original binary")
        (self.root / "inspect/game_build.txt").write_text("123", encoding="utf-8")
        (self.root / "inspect/proto_schema.json").write_text("{}", encoding="utf-8")
        (self.root / "inspect/js_keys.json").write_text("{}", encoding="utf-8")
        (self.root / "inspect/decode_report.json").write_text('{"status":"passed","build_id":"123"}', encoding="utf-8")
        files = {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in [*self.originals, self.raw, self.root / "inspect/proto_schema.json", self.root / "inspect/js_keys.json"]}
        (self.root / "inspect/baseline_manifest.json").write_text(json.dumps({"format": 1, "build_id": "123", "files": files}), encoding="utf-8")
        (self.root / "shared/sdk/mod.json").write_text('{"id":"sdk","name":"SDK","version":"1"}', encoding="utf-8")
        self.add_generated("generated", ["sdk"])
        self.profile = {"enabled": ["generated"]}
        self.calls = []

    def add_generated(self, mid, dependencies=()):
        folder = self.root / "mods" / mid
        folder.mkdir(parents=True, exist_ok=True)
        terminal = {"id": mid, "name": mid, "version": "1", "dependencies": list(dependencies),
                    "prepare": [f"mods/{mid}/generate.py"], "gameBuilds": ["123"]}
        (folder / "terminal.json").write_text(json.dumps(terminal), encoding="utf-8")
        (folder / "generate.py").write_text("# synthetic generator\n", encoding="utf-8")
        return folder

    def runner(self, command, **kwargs):
        self.assertEqual(command[:4], [sys.executable, "-E", "-s", "-u"])
        self.assertEqual(kwargs, {"cwd": str(self.root), "check": False})
        self.assertIn("baseline", self.table.read_text(encoding="utf-8"))
        self.assertIn("baseline", self.script.read_text(encoding="utf-8"))
        self.calls.append(command[-1])
        folder = Path(command[-1]).parent
        terminal = json.loads((folder / "terminal.json").read_text(encoding="utf-8"))
        descriptor = {"id": folder.name, "name": folder.name, "version": "1", "dependencies": terminal["dependencies"]}
        (folder / "mod.json").write_text(json.dumps(descriptor), encoding="utf-8")
        return types.SimpleNamespace(returncode=0)

    def prepare(self, **kwargs):
        return prepare_profile(self.root, self.profile, "123", runner=kwargs.pop("runner", self.runner), **kwargs)

    def test_restore_before_generator_never_reads_previous_composed_current_data(self):
        original_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in [*self.originals, self.raw]]
        self.table.write_text('[{"Id":1,"Value":"modded"}]', encoding="utf-8")
        self.script.write_text("exports.value='modded';", encoding="utf-8")
        report = self.prepare()
        self.assertEqual(report["prepared"], ["generated"])
        self.assertEqual(len(report["restored_current_files"]), 2)
        self.assertEqual(original_hashes, [hashlib.sha256(path.read_bytes()).hexdigest() for path in [*self.originals, self.raw]])
        self.assertTrue((self.root / "mods/generated" / STATE_NAME).exists())

    def test_cache_hit_does_not_rewrite_current_or_immutable_baseline(self):
        self.prepare()
        before = {path: path.stat().st_mtime_ns for path in [self.table, self.script, *self.originals, self.raw]}
        self.calls.clear()
        report = self.prepare()
        self.assertEqual(report["prepared"], [])
        self.assertEqual(report["cached"], ["generated"])
        self.assertEqual(report["restored_current_files"], [])
        self.assertFalse(self.calls)
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in before})

    def test_failure_never_marks_generation(self):
        with self.assertRaisesRegex(PrepareError, "exit code 7"):
            self.prepare(runner=lambda *args, **kwargs: types.SimpleNamespace(returncode=7))
        self.assertFalse((self.root / "mods/generated" / STATE_NAME).exists())

    def test_later_failure_does_not_mark_earlier_successful_dependency(self):
        dependency = self.add_generated("dependency", ["sdk"])
        terminal = self.root / "mods/generated/terminal.json"
        data = json.loads(terminal.read_text(encoding="utf-8"))
        data["dependencies"] = ["dependency"]
        terminal.write_text(json.dumps(data), encoding="utf-8")
        def fail_last(command, **kwargs):
            if Path(command[-1]).parent.name == "generated":
                return 4
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(PrepareError, "exit code 4"):
            self.prepare(runner=fail_last)
        self.assertFalse((dependency / STATE_NAME).exists())
        self.assertFalse((self.root / "mods/generated" / STATE_NAME).exists())

    def test_terminal_only_dependency_is_prepared_first_and_mod_dependencies_are_unified(self):
        self.add_generated("dependency", ["sdk"])
        terminal = self.root / "mods/generated/terminal.json"
        data = json.loads(terminal.read_text(encoding="utf-8"))
        data["dependencies"] = ["dependency"]
        terminal.write_text(json.dumps(data), encoding="utf-8")
        (self.root / "mods/generated/mod.json").write_text('{"id":"generated","name":"g","version":"1","dependencies":["sdk"]}', encoding="utf-8")
        report = self.prepare()
        self.assertEqual(report["order"], ["sdk", "dependency", "generated"])
        self.assertEqual([Path(path).parent.name for path in self.calls], ["dependency", "generated"])

    def test_changed_shared_import_forces_regeneration(self):
        self.prepare()
        for filename in ("bbchar.py", "native_table_keys.py"):
            with self.subTest(source=filename):
                self.calls.clear()
                (self.root / filename).write_text("# changed shared import\n", encoding="utf-8")
                self.assertEqual(self.prepare()["prepared"], ["generated"])
                self.assertEqual(len(self.calls), 1)

    def test_changed_nested_source_with_same_mtime_forces_regeneration(self):
        nested = self.root / "mods/generated/nested"
        nested.mkdir()
        source = nested / "logic.py"
        source.write_text("# old", encoding="utf-8")
        self.prepare()
        before = source.stat()
        source.write_text("# new", encoding="utf-8")
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.prepare()["prepared"], ["generated"])

    def test_changed_generated_dependency_forces_cached_dependent_regeneration(self):
        self.add_generated("dependency", ["sdk"])
        terminal = self.root / "mods/generated/terminal.json"
        data = json.loads(terminal.read_text(encoding="utf-8"))
        data["dependencies"] = ["dependency"]
        terminal.write_text(json.dumps(data), encoding="utf-8")
        self.prepare()
        self.calls.clear()
        (self.root / "mods/dependency/generate.py").write_text("# changed dependency", encoding="utf-8")
        report = self.prepare()
        self.assertEqual(report["prepared"], ["dependency", "generated"])

    def test_missing_dependency_fails_before_current_baseline_rewrite(self):
        self.table.write_text("modded", encoding="utf-8")
        self.profile["enabled"] = ["missing"]
        with self.assertRaisesRegex(PrepareError, "missing mod or terminal"):
            self.prepare()
        self.assertEqual(self.table.read_text(encoding="utf-8"), "modded")
        self.assertFalse(self.calls)

    def test_mutated_immutable_baseline_fails_before_generator(self):
        self.originals[0].write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "baseline changed"):
            self.prepare()
        self.assertFalse(self.calls)

    def test_generator_mutating_raw_is_not_marked(self):
        def corrupt(command, **kwargs):
            result = self.runner(command, **kwargs)
            self.raw.write_bytes(b"corrupted")
            return result
        with self.assertRaisesRegex(Exception, "baseline changed"):
            self.prepare(runner=corrupt)
        self.assertFalse((self.root / "mods/generated" / STATE_NAME).exists())

    def test_unverified_extra_current_input_rejected(self):
        (self.root / "decoded/tables/Unverified.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(PrepareError, "no verified immutable baseline"):
            self.prepare()
        self.assertFalse(self.calls)

    def test_real_temporary_child_process_reads_restored_baseline(self):
        generated = self.root / "mods/generated/generate.py"
        generated.write_text(
            "import json\nfrom pathlib import Path\n"
            "root=Path.cwd()\n"
            "assert 'baseline' in (root/'decoded/tables/Fixture.json').read_text()\n"
            "assert 'baseline' in (root/'decoded/data/js/core/Fixture.js').read_text()\n"
            "target=Path(__file__).parent/'mod.json'\n"
            "target.write_text(json.dumps({'id':'generated','name':'Generated','version':'1','dependencies':['sdk']}))\n"
            "print('Temporary generator read pristine current input',flush=True)\n", encoding="utf-8")
        self.table.write_text("modded", encoding="utf-8")
        self.script.write_text("modded", encoding="utf-8")
        report = prepare_profile(self.root, self.profile, "123")
        self.assertEqual(report["prepared"], ["generated"])
        self.assertTrue((generated.parent / STATE_NAME).exists())

    def test_dependency_cycle_fails_before_generation(self):
        self.add_generated("dependency", ["generated"])
        terminal = self.root / "mods/generated/terminal.json"
        data = json.loads(terminal.read_text(encoding="utf-8"))
        data["dependencies"] = ["dependency"]
        terminal.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(PrepareError, "dependency cycle"):
            self.prepare()
        self.assertFalse(self.calls)

    def test_dirty_dependency_propagates_through_mod_without_prepare(self):
        self.add_generated("dependency", ["sdk"])
        bridge = self.root / "mods/bridge"
        bridge.mkdir()
        (bridge / "mod.json").write_text('{"id":"bridge","name":"Bridge","version":"1","dependencies":["dependency"]}', encoding="utf-8")
        terminal = self.root / "mods/generated/terminal.json"
        data = json.loads(terminal.read_text(encoding="utf-8"))
        data["dependencies"] = ["bridge"]
        terminal.write_text(json.dumps(data), encoding="utf-8")
        self.prepare()
        (self.root / "mods/dependency/generate.py").write_text("# changed", encoding="utf-8")
        self.assertEqual(self.prepare()["prepared"], ["dependency", "generated"])

    def test_cli_calls_prepare_inside_the_loaders_prepare_lock(self):
        events = []
        def locked(function, name):
            self.assertEqual(name, "prepare")
            events.append("acquired")
            try:
                return function()
            finally:
                events.append("released")
        def prepare(*args, **kwargs):
            self.assertEqual(events, ["acquired"])
            return {"status": "passed"}
        loader = types.SimpleNamespace(ROOT=str(self.root), STAGING=False, locked=locked,
            load_profile=lambda: self.profile, game_build=lambda: "123")
        with patch.dict(sys.modules, {"bbmod": loader}), patch.object(prepare_mods, "prepare_profile", prepare):
            self.assertEqual(prepare_mods.main([]), 0)
        self.assertEqual(events, ["acquired", "released"])


if __name__ == "__main__":
    unittest.main()
