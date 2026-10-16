"""Exact derived-output contracts and build provenance; unified-run tests only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_cache import InputContractError, prepare_fingerprint, needs_prepare, mark_prepared
from build_provenance import capture, canonical_sha


class BuildInputContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "one"
        self.root = self.workspace / "ZenithTerminal" / "Launcher"
        self.mod = self.root / "mods" / "char-ruby"
        (self.mod / "gen").mkdir(parents=True)
        (self.root / "inspect").mkdir()
        (self.root / "inspect/game_build.txt").write_text("123", encoding="utf-8")
        (self.root / "compatibility-contracts.json").write_text("{}", encoding="utf-8")
        for name in ("dependencies.lock.json", "requirements.lock.txt", "requirements.typetree.lock.txt"):
            (self.workspace / name).write_text("fixture lock", encoding="utf-8")
        self.sources = {}
        for name in ("ruby_audio.py", "import_ruby.py", "build_ruby.py"):
            content = ("# reviewed fixture source " + name).encode()
            (self.mod / name).write_bytes(content)
            self.sources[name] = hashlib.sha256(content).hexdigest()
        (self.mod / "mod.json").write_text('{"id":"char-ruby","name":"Fixture","version":"1"}', encoding="utf-8")
        self.diagnostic = self.mod / "gen/audio_map.json"
        self.diagnostic.write_text('{"generated":"old","sheets":{"id":1}}', encoding="utf-8")
        self.real_input = self.mod / "gen/actions.json"
        self.real_input.write_text('[{"action":"fixture"}]', encoding="utf-8")
        self.contract = {"format": 1, "status": "reviewed", "build_id": "123", "mods": {"char-ruby": {
            "derived_outputs": [{"path": "gen/audio_map.json", "phase": "build-diagnostic"}],
            "bound_sources": dict(self.sources)}}}
        self.write_contract()

    def write_contract(self):
        (self.root / "build-input-contracts.json").write_text(json.dumps(self.contract), encoding="utf-8")

    def fingerprint(self):
        return prepare_fingerprint(str(self.mod), [], str(self.root))

    def provenance(self, root=None):
        root = self.root if root is None else root
        return capture(root, ["char-ruby"], {"char-ruby": {"_dir": str(root / "mods/char-ruby")}}, "123")

    def test_one_exact_diagnostic_can_change_without_changing_true_input_fingerprint(self):
        before = self.fingerprint()
        self.diagnostic.write_text('{"generated":"new","sheets":{"id":399,"acb":"derived.acb"},"cue_ids":{"x":2}}', encoding="utf-8")
        after = self.fingerprint()
        self.assertEqual(before, after)
        self.assertEqual(after["declared_derived_outputs"], ["gen/audio_map.json"])
        self.assertNotIn("mod/gen/audio_map.json", after["inputs"])
        self.assertIn("mod/gen/actions.json", after["inputs"])
        self.assertIn("contract/build-input-contracts.json", after["inputs"])

    def test_diagnostic_addition_and_deletion_are_both_derived(self):
        before = self.fingerprint()
        self.diagnostic.unlink()
        self.assertEqual(before, self.fingerprint())
        self.diagnostic.write_text("new derived report", encoding="utf-8")
        self.assertEqual(before, self.fingerprint())

    def test_other_generated_tree_and_asset_changes_are_detected(self):
        before = self.fingerprint()
        self.real_input.write_text('[{"action":"changed"}]', encoding="utf-8")
        self.assertNotEqual(before["sha256"], self.fingerprint()["sha256"])
        before = self.fingerprint()
        extra = self.mod / "gen/new_material.bin"
        extra.write_bytes(b"actual input")
        self.assertNotEqual(before["sha256"], self.fingerprint()["sha256"])
        extra.unlink()
        self.assertEqual(before["sha256"], self.fingerprint()["sha256"])

    def test_changed_producer_or_reader_rejects_old_contract_before_cache_can_hide_it(self):
        mark_prepared(str(self.mod), ["mods/char-ruby/build_ruby.py"], str(self.root))
        (self.mod / "ruby_audio.py").write_text("# now reads the diagnostic as an input", encoding="utf-8")
        with self.assertRaisesRegex(InputContractError, "producer/reader changed"):
            self.fingerprint()
        with self.assertRaises(InputContractError):
            needs_prepare(str(self.mod), ["mods/char-ruby/build_ruby.py"], str(self.root))

    def test_contract_must_match_review_status_and_build(self):
        for field, value in (("status", "suggested"), ("build_id", "next-build")):
            with self.subTest(field=field):
                original = deepcopy(self.contract)
                self.contract[field] = value
                self.write_contract()
                with self.assertRaises(InputContractError):
                    self.fingerprint()
                self.contract = original
        self.write_contract()

    def test_no_wildcard_or_directory_wide_exclusions(self):
        output = self.contract["mods"]["char-ruby"]["derived_outputs"][0]
        for invalid in ("gen/*", "../audio_map.json", "gen/**", "gen\\audio_map.json", "/gen/audio_map.json"):
            output["path"] = invalid
            self.write_contract()
            with self.assertRaises(InputContractError):
                self.fingerprint()

    def test_descriptor_and_true_material_changes_remain_build_inputs(self):
        before = self.provenance()
        (self.mod / "mod.json").write_text('{"id":"char-ruby","name":"Fixture","version":"2"}', encoding="utf-8")
        self.assertNotEqual(canonical_sha(before), canonical_sha(self.provenance()))
        before = self.provenance()
        self.real_input.write_text("changed material", encoding="utf-8")
        self.assertNotEqual(canonical_sha(before), canonical_sha(self.provenance()))

    def test_provenance_records_contract_and_individual_true_files(self):
        before = self.provenance()
        self.assertIn("build-input-contracts.json", before["common_sources"])
        self.assertEqual(before["mods"]["char-ruby"]["declared_derived_outputs"], ["gen/audio_map.json"])
        self.assertIn("mod/gen/actions.json", before["mods"]["char-ruby"]["input_files"])
        self.diagnostic.write_text("updated derived output", encoding="utf-8")
        self.assertEqual(before, self.provenance())

    def test_resolved_workspace_root_is_part_of_the_build_identity(self):
        first = self.provenance()
        other_workspace = Path(self.temp.name) / "two"
        shutil.copytree(self.workspace, other_workspace)
        other_root = other_workspace / "ZenithTerminal" / "Launcher"
        second = self.provenance(other_root)
        self.assertEqual(first["workspace_root"], str(self.root.resolve()))
        self.assertNotEqual(canonical_sha(first), canonical_sha(second))
        self.assertEqual({key: value for key, value in first.items() if key != "workspace_root"},
                         {key: value for key, value in second.items() if key != "workspace_root"})


if __name__ == "__main__":
    unittest.main()
