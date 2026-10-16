import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lz4.frame

from safe_install import augment_manifest, install, read_manifest, uninstall


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


class InstallIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "ZenithTerminal" / "Launcher"
        self.ab = self.root / "game" / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
        self.ab.mkdir(parents=True)
        (self.workspace / "private").mkdir()
        (self.root / "mods").mkdir()
        (self.root / "inspect").mkdir()
        self.output = self.root / "patch_out"
        (self.output / "data" / "js").mkdir(parents=True)
        self.merge_bytes = json.dumps([{"r": "data/js/base.ab", "m": "m_1.m", "s": 0}]).encode()
        self.manifest_bytes = lz4.frame.compress(b"FastManifest V3\r\nN:1\r\ndata/js/base\r\nN:1\r\n0\r\nN:0\r\n----\r\n")
        (self.ab / "merge.json").write_bytes(self.merge_bytes)
        (self.ab / "manifest").write_bytes(self.manifest_bytes)
        # Payload validation is separately exercised against real UnityFS fixtures.
        # This integration fixture starts at the already-verified install boundary.
        self.bundle = self.output / "data" / "js" / "base.ab"
        self.bundle.write_bytes(b"verified-test-bundle")
        (self.output / "_build.json").write_text(json.dumps({"gameBuild": "test", "mods": {"fixture": "1"}}))
        baseline = {"source_merge": {"sha256": hash_bytes(self.merge_bytes)},
                    "source_manifest": {"sha256": hash_bytes(self.manifest_bytes)}}
        (self.root / "inspect" / "baseline_manifest.json").write_text(json.dumps(baseline))
        build_path = self.output / "_build.json"
        build_record = json.loads(build_path.read_text())
        build_record["baseline_manifest_sha256"] = hash_bytes((self.root / "inspect" / "baseline_manifest.json").read_bytes())
        build_path.write_text(json.dumps(build_record))
        self.verification = {"status": "passed", "build_id": "test",
                             "files": [{"path": "data/js/base.ab", "sha256": hash_bytes(self.bundle.read_bytes()), "kind": "bundle"}],
                             "metadata_hashes": {"_build.json": hash_bytes((self.output / "_build.json").read_bytes())}}
        self.save_verification()
        self.environment = patch.dict(os.environ, {"BBMOD_BUILD_ID": "test", "BBMOD_OUT": str(self.output)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def save_verification(self):
        (self.output / "_verification.json").write_text(json.dumps(self.verification))

    def test_group_install_uninstall_and_repeat(self):
        result = install(self.root)
        self.assertEqual(result["installed_bundles"], 1)
        self.assertEqual(json.loads((self.ab / "merge.json").read_text())[0]["m"], "m_mod.m")
        install(self.root)
        result = uninstall(self.root)
        self.assertEqual(result["status"], "uninstalled")
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertEqual((self.ab / "manifest").read_bytes(), self.manifest_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())
        self.assertEqual(uninstall(self.root)["status"], "already_uninstalled")

    def test_failed_install_restores_original_group(self):
        def fault(event, index):
            if event == "after_apply" and index == 4:
                raise RuntimeError("synthetic power interruption")
        with self.assertRaises(Exception):
            install(self.root, fault=fault)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertEqual((self.ab / "manifest").read_bytes(), self.manifest_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())
        self.assertFalse((self.root / "mods" / "installed.json").exists())

    def test_deleted_verified_bundle_is_rejected(self):
        self.bundle.unlink()
        with self.assertRaises(ValueError):
            install(self.root)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)

    def test_changed_verified_bundle_is_rejected(self):
        self.bundle.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            install(self.root)

    def test_deleted_verified_metadata_is_rejected(self):
        additions = self.output / "_manifest_add.json"
        additions.write_text(json.dumps({"names": [], "entries": [], "guids": []}))
        self.verification["metadata_hashes"]["_manifest_add.json"] = hash_bytes(additions.read_bytes())
        self.save_verification()
        additions.unlink()
        with self.assertRaises(ValueError):
            install(self.root)

    def test_pristine_target_drift_is_rejected(self):
        (self.ab / "merge.json").write_bytes(b"[]")
        with self.assertRaises(ValueError):
            install(self.root)

    def test_tampered_uninstall_backup_is_rejected(self):
        install(self.root)
        before = (self.ab / "merge.json").read_bytes()
        (self.ab / "merge.json.orig").write_bytes(b"[]")
        with self.assertRaises(ValueError):
            uninstall(self.root)
        self.assertEqual((self.ab / "merge.json").read_bytes(), before)

    def test_source_changed_after_hash_check_is_rejected(self):
        import safe_install
        original_digest = safe_install.digest
        def mutate_after_digest(path):
            result = original_digest(path)
            if path == self.bundle:
                path.write_bytes(b"changed-after-check")
            return result
        with patch("safe_install.digest", side_effect=mutate_after_digest):
            with self.assertRaises(ValueError):
                install(self.root)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)

    def test_manifest_dependency_roundtrip_and_conflict(self):
        additions = {"names": ["data/js/new"], "entries": [["data/js/new", ["data/js/base"]]],
                     "guids": [["data/js/new", "a" * 32]]}
        raw = augment_manifest(self.manifest_bytes, additions)
        names, entries, guids = read_manifest(raw)
        self.assertEqual(names, ["data/js/base", "data/js/new"])
        self.assertEqual(entries[-1], ["1", ["0"]])
        self.assertEqual(guids[-1], ["1", ["a" * 32]])
        with self.assertRaises(ValueError):
            augment_manifest(raw, {"entries": [["data/js/new", []]]})


if __name__ == "__main__":
    unittest.main()
