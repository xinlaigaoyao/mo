"""Exact hash/replacement/count contracts; no default blanket multi-match allowance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from js_contracts import bind_spec
from composer_core import apply_js_replacements

LAUNCHER = Path(__file__).resolve().parents[1]
PRODUCTION = json.loads((LAUNCHER / "compatibility-contracts.json").read_text(encoding="utf-8"))


class ExactContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fixture(self, position):
        contract = deepcopy(PRODUCTION["contracts"][position])
        baseline = ("/* fixture module */\n" + (contract["anchor"] + ";\n") * contract["expectedCount"]).encode()
        contract["baseline_module_sha256"] = hashlib.sha256(baseline).hexdigest()
        data = {"format": 1, "status": "reviewed", "build_id": "25627491", "contracts": [contract]}
        spec = {"file": contract["file"], "replace": [[contract["anchor"], contract["replacement"]]]}
        return contract, data, spec, baseline

    def apply(self, contract, data, spec, baseline, *, mod=None, logical=None, build="25627491"):
        (self.root / "compatibility-contracts.json").write_text(json.dumps(data), encoding="utf-8")
        bound = bind_spec(spec, mod or contract["mod"], logical or contract["file"], self.root, build, baseline)
        diagnostics = []
        changed = apply_js_replacements(baseline.decode(), bound["replace"], contract["mod"], contract["file"],
            diagnostics, {}, {}, str(self.root), bound)
        return bound, changed, diagnostics

    def check_approved(self, module, expected_count):
        position = next(index for index, item in enumerate(PRODUCTION["contracts"]) if item["file"] == module)
        contract, data, spec, baseline = self.fixture(position)
        original = deepcopy(spec)
        self.assertEqual(contract["expectedCount"], expected_count)
        bound, changed, diagnostics = self.apply(contract, data, spec, baseline)
        self.assertEqual(bound["replace"][0]["expectedCount"], expected_count)
        self.assertFalse(diagnostics)
        self.assertEqual(changed.count(contract["replacement"]), expected_count)
        self.assertEqual(spec, original)  # binding cannot mutate the source descriptor

    def test_potential_util_hash_bound_exact_three(self):
        self.check_approved("data/js/core/PotentialUtil", 3)

    def test_scene_hero_select_hash_bound_exact_two(self):
        self.check_approved("data/js/gameplay/battlebreedprepare/SceneUIHeroSelect", 2)

    def test_battle_prepare_util_hash_bound_exact_two(self):
        self.check_approved("data/js/gameplay/battlebreedprepare/BattlePrepareUtil", 2)

    def test_resource_converter_hash_bound_exact_two(self):
        self.check_approved("data/js/server/views/ResConverter", 2)

    def assert_unapproved(self, mutate=None, **overrides):
        for position in range(4):
            with self.subTest(contract=position):
                contract, data, spec, baseline = self.fixture(position)
                if mutate:
                    mutate(contract, data, spec)
                bound, changed, diagnostics = self.apply(contract, data, spec, baseline, **overrides)
                self.assertIsInstance(bound["replace"][0], list)
                self.assertEqual(changed, baseline.decode())
                self.assertTrue(diagnostics)

    def test_wrong_baseline_sha_never_grants_multiple_matches(self):
        self.assert_unapproved(lambda contract, data, spec: contract.update(baseline_module_sha256="0" * 64))

    def test_wrong_anchor_sha_never_grants_multiple_matches(self):
        self.assert_unapproved(lambda contract, data, spec: contract.update(anchor_sha256="0" * 64))

    def test_literal_anchor_is_checked_as_well_as_sha(self):
        self.assert_unapproved(lambda contract, data, spec: contract.update(anchor=contract["anchor"] + " "))

    def test_changed_replacement_cannot_reuse_approved_count(self):
        self.assert_unapproved(lambda contract, data, spec: spec["replace"][0].__setitem__(1, "unreviewedReplacement()"))

    def test_unreviewed_status_is_not_applied(self):
        self.assert_unapproved(lambda contract, data, spec: data.update(status="suggested-not-applied"))

    def test_different_build_mod_or_module_is_not_applied(self):
        self.assert_unapproved(build="next-build")
        self.assert_unapproved(mod="other-mod")
        self.assert_unapproved(logical="data/js/OtherModule")

    def test_count_mismatch_fails_even_when_hashes_and_replacement_match(self):
        for position in range(4):
            contract, data, spec, baseline = self.fixture(position)
            contract["expectedCount"] += 1
            bound, changed, diagnostics = self.apply(contract, data, spec, baseline)
            self.assertIsInstance(bound["replace"][0], dict)
            self.assertEqual(changed, baseline.decode())
            self.assertIn("expected", diagnostics[0])

    def test_changed_actual_module_bytes_disable_contract_before_count_check(self):
        for position in range(4):
            contract, data, spec, baseline = self.fixture(position)
            baseline += (contract["anchor"] + ";\n").encode()
            bound, changed, diagnostics = self.apply(contract, data, spec, baseline)
            self.assertIsInstance(bound["replace"][0], list)
            self.assertEqual(changed, baseline.decode())
            self.assertTrue(diagnostics)

    def test_four_production_contracts_match_immutable_baseline(self):
        paths = [LAUNCHER / "decoded" / (item["file"] + ".js.orig") for item in PRODUCTION["contracts"]]
        if not all(path.is_file() for path in paths):
            self.skipTest("requires a successfully decoded local baseline; synthetic guard tests remain runnable")
        self.assertEqual(PRODUCTION["status"], "reviewed")
        self.assertEqual(PRODUCTION["build_id"], "25627491")
        self.assertEqual(len(PRODUCTION["contracts"]), 4)
        for contract, path in zip(PRODUCTION["contracts"], paths):
            baseline = path.read_bytes()
            self.assertEqual(hashlib.sha256(baseline).hexdigest(), contract["baseline_module_sha256"])
            self.assertEqual(hashlib.sha256(contract["anchor"].encode()).hexdigest(), contract["anchor_sha256"])
            self.assertEqual(baseline.decode().count(contract["anchor"]), contract["expectedCount"])


if __name__ == "__main__":
    unittest.main()
