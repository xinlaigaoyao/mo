"""Verified working-copy play with persistent progress and reversible launch files.

Unlike runtime_guard.finish, normal exit never restores or edits saves. The
explicitly bound current save tree is backed up before and after play on E:.
This program is a user-invoked launcher; development never runs its play command
without desktop authorization. Paths and save identities stay in private state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import runtime_launcher as launch
from desktop_session import require_unlocked

ROOT, LAUNCHER, GAME = launch.ROOT, launch.LAUNCHER, launch.GAME
sys.path.insert(0, str(LAUNCHER))
import runtime_guard as guard
from install_transaction import checked_path, _hash, _locked, _replace, _write_json
from safe_install import require_closed, install, pristine
from save_safety import ensure_private_directory, verify_backup, _binding, _load_backup

PRIVATE = ROOT / "private/play"
STATE = PRIVATE / "launcher.json"
CONFIG = PRIVATE / "config.json"
BUILD = launch.BUILD


class PlayLauncherError(RuntimeError):
    pass


def _path(path):
    path = checked_path(path)
    if not path.is_relative_to(ROOT):
        raise PlayLauncherError("owned launch output is outside the workbench")
    return path


def _json(path):
    path = checked_path(path)
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise PlayLauncherError("a bound local record is missing or oversized")
    return json.loads(path.read_text("utf-8"))


def _root(config):
    root = checked_path(config["root"])
    if (root == Path(root.anchor) or not root.is_dir() or root.is_relative_to(ROOT)
            or ROOT.is_relative_to(root) or _binding(root) != config["root_binding"]):
        raise PlayLauncherError("explicit save binding changed or overlaps the workbench")
    return root


def configure(save_root=None, preserved_run=None):
    require_closed()
    if guard.STATE.exists() or (launch.PRIVATE / "launcher.json").exists() or STATE.exists():
        raise PlayLauncherError("finish the active test or play session before configuring normal play")
    if (save_root is None) == (preserved_run is None):
        raise PlayLauncherError("one explicit save root or preserved run is required")
    if preserved_run is not None:
        if re.fullmatch(r"[a-f0-9]{32}", preserved_run) is None:
            raise PlayLauncherError("invalid preserved run identity")
        previous = _json(launch.PRIVATE / "runs" / preserved_run / "preserved-state.json")
        if previous.get("run_id") != preserved_run:
            raise PlayLauncherError("preserved run differs")
        guard._backup_matches(previous)
        plan = checked_path(previous["preserved_progress"]["plan"])
        if (plan != checked_path(launch.PRIVATE / "runs" / preserved_run / "progress-preservation.json")
                or _hash(plan) != previous["preserved_progress"]["plan_sha256"]):
            raise PlayLauncherError("preserved progress evidence changed")
        preservation = _json(plan)
        expected_run = checked_path(launch.PRIVATE / "runs" / preserved_run)
        current_backup = checked_path(preservation["backup"]["backup_dir"])
        if (preservation.get("run_id") != preserved_run
                or not current_backup.is_relative_to(expected_run / "preserved-progress")):
            raise PlayLauncherError("preserved progress backup ownership differs")
        verified = verify_backup(current_backup)
        _, manifest = _load_backup(current_backup)
        expected = {item["path"]: (item["size"], item["sha256"]) for item in preservation["tree"]["files"]}
        actual = {item["path"]: (item["size"], item["sha256"]) for item in manifest["files"]}
        identity = checked_path(previous["root"]).stat()
        if (verified["manifest_sha256"] != preservation["backup"]["manifest_sha256"]
                or manifest["save_root_digest"] != _binding(checked_path(previous["root"]))
                or actual != expected or preservation["tree"]["identity"] != previous["before"]["identity"]
                or {"device": identity.st_dev, "inode": identity.st_ino} != preservation["tree"]["identity"]):
            raise PlayLauncherError("preserved progress backup binding differs")
        save_root = previous["root"]
    root = checked_path(save_root)
    candidate = {"schema": 1, "root": str(root), "root_binding": _binding(root),
                 "baseline_sha256": launch._baseline()[0], "source_preserved_run": preserved_run}
    _root(candidate)
    ensure_private_directory(_path(PRIVATE))
    with _locked(_path(PRIVATE / "config-lock")):
        if CONFIG.exists() and _json(CONFIG) != candidate:
            raise PlayLauncherError("refusing to replace a different existing normal-play binding")
        _write_json(_path(CONFIG), candidate)
    return {"status": "configured", "save_root_explicitly_bound": True, "save_writes_performed": False}


def _build(install_if_missing=False):
    from package_patch import character_gate
    _, output, build, verification = character_gate()
    record = LAUNCHER / "mods/installed.json"
    if not record.exists():
        if not install_if_missing:
            raise PlayLauncherError("the verified character build is not installed")
        old = {key: os.environ.get(key) for key in ("BBMOD_BUILD_ID", "BBMOD_OUT")}
        os.environ["BBMOD_BUILD_ID"] = BUILD
        os.environ["BBMOD_OUT"] = str(output)
        try:
            install(LAUNCHER)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    installed = _json(record)
    if any(installed.get(k) != value for k, value in build.items()):
        raise PlayLauncherError("installed character differs from the verified build")
    ab = GAME / "BlazblueEntropyEffect_Data/StreamingAssets/ab"
    if (_hash(checked_path(ab / "m_mod.m")) != installed["container_sha256"]
            or _hash(checked_path(ab / "manifest")) != installed["manifest_sha256"]):
        raise PlayLauncherError("installed native character bytes changed")
    expected_names = {item["path"] for item in verification["files"] if item.get("kind") == "bundle"}
    indexed = _json(ab / "merge.json")
    baseline = _json(launch.BASELINE)
    original_path = checked_path(pristine(ab / "merge.json", BUILD))
    relative = "BlazblueEntropyEffect_Data/StreamingAssets/ab/merge.json"
    original_hash = next((row["sha256"] for row in baseline["files"] if row["path"] == relative), None)
    if original_hash is None or _hash(original_path) != original_hash:
        raise PlayLauncherError("installed merge has no exact pristine baseline")
    expected_merge = _json(original_path)
    original_index = {row["r"]: row for row in expected_merge}
    if len(original_index) != len(expected_merge):
        raise PlayLauncherError("pristine merge contains duplicate resources")
    expected_offset = 0
    for name in sorted(expected_names):
        row = original_index.get(name)
        if row is None:
            row = {"r": name, "m": "m_mod.m", "s": 0}
            original_index[name] = row
            expected_merge.append(row)
        row["m"] = "m_mod.m"
        row["s"] = str(expected_offset) if isinstance(row["s"], str) else expected_offset
        expected_offset += checked_path(output / name).stat().st_size
    if indexed != expected_merge:
        raise PlayLauncherError("complete installed merge differs from the verified native layout")
    selected = [item for item in indexed if item.get("m") == "m_mod.m"]
    offset = 0
    ordered = sorted(selected, key=lambda item: int(item["s"]))
    if [item["r"] for item in ordered] != sorted(expected_names):
        raise PlayLauncherError("installed resource order or uniqueness differs")
    expected_container = hashlib.sha256()
    for item in ordered:
        if item["r"] not in expected_names or int(item["s"]) != offset:
            raise PlayLauncherError("installed container resource layout differs")
        offset += checked_path(output / item["r"]).stat().st_size
        with checked_path(output / item["r"]).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                expected_container.update(chunk)
    if {item["r"] for item in selected} != expected_names or offset != (ab / "m_mod.m").stat().st_size:
        raise PlayLauncherError("installed container resource set differs")
    if expected_container.hexdigest() != installed["container_sha256"]:
        raise PlayLauncherError("installed container differs from the verified resource bytes")
    return _hash(output / "_build.json")


def _paths(run_id):
    if re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
        raise PlayLauncherError("invalid normal-play run identity")
    return _path(PRIVATE / "runs" / run_id), _path(ROOT / ("play-bbee-" + run_id + ".lnk"))


def _read_state():
    state = _json(STATE)
    if state.get("schema") != 1 or state.get("mode") != "preserve_progress":
        raise PlayLauncherError("unrecognized normal-play recovery state")
    run_dir, link = _paths(state["run_id"])
    baseline, records = launch._baseline()
    if (state["baseline_sha256"] != baseline or state["original_files"] != records
            or state["appid_sha256"] != hashlib.sha256(launch.APPID).hexdigest()):
        raise PlayLauncherError("normal-play recovery inputs differ")
    root = _root(state)
    meta = root.stat()
    if {"device": meta.st_dev, "inode": meta.st_ino} != state["before"]["identity"]:
        raise PlayLauncherError("the normal-play save root was replaced")
    backup = checked_path(state["backup"]["backup_dir"])
    if not backup.is_relative_to(run_dir / "before-backups"):
        raise PlayLauncherError("normal-play backup ownership differs")
    if verify_backup(backup)["manifest_sha256"] != state["backup"]["manifest_sha256"]:
        raise PlayLauncherError("normal-play backup changed")
    _, manifest = _load_backup(backup)
    if manifest["save_root_digest"] != state["root_binding"]:
        raise PlayLauncherError("normal-play backup root differs")
    return state, root, run_dir, link


def prepare(install_if_missing=False):
    require_unlocked()
    require_closed()
    ensure_private_directory(_path(PRIVATE))
    with _locked(checked_path(launch.PRIVATE / "guard-lock")):
        require_closed()
        if guard.STATE.exists() or launch.STATE.exists() or STATE.exists():
            raise PlayLauncherError("a test or play session is already active")
        config = _json(CONFIG)
        root = _root(config)
        baseline, records = launch._baseline()
        if config["baseline_sha256"] != baseline:
            raise PlayLauncherError("normal-play configuration baseline changed")
        for name in (*launch.PROXIES, launch.EXE):
            launch._same_file(GAME / name, records[name])
        launch._absent(GAME / "steam_appid.txt")
        build_sha = _build(install_if_missing)
        run_id = uuid.uuid4().hex
        run_dir, link = _paths(run_id)
        ensure_private_directory(run_dir)
        before = guard._tree(root)
        backup = guard._verified_snapshot_backup(root, run_dir / "before-backups", before)
        state = {"schema": 1, "mode": "preserve_progress", "phase": "preparing", "run_id": run_id,
                 "root": str(root), "root_binding": config["root_binding"], "before": before, "backup": backup,
                 "baseline_sha256": baseline, "original_files": records, "build_record_sha256": build_sha,
                 "appid_sha256": hashlib.sha256(launch.APPID).hexdigest(), "link_sha256": None}
        _write_json(_path(STATE), state)
        isolated = run_dir / "isolated"
        ensure_private_directory(isolated)
        for name in launch.PROXIES:
            require_closed()
            launch._same_file(GAME / name, records[name])
            _replace(checked_path(GAME / name), _path(isolated / name))
        appid = _path(run_dir / "appid.pending")
        with appid.open("xb") as stream:
            stream.write(launch.APPID)
            stream.flush()
            os.fsync(stream.fileno())
        require_closed()
        launch._absent(GAME / "steam_appid.txt")
        _replace(appid, checked_path(GAME / "steam_appid.txt"))
        staged = _path(run_dir / "launch.pending.lnk")
        arguments = launch.ARGUMENTS + ' -logFile "' + str(run_dir / "Player.log") + '"'
        state["link_sha256"] = launch._shortcut(staged, arguments=arguments)
        state["arguments"] = arguments
        _write_json(_path(STATE), state)
        launch._absent(link)
        _replace(staged, link)
        if guard._comparable(guard._tree(root)) != guard._comparable(before):
            raise PlayLauncherError("saves changed during launch preparation")
        state["phase"] = "prepared"
        _write_json(_path(STATE), state)
        return {"status": "prepared", "run_id": run_id, "progress_policy": "preserve",
                "launch_performed": False, "save_writes_performed": False,
                "shortcut": link.name, "build_record_sha256": build_sha}


def finish():
    require_closed()
    with _locked(checked_path(launch.PRIVATE / "guard-lock")):
        require_closed()
        state, root, run_dir, link = _read_state()
        launch._absent(_path(run_dir / "finished-state.json"))
        launch._absent(_path(run_dir / "finished-summary.json"))
        current = guard._tree(root)
        after = guard._verified_snapshot_backup(root, run_dir / "after-backups", current)
        isolated = run_dir / "isolated"
        if isolated.exists() and any(p.name not in launch.PROXIES for p in isolated.iterdir()):
            raise PlayLauncherError("unknown files exist in the owned launch isolation")
        for name in launch.PROXIES:
            target, copy = checked_path(GAME / name), _path(isolated / name)
            if not target.exists() and not copy.exists():
                raise PlayLauncherError("original launch input is missing")
            for path in (target, copy):
                if path.exists():
                    launch._same_file(path, state["original_files"][name])
        owned = [(GAME / "steam_appid.txt", state["appid_sha256"]),
                 (run_dir / "appid.pending", state["appid_sha256"]),
                 (link, state["link_sha256"]), (run_dir / "launch.pending.lnk", state["link_sha256"])]
        unbound = []
        for path, expected in owned:
            if checked_path(path).exists():
                if expected is None:
                    if Path(path) != run_dir / "launch.pending.lnk":
                        raise PlayLauncherError("an unbound public shortcut exists")
                    fingerprint = _hash(checked_path(path))
                    launch._same_file(path, fingerprint)
                    destination = _path(run_dir / ("unbound-shortcut-" + fingerprint + ".lnk"))
                    launch._absent(destination)
                    unbound.append((checked_path(path), destination, fingerprint))
                    continue
                launch._same_file(path, expected)
        for name in launch.PROXIES:
            require_closed()
            target, copy = checked_path(GAME / name), _path(isolated / name)
            if copy.exists():
                if target.exists():
                    copy.unlink()
                else:
                    _replace(copy, target)
            launch._same_file(target, state["original_files"][name])
        for path, expected in owned:
            path = checked_path(path)
            if path.exists() and expected is not None:
                require_closed()
                launch._same_file(path, expected)
                path.unlink()
        for path, destination, fingerprint in unbound:
            require_closed()
            launch._same_file(path, fingerprint)
            launch._absent(destination)
            _replace(path, destination)
            launch._same_file(destination, fingerprint)
        require_closed()
        if guard._comparable(guard._tree(root)) != guard._comparable(current):
            raise PlayLauncherError("current progress changed during launch cleanup")
        if isolated.exists():
            isolated.rmdir()
        result = {"status": "finished_preserving_progress", "run_id": state["run_id"],
                  "build_record_sha256": state["build_record_sha256"], "save_writes_performed": False,
                  "progress_preserved_exactly": True, "before_backup_verified": True,
                  "after_backup_verified": True, "launch_configuration_restored": True,
                  "unbound_private_shortcut_quarantined": bool(unbound),
                  "character_remains_installed": (LAUNCHER / "mods/installed.json").exists(),
                  "runtime_acceptance_passed": False}
        state.update(phase="finished", after=after, current=current)
        _write_json(_path(STATE), state)
        _replace(_path(STATE), _path(run_dir / "finished-state.json"))
        _write_json(_path(run_dir / "finished-summary.json"), result)
        _write_json(_path(ROOT / "evidence/play-session.json"), result)
        return result


def play():
    prepared = prepare(install_if_missing=True)
    run_dir, _ = _paths(prepared["run_id"])
    # Construct argv directly so a path containing spaces remains one argument.
    command = [str(GAME / launch.EXE), "-screen-fullscreen", "0", "-screen-width", "1280",
               "-screen-height", "720", "-logFile", str(run_dir / "Player.log")]
    code = None
    try:
        keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "SYSTEMDRIVE", "PROGRAMFILES",
                "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
                "PROGRAMDATA", "ALLUSERSPROFILE", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        environment = {key: value for key, value in os.environ.items() if key.upper() in keep}
        temporary = _path(ROOT / "private/temp/play")
        temporary.mkdir(parents=True, exist_ok=True)
        environment.update(TEMP=str(temporary), TMP=str(temporary))
        process = subprocess.Popen(command, cwd=GAME, env=environment)
        code = process.wait()
    finally:
        result = finish()
    return {**result, "game_exit_code": code}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("configure")
    source = config.add_mutually_exclusive_group(required=True)
    source.add_argument("--save-root")
    source.add_argument("--from-preserved-run")
    commands.add_parser("prepare")
    commands.add_parser("play")
    commands.add_parser("finish")
    options = parser.parse_args()
    try:
        if options.command == "configure":
            result = configure(options.save_root, options.from_preserved_run)
        elif options.command == "prepare":
            result = prepare()
        else:
            result = play() if options.command == "play" else finish()
    except Exception:
        print(json.dumps({"status": "normal_play_stopped", "private_recovery_evidence_retained": True,
                          "saves_not_restored_or_overwritten": True}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
