"""Reproducible BBEE build workbench. Never mutates the source game installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ZenithTerminal" / "Launcher"
PYTHON = ROOT / "ZenithTerminal" / "Interpreter" / "pythoncore-3.14-64" / "python.exe"
SOURCE_GAME = Path(r"E:\SteamLibrary\steamapps\common\BlazblueEntropyEffect")
BUILD = "25627491"
BASELINE = ROOT / "baselines" / BUILD
EVIDENCE = ROOT / "evidence"
PRIVATE = ROOT / "private"
EXCLUDED_NAMES = {"Juij_Steam.json"}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")
    os.replace(temporary, path)


def bounded(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise ValueError(f"Path outside workspace: {path}")
    return resolved


def snapshot() -> None:
    """Copy a real, immutable input snapshot and a separate writable build target."""
    if (BASELINE / "manifest.json").exists():
        print("Existing baseline; verifying instead of replacing it.", flush=True)
        verify_baseline()
        return
    target = bounded(BASELINE / "game", ROOT)
    working = bounded(LAUNCHER / "game", ROOT)
    for destination in (target, working):
        if destination.exists() and any(destination.iterdir()):
            raise RuntimeError(f"Refusing to overwrite nonempty target: {destination}")
    merge_relative = Path("BlazblueEntropyEffect_Data/StreamingAssets/ab/merge.json")
    merge = json.loads((SOURCE_GAME / merge_relative).read_text("utf-8-sig"))
    if any(row["m"] == "m_mod.m" for row in merge):
        raise RuntimeError("Source game already contains Zenith changes; baseline must be chosen explicitly")
    files = []
    total = 0
    next_progress = 1024**3
    started = time.time()
    for source in sorted(SOURCE_GAME.rglob("*")):
        if source.is_symlink() or getattr(source.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError("Refusing linked source game path")
        if not source.is_file() or source.name in EXCLUDED_NAMES:
            continue
        relative = source.relative_to(SOURCE_GAME)
        original = target / relative
        sandbox = working / relative
        original.parent.mkdir(parents=True, exist_ok=True)
        sandbox.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, original)
        digest = sha(original)
        if sha(source) != digest:
            raise RuntimeError(f"Input changed during snapshot: {relative}")
        shutil.copy2(original, sandbox)
        if sha(sandbox) != digest:
            raise RuntimeError(f"Working copy differs: {relative}")
        original.chmod(0o444)
        length = original.stat().st_size
        files.append({"path": relative.as_posix(), "bytes": length, "sha256": digest})
        total += length
        if total >= next_progress:
            print(f"Snapshot {len(files)} files, {total / 1024**3:.1f} GiB", flush=True)
            next_progress += 1024**3
    result = {"build_id": BUILD, "source_game": str(SOURCE_GAME),
              "source_authenticity": "local installation snapshot; not Steam depot certification",
              "excluded_sensitive_configuration": sorted(EXCLUDED_NAMES),
              "files": files, "total_bytes": total, "elapsed_seconds": round(time.time() - started, 2)}
    write_json(BASELINE / "manifest.json", result)
    print(f"Snapshot complete: {len(files)} files, {total} bytes", flush=True)


def verify_baseline(*, source=False) -> None:
    manifest = json.loads((BASELINE / "manifest.json").read_text("utf-8"))
    errors = []
    area = SOURCE_GAME if source else BASELINE / "game"
    expected_paths = {record["path"] for record in manifest["files"]}
    actual_paths = {path.relative_to(area).as_posix() for path in area.rglob("*")
                    if path.is_file() and path.name not in EXCLUDED_NAMES}
    if actual_paths != expected_paths:
        errors.append("File set differs from snapshot")
    for record in manifest["files"]:
        path = bounded(area / record["path"], area)
        if not path.is_file() or path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
            errors.append(record["path"])
    if errors:
        raise RuntimeError(f"{'Source game' if source else 'Independent baseline'} changed: {errors[:10]}")
    record = {"status": "passed", "files_verified": len(manifest["files"]), "source_game": source,
              "excluded_sensitive_configuration": sorted(EXCLUDED_NAMES)}
    write_json(EVIDENCE / ("source-game-final.json" if source else "baseline-final.json"), record)
    print(f"{'Source game' if source else 'Baseline'} verified: {len(manifest['files'])} file hashes", flush=True)


def cleanup() -> None:
    """Remove only named task-generated scratch areas; retain deliverables and all private backups."""
    targets = list(LAUNCHER.glob(".decode-*"))
    targets += [PRIVATE / name for name in ("temp", "compile", "build-profile", "dotnet-profile")]
    targets += [ROOT / "builds" / name for name in ("probe", "full-repeat", "withdrawal", "fixture-full-blocked")]
    targets += [ROOT / name for name in ("agent-build-verification-notes.md", "agent-composer-notes.md",
                                       "agent-recovery-notes.md", "agent-validation-notes.md")]
    for area in (LAUNCHER, ROOT / "ZenithTerminal" / "Gui", ROOT / "scripts"):
        targets += list(area.rglob("__pycache__"))
    source = ROOT / "tools" / "Il2CppDumper-6.7.46"
    if source.exists():
        targets += [source / "Il2CppDumper" / name for name in ("bin", "obj")]
    removed = []
    for target in sorted(set(targets), key=lambda path: len(path.parts), reverse=True):
        bounded(target, ROOT)
        if target == ROOT or target.is_symlink():
            raise ValueError("Unsafe cleanup target")
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(str(target.relative_to(ROOT)))
        elif target.is_file():
            target.unlink()
            removed.append(str(target.relative_to(ROOT)))
    empty_saves = bounded(PRIVATE / "test-saves", ROOT)
    if empty_saves.is_dir() and not any(empty_saves.iterdir()):
        empty_saves.rmdir()
        removed.append(str(empty_saves.relative_to(ROOT)))
    write_json(EVIDENCE / "cleanup.json", {"status": "passed", "removed": removed,
               "retained": ["source", "final builds", "evidence", "independent baseline", "private verified backups"]})
    print(f"Cleaned {len(removed)} task scratch directories", flush=True)


def environment() -> dict[str, str]:
    # Do not pass provider credentials, arbitrary Python/Node preload settings, or real profile paths to build scripts.
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
            "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
            "PROGRAMDATA", "ALLUSERSPROFILE", "SYSTEMDRIVE"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    profile = PRIVATE / "build-profile"
    temporary = PRIVATE / "temp"
    for path in (profile, temporary):
        path.mkdir(parents=True, exist_ok=True)
    env.update({"USERPROFILE": str(profile), "HOME": str(profile), "TEMP": str(temporary), "TMP": str(temporary),
                "APPDATA": str(profile / "AppData" / "Roaming"), "LOCALAPPDATA": str(profile / "AppData" / "Local"),
                "PYTHONNOUSERSITE": "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
                "BBMOD_BUILD_ID": BUILD, "BBEE_OFFLINE": "1", "BBEE_WORKBENCH": "1",
                "BBEE_SAVE_ROOT": str(PRIVATE / "test-saves"), "BBEE_ALLOW_EMPTY_SAVE": "1",
                "DOTNET_CLI_HOME": str(PRIVATE / "dotnet-profile"), "NUGET_PACKAGES": str(ROOT / "tools" / "nuget"),
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false"})
    (PRIVATE / "test-saves").mkdir(parents=True, exist_ok=True)
    return env


def run_script(relative: str, args: list[str], label: str, profile=None, output=None) -> int:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", label) is None:
        raise ValueError("Evidence label must be a simple file-safe name")
    script = bounded(LAUNCHER / relative, LAUNCHER)
    if not script.is_file() or script.suffix != ".py":
        raise ValueError("Script must be an existing Python file inside Launcher")
    EVIDENCE.mkdir(exist_ok=True)
    log = EVIDENCE / f"{label}.log"
    bootstrap = ("import faulthandler,os,runpy,sys; "
                 "sys.stdout.reconfigure(encoding='utf-8',errors='replace',line_buffering=True,write_through=True); "
                 "sys.stderr.reconfigure(encoding='utf-8',errors='replace',line_buffering=True,write_through=True); "
                 "faulthandler.enable(); faulthandler.dump_traceback_later(600,repeat=True); "
                 "p=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,os.path.dirname(p)); "
                 "runpy.run_path(p,run_name='__main__')")
    command = [str(PYTHON), "-E", "-s", "-c", bootstrap, str(script), *args]
    started = time.time()
    env = environment()
    if profile:
        path = bounded(Path(profile), ROOT)
        if not path.is_file():
            raise ValueError("Staging profile does not exist")
        env["BBMOD_PROFILE"] = str(path)
    if output:
        env["BBMOD_OUT"] = str(bounded(Path(output), ROOT))
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=LAUNCHER, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            output.write(line)
            output.flush()
            print(line, end="", flush=True)
        code = process.wait()
    recorded_command = command.copy()
    for position, argument in enumerate(recorded_command[:-1]):
        if argument == "--save-root":
            recorded_command[position + 1] = "<private-save-root>"
    write_json(EVIDENCE / f"{label}.json", {"command": recorded_command, "cwd": str(LAUNCHER), "exit_code": code,
                                           "elapsed_seconds": round(time.time() - started, 2), "log": str(log),
                                           "log_sha256": sha(log), "game_target": str(LAUNCHER / "game")})
    return code


def prepare(profile=None) -> int:
    return run_script("prepare_mods.py", [], "prepare-profile", profile=profile)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot")
    commands.add_parser("verify-baseline")
    commands.add_parser("verify-source")
    commands.add_parser("cleanup")
    preparer = commands.add_parser("prepare")
    preparer.add_argument("--profile")
    runner = commands.add_parser("run")
    runner.add_argument("--label", required=True)
    runner.add_argument("--profile")
    runner.add_argument("--output")
    runner.add_argument("script")
    runner.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot()
    elif args.command == "verify-baseline":
        verify_baseline()
    elif args.command == "verify-source":
        verify_baseline(source=True)
    elif args.command == "cleanup":
        cleanup()
    elif args.command == "prepare":
        return prepare(args.profile)
    else:
        return run_script(args.script, args.args, args.label, args.profile, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
