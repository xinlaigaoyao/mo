"""Save backup/restore tests use generated fixtures, never a user's save data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER))
import save_safety
from install_transaction import TransactionError
from save_safety import SaveSafetyError, backup_saves, restore_saves, verify_backup


class SaveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bbee-save-synthetic-")
        self.root = Path(self.temporary.name)
        self.saves, self.private = self.root / "synthetic-save-root", self.root / "private"
        self.saves.mkdir()
        self.expected = {"1": b"synthetic compressed-looking bytes\x00\xff", "Backup/1": b"synthetic backup",
                         "ColdBackup/1": b"synthetic cold backup", "settings": b""}
        for name, data in self.expected.items():
            path = self.saves / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def tearDown(self):
        self.temporary.cleanup()

    def backup(self, **kwargs):
        return backup_saves(self.saves, self.private, **kwargs)

    def snapshot(self):
        return {p.relative_to(self.saves).as_posix(): p.read_bytes() for p in self.saves.rglob("*") if p.is_file()}

    def test_backup_is_complete_verified_and_has_no_plaintext_root(self):
        result = self.backup()
        self.assertEqual(result["status"], "backed_up")
        self.assertEqual(result["file_count"], 4)
        self.assertEqual(verify_backup(result["backup_dir"])["status"], "verified")
        manifest_text = (Path(result["backup_dir"]) / "manifest.json").read_text()
        self.assertNotIn(str(self.saves), manifest_text)
        manifest = json.loads(manifest_text)
        self.assertEqual({entry["path"] for entry in manifest["files"]}, set(self.expected))
        self.assertEqual(self.snapshot(), self.expected)

    def test_backup_dry_run_creates_nothing(self):
        before = self.snapshot()
        result = self.backup(dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(self.private.exists())
        self.assertEqual(self.snapshot(), before)

    def test_empty_root_is_no_saves_not_success(self):
        empty = self.root / "empty-root"
        empty.mkdir()
        for dry in (False, True):
            result = backup_saves(empty, self.private, dry_run=dry)
            self.assertEqual(result["status"], "no_saves")
            self.assertIsNone(result["backup_dir"])
            self.assertFalse(self.private.exists())

    def test_unreadable_tree_is_an_error_not_no_saves(self):
        with patch("save_safety.os.scandir", side_effect=PermissionError("synthetic denied")):
            with self.assertRaises(SaveSafetyError):
                self.backup()
        self.assertFalse(self.private.exists())

    def test_missing_or_unbound_root_is_rejected(self):
        for root in (None, self.root / "does-not-exist", Path(self.root.anchor)):
            with self.subTest(root=root):
                with self.assertRaises(TransactionError):
                    backup_saves(root, self.private)
        self.assertFalse(self.private.exists())

    def test_overlapping_private_root_is_rejected(self):
        with self.assertRaises(SaveSafetyError):
            backup_saves(self.saves, self.saves / "backup")
        with self.assertRaises(SaveSafetyError):
            backup_saves(self.saves, self.root)

    def test_tampered_payload_prevents_restore_and_preserves_current_tree(self):
        result = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        current = self.snapshot()
        (Path(result["backup_dir"]) / "payload" / "Backup" / "1").write_bytes(b"tampered")
        with self.assertRaises(SaveSafetyError):
            restore_saves(self.saves, result["backup_dir"], self.private)
        self.assertEqual(self.snapshot(), current)

    def test_restore_snapshots_current_tree_and_restores_exact_file_set(self):
        original = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        (self.saves / "Backup" / "1").unlink()
        (self.saves / "extra").write_bytes(b"extra current state")
        current = self.snapshot()
        result = restore_saves(self.saves, original["backup_dir"], self.private)
        self.assertEqual(result["status"], "restored")
        self.assertEqual(self.snapshot(), self.expected)
        pre = Path(result["before_restore"]["backup_dir"])
        pre_files = {p.relative_to(pre / "payload").as_posix(): p.read_bytes() for p in (pre / "payload").rglob("*") if p.is_file()}
        self.assertEqual(pre_files, current)
        self.assertEqual(verify_backup(pre)["status"], "verified")

    def test_restore_dry_run_is_side_effect_free(self):
        original = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        current = self.snapshot()
        before_names = sorted(str(p.relative_to(self.private)) for p in self.private.rglob("*"))
        result = restore_saves(self.saves, original["backup_dir"], self.private, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(self.snapshot(), current)
        self.assertEqual(sorted(str(p.relative_to(self.private)) for p in self.private.rglob("*")), before_names)

    def test_cross_root_restore_requires_explicit_clone_rebind(self):
        original = self.backup()
        clone = self.root / "synthetic-clone"
        clone.mkdir()
        with self.assertRaises(SaveSafetyError):
            restore_saves(clone, original["backup_dir"], self.private)
        result = restore_saves(clone, original["backup_dir"], self.private, allow_rebind=True)
        self.assertEqual(result["status"], "restored")
        self.assertEqual(result["before_restore"]["status"], "no_saves")
        self.assertEqual({p.relative_to(clone).as_posix(): p.read_bytes() for p in clone.rglob("*") if p.is_file()}, self.expected)

    def test_restore_failure_rolls_back_current_tree(self):
        original = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        (self.saves / "extra").write_bytes(b"must survive failure")
        current = self.snapshot()
        def fail(event, index):
            if event == "after_apply" and index == 1:
                raise OSError("injected restore failure")
        with self.assertRaises(OSError):
            restore_saves(self.saves, original["backup_dir"], self.private, fault=fail)
        self.assertEqual(self.snapshot(), current)

    def test_backup_change_after_initial_verification_cannot_be_committed(self):
        original = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        current = self.snapshot()
        real_backup = save_safety._backup_locked
        def backup_then_tamper(*args, **kwargs):
            result = real_backup(*args, **kwargs)
            (Path(original["backup_dir"]) / "payload" / "1").write_bytes(b"tampered after initial verification")
            return result
        with patch("save_safety._backup_locked", backup_then_tamper):
            with self.assertRaises(TransactionError):
                restore_saves(self.saves, original["backup_dir"], self.private)
        self.assertEqual(self.snapshot(), current)

    def test_cloud_sync_after_pre_restore_snapshot_is_never_overwritten(self):
        original = self.backup()
        (self.saves / "1").write_bytes(b"current progress before snapshot")
        real_backup = save_safety._backup_locked
        def backup_then_sync(*args, **kwargs):
            result = real_backup(*args, **kwargs)
            (self.saves / "1").write_bytes(b"new cloud progress after snapshot")
            return result
        with patch("save_safety._backup_locked", backup_then_sync):
            with self.assertRaises(TransactionError):
                restore_saves(self.saves, original["backup_dir"], self.private)
        expected = dict(self.expected)
        expected["1"] = b"new cloud progress after snapshot"
        self.assertEqual(self.snapshot(), expected)

    def test_cloud_sync_drift_blocks_deletion_of_extra_current_file(self):
        original = self.backup()
        (self.saves / "extra").write_bytes(b"extra before snapshot")
        real_backup = save_safety._backup_locked
        def backup_then_sync(*args, **kwargs):
            result = real_backup(*args, **kwargs)
            (self.saves / "extra").write_bytes(b"extra new cloud progress")
            return result
        with patch("save_safety._backup_locked", backup_then_sync):
            with self.assertRaises(TransactionError):
                restore_saves(self.saves, original["backup_dir"], self.private)
        self.assertEqual((self.saves / "extra").read_bytes(), b"extra new cloud progress")
        for name, data in self.expected.items():
            self.assertEqual((self.saves / name).read_bytes(), data)

    def test_cloud_sync_creation_blocks_restore_to_previously_absent_slot(self):
        original = self.backup()
        (self.saves / "Backup" / "1").unlink()
        real_backup = save_safety._backup_locked
        def backup_then_sync(*args, **kwargs):
            result = real_backup(*args, **kwargs)
            (self.saves / "Backup" / "1").write_bytes(b"new cloud-created slot")
            return result
        with patch("save_safety._backup_locked", backup_then_sync):
            with self.assertRaises(TransactionError):
                restore_saves(self.saves, original["backup_dir"], self.private)
        self.assertEqual((self.saves / "Backup" / "1").read_bytes(), b"new cloud-created slot")

    def test_interrupted_restore_is_rolled_back_before_the_next_restore(self):
        class Crash(BaseException):
            pass
        original = self.backup()
        (self.saves / "1").write_bytes(b"new progress")
        (self.saves / "extra").write_bytes(b"extra latest state")
        current = self.snapshot()
        def crash(event, index):
            if event == "after_apply" and index == 1:
                raise Crash()
        with self.assertRaises(Crash):
            restore_saves(self.saves, original["backup_dir"], self.private, fault=crash)
        result = restore_saves(self.saves, original["backup_dir"], self.private)
        self.assertEqual(result["status"], "restored")
        self.assertEqual(self.snapshot(), self.expected)
        before = Path(result["before_restore"]["backup_dir"]) / "payload"
        self.assertEqual({p.relative_to(before).as_posix(): p.read_bytes() for p in before.rglob("*") if p.is_file()}, current)

    def test_manifest_traversal_and_duplicate_entries_are_rejected(self):
        original = self.backup()
        path = Path(original["backup_dir"]) / "manifest.json"
        valid = json.loads(path.read_text())
        for mode in ("traversal", "duplicate"):
            manifest = json.loads(json.dumps(valid))
            if mode == "traversal":
                manifest["files"][0]["path"] = "../outside"
            else:
                manifest["files"].append(manifest["files"][0].copy())
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(mode=mode):
                with self.assertRaises(SaveSafetyError):
                    verify_backup(original["backup_dir"])
        self.assertEqual(self.snapshot(), self.expected)

    def test_extra_backup_payload_file_is_rejected(self):
        original = self.backup()
        (Path(original["backup_dir"]) / "payload" / "unknown").write_bytes(b"unexpected")
        with self.assertRaises(SaveSafetyError):
            verify_backup(original["backup_dir"])

    def test_link_in_save_tree_is_rejected(self):
        outside = self.root / "outside"
        outside.write_bytes(b"private outside bytes")
        try:
            (self.saves / "linked").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation is not enabled on this host")
        with self.assertRaises(TransactionError):
            self.backup()
        self.assertFalse(self.private.exists())


if __name__ == "__main__":
    unittest.main()
