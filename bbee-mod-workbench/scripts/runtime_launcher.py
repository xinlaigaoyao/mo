"""Prepare or restore an owned, reversible launch shortcut for the copied game.

This tool never launches a process for the game, reads proxy configuration,
changes Steam, or discovers accounts. The operator opens the shortcut normally
through Explorer after a verified runtime save guard has been established.
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

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZenithTerminal" / "Launcher"
sys.path.insert(0, str(LAUNCHER))

import runtime_guard as guard
from desktop_session import DesktopSessionError, require_unlocked
from install_transaction import TransactionError, checked_path, _hash, _locked, _replace, _write_json
from safe_install import require_closed
from save_safety import ensure_private_directory

BUILD = "25627491"
GAME = LAUNCHER / "game"
BASELINE = ROOT / "baselines" / BUILD / "manifest.json"
PRIVATE = ROOT / "private" / "runtime"
STATE = PRIVATE / "launcher.json"
PROXIES = ("Juij_Steam.dll", "version.dll", "winmm.dll")
EXE = "BlazblueEntropyEffect.exe"
APPID = b"2273430\n"
ARGUMENTS = "-screen-fullscreen 0 -screen-width 1280 -screen-height 720"


class RuntimeLauncherError(TransactionError):
    """Keep the private launch journal and restore after resolving the conflict."""


def _baseline():
    path = checked_path(BASELINE)
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("build_id") != BUILD:
        raise RuntimeLauncherError("unexpected baseline build")
    rows = manifest["files"]
    files = {row["path"]: row for row in rows}
    if len(files) != len(rows):
        raise RuntimeLauncherError("baseline contains duplicate paths")
    records = {}
    for name in (*PROXIES, EXE):
        row = files.get(name)
        if not isinstance(row, dict) or re.fullmatch(r"[a-f0-9]{64}", row.get("sha256", "")) is None:
            raise RuntimeLauncherError("baseline launch input is missing")
        records[name] = row["sha256"]
    if len({records[name] for name in PROXIES}) != 1:
        raise RuntimeLauncherError("the three copied proxies are not the known identical input")
    return hashlib.sha256(raw).hexdigest(), records


def _paths(run_id):
    if re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
        raise RuntimeLauncherError("invalid launch run identity")
    session = checked_path(PRIVATE / "launcher" / run_id)
    link = checked_path(ROOT / ("runtime-bbee-" + run_id + ".lnk"))
    return session, link


def _same_file(path, expected):
    path = checked_path(path)
    if not path.is_file() or path.stat().st_nlink != 1 or _hash(path) != expected:
        raise RuntimeLauncherError("an owned launch file differs from its recorded bytes")


def _absent(path):
    if checked_path(path).exists():
        raise RuntimeLauncherError("refusing an unknown preexisting launch file")


def _save(state):
    _write_json(checked_path(STATE), state)


def _load():
    state = json.loads(checked_path(STATE).read_text("utf-8"))
    manifest_sha, records = _baseline()
    if (state.get("version") != 1 or state.get("phase") not in {"preparing", "prepared", "restored"}
            or state.get("baseline_sha256") != manifest_sha
            or state.get("proxy_sha256") != {name: records[name] for name in PROXIES}
            or state.get("exe_sha256") != records[EXE]
            or state.get("appid_sha256") != hashlib.sha256(APPID).hexdigest()):
        raise RuntimeLauncherError("launch journal no longer matches the immutable input")
    _paths(state.get("run_id", ""))
    link_sha = state.get("link_sha256")
    if link_sha is not None and re.fullmatch(r"[a-f0-9]{64}", link_sha) is None:
        raise RuntimeLauncherError("invalid shortcut ownership hash")
    return state


def _shortcut(path, *, target=None, directory=None, arguments=None):
    """Create a Shell link file only; no ShellExecute, Start-Process or UI API."""
    if os.name != "nt":
        raise RuntimeLauncherError("the launch shortcut requires Windows")
    _absent(path)
    shell = checked_path(Path(os.environ["SYSTEMROOT"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    env = {name: value for name, value in os.environ.items()
           if name.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "SYSTEMDRIVE"}}
    scratch = checked_path(ROOT / "private/temp/shortcut")
    scratch.mkdir(parents=True, exist_ok=True)
    env.update({"TEMP": str(scratch), "TMP": str(scratch), "USERPROFILE": str(scratch),
                "APPDATA": str(scratch / "AppData/Roaming"), "LOCALAPPDATA": str(scratch / "AppData/Local"),
                "BBEE_LINK_PATH": str(path), "BBEE_LINK_TARGET": str(target or GAME / EXE),
                "BBEE_LINK_DIRECTORY": str(directory or GAME),
                "BBEE_LINK_ARGUMENTS": ARGUMENTS if arguments is None else arguments})
    script = """$ErrorActionPreference='Stop'
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($env:BBEE_LINK_PATH)
$link.TargetPath=$env:BBEE_LINK_TARGET
$link.WorkingDirectory=$env:BBEE_LINK_DIRECTORY
$link.Arguments=$env:BBEE_LINK_ARGUMENTS
$link.WindowStyle=1
$link.Save()
$read=$shell.CreateShortcut($env:BBEE_LINK_PATH)
if(($read.TargetPath -ne $env:BBEE_LINK_TARGET) -or
   ($read.WorkingDirectory -ne $env:BBEE_LINK_DIRECTORY) -or
   ($read.Arguments -ne $env:BBEE_LINK_ARGUMENTS)){throw 'Shortcut readback failed'}
"""
    result = subprocess.run([str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                            env=env, capture_output=True, text=True, errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeLauncherError("shortcut creation or readback failed; private recovery evidence retained")
    if not checked_path(path).is_file():
        raise RuntimeLauncherError("shortcut creation did not produce a regular file")
    return _hash(path)


def _record(action, state, **fields):
    value = {"status": action, "run_id": state["run_id"], **fields}
    evidence = checked_path(ROOT / "evidence")
    evidence.mkdir(exist_ok=True)
    _write_json(evidence / ("runtime-launcher-" + ("restore" if action == "restored" else "prepare") + ".json"), value)
    return value


def prepare():
    require_unlocked()  # Before even creating a private directory or lock file.
    require_closed()
    ensure_private_directory(checked_path(PRIVATE))
    with _locked(checked_path(PRIVATE / "guard-lock")):
        require_closed()
        _absent(STATE)
        active = guard._state()
        guard._backup_matches(active)
        session, link = _paths(active["run_id"])
        _absent(session)
        _absent(link)
        _absent(GAME / "steam_appid.txt")
        manifest_sha, records = _baseline()
        _same_file(GAME / EXE, records[EXE])
        for name in PROXIES:
            _same_file(GAME / name, records[name])
        ensure_private_directory(checked_path(PRIVATE / "launcher"))
        ensure_private_directory(session)
        state = {"version": 1, "run_id": active["run_id"], "phase": "preparing",
                 "baseline_sha256": manifest_sha, "exe_sha256": records[EXE],
                 "proxy_sha256": {name: records[name] for name in PROXIES},
                 "appid_sha256": hashlib.sha256(APPID).hexdigest(), "link_sha256": None}
        # Durable ownership is established before touching the copied game.
        _save(state)
        for name in PROXIES:
            require_closed()
            source, isolated = checked_path(GAME / name), checked_path(session / name)
            _same_file(source, records[name])
            _absent(isolated)
            _replace(source, isolated)
            _same_file(isolated, records[name])
        appid_pending = checked_path(session / "appid.pending")
        with appid_pending.open("xb") as stream:
            stream.write(APPID)
            stream.flush()
            os.fsync(stream.fileno())
        _same_file(appid_pending, state["appid_sha256"])
        require_closed()
        _absent(GAME / "steam_appid.txt")
        _replace(appid_pending, checked_path(GAME / "steam_appid.txt"))
        staging_link = checked_path(session / "launch.pending.lnk")
        state["link_sha256"] = _shortcut(staging_link)
        _save(state)  # Shortcut hash is durable before its public path exists.
        require_closed()
        _absent(link)
        _replace(staging_link, link)
        _same_file(link, state["link_sha256"])
        guard._backup_matches(guard._state())
        require_closed()
        state["phase"] = "prepared"
        _save(state)
        return _record("prepared", state, proxies_isolated=len(PROXIES), appid_hint_created=True,
                       shortcut=link.name, launch_performed=False, shortcut_working_directory="copied_game",
                       actual_working_directory_verified=False,
                       arguments=ARGUMENTS)


def restore():
    require_closed()
    with _locked(checked_path(PRIVATE / "guard-lock")):
        require_closed()
        state = _load()
        session, link = _paths(state["run_id"])
        appid = checked_path(GAME / "steam_appid.txt")
        staging_link = checked_path(session / "launch.pending.lnk")
        appid_pending = checked_path(session / "appid.pending")
        if session.exists():
            allowed = {*PROXIES, "appid.pending", "launch.pending.lnk"}
            if any(path.name not in allowed for path in session.iterdir()):
                raise RuntimeLauncherError("unknown files exist in the owned launch session")
        run_dir = checked_path(PRIVATE / "runs" / state["run_id"])
        if not run_dir.is_dir():
            raise RuntimeLauncherError("the launch run recovery directory is unavailable")
        archived = checked_path(run_dir / "launcher-restored.json")
        _absent(archived)
        # Validate the entire owned set before restoring any individual member.
        for name in PROXIES:
            target, isolated = checked_path(GAME / name), checked_path(session / name)
            if not target.exists() and not isolated.exists():
                raise RuntimeLauncherError("an original proxy is missing from both owned locations")
            for path in (target, isolated):
                if path.exists():
                    _same_file(path, state["proxy_sha256"][name])
        for path in (appid, appid_pending):
            if path.exists():
                _same_file(path, state["appid_sha256"])
        unbound = None
        for path in (link, staging_link):
            if path.exists():
                if state["link_sha256"] is None:
                    if path != staging_link:
                        raise RuntimeLauncherError("a public shortcut exists without a recorded ownership hash")
                    # COM may have saved the private staging file before its
                    # readback/hash was journaled. Retain those unknown bytes
                    # for inspection, without executing or deleting them.
                    fingerprint = _hash(checked_path(path))
                    _same_file(path, fingerprint)
                    destination = checked_path(run_dir / ("unbound-shortcut-" + fingerprint + ".lnk"))
                    _absent(destination)
                    unbound = (path, destination, fingerprint)
                    continue
                _same_file(path, state["link_sha256"])
        # A crash during these steps can be resumed using the same journal.
        for name in PROXIES:
            require_closed()
            target, isolated = checked_path(GAME / name), checked_path(session / name)
            if isolated.exists():
                _same_file(isolated, state["proxy_sha256"][name])
                if target.exists():
                    _same_file(target, state["proxy_sha256"][name])
                    isolated.unlink()
                else:
                    _replace(isolated, target)
            _same_file(target, state["proxy_sha256"][name])
        for path, expected in ((appid, state["appid_sha256"]), (appid_pending, state["appid_sha256"]),
                               (link, state["link_sha256"]), (staging_link, state["link_sha256"])):
            if path.exists() and expected is not None:
                require_closed()
                _same_file(path, expected)
                path.unlink()
        if unbound:
            source, destination, fingerprint = unbound
            require_closed()
            _same_file(source, fingerprint)
            _absent(destination)
            _replace(source, destination)
            _same_file(destination, fingerprint)
        require_closed()
        for name in PROXIES:
            _same_file(GAME / name, state["proxy_sha256"][name])
        _absent(appid)
        _absent(link)
        state["phase"] = "restored"
        _save(state)
        if session.exists():
            session.rmdir()  # Only an empty, explicitly owned session directory.
        _replace(checked_path(STATE), archived)
        return _record("restored", state, proxies_restored=len(PROXIES), appid_hint_removed=True,
                       owned_shortcut_removed=True, original_steam_installation_touched=False,
                       unbound_private_shortcut_quarantined=bool(unbound))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "restore"))
    options = parser.parse_args()
    try:
        result = prepare() if options.command == "prepare" else restore()
    except DesktopSessionError as exc:
        print(json.dumps({"status": "runtime_launcher_stopped", "launch_performed": False,
                          "desktop_session": exc.record, "no_launch_files_changed": True}))
        return 1
    except Exception:
        # Do not expose raw OS exceptions, private run paths or save identities.
        print(json.dumps({"status": "runtime_launcher_stopped", "launch_performed": False,
                          "private_recovery_evidence_retained": True}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
