"""Generated LocalLow-like fixtures only; never launch a game or use real saves."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER))
import runtime_guard as guard


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bbee-runtime-guard-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.launcher = self.workspace / "ZenithTerminal" / "Launcher"
        self.launcher.mkdir(parents=True)
        self.private = self.workspace / "private"
        self.state = self.private / "runtime" / "guard.json"
        self.root = self.workspace / "synthetic-original-locallow"
        self.root.mkdir()
        self.slot = self.root / "Save" / "1"
        self.slot.parent.mkdir()
        self.slot.write_bytes(b"ORIGINAL")
        (self.root / "original-empty").mkdir()
        self.log = self.root / "Player.log"
        self.log.write_bytes(b"private synthetic original log")
        for item in (self.slot, self.log, self.slot.parent, self.root / "original-empty", self.root):
            os.utime(item, ns=(1_600_000_000_000_000_000, 1_600_000_001_000_000_000))
        for item in (patch.multiple(guard, ROOT=self.launcher, PRIVATE=self.private, STATE=self.state),
                     patch("runtime_guard.require_closed"), patch("runtime_guard.print")):
            item.start()
            self.addCleanup(item.stop)

    def begin(self):
        result = guard.begin(self.root)
        self.run_id = result["run_id"]
        self.saved_state = json.loads(self.state.read_text())
        return result

    def mark_all(self):
        for check in guard.CHECKS:
            guard.mark(check, self.run_id)

    def probe(self, **overrides):
        data = {"status": "loaded", "run_id": self.run_id, "observed_ms": guard._now_ms(),
                "save_root_matches": True, "working_directory_matches": True, "is_playing": True}
        data.update(overrides)
        path = self.state.parent / "probe.json"
        path.write_text(json.dumps(data))
        os.utime(path, ns=(guard._now_ms() * 1_000_000, guard._now_ms() * 1_000_000))
        return path

    def evidence(self):
        return json.loads((self.workspace / "evidence" / "runtime-acceptance.json").read_text())

    def test_begin_binds_the_same_bytes_as_its_verified_backup(self):
        result = self.begin()
        self.assertTrue(result["backup_verified"])
        guard._backup_matches(self.saved_state)
        self.assertEqual(self.evidence()["status"], "runtime_pending")
        self.assertFalse(self.evidence()["runtime_acceptance_passed"])

    def test_begin_refuses_an_active_normal_play_session(self):
        active = self.private / "play/launcher.json"
        active.parent.mkdir(parents=True)
        active.write_text("{}")
        with self.assertRaises(guard.RuntimeGuardError):
            self.begin()
        self.assertFalse(self.state.exists())
        self.assertEqual(self.slot.read_bytes(), b"ORIGINAL")

    def test_begin_refuses_a_tree_changed_after_backup(self):
        real_backup = guard.backup_saves
        def changed(*args, **kwargs):
            result = real_backup(*args, **kwargs)
            self.slot.write_bytes(b"CHANGED!")
            return result
        with patch("runtime_guard.backup_saves", side_effect=changed):
            with self.assertRaises(guard.RuntimeGuardError):
                guard.begin(self.root)
        self.assertFalse(self.state.exists())

    def test_same_size_and_mtime_content_change_is_restored(self):
        self.begin()
        original_mtime = self.slot.stat().st_mtime_ns
        self.slot.write_bytes(b"CHANGED!")
        os.utime(self.slot, ns=(original_mtime, original_mtime))
        result = guard.finish()
        self.assertEqual(self.slot.read_bytes(), b"ORIGINAL")
        self.assertTrue(result["runtime_changed_files"])
        self.assertTrue(result["original_save_root_restored_exactly"])
        self.assertEqual(self.slot.stat().st_mtime_ns, original_mtime)

    def test_empty_directories_and_metadata_are_restored(self):
        self.begin()
        (self.root / "original-empty").rmdir()
        generated = self.root / "generated" / "nested"
        generated.mkdir(parents=True)
        (generated / "new-log").write_bytes(b"runtime new file")
        self.slot.write_bytes(b"runtime progress")
        result = guard.finish()
        self.assertTrue((self.root / "original-empty").is_dir())
        self.assertFalse((self.root / "generated").exists())
        self.assertEqual(self.slot.read_bytes(), b"ORIGINAL")
        expected = next(item for item in self.saved_state["before"]["files"] if item["path"] == "Save/1")
        self.assertEqual(self.slot.stat().st_mtime_ns, expected["mtime_ns"])
        self.assertEqual(result["restoration_scope"], "file_bytes_names_directories_mode_mtime")
        self.assertFalse(result["access_times_verified_exactly"])

    def test_directory_access_time_drift_is_not_misreported_as_exact(self):
        self.begin()
        real_metadata = guard._metadata
        def directory_access_changes(path):
            value = real_metadata(path)
            if Path(path).is_dir():
                value["atime_ns"] += 1_000_000
            return value
        with patch("runtime_guard._metadata", side_effect=directory_access_changes):
            result = guard.finish()
        self.assertEqual(self.slot.read_bytes(), b"ORIGINAL")
        self.assertTrue(result["original_save_root_restored_exactly"])
        self.assertEqual(result["access_time_restore_policy"], "best_effort")
        self.assertTrue(result["access_times_restore_attempted"])
        self.assertFalse(result["access_times_verified_exactly"])

    def test_original_log_is_restored_and_runtime_log_remains_private(self):
        self.begin()
        self.log.write_bytes(b"private runtime account and raw log marker")
        result = guard.finish()
        self.assertEqual(self.log.read_bytes(), b"private synthetic original log")
        private_logs = list(Path(self.saved_state["run_dir"]).glob("Player-*.log"))
        self.assertTrue(private_logs)
        self.assertEqual(private_logs[0].read_bytes(), b"private runtime account and raw log marker")
        public = json.dumps(result) + json.dumps(self.evidence())
        self.assertNotIn("raw log marker", public)
        self.assertNotIn(str(self.root), public)
        self.assertNotIn("Player.log", public)

    def test_backup_drift_stops_before_restore(self):
        self.begin()
        self.slot.write_bytes(b"runtime progress")
        backup = Path(self.saved_state["backup"]) / "payload" / "Save" / "1"
        backup.write_bytes(b"tampered backup")
        with self.assertRaises(Exception):
            guard.finish()
        self.assertEqual(self.slot.read_bytes(), b"runtime progress")
        self.assertTrue(self.state.exists())
        self.assertFalse(self.evidence()["runtime_acceptance_passed"])

    def test_valid_replacement_backup_after_initial_check_cannot_be_adopted(self):
        import hashlib
        self.begin()
        self.slot.write_bytes(b"runtime progress")
        real_restore = guard.restore_saves
        def replace_before_restore(*args, **kwargs):
            backup = Path(self.saved_state["backup"])
            payload = backup / "payload" / "Save" / "1"
            payload.write_bytes(b"valid-looking replacement backup")
            manifest_path = backup / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            entry = next(item for item in manifest["files"] if item["path"] == "Save/1")
            entry["sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
            entry["size"] = payload.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
            return real_restore(*args, **kwargs)
        with patch("runtime_guard.restore_saves", side_effect=replace_before_restore):
            with self.assertRaises(Exception):
                guard.finish()
        self.assertEqual(self.slot.read_bytes(), b"runtime progress")
        self.assertTrue(self.state.exists())

    def test_stale_probe_cannot_satisfy_runtime_acceptance(self):
        self.begin()
        self.mark_all()
        self.probe(run_id=uuid.uuid4().hex)
        result = guard.finish()
        self.assertEqual(result["runtime_probe"]["status"], "stale")
        self.assertFalse(result["runtime_acceptance_passed"])
        self.assertEqual(result["status"], "restored_without_runtime_acceptance")

    def test_old_observation_with_current_run_id_is_still_stale(self):
        self.begin()
        self.mark_all()
        self.probe(observed_ms=self.saved_state["began_ms"] - 1)
        result = guard.finish()
        self.assertEqual(result["runtime_probe"]["status"], "stale")
        self.assertFalse(result["runtime_acceptance_passed"])

    def test_missing_probe_or_marks_do_not_claim_runtime_passed(self):
        self.begin()
        self.mark_all()
        result = guard.finish()
        self.assertEqual(result["runtime_probe"]["status"], "missing")
        self.assertFalse(result["runtime_acceptance_passed"])

    def test_current_probe_is_sanitized_and_requires_all_current_marks(self):
        self.begin()
        self.mark_all()
        self.probe(account_path="PRIVATE-ACCOUNT-PATH", raw_log="PRIVATE-LOG-CONTENT", unity_version="not public")
        result = guard.finish()
        self.assertTrue(result["runtime_acceptance_passed"])
        public = json.dumps(result) + json.dumps(self.evidence())
        for private in ("PRIVATE-ACCOUNT-PATH", "PRIVATE-LOG-CONTENT", "not public", str(self.root)):
            self.assertNotIn(private, public)

    def test_current_probe_with_wrong_working_directory_cannot_pass(self):
        self.begin()
        self.mark_all()
        self.probe(working_directory_matches=False)
        result = guard.finish()
        self.assertEqual(result["runtime_probe"]["status"], "current")
        self.assertFalse(result["runtime_probe"]["working_directory_matches"])
        self.assertFalse(result["runtime_acceptance_passed"])

    def test_current_probe_without_working_directory_evidence_cannot_pass(self):
        self.begin()
        self.mark_all()
        path = self.probe()
        data = json.loads(path.read_text())
        data.pop("working_directory_matches")
        path.write_text(json.dumps(data))
        result = guard.finish()
        self.assertEqual(result["runtime_probe"]["status"], "current")
        self.assertFalse(result["runtime_probe"]["working_directory_matches"])
        self.assertFalse(result["runtime_acceptance_passed"])

    def test_mark_rejects_unknown_check_and_other_run(self):
        self.begin()
        with self.assertRaises(guard.RuntimeGuardError):
            guard.mark("arbitrary private text", self.run_id)
        with self.assertRaises(guard.RuntimeGuardError):
            guard.mark(guard.CHECKS[0], uuid.uuid4().hex)
        self.assertEqual(json.loads(self.state.read_text())["marks"], {})

    def test_previous_public_success_and_probe_are_archived_before_new_run(self):
        self.state.parent.mkdir(parents=True)
        (self.state.parent / "probe.json").write_text(json.dumps({"status": "loaded", "run_id": uuid.uuid4().hex}))
        evidence = self.workspace / "evidence" / "runtime-acceptance.json"
        evidence.parent.mkdir()
        evidence.write_text(json.dumps({"runtime_acceptance_passed": True, "old": True}))
        self.begin()
        self.assertFalse((self.state.parent / "probe.json").exists())
        self.assertFalse(self.evidence()["runtime_acceptance_passed"])
        self.assertTrue((Path(self.saved_state["run_dir"]) / "preexisting-probe.json").is_file())
        self.assertTrue((Path(self.saved_state["run_dir"]) / "previous-runtime-acceptance.json").is_file())

    def test_finish_failure_keeps_active_guard_and_private_backups(self):
        self.begin()
        self.slot.write_bytes(b"runtime progress")
        with patch("runtime_guard.restore_saves", side_effect=OSError("synthetic restore failure")):
            with self.assertRaises(OSError):
                guard.finish()
        self.assertTrue(self.state.exists())
        self.assertTrue(Path(self.saved_state["backup"]).is_dir())
        self.assertFalse(self.evidence()["runtime_acceptance_passed"])

    def test_release_preserves_progress_and_keeps_both_verified_backups(self):
        self.begin()
        self.slot.write_bytes(b"PLAYER-PROGRESS-KEEP")
        (self.root / "new-empty").mkdir()
        before = guard._comparable(guard._tree(self.root))
        with patch("runtime_guard.restore_saves", side_effect=AssertionError("release must not restore saves")):
            result = guard.release_preserving_progress()
        self.assertEqual(self.slot.read_bytes(), b"PLAYER-PROGRESS-KEEP")
        self.assertEqual(guard._comparable(guard._tree(self.root)), before)
        self.assertTrue(result["current_progress_preserved_exactly"])
        self.assertFalse(result["save_writes_performed"])
        self.assertFalse(result["runtime_acceptance_passed"])
        self.assertFalse(self.state.exists())
        archived = json.loads((Path(self.saved_state["run_dir"]) / "preserved-state.json").read_text())
        guard._backup_matches(archived)
        plan = json.loads(Path(archived["preserved_progress"]["plan"]).read_text())
        guard.verify_backup(plan["backup"]["backup_dir"])

    def test_release_refuses_changed_backup_and_active_launch_files(self):
        self.begin()
        launch = self.state.parent / "launcher.json"
        launch.write_text("{}")
        with self.assertRaises(guard.RuntimeGuardError):
            guard.release_preserving_progress()
        launch.unlink()
        backup = Path(self.saved_state["backup"]) / "payload" / "Save" / "1"
        backup.write_bytes(b"TAMPERED")
        with self.assertRaises(Exception):
            guard.release_preserving_progress()
        self.assertTrue(self.state.exists())
        self.assertEqual(self.slot.read_bytes(), b"ORIGINAL")

    def test_release_rejects_progress_changed_during_backup(self):
        self.begin()
        real = guard._verified_snapshot_backup
        def changing(*args):
            backup = real(*args)
            self.slot.write_bytes(b"NEWER-PROGRESS")
            return backup
        with patch("runtime_guard._verified_snapshot_backup", side_effect=changing):
            with self.assertRaises(guard.RuntimeGuardError):
                guard.release_preserving_progress()
        self.assertTrue(self.state.exists())
        self.assertEqual(self.slot.read_bytes(), b"NEWER-PROGRESS")


if __name__ == "__main__":
    unittest.main()
