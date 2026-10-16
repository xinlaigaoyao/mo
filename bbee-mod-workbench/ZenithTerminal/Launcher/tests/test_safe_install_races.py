"""Real temporary-folder install/uninstall races, including process death.

All bytes are generated fixtures at the verified-build boundary. No game or
actual user save is read, written, or launched by these tests.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import safe_install
from install_transaction import FileChange, TransactionError, apply_transaction
import test_safe_install as integration_fixture

LAUNCHER = Path(__file__).resolve().parents[1]


class SafeInstallRaceTests(unittest.TestCase):
    setUp = integration_fixture.InstallIntegrationTests.setUp
    save_verification = integration_fixture.InstallIntegrationTests.save_verification

    def test_late_target_creation_is_not_adopted_as_a_new_original(self):
        container = self.ab / "m_mod.m"
        real_apply = safe_install.apply_transaction
        def drift(changes, **kwargs):
            container.write_bytes(b"external target created after plan snapshot")
            return real_apply(changes, **kwargs)
        with patch("safe_install.apply_transaction", side_effect=drift):
            with self.assertRaises(TransactionError):
                safe_install.install(self.root)
        self.assertEqual(container.read_bytes(), b"external target created after plan snapshot")
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertFalse((self.root / "mods" / "installed.json").exists())

    def test_uninstall_rejects_target_drift_between_plan_and_transaction(self):
        safe_install.install(self.root)
        container = self.ab / "m_mod.m"
        merge = (self.ab / "merge.json").read_bytes()
        real_apply = safe_install.apply_transaction
        def drift(changes, **kwargs):
            container.write_bytes(b"external latest container")
            return real_apply(changes, **kwargs)
        with patch("safe_install.apply_transaction", side_effect=drift):
            with self.assertRaises(TransactionError):
                safe_install.uninstall(self.root)
        self.assertEqual(container.read_bytes(), b"external latest container")
        self.assertEqual((self.ab / "merge.json").read_bytes(), merge)
        self.assertTrue((self.root / "mods" / "installed.json").exists())

    def test_assembled_container_is_bound_to_the_recorded_source_hash(self):
        real_apply = safe_install.apply_transaction
        def tamper(changes, **kwargs):
            changes = list(changes)
            container_change = next(change for change in changes if Path(change.target).name == "m_mod.m")
            Path(container_change.source).write_bytes(b"tampered after recorded container hash")
            return real_apply(changes, **kwargs)
        with patch("safe_install.apply_transaction", side_effect=tamper):
            with self.assertRaises(TransactionError):
                safe_install.install(self.root)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())

    def test_new_pristine_backup_cannot_overwrite_an_external_new_file(self):
        backup = self.ab / "merge.json.orig"
        real_apply = safe_install.apply_transaction
        def drift(changes, **kwargs):
            backup.write_bytes(b"external recovery input")
            return real_apply(changes, **kwargs)
        with patch("safe_install.apply_transaction", side_effect=drift):
            with self.assertRaises(TransactionError):
                safe_install.install(self.root)
        self.assertEqual(backup.read_bytes(), b"external recovery input")
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())

    def test_existing_pristine_backup_drift_is_detected_without_rewriting_it(self):
        safe_install.install(self.root)
        backup = self.ab / "merge.json.orig"
        installed_merge = (self.ab / "merge.json").read_bytes()
        def drift(event, index):
            if event == "after_prepare":
                backup.write_bytes(b"external change to read-only pristine input")
        with self.assertRaises(TransactionError):
            safe_install.install(self.root, fault=drift)
        self.assertEqual(backup.read_bytes(), b"external change to read-only pristine input")
        self.assertEqual((self.ab / "merge.json").read_bytes(), installed_merge)

    def test_orphan_build_stamp_is_not_silently_overwritten(self):
        stamp = self.ab / "merge.json.orig.build"
        stamp.write_bytes(b"external-stamp")
        with self.assertRaises(ValueError):
            safe_install.install(self.root)
        self.assertEqual(stamp.read_bytes(), b"external-stamp")
        self.assertFalse((self.ab / "merge.json.orig").exists())

    def test_baseline_changed_after_verified_build_is_rejected(self):
        baseline = self.root / "inspect" / "baseline_manifest.json"
        data = json.loads(baseline.read_text())
        data["unverified_change"] = True
        baseline.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            safe_install.install(self.root)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())

    def test_baseline_drift_after_prepare_cannot_be_committed(self):
        baseline = self.root / "inspect" / "baseline_manifest.json"
        def drift(event, index):
            if event == "after_prepare":
                baseline.write_bytes(b"external new baseline")
        with self.assertRaises(TransactionError):
            safe_install.install(self.root, fault=drift)
        self.assertEqual(baseline.read_bytes(), b"external new baseline")
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())

    def test_extra_file_changes_require_original_state_binding(self):
        save = self.workspace / "private" / "synthetic-unbound-save"
        save.write_bytes(b"original")
        with self.assertRaises(TransactionError):
            safe_install.install(self.root, extra_changes=[FileChange(save, data=b"new")], extra_allowed=[save])
        self.assertEqual(save.read_bytes(), b"original")

    def test_actual_process_death_retries_install_and_uninstall_with_save_in_same_group(self):
        save = self.workspace / "private" / "synthetic-saves" / "1"
        save.parent.mkdir()
        original_save, installed_save, stock_save = b"synthetic original", b"synthetic installed", b"synthetic stock"
        save.write_bytes(original_save)
        script = """import hashlib, os, sys
from pathlib import Path
import safe_install
from install_transaction import FileChange
safe_install.require_closed = lambda: None
root, save = Path(sys.argv[1]), Path(sys.argv[2])
os.environ['BBMOD_BUILD_ID'] = 'test'
os.environ['BBMOD_OUT'] = str(root / 'patch_out')
command = sys.argv[3]
content = b'synthetic installed' if command == 'install' else b'synthetic stock'
change = FileChange(save, data=content, expected_before_exists=True,
                    expected_before_sha256=hashlib.sha256(save.read_bytes()).hexdigest())
def crash(event, index):
    if event == 'before_commit': os._exit(78)
getattr(safe_install, command)(root, extra_changes=[change], extra_allowed=[save], fault=crash)
"""
        def terminate_mid_group(command):
            child = subprocess.run([sys.executable, "-E", "-s", "-u", "-c", script, str(self.root), str(save), command],
                                   cwd=LAUNCHER, capture_output=True, timeout=30)
            self.assertEqual(child.returncode, 78, child.stderr.decode(errors="replace"))
        terminate_mid_group("install")
        self.assertEqual(save.read_bytes(), installed_save)
        change = FileChange(save, data=installed_save, expected_before_exists=True,
                            expected_before_sha256=hashlib.sha256(original_save).hexdigest())
        self.assertEqual(safe_install.install(self.root, extra_changes=[change], extra_allowed=[save])["transaction"]["status"], "committed")
        self.assertEqual(save.read_bytes(), installed_save)
        terminate_mid_group("uninstall")
        self.assertEqual(save.read_bytes(), stock_save)
        change = FileChange(save, data=stock_save, expected_before_exists=True,
                            expected_before_sha256=hashlib.sha256(installed_save).hexdigest())
        self.assertEqual(safe_install.uninstall(self.root, extra_changes=[change], extra_allowed=[save])["status"], "uninstalled")
        self.assertEqual(save.read_bytes(), stock_save)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge_bytes)
        self.assertEqual((self.ab / "manifest").read_bytes(), self.manifest_bytes)
        self.assertFalse((self.ab / "m_mod.m").exists())
        self.assertFalse((self.root / "mods" / "installed.json").exists())
        journals = [json.loads(path.read_text()) for path in (self.workspace / "private" / "transactions").glob("*/journal.json")]
        self.assertEqual(sum(journal["state"] == "rolled_back" for journal in journals), 2)
        self.assertEqual(sum(journal["state"] == "committed" for journal in journals), 2)


if __name__ == "__main__":
    unittest.main()
