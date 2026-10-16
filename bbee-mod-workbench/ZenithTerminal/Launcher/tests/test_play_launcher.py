"""Synthetic persistent-play lifecycle; never start an executable or read user saves."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER.parents[1] / "scripts"))
import play_launcher as play
import runtime_launcher as launch
import runtime_guard as guard
import package_patch

REAL_BUILD = play._build


class PersistentPlayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="bbee-persistent-play-synthetic-")
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "workbench"
        self.launcher = self.root / "ZenithTerminal/Launcher"
        self.game = self.launcher / "game"
        self.game.mkdir(parents=True)
        self.private = self.root / "private"
        self.runtime = self.private / "runtime"
        self.play_private = self.private / "play"
        self.saves = base / "explicit-synthetic-saves"
        self.saves.mkdir()
        self.slot = self.saves / "1"
        self.slot.write_bytes(b"PLAYER-PROGRESS-BEFORE")
        (self.saves / "empty").mkdir()
        records = []
        for name in (*launch.PROXIES, launch.EXE):
            data = b"SYNTHETIC-PROXY" if name in launch.PROXIES else b"NEVER-EXECUTE"
            (self.game / name).write_bytes(data)
            records.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        self.baseline = self.root / "baselines" / launch.BUILD / "manifest.json"
        self.baseline.parent.mkdir(parents=True)
        self.baseline.write_text(json.dumps({"build_id": launch.BUILD, "files": records}))
        (self.launcher / "mods").mkdir()
        (self.launcher / "mods/installed.json").write_text("{}")
        (self.root / "evidence").mkdir()
        for item in (
            patch.multiple(play, ROOT=self.root, LAUNCHER=self.launcher, GAME=self.game,
                           PRIVATE=self.play_private, STATE=self.play_private / "launcher.json",
                           CONFIG=self.play_private / "config.json"),
            patch.multiple(launch, ROOT=self.root, LAUNCHER=self.launcher, GAME=self.game,
                           PRIVATE=self.runtime, STATE=self.runtime / "launcher.json", BASELINE=self.baseline),
            patch.multiple(guard, ROOT=self.launcher, PRIVATE=self.private, STATE=self.runtime / "guard.json"),
            patch("play_launcher.require_closed"), patch("play_launcher.require_unlocked"),
            patch("runtime_guard.require_closed"), patch("runtime_guard.print"),
            patch("runtime_launcher._shortcut", side_effect=self.shortcut),
            patch("play_launcher._build", return_value="b" * 64)):
            item.start()
            self.addCleanup(item.stop)

    def shortcut(self, path, **kwargs):
        path.write_bytes(b"SYNTHETIC-SHORTCUT")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def configured(self):
        play.configure(save_root=self.saves)

    def test_normal_exit_keeps_new_progress_and_restores_only_owned_launch_files(self):
        self.configured()
        prepared = play.prepare()
        self.slot.write_bytes(b"PLAYER-PROGRESS-AFTER")
        (self.saves / "new-empty").mkdir()
        expected = guard._comparable(guard._tree(self.saves))
        with patch("runtime_guard.restore_saves", side_effect=AssertionError("normal exit must not restore")):
            result = play.finish()
        self.assertEqual(guard._comparable(guard._tree(self.saves)), expected)
        self.assertTrue(result["progress_preserved_exactly"])
        self.assertTrue(result["character_remains_installed"])
        self.assertFalse(result["runtime_acceptance_passed"])
        self.assertFalse(play.STATE.exists())
        self.assertFalse((self.game / "steam_appid.txt").exists())
        run_dir, link = play._paths(prepared["run_id"])
        self.assertFalse(link.exists())
        archived = json.loads((run_dir / "finished-state.json").read_text())
        for key in ("backup", "after"):
            guard.verify_backup(archived[key]["backup_dir"])
        for name in launch.PROXIES:
            self.assertEqual((self.game / name).read_bytes(), b"SYNTHETIC-PROXY")

    def test_test_guard_blocks_normal_play_before_launch_changes(self):
        self.configured()
        guard.begin(self.saves)
        with self.assertRaises(play.PlayLauncherError):
            play.prepare()
        self.assertFalse(play.STATE.exists())
        for name in launch.PROXIES:
            self.assertTrue((self.game / name).exists())

    def test_unknown_appid_and_proxy_drift_are_never_overwritten(self):
        self.configured()
        appid = self.game / "steam_appid.txt"
        appid.write_bytes(b"UNKNOWN-INPUT")
        with self.assertRaises(Exception):
            play.prepare()
        self.assertEqual(appid.read_bytes(), b"UNKNOWN-INPUT")
        appid.unlink()
        play.prepare()
        unknown = self.game / launch.PROXIES[-1]
        unknown.write_bytes(b"UNKNOWN-NEW-FILE")
        with self.assertRaises(Exception):
            play.finish()
        self.assertEqual(unknown.read_bytes(), b"UNKNOWN-NEW-FILE")
        self.assertTrue(play.STATE.exists())

    def test_interrupted_preparation_is_recoverable_without_save_rollback(self):
        self.configured()
        original = play._replace
        moves = 0
        def interrupted(source, target):
            nonlocal moves
            if source.name in launch.PROXIES:
                moves += 1
                if moves == 2:
                    raise OSError("synthetic interruption")
            return original(source, target)
        with patch("play_launcher._replace", side_effect=interrupted):
            with self.assertRaises(OSError):
                play.prepare()
        self.slot.write_bytes(b"KEEP-AFTER-INTERRUPTION")
        play.finish()
        self.assertEqual(self.slot.read_bytes(), b"KEEP-AFTER-INTERRUPTION")
        self.assertFalse(play.STATE.exists())

    def test_user_launcher_uses_game_cwd_and_preserves_progress_on_exit(self):
        self.configured()
        child = Mock()
        def simulated_exit():
            self.slot.write_bytes(b"PROGRESS-WRITTEN-BY-FAKE-GAME")
            return 0
        child.wait.side_effect = simulated_exit
        with patch("play_launcher.subprocess.Popen", return_value=child) as start:
            result = play.play()
        self.assertEqual(start.call_args.kwargs["cwd"], self.game)
        self.assertEqual(start.call_args.args[0][0], str(self.game / launch.EXE))
        self.assertEqual(start.call_args.kwargs["env"]["TEMP"], str(self.root / "private/temp/play"))
        self.assertEqual(self.slot.read_bytes(), b"PROGRESS-WRITTEN-BY-FAKE-GAME")
        self.assertEqual(result["game_exit_code"], 0)
        self.assertFalse(play.STATE.exists())

    def test_preserved_test_run_can_be_explicitly_bound_without_save_write(self):
        run = guard.begin(self.saves)["run_id"]
        self.slot.write_bytes(b"USER-PLAYTEST-PROGRESS")
        guard.release_preserving_progress()
        play.configure(preserved_run=run)
        self.assertEqual(self.slot.read_bytes(), b"USER-PLAYTEST-PROGRESS")
        self.assertFalse(guard.STATE.exists())
        self.assertTrue(play.CONFIG.exists())

    def test_valid_looking_replaced_progress_backup_is_refused(self):
        run = guard.begin(self.saves)["run_id"]
        guard.release_preserving_progress()
        run_dir = self.runtime / "runs" / run
        plan = json.loads((run_dir / "progress-preservation.json").read_text())
        backup = Path(plan["backup"]["backup_dir"])
        payload = backup / "payload/1"
        payload.write_bytes(b"DIFFERENT-BUT-INTERNALLY-VALID")
        manifest_file = backup / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        entry = next(e for e in manifest["files"] if e["path"] == "1")
        entry.update(size=payload.stat().st_size, sha256=hashlib.sha256(payload.read_bytes()).hexdigest())
        manifest_file.write_text(json.dumps(manifest))
        guard.verify_backup(backup)
        with self.assertRaises(play.PlayLauncherError):
            play.configure(preserved_run=run)
        self.assertFalse(play.CONFIG.exists())

    def test_shortcut_creation_interruption_quarantines_unbound_bytes_and_recovers(self):
        self.configured()
        def failing_link(path, **kwargs):
            path.write_bytes(b"PARTIAL-OWNED-LINK-DO-NOT-EXECUTE")
            raise OSError("synthetic COM readback interruption")
        with patch("runtime_launcher._shortcut", side_effect=failing_link):
            with self.assertRaises(OSError):
                play.prepare()
        result = play.finish()
        self.assertTrue(result["unbound_private_shortcut_quarantined"])
        self.assertFalse(play.STATE.exists())
        self.assertEqual(self.slot.read_bytes(), b"PLAYER-PROGRESS-BEFORE")

    def test_unknown_finished_archive_is_not_overwritten(self):
        self.configured()
        state = play.prepare()
        run_dir, _ = play._paths(state["run_id"])
        unknown = run_dir / "finished-state.json"
        unknown.write_bytes(b"UNKNOWN-HISTORY")
        with self.assertRaises(Exception):
            play.finish()
        self.assertEqual(unknown.read_bytes(), b"UNKNOWN-HISTORY")
        self.assertTrue(play.STATE.exists())

    def native_fixture(self):
        output = self.launcher / "patch_out"
        output.mkdir()
        (output / "a.ab").write_bytes(b"BUNDLE-A")
        (output / "b.ab").write_bytes(b"BUNDLE-B")
        ab = self.game / "BlazblueEntropyEffect_Data/StreamingAssets/ab"
        ab.mkdir(parents=True)
        original = [{"r":"stock.ab","m":"stock.m","s":42}]
        raw = json.dumps(original).encode()
        (ab / "merge.json.orig").write_bytes(raw)
        (ab / "merge.json.orig.build").write_text(play.BUILD)
        baseline = json.loads(self.baseline.read_text())
        baseline["files"].append({"path":"BlazblueEntropyEffect_Data/StreamingAssets/ab/merge.json",
                                   "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
        self.baseline.write_text(json.dumps(baseline))
        merge = [*original,{"r":"a.ab","m":"m_mod.m","s":0},{"r":"b.ab","m":"m_mod.m","s":8}]
        (ab / "merge.json").write_text(json.dumps(merge))
        (ab / "manifest").write_bytes(b"BOUND-MANIFEST")
        (ab / "m_mod.m").write_bytes(b"BUNDLE-ABUNDLE-B")
        build = {"gameBuild":play.BUILD,"mods":["char-yuwen-yi"]}
        (output / "_build.json").write_text(json.dumps(build))
        record = {**build,"container_sha256":hashlib.sha256(b"BUNDLE-ABUNDLE-B").hexdigest(),
                  "manifest_sha256":hashlib.sha256(b"BOUND-MANIFEST").hexdigest()}
        (self.launcher / "mods/installed.json").write_text(json.dumps(record))
        verification = {"files":[{"path":name,"kind":"bundle"} for name in ("a.ab","b.ab")]}
        return output, ab, build, record, verification

    def test_complete_merge_drift_is_refused_even_when_mod_container_is_unchanged(self):
        output, ab, build, record, verification = self.native_fixture()
        with patch("package_patch.character_gate",return_value=(None,output,build,verification)):
            REAL_BUILD()
            for variant in ("stock_pointer","duplicate_stock"):
                with self.subTest(variant=variant):
                    merge = json.loads((ab / "merge.json").read_text())
                    if variant == "stock_pointer":merge[0]["s"] = 999
                    else:merge.append(dict(merge[0]))
                    (ab / "merge.json").write_text(json.dumps(merge))
                    with self.assertRaises(play.PlayLauncherError):REAL_BUILD()
                    (ab / "merge.json").write_text(json.dumps([
                        {"r":"stock.ab","m":"stock.m","s":42},{"r":"a.ab","m":"m_mod.m","s":0},
                        {"r":"b.ab","m":"m_mod.m","s":8}]))

    def test_automatic_install_uses_exact_verified_output_instead_of_inherited_profile(self):
        output, ab, build, record, verification = self.native_fixture()
        installed = self.launcher / "mods/installed.json"
        installed.unlink()
        def simulated_install(root):
            import os
            self.assertEqual(os.environ["BBMOD_OUT"],str(output))
            installed.write_text(json.dumps(record))
        with patch("package_patch.character_gate",return_value=(None,output,build,verification)), \
             patch("play_launcher.install",side_effect=simulated_install), \
             patch.dict("os.environ",{"BBMOD_OUT":str(self.root/"wrong-profile"),"BBMOD_BUILD_ID":"WRONG"}):
            REAL_BUILD(install_if_missing=True)
            import os
            self.assertEqual(os.environ["BBMOD_OUT"],str(self.root/"wrong-profile"))
            self.assertEqual(os.environ["BBMOD_BUILD_ID"],"WRONG")


if __name__ == "__main__":
    unittest.main()
