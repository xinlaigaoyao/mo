"""Exercise the public commands against generated game/save fixtures only."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import lz4.frame

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER))
import entry_point
import safe_install
from install_transaction import TransactionError, apply_transaction


def digest(data):
    return hashlib.sha256(data).hexdigest()


def varint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    return bytes(result + bytes([number]))


def field(number, data):
    return varint((number << 3) | 2) + varint(len(data)) + data


def synthetic_save():
    entries = b"".join(field(1, b"\x08" + varint(actor)) for actor in (200101, 200301, 101))
    model = field(1, entries)
    message = field(1, b"ModelPlayerNewBaseActorPack") + field(2, model)
    return lz4.frame.compress(field(2, message) + b"\x30\x2a")


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bbee-entry-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "ZenithTerminal" / "Launcher"
        self.game = self.root / "game"
        self.ab = self.game / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
        self.ab.mkdir(parents=True)
        (self.game / entry_point.EXE).write_bytes(b"synthetic non-executable placeholder")
        for name in ("mods/fixture", "inspect", "tools", "patch_out/data/js"):
            (self.root / name).mkdir(parents=True)
        shutil.copyfile(LAUNCHER / "tools" / "savefile.py", self.root / "tools" / "savefile.py")
        (self.root / "mods" / "fixture" / "mod.json").write_text(json.dumps({"id": "fixture", "ActorId": 200301}))
        self.saves = self.workspace / "private" / "test-saves"
        self.saves.mkdir(parents=True)
        self.slot = self.saves / "1"
        self.original_save = synthetic_save()
        self.slot.write_bytes(self.original_save)
        self.merge = json.dumps([{"r": "data/js/base.ab", "m": "m_1.m", "s": 0}]).encode()
        self.manifest = lz4.frame.compress(b"FastManifest V3\r\nN:1\r\ndata/js/base\r\nN:1\r\n0\r\nN:0\r\n----\r\n")
        (self.ab / "merge.json").write_bytes(self.merge)
        (self.ab / "manifest").write_bytes(self.manifest)
        output = self.root / "patch_out"
        payload = output / "data" / "js" / "base.ab"
        payload.write_bytes(b"already verified synthetic bundle boundary")
        record = output / "_build.json"
        record.write_text(json.dumps({"gameBuild": "25627491", "mods": {"fixture": "1"}}))
        (output / "_verification.json").write_text(json.dumps({"status": "passed", "build_id": "25627491",
            "files": [{"path": "data/js/base.ab", "sha256": digest(payload.read_bytes()), "kind": "bundle"}],
            "metadata_hashes": {"_build.json": digest(record.read_bytes())}}))
        (self.root / "inspect" / "baseline_manifest.json").write_text(json.dumps({
            "source_merge": {"sha256": digest(self.merge)}, "source_manifest": {"sha256": digest(self.manifest)}}))
        build_record = json.loads(record.read_text())
        build_record["descriptors"] = {"fixture": digest((self.root / "mods" / "fixture" / "mod.json").read_bytes())}
        build_record["baseline_manifest_sha256"] = digest((self.root / "inspect" / "baseline_manifest.json").read_bytes())
        record.write_text(json.dumps(build_record))
        verification_path = output / "_verification.json"
        verification = json.loads(verification_path.read_text())
        verification["metadata_hashes"]["_build.json"] = digest(record.read_bytes())
        verification_path.write_text(json.dumps(verification))
        (self.root / "inspect" / "game_build.txt").write_text("25627491")
        patches = [patch.multiple(entry_point, ROOT=str(self.root), GAME=str(self.game), AB=str(self.ab),
                                  BUILD_MARK=str(self.root / "inspect" / "game_build.txt")),
                   patch.dict(os.environ, {"BBMOD_BUILD_ID": "25627491", "BBMOD_OUT": str(output),
                                            "BBEE_SAVE_ROOT": str(self.saves), "BBEE_ALLOW_EMPTY_SAVE": "0",
                                            "BBMOD_MODS_EXTRA": ""}),
                   patch("safe_install.require_closed"), patch("validation_tables.validate_baseline", return_value={}),
                   patch("entry_point.prepare_mods", return_value=0),
                   patch("entry_point.say")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_build_failure_never_starts_save_backup_or_planning(self):
        with (patch("entry_point.bbmod", return_value=1), patch("entry_point.backup_save") as backup,
              patch("entry_point.plan_save_changes") as planner):
            with self.assertRaises(SystemExit):
                entry_point.install([])
        backup.assert_not_called()
        planner.assert_not_called()
        self.assertEqual(self.slot.read_bytes(), self.original_save)
        self.assertFalse((self.workspace / "private" / "save-backups").exists())

    def test_prepare_failure_never_starts_build_or_save_operations(self):
        with (patch("entry_point.prepare_mods", return_value=1), patch("entry_point.bbmod") as build,
              patch("entry_point.backup_save") as backup, patch("entry_point.plan_save_changes") as planner):
            with self.assertRaises(SystemExit):
                entry_point.install([])
        build.assert_not_called()
        backup.assert_not_called()
        planner.assert_not_called()
        self.assertEqual(self.slot.read_bytes(), self.original_save)

    def test_install_order_is_prepare_build_backup_plan_then_group_commit(self):
        events = []
        real_backup, real_plan, real_install = entry_point.backup_save, entry_point.plan_save_changes, safe_install.install
        def backup(*args, **kwargs):
            events.append("backup")
            return real_backup(*args, **kwargs)
        def plan(*args, **kwargs):
            events.append("plan")
            return real_plan(*args, **kwargs)
        def install(*args, **kwargs):
            events.append("commit")
            return real_install(*args, **kwargs)
        with (patch("entry_point.prepare_mods", side_effect=lambda: events.append("prepare") or 0),
              patch("entry_point.bbmod", side_effect=lambda command: events.append(command) or 0),
              patch("entry_point.backup_save", side_effect=backup), patch("entry_point.plan_save_changes", side_effect=plan),
              patch("safe_install.install", side_effect=install)):
            entry_point.install([])
        self.assertEqual(events, ["prepare", "build", "backup", "plan", "commit"])

    def test_install_save_change_is_in_the_game_transaction_and_uninstall_cleans_all(self):
        with patch("entry_point.bbmod", return_value=0) as build:
            result = entry_point.install([])
        build.assert_called_once_with("build")
        self.assertEqual(result["transaction"]["status"], "committed")
        codec = entry_point._save_codec()
        decoded = lz4.frame.decompress(self.slot.read_bytes())
        codec.MOD_ACTORS = {200101}
        self.assertEqual(codec.scan_custom(decoded), 0)
        codec.MOD_ACTORS = {200301}
        self.assertGreater(codec.scan_custom(decoded), 0)
        result = entry_point.uninstall([])
        self.assertEqual(result["status"], "uninstalled")
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge)
        self.assertEqual((self.ab / "manifest").read_bytes(), self.manifest)
        codec.MOD_ACTORS = {200101, 200301}
        self.assertEqual(codec.scan_custom(lz4.frame.decompress(self.slot.read_bytes())), 0)

    def test_install_failure_after_save_write_rolls_back_game_and_save_together(self):
        real_install = safe_install.install
        def fail(event, index):
            if event == "before_commit":
                raise OSError("synthetic disk failure after all writes")
        def install_with_fault(*args, **kwargs):
            return real_install(*args, fault=fail, **kwargs)
        with patch("entry_point.bbmod", return_value=0), patch("safe_install.install", side_effect=install_with_fault):
            with self.assertRaises(OSError):
                entry_point.install([])
        self.assertEqual(self.slot.read_bytes(), self.original_save)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge)
        self.assertEqual((self.ab / "manifest").read_bytes(), self.manifest)
        self.assertFalse((self.ab / "m_mod.m").exists())
        self.assertFalse((self.root / "mods" / "installed.json").exists())

    def test_planned_save_refuses_cloud_sync_drift(self):
        changes = entry_point.plan_save_changes(self.saves, remove_all=True)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].expected_before_sha256, digest(self.original_save))
        synced = lz4.frame.compress(b"\x30\x2b")
        self.slot.write_bytes(synced)
        with self.assertRaises(TransactionError):
            apply_transaction(changes, allowed_targets=[self.slot], state_dir=self.workspace / "private" / "drift-test")
        self.assertEqual(self.slot.read_bytes(), synced)

    def test_save_planning_refuses_a_descriptor_changed_after_build(self):
        (self.root / "mods" / "fixture" / "mod.json").write_text(json.dumps({"id": "fixture", "ActorId": 200101}))
        with self.assertRaises(ValueError):
            entry_point.plan_save_changes(self.saves)
        self.assertEqual(self.slot.read_bytes(), self.original_save)

    def test_repair_save_uses_verified_backup_and_standalone_transaction(self):
        result = entry_point.repair_save([])
        self.assertEqual(result["status"], "committed")
        codec = entry_point._save_codec()
        self.assertEqual(codec.scan_custom(lz4.frame.decompress(self.slot.read_bytes())), 0)
        self.assertEqual((self.ab / "merge.json").read_bytes(), self.merge)
        self.assertTrue(list((self.workspace / "private" / "save-backups").glob("save-backup-*")))

    def test_missing_save_binding_is_rejected_without_discovery(self):
        with patch.dict(os.environ, {"BBEE_SAVE_ROOT": ""}):
            with self.assertRaises(SystemExit):
                entry_point.backup_save()
        self.assertEqual(self.slot.read_bytes(), self.original_save)

    def test_empty_root_requires_explicit_fresh_workbench_flag(self):
        self.slot.unlink()
        with self.assertRaises(SystemExit):
            entry_point.backup_save()
        with patch.dict(os.environ, {"BBEE_ALLOW_EMPTY_SAVE": "1"}):
            root, result = entry_point.backup_save()
            self.assertEqual(result["status"], "no_saves")
            self.assertIsNone(result["backup_dir"])
        self.assertFalse((self.workspace / "private" / "save-backups").exists())

    def test_empty_flag_does_not_excuse_an_external_account_root(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-external-account-") as outside:
            with patch.dict(os.environ, {"BBEE_ALLOW_EMPTY_SAVE": "1", "BBEE_SAVE_ROOT": outside}):
                with self.assertRaises(SystemExit):
                    entry_point.backup_save()

    def test_setup_missing_dependency_fails_with_no_pip_subprocess(self):
        real_import = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "UnityPy":
                raise ImportError("synthetic missing dependency")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=missing), patch("entry_point.subprocess.run") as run:
            with self.assertRaises(SystemExit):
                entry_point.setup([])
        run.assert_not_called()

    def test_setup_zero_exit_does_not_bypass_baseline_validation(self):
        with (patch("entry_point.subprocess.run", return_value=subprocess.CompletedProcess([], 0)),
              patch("entry_point.PKGS", []),
              patch("entry_point.shutil.which", return_value="synthetic-node"),
              patch("validation_tables.validate_baseline", side_effect=ValueError("invalid baseline")) as verify):
            with self.assertRaises(ValueError):
                entry_point.setup([])
        verify.assert_called_once_with(self.root, "25627491")


if __name__ == "__main__":
    unittest.main()
