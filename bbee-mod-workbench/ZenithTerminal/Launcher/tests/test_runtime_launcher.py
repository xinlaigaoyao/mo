"""Synthetic owned-file recovery checks; never launch a game or a COM shell."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER.parents[1] / "scripts"))
import runtime_launcher as launch
import runtime_guard as guard
import desktop_session


class RuntimeLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bbee-owned-launch-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.launcher = self.root / "ZenithTerminal" / "Launcher"
        self.game = self.launcher / "game"
        self.game.mkdir(parents=True)
        self.private = self.root / "private" / "runtime"
        self.state = self.private / "launcher.json"
        self.manifest = self.root / "baselines" / launch.BUILD / "manifest.json"
        self.manifest.parent.mkdir(parents=True)
        records = []
        for name in (*launch.PROXIES, launch.EXE):
            data = b"ORIGINAL-PROXY" if name in launch.PROXIES else b"SYNTHETIC-EXE-NEVER-EXECUTE"
            (self.game / name).write_bytes(data)
            records.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        self.manifest.write_text(json.dumps({"build_id": launch.BUILD, "files": records}))
        self.saves = self.root / "synthetic-save-root"
        self.saves.mkdir()
        (self.saves / "1").write_bytes(b"SYNTHETIC-SAVE")
        patches = [patch.multiple(launch, ROOT=self.root, LAUNCHER=self.launcher, GAME=self.game,
                                  PRIVATE=self.private, STATE=self.state, BASELINE=self.manifest),
                   patch.multiple(guard, ROOT=self.launcher, PRIVATE=self.root / "private",
                                  STATE=self.private / "guard.json"),
                   patch("runtime_launcher.require_closed"), patch("runtime_guard.require_closed"),
                   patch("runtime_guard.print"), patch("runtime_launcher.require_unlocked"),
                   patch("runtime_launcher._shortcut", side_effect=self.shortcut)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def shortcut(self, path):
        path.write_bytes(b"SYNTHETIC-SHORTCUT-NEVER-EXECUTE")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def guarded(self):
        self.run_id = guard.begin(self.saves)["run_id"]
        return self.run_id

    def test_prepare_and_restore_bind_owned_files_to_current_guard(self):
        self.guarded()
        result = launch.prepare()
        self.assertEqual(result["run_id"], self.run_id)
        self.assertFalse(result["launch_performed"])
        session, link = launch._paths(self.run_id)
        self.assertTrue(link.is_file())
        self.assertEqual((self.game / "steam_appid.txt").read_bytes(), launch.APPID)
        for name in launch.PROXIES:
            self.assertFalse((self.game / name).exists())
            self.assertEqual((session / name).read_bytes(), b"ORIGINAL-PROXY")
        restored = launch.restore()
        self.assertEqual(restored["proxies_restored"], 3)
        self.assertFalse(link.exists())
        self.assertFalse(self.state.exists())
        self.assertFalse(session.exists())
        self.assertFalse((self.game / "steam_appid.txt").exists())
        for name in launch.PROXIES:
            self.assertEqual((self.game / name).read_bytes(), b"ORIGINAL-PROXY")

    def test_prepare_requires_a_verified_active_runtime_guard(self):
        with self.assertRaises(Exception):
            launch.prepare()
        self.assertFalse(self.state.exists())
        for name in launch.PROXIES:
            self.assertTrue((self.game / name).is_file())

    def test_preexisting_appid_stops_before_proxy_changes(self):
        self.guarded()
        (self.game / "steam_appid.txt").write_bytes(b"UNKNOWN-PREEXISTING")
        with self.assertRaises(launch.RuntimeLauncherError):
            launch.prepare()
        self.assertFalse(self.state.exists())
        for name in launch.PROXIES:
            self.assertTrue((self.game / name).is_file())

    def test_proxy_drift_refuses_entire_restore_before_any_changes(self):
        self.guarded()
        launch.prepare()
        session, link = launch._paths(self.run_id)
        (self.game / launch.PROXIES[-1]).write_bytes(b"UNKNOWN-TARGET")
        with self.assertRaises(launch.RuntimeLauncherError):
            launch.restore()
        self.assertTrue(self.state.exists())
        self.assertTrue(link.is_file())
        for name in launch.PROXIES:
            self.assertTrue((session / name).is_file())
        self.assertFalse((self.game / launch.PROXIES[0]).exists())

    def test_restore_handles_a_crash_after_one_proxy_was_isolated(self):
        self.guarded()
        replace = launch._replace
        moved = 0
        def fail_after_first(source, target):
            nonlocal moved
            if source.name in launch.PROXIES:
                moved += 1
                if moved == 2:
                    raise OSError("synthetic interruption before second move")
            return replace(source, target)
        with patch("runtime_launcher._replace", side_effect=fail_after_first):
            with self.assertRaises(OSError):
                launch.prepare()
        self.assertTrue(self.state.exists())
        result = launch.restore()
        self.assertEqual(result["status"], "restored")
        for name in launch.PROXIES:
            self.assertEqual((self.game / name).read_bytes(), b"ORIGINAL-PROXY")

    def test_changed_shortcut_is_retained_and_refuses_restore(self):
        self.guarded()
        launch.prepare()
        session, link = launch._paths(self.run_id)
        link.write_bytes(b"UNKNOWN-REPLACEMENT-SHORTCUT")
        with self.assertRaises(launch.RuntimeLauncherError):
            launch.restore()
        self.assertTrue(self.state.exists())
        self.assertEqual(link.read_bytes(), b"UNKNOWN-REPLACEMENT-SHORTCUT")
        self.assertTrue((session / launch.PROXIES[0]).is_file())

    def test_com_write_before_hash_journal_is_quarantined_during_restore(self):
        self.guarded()
        def interrupted(path):
            path.write_bytes(b"UNKNOWN-PRIVATE-COM-PARTIAL")
            raise OSError("synthetic interruption after COM saved the link")
        with patch("runtime_launcher._shortcut", side_effect=interrupted):
            with self.assertRaises(OSError):
                launch.prepare()
        result = launch.restore()
        self.assertTrue(result["unbound_private_shortcut_quarantined"])
        digest = hashlib.sha256(b"UNKNOWN-PRIVATE-COM-PARTIAL").hexdigest()
        retained = self.private / "runs" / self.run_id / ("unbound-shortcut-" + digest + ".lnk")
        self.assertEqual(retained.read_bytes(), b"UNKNOWN-PRIVATE-COM-PARTIAL")
        self.assertEqual((self.saves / "1").read_bytes(), b"SYNTHETIC-SAVE")
        for name in launch.PROXIES:
            self.assertEqual((self.game / name).read_bytes(), b"ORIGINAL-PROXY")

    def test_unbound_public_shortcut_refuses_restore_and_remains_untouched(self):
        self.guarded()
        with patch("runtime_launcher._shortcut", side_effect=OSError("before write")):
            with self.assertRaises(OSError):
                launch.prepare()
        _, link = launch._paths(self.run_id)
        link.write_bytes(b"UNKNOWN-PUBLIC-LINK")
        with self.assertRaises(launch.RuntimeLauncherError):
            launch.restore()
        self.assertEqual(link.read_bytes(), b"UNKNOWN-PUBLIC-LINK")
        self.assertTrue(self.state.exists())

    def test_restore_remains_available_after_guard_finish(self):
        self.guarded()
        launch.prepare()
        guard.finish()
        self.assertEqual(launch.restore()["status"], "restored")
        self.assertFalse(self.state.exists())

    def test_locked_or_unknown_desktop_stops_before_any_launch_mutation(self):
        self.guarded()
        for status in ("locked", "unknown"):
            with self.subTest(status=status):
                failure = desktop_session.DesktopSessionError(desktop_session._record(status, "synthetic"))
                with patch("runtime_launcher.require_unlocked", side_effect=failure), \
                     patch("runtime_launcher.ensure_private_directory") as directory, \
                     patch("runtime_launcher._locked") as lock, \
                     patch("runtime_launcher.guard._state") as state:
                    with self.assertRaises(desktop_session.DesktopSessionError):
                        launch.prepare()
                    directory.assert_not_called()
                    lock.assert_not_called()
                    state.assert_not_called()
                self.assertFalse(self.state.exists())
                self.assertFalse((self.game / "steam_appid.txt").exists())
                for name in launch.PROXIES:
                    self.assertEqual((self.game / name).read_bytes(), b"ORIGINAL-PROXY")

    def test_restore_is_available_while_desktop_is_locked(self):
        self.guarded()
        launch.prepare()
        with patch("runtime_launcher.require_unlocked", side_effect=AssertionError("restore must not query desktop")):
            self.assertEqual(launch.restore()["status"], "restored")


if __name__ == "__main__":
    unittest.main()
