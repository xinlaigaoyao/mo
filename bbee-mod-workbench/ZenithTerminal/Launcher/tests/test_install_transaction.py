"""Synthetic filesystem tests: never use the installed game or real saves."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER))
import install_transaction
from install_transaction import (FileChange, RecoveryError, TransactionError,
                                 TransactionLocked, apply_transaction, recover_transactions)


class SimulatedCrash(BaseException):
    pass


class InstallTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bbee-transaction-synthetic-")
        self.root = Path(self.temporary.name)
        self.game = self.root / "synthetic-game"
        self.game.mkdir()
        self.state = self.root / "private-state"
        self.targets = [self.game / name for name in ("bundle.m", "merge.json", "manifest.json", "installed.json")]
        self.originals = {p: ("original-" + p.name).encode() for p in self.targets}
        for target, content in self.originals.items():
            target.write_bytes(content)
        self.changes = [FileChange(p, data=("new-" + p.name).encode()) for p in self.targets]

    def tearDown(self):
        self.temporary.cleanup()

    def apply(self, changes=None, **kwargs):
        return apply_transaction(self.changes if changes is None else changes,
                                 allowed_targets=self.targets, state_dir=self.state, **kwargs)

    def assert_original_group(self):
        self.assertEqual({p: p.read_bytes() for p in self.targets}, self.originals)

    def test_group_commit_and_idempotent_retry(self):
        first = self.apply(transaction_id="install-one")
        self.assertEqual(first["status"], "committed")
        self.assertEqual(self.apply(transaction_id="install-one")["status"], "already_committed")
        for target in self.targets:
            self.assertEqual(target.read_bytes(), ("new-" + target.name).encode())
        journal = json.loads((self.state / "install-one" / "journal.json").read_text())
        self.assertEqual(journal["state"], "committed")
        self.assertEqual(len(list((self.state / "install-one" / "backups").iterdir())), 4)
        self.assertEqual(recover_transactions(allowed_targets=self.targets, state_dir=self.state), [])

    def test_same_id_with_different_bytes_is_rejected(self):
        self.apply(transaction_id="same")
        with self.assertRaises(TransactionError):
            self.apply([FileChange(self.targets[0], data=b"different")], transaction_id="same")
        self.assertEqual(self.targets[0].read_bytes(), b"new-bundle.m")

    def test_failures_at_each_apply_position_restore_whole_group(self):
        for position in range(len(self.targets)):
            def fail(event, index):
                if event == "after_apply" and index == position:
                    raise OSError("injected disk failure")
            with self.subTest(position=position):
                with self.assertRaisesRegex(OSError, "injected"):
                    self.apply(fault=fail, transaction_id="retryable")
                self.assert_original_group()
        self.assertEqual(self.apply(transaction_id="retryable")["status"], "committed")

    def test_precommit_failure_restores_all_files(self):
        def fail(event, index):
            if event == "before_commit":
                raise OSError("injected commit failure")
        with self.assertRaises(OSError):
            self.apply(fault=fail)
        self.assert_original_group()

    def test_crashes_during_preparation_clean_stages_without_changing_targets(self):
        for event_name in ("before_prepare", "after_backup", "after_stage", "after_prepare"):
            def crash(event, index):
                if event == event_name:
                    raise SimulatedCrash()
            with self.subTest(event=event_name):
                with self.assertRaises(SimulatedCrash):
                    self.apply(fault=crash, transaction_id="prepare-crash")
                recover_transactions(allowed_targets=self.targets, state_dir=self.state)
                self.assert_original_group()
                self.assertEqual(list(self.game.glob(".*.bbee-stage-*")), [])

    def test_crash_between_stage_creation_and_ownership_journal_is_recoverable(self):
        source = self.root / "source"
        source.write_bytes(b"source bytes")
        real_copy = install_transaction._copy_file
        def crash_copy(incoming, outgoing, on_created=None):
            if on_created:
                with outgoing.open("xb") as stream:
                    stream.write(b"partial stage")
                    stream.flush()
                    os.fsync(stream.fileno())
                raise SimulatedCrash()
            return real_copy(incoming, outgoing)
        with patch("install_transaction._copy_file", crash_copy):
            with self.assertRaises(SimulatedCrash):
                self.apply([FileChange(self.targets[0], source=source)], transaction_id="stage-gap")
        recover_transactions(allowed_targets=self.targets, state_dir=self.state)
        self.assert_original_group()
        self.assertEqual(list(self.game.glob(".*.bbee-stage-*")), [])

    def test_retry_after_death_before_initial_journal_preserves_orphan(self):
        orphan = self.state / "initial-gap" / "backups"
        orphan.mkdir(parents=True)
        result = self.apply(transaction_id="initial-gap")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(len(list(self.state.glob("initial-gap.attempt-*"))), 1)

    def test_delete_and_create_are_rolled_back_together(self):
        created = self.game / "new" / "save-copy"
        targets = self.targets + [created]
        def fail(event, index):
            if event == "after_apply" and index == 2:
                raise OSError("injected")
        with self.assertRaises(OSError):
            apply_transaction([FileChange(self.targets[0], delete=True),
                               FileChange(created, data=b"new save bytes"),
                               FileChange(self.targets[1], data=b"repoint")],
                              allowed_targets=targets, state_dir=self.state, fault=fail)
        self.assert_original_group()
        self.assertFalse(created.exists())
        self.assertFalse(created.parent.exists())

    def test_pending_group_is_recovered_on_next_install(self):
        def crash(event, index):
            if event == "after_apply" and index == 1:
                raise SimulatedCrash()
        with self.assertRaises(SimulatedCrash):
            self.apply(fault=crash, transaction_id="interrupted")
        self.assertNotEqual(self.targets[0].read_bytes(), self.originals[self.targets[0]])
        result = self.apply(transaction_id="replacement")
        self.assertEqual(result["recovered"], [{"transaction_id": "interrupted", "status": "rolled_back"}])
        self.assertEqual(json.loads((self.state / "interrupted" / "journal.json").read_text())["state"], "rolled_back")

    def test_hard_process_death_releases_lock_and_recovers(self):
        script = """import os, sys
from install_transaction import FileChange, apply_transaction
from pathlib import Path
targets = [Path(x) for x in sys.argv[2:]]
def crash(event, index):
    if event == 'after_apply' and index == 1:
        os._exit(73)
apply_transaction([FileChange(p, data=b'child new bytes') for p in targets],
                  allowed_targets=targets, state_dir=sys.argv[1], transaction_id='hard-crash', fault=crash)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.state), *map(str, self.targets)],
                               cwd=LAUNCHER, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 73, child.stderr.decode(errors="replace"))
        recovered = recover_transactions(allowed_targets=self.targets, state_dir=self.state)
        self.assertEqual(recovered, [{"transaction_id": "hard-crash", "status": "rolled_back"}])
        self.assert_original_group()

    def test_committed_group_survives_process_death(self):
        script = """import os, sys
from install_transaction import FileChange, apply_transaction
def crash(event, index):
    if event == 'after_commit': os._exit(74)
apply_transaction([FileChange(p, data=b'committed bytes') for p in sys.argv[2:]],
                  allowed_targets=sys.argv[2:], state_dir=sys.argv[1], transaction_id='committed', fault=crash)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.state), *map(str, self.targets)],
                               cwd=LAUNCHER, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 74, child.stderr.decode(errors="replace"))
        self.assertEqual(recover_transactions(allowed_targets=self.targets, state_dir=self.state), [])
        self.assertTrue(all(p.read_bytes() == b"committed bytes" for p in self.targets))

    def test_backup_tamper_stops_before_any_rollback_write(self):
        def crash(event, index):
            if event == "after_apply" and index == 0:
                raise SimulatedCrash()
        with self.assertRaises(SimulatedCrash):
            self.apply(fault=crash, transaction_id="tampered")
        (self.state / "tampered" / "backups" / "000001.bin").write_bytes(b"bad backup")
        with self.assertRaises(RecoveryError):
            recover_transactions(allowed_targets=self.targets, state_dir=self.state)
        self.assertEqual(self.targets[0].read_bytes(), b"new-bundle.m")
        self.assertEqual(self.targets[1].read_bytes(), self.originals[self.targets[1]])

    def test_external_change_is_not_overwritten_by_recovery(self):
        def crash(event, index):
            if event == "after_apply" and index == 0:
                raise SimulatedCrash()
        with self.assertRaises(SimulatedCrash):
            self.apply(fault=crash)
        self.targets[1].write_bytes(b"unrelated external change")
        with self.assertRaises(RecoveryError):
            recover_transactions(allowed_targets=self.targets, state_dir=self.state)
        self.assertEqual(self.targets[1].read_bytes(), b"unrelated external change")

    def test_before_apply_hook_cannot_overwrite_new_external_target_content(self):
        def drift(event, index):
            if event == "before_apply" and index == 0:
                self.targets[0].write_bytes(b"new external content after final planning")
        with self.assertRaises(RecoveryError):
            self.apply(fault=drift, transaction_id="hook-target-drift")
        self.assertEqual(self.targets[0].read_bytes(), b"new external content after final planning")
        for target in self.targets[1:]:
            self.assertEqual(target.read_bytes(), self.originals[target])
        journal = json.loads((self.state / "hook-target-drift" / "journal.json").read_text())
        self.assertEqual(journal["state"], "applying")
        self.assertTrue((self.state / "hook-target-drift" / "backups" / "000000.bin").exists())

    def test_before_apply_stage_drift_is_rejected_and_targets_roll_back(self):
        def drift(event, index):
            if event == "before_apply" and index == 1:
                stage = self.targets[1].with_name(f".{self.targets[1].name}.bbee-stage-hook-stage-drift-1")
                stage.write_bytes(b"tampered staged content")
        with self.assertRaises(TransactionError):
            self.apply(fault=drift, transaction_id="hook-stage-drift")
        self.assert_original_group()

    def test_before_commit_hook_drift_cannot_be_committed(self):
        def drift(event, index):
            if event == "before_commit":
                self.targets[0].write_bytes(b"external content just before commit")
        with self.assertRaises(RecoveryError):
            self.apply(fault=drift, transaction_id="hook-commit-drift")
        self.assertEqual(self.targets[0].read_bytes(), b"external content just before commit")
        self.assertEqual(json.loads((self.state / "hook-commit-drift" / "journal.json").read_text())["state"], "applying")

    def test_exact_whitelist_and_duplicate_target_are_enforced(self):
        outsider = self.root / "outside.txt"
        for changes in ([FileChange(outsider, data=b"no")],
                        [FileChange(self.targets[0], data=b"a"), FileChange(self.targets[0], data=b"b")]):
            with self.subTest(changes=changes):
                with self.assertRaises(TransactionError):
                    self.apply(changes)
        self.assert_original_group()
        self.assertFalse(outsider.exists())
        self.assertFalse(self.state.exists())

    def test_source_copy_and_dry_run_have_expected_effects(self):
        source = self.root / "generated-bundle"
        source.write_bytes(b"generated bundle")
        self.assertEqual(self.apply([FileChange(self.targets[0], source=source)], dry_run=True)["status"], "dry_run")
        self.assert_original_group()
        self.assertFalse(self.state.exists())
        self.apply([FileChange(self.targets[0], source=source)])
        self.assertEqual(self.targets[0].read_bytes(), b"generated bundle")

    def test_required_source_hash_is_checked_before_any_target_changes(self):
        with self.assertRaises(TransactionError):
            self.apply([FileChange(self.targets[0], data=b"bad payload", expected_sha256="0" * 64)])
        self.assert_original_group()
        self.assertFalse(self.state.exists())

    def test_original_hash_precondition_stops_the_entire_group(self):
        import hashlib
        expected = hashlib.sha256(self.originals[self.targets[-1]]).hexdigest()
        self.targets[-1].write_bytes(b"cloud sync changed it after planning")
        changes = self.changes[:-1] + [FileChange(self.targets[-1], data=b"planned cleanup",
                                                  expected_before_sha256=expected)]
        with self.assertRaises(TransactionError):
            self.apply(changes)
        for target in self.targets[:-1]:
            self.assertEqual(target.read_bytes(), self.originals[target])
        self.assertEqual(self.targets[-1].read_bytes(), b"cloud sync changed it after planning")

    def test_expected_absence_and_presence_are_checked_under_lock(self):
        with self.assertRaises(TransactionError):
            self.apply([FileChange(self.targets[0], data=b"new", expected_before_exists=False)])
        absent = self.game / "new-target"
        with self.assertRaises(TransactionError):
            apply_transaction([FileChange(absent, data=b"new", expected_before_exists=True)],
                              allowed_targets=[absent], state_dir=self.state)
        self.assert_original_group()
        self.assertFalse(absent.exists())

    def test_preexisting_stage_is_not_deleted(self):
        stage = self.game / ".bundle.m.bbee-stage-collision-0"
        stage.write_bytes(b"unrelated existing file")
        with self.assertRaises(FileExistsError):
            self.apply(transaction_id="collision")
        self.assertEqual(stage.read_bytes(), b"unrelated existing file")
        self.assert_original_group()

    def test_concurrent_process_is_locked_out(self):
        ready = self.root / "lock-ready"
        script = """import sys
from pathlib import Path
from install_transaction import _locked
with _locked(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text('ready')
    sys.stdin.read(1)
"""
        child = subprocess.Popen([sys.executable, "-c", script, str(self.state), str(ready)], cwd=LAUNCHER,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline and child.poll() is None:
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            with self.assertRaises(TransactionLocked):
                self.apply()
            self.assert_original_group()
        finally:
            child.communicate("x", timeout=5)

    def test_symlink_component_is_rejected(self):
        actual, link = self.root / "outside", self.root / "link"
        actual.mkdir()
        victim = actual / "victim"
        victim.write_bytes(b"untouched")
        try:
            link.symlink_to(actual, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation is not enabled on this host")
        with self.assertRaises(TransactionError):
            apply_transaction([FileChange(link / "victim", data=b"no")], allowed_targets=[link / "victim"], state_dir=self.state)
        self.assertEqual(victim.read_bytes(), b"untouched")

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_junction_component_is_rejected(self):
        actual, link = self.root / "outside", self.root / "junction"
        actual.mkdir()
        victim = actual / "victim"
        victim.write_bytes(b"untouched")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(actual)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        with self.assertRaises(TransactionError):
            apply_transaction([FileChange(link / "victim", data=b"no")], allowed_targets=[link / "victim"], state_dir=self.state)
        self.assertEqual(victim.read_bytes(), b"untouched")


if __name__ == "__main__":
    unittest.main()
