"""Private backup/restore guard for a deliberately authorized runtime check.

No account discovery or game launch occurs here. The caller closes the game and
quiesces cloud writers before begin/finish. Exact restoration covers file bytes,
relative names, directory names, mode and modification times. Access times are
written back best-effort: Windows directory path checks can themselves advance
them. Creation/change times, ACLs and a tree-wide atomic switch are excluded.
Raw logs, probe JSON, filenames, root paths and recovery evidence stay private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
import uuid

from install_transaction import (TransactionError, checked_path, _copy_file, _hash,
                                 _locked, _mkdir, _replace, _write_json)
from safe_install import require_closed
from save_safety import (backup_saves, verify_backup, restore_saves,
                         ensure_private_directory, _binding, _load_backup, _relative, _scan)

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT.parent.parent / "private"
STATE = PRIVATE / "runtime" / "guard.json"
CHECKS = ("process_started", "window_observed", "f9_triggered", "f9_report_observed")


class RuntimeGuardError(TransactionError):
    """The private guard remains available; runtime acceptance is not confirmed."""


def _now_ms():
    return time.time_ns() // 1_000_000


def write(path, value):
    _write_json(checked_path(path), value)


def _text(path, value):
    path = checked_path(path)
    temporary = checked_path(path.with_name(path.name + ".pending-" + uuid.uuid4().hex))
    with temporary.open("xb") as stream:
        stream.write(value.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    _replace(temporary, path)


def _metadata(path):
    meta = checked_path(path).stat()
    return {"mode": stat.S_IMODE(meta.st_mode), "atime_ns": meta.st_atime_ns, "mtime_ns": meta.st_mtime_ns}


def _tree(root):
    """Snapshot the entire explicit tree, hashing bytes as well as scan metadata."""
    root = checked_path(root)
    if not root.is_dir():
        raise RuntimeGuardError("the bound root is not a physical directory")
    root_stat = root.stat()
    directories = {"": _metadata(root)}
    def unreadable(exc):
        raise RuntimeGuardError("the bound tree could not be completely inspected") from exc
    for parent, names, _ in os.walk(root, followlinks=False, onerror=unreadable):
        checked_path(parent)
        for name in names:
            path = checked_path(Path(parent) / name)
            if not path.is_dir():
                raise RuntimeGuardError("the bound tree has an invalid directory")
            directories[path.relative_to(root).as_posix()] = _metadata(path)
    scanned = _scan(root)
    files = []
    for item in scanned:
        path = checked_path(root / Path(*_relative(item["path"]).parts))
        metadata = _metadata(path)
        fingerprint = _hash(path)
        final = path.stat()
        if final.st_size != item["size"] or final.st_mtime_ns != item["mtime_ns"]:
            raise RuntimeGuardError("a bound file changed while being inspected")
        files.append({**item, **metadata, "sha256": fingerprint})
    if _scan(root) != scanned:
        raise RuntimeGuardError("the bound tree changed while being inspected")
    return {"identity": {"device": root_stat.st_dev, "inode": root_stat.st_ino},
            "files": files, "directories": directories}


def _comparable(tree):
    # Hashing/enumeration may update atime. Preserve it, but do not mistake our
    # verification reads for game writes or require unchanged read timestamps.
    return {"identity": tree["identity"],
            "files": [{key: value for key, value in item.items() if key != "atime_ns"} for item in tree["files"]],
            "directories": {key: {name: value for name, value in meta.items() if name != "atime_ns"}
                            for key, meta in tree["directories"].items()}}


def _backup_matches(state):
    """Bind every restore consumption to begin's manifest and expected bytes."""
    backup = checked_path(state["backup"])
    run_dir = checked_path(state["run_dir"])
    if not backup.is_relative_to(run_dir):
        raise RuntimeGuardError("runtime backup escapes its private run directory")
    checked = verify_backup(backup)
    if checked["manifest_sha256"] != state["backup_manifest_sha256"]:
        raise RuntimeGuardError("private runtime backup manifest changed")
    _, manifest = _load_backup(backup)
    if manifest["save_root_digest"] != _binding(checked_path(state["root"])):
        raise RuntimeGuardError("private runtime backup has a different root binding")
    expected = {item["path"]: (item["size"], item["sha256"]) for item in state["before"]["files"]}
    actual = {item["path"]: (item["size"], item["sha256"]) for item in manifest["files"]}
    if actual != expected:
        raise RuntimeGuardError("private runtime backup differs from the guarded tree")
    return checked


def _state():
    state = json.loads(checked_path(STATE).read_text("utf-8"))
    if state.get("version") != 2:
        raise RuntimeGuardError("unrecognized runtime guard; keep private recovery evidence")
    try:
        uuid.UUID(hex=state["run_id"])
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeGuardError("invalid runtime run identity") from exc
    expected_run = checked_path(STATE.parent / "runs" / state["run_id"])
    if checked_path(state["run_dir"]) != expected_run:
        raise RuntimeGuardError("runtime run directory does not match its identity")
    root = checked_path(state["root"])
    if root == Path(root.anchor) or not root.is_dir():
        raise RuntimeGuardError("the guarded root is unavailable")
    if root == PRIVATE or PRIVATE in root.parents or root in PRIVATE.parents:
        raise RuntimeGuardError("private recovery evidence and guarded root overlap")
    meta = root.stat()
    if {"device": meta.st_dev, "inode": meta.st_ino} != state["before"]["identity"]:
        raise RuntimeGuardError("the guarded root directory was replaced")
    return state


def _evidence_path():
    return checked_path(ROOT.parent.parent / "evidence" / "runtime-acceptance.json")


def begin(save_root):
    require_closed()
    root = checked_path(save_root)
    if root == Path(root.anchor) or not root.is_dir():
        raise RuntimeGuardError("an explicit existing physical save directory is required")
    if root == PRIVATE or PRIVATE in root.parents or root in PRIVATE.parents:
        raise RuntimeGuardError("private recovery evidence and guarded root overlap")
    ensure_private_directory(PRIVATE)
    ensure_private_directory(STATE.parent)
    with _locked(STATE.parent / "guard-lock"):
        if checked_path(PRIVATE / "play/launcher.json").exists():
            raise RuntimeGuardError("normal play is active; finish its launch cleanup before starting a test guard")
        if checked_path(STATE).exists():
            raise RuntimeGuardError("a runtime guard is already active; restore it first")
        run_id = uuid.uuid4().hex
        run_dir = checked_path(STATE.parent / "runs" / run_id)
        ensure_private_directory(run_dir)
        before = _tree(root)
        backup = backup_saves(root, run_dir / "backups")
        if backup["status"] != "backed_up":
            raise RuntimeGuardError("no verified save backup was created; runtime acceptance did not start")
        checked = verify_backup(backup["backup_dir"])
        state = {"version": 2, "run_id": run_id, "root": str(root), "run_dir": str(run_dir),
                 "backup": backup["backup_dir"], "before": before,
                 "backup_manifest_sha256": checked["manifest_sha256"], "marks": {}}
        _backup_matches(state)
        if _comparable(_tree(root)) != _comparable(before):
            raise RuntimeGuardError("bound files changed after backup; runtime acceptance did not start")
        require_closed()
        old_probe = checked_path(STATE.parent / "probe.json")
        if old_probe.exists():
            if not old_probe.is_file():
                raise RuntimeGuardError("the previous private probe is not a regular file")
            _replace(old_probe, run_dir / "preexisting-probe.json")
        state["began_ms"] = _now_ms()
        _text(STATE.parent / "expected-root.txt", root.as_posix())
        _text(STATE.parent / "run-id.txt", run_id)
        write(STATE, state)
        evidence = _evidence_path()
        _mkdir(evidence.parent)
        if evidence.exists():
            _replace(evidence, run_dir / "previous-runtime-acceptance.json")
        write(evidence, {"status": "runtime_pending", "run_id": run_id,
                         "runtime_acceptance_passed": False, "backup_verified": True})
        record = {"status": "guarded", "run_id": run_id, "backed_up_files": backup["file_count"],
                  "backup_verified": True}
        print(json.dumps(record))
        return record


def mark(check, run_id):
    """Record an externally observed check, never arbitrary text or paths."""
    if check not in CHECKS:
        raise RuntimeGuardError("unknown runtime check")
    with _locked(checked_path(STATE.parent / "guard-lock")):
        state = _state()
        if run_id != state["run_id"]:
            raise RuntimeGuardError("runtime check belongs to a different run")
        state.setdefault("marks", {})[check] = {"run_id": run_id, "observed_ms": _now_ms()}
        write(STATE, state)
        return {"status": "marked", "run_id": run_id, "check": check}


def _probe(state):
    result = {"status": "missing", "loaded": False, "save_root_matches": False,
              "working_directory_matches": False, "is_playing": False}
    path = checked_path(STATE.parent / "probe.json")
    if not path.exists():
        return result
    try:
        first = path.stat()
        raw = path.read_bytes()
        last = path.stat()
        if (first.st_ino, first.st_size, first.st_mtime_ns) != (last.st_ino, last.st_size, last.st_mtime_ns):
            return {**result, "status": "changed_during_read"}
        probe = json.loads(raw)
        observed = probe.get("observed_ms")
        if (isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed)
                or probe.get("run_id") != state["run_id"] or observed < state["began_ms"]
                or observed > _now_ms() + 5000 or last.st_mtime_ns // 1_000_000 < state["began_ms"]):
            return {**result, "status": "stale"}
        return {"status": "current", "loaded": probe.get("status") == "loaded",
                "save_root_matches": probe.get("save_root_matches") is True,
                "working_directory_matches": probe.get("working_directory_matches") is True,
                "is_playing": probe.get("is_playing") is True}
    except (OSError, ValueError, TypeError, AttributeError):
        return {**result, "status": "invalid"}


def _verified_snapshot_backup(root, destination, tree):
    """Back up the current bytes without restoring or decoding any save."""
    root, destination = checked_path(root), checked_path(destination)
    result = backup_saves(root, destination)
    if result.get("status") != "backed_up":
        raise RuntimeGuardError("current progress has no verified backup")
    verified = verify_backup(result["backup_dir"])
    _, manifest = _load_backup(result["backup_dir"])
    expected = {item["path"]: (item["size"], item["sha256"]) for item in tree["files"]}
    actual = {item["path"]: (item["size"], item["sha256"]) for item in manifest["files"]}
    if (manifest["save_root_digest"] != _binding(root) or actual != expected
            or _comparable(_tree(root)) != _comparable(tree)):
        raise RuntimeGuardError("current progress changed while its backup was verified")
    return {"backup_dir": result["backup_dir"], **verified}


def release_preserving_progress():
    """Close a test guard while keeping current progress and both private backups.

    This is an explicit alternative to finish(), never a successful restoration
    receipt. No save file, save directory, or save metadata is written here.
    """
    require_closed()
    with _locked(checked_path(STATE.parent / "guard-lock")):
        require_closed()
        if checked_path(STATE.parent / "launcher.json").exists():
            raise RuntimeGuardError("restore the owned test launch configuration before releasing its guard")
        state = _state()
        _backup_matches(state)
        root, run_dir = checked_path(state["root"]), checked_path(state["run_dir"])
        archived = checked_path(run_dir / "preserved-state.json")
        if archived.exists():
            raise RuntimeGuardError("a previous progress release exists; retain both recovery records")
        plan = checked_path(run_dir / "progress-preservation.json")
        if plan.exists():
            preservation = json.loads(plan.read_text("utf-8"))
            if preservation.get("run_id") != state["run_id"]:
                raise RuntimeGuardError("progress backup belongs to another run")
            current = preservation["tree"]
            backup = checked_path(preservation["backup"]["backup_dir"])
            if not backup.is_relative_to(run_dir / "preserved-progress"):
                raise RuntimeGuardError("current progress backup escapes this run")
            checked = verify_backup(backup)
            if checked["manifest_sha256"] != preservation["backup"]["manifest_sha256"]:
                raise RuntimeGuardError("current progress backup manifest changed")
            _, manifest = _load_backup(backup)
            expected = {item["path"]: (item["size"], item["sha256"]) for item in current["files"]}
            actual = {item["path"]: (item["size"], item["sha256"]) for item in manifest["files"]}
            if manifest["save_root_digest"] != _binding(root) or actual != expected:
                raise RuntimeGuardError("current progress backup binding differs")
        else:
            current = _tree(root)
            preservation = {"schema": 1, "run_id": state["run_id"], "tree": current,
                            "backup": _verified_snapshot_backup(root, run_dir / "preserved-progress", current)}
            write(plan, preservation)
        require_closed()
        _backup_matches(_state())
        if _comparable(_tree(root)) != _comparable(current):
            raise RuntimeGuardError("current progress changed before releasing its guard")
        state["preserved_progress"] = {"plan": str(plan), "plan_sha256": _hash(plan)}
        write(STATE, state)
        record = {"status": "released_preserving_progress", "run_id": state["run_id"],
                  "original_backup_verified": True, "current_progress_backup_verified": True,
                  "current_progress_files": len(current["files"]), "current_progress_preserved_exactly": True,
                  "save_writes_performed": False, "save_restoration_performed": False,
                  "runtime_acceptance_passed": False,
                  "acceptance_scope": "progress preservation only; character runtime remains separate"}
        write(run_dir / "preserved-summary.json", record)
        _replace(checked_path(STATE), archived)
        write(_evidence_path(), record)
        print(json.dumps(record))
        return record


def _restore_metadata(root, before):
    expected_files = {item["path"]: item for item in before["files"]}
    for relative, metadata in expected_files.items():
        path = checked_path(root / Path(*_relative(relative).parts))
        if _hash(path) != metadata["sha256"]:
            raise RuntimeGuardError("restored bytes changed before metadata restoration")
        os.utime(path, ns=(metadata["atime_ns"], metadata["mtime_ns"]))
        os.chmod(path, metadata["mode"])
    current = _tree(root)
    expected_dirs = before["directories"]
    for relative in sorted(set(current["directories"]) - set(expected_dirs), key=lambda p: (p.count("/"), len(p)), reverse=True):
        if relative:
            checked_path(root / Path(*_relative(relative).parts)).rmdir()  # only empty generated directories
    for relative in sorted(expected_dirs, key=lambda p: (p.count("/"), len(p))):
        if relative:
            _mkdir(checked_path(root / Path(*_relative(relative).parts)))
    for relative in sorted(expected_dirs, key=lambda p: (p.count("/"), len(p)), reverse=True):
        path = root if relative == "" else checked_path(root / Path(*_relative(relative).parts))
        metadata = expected_dirs[relative]
        os.utime(path, ns=(metadata["atime_ns"], metadata["mtime_ns"]))
        os.chmod(path, metadata["mode"])
    if _comparable(_tree(root)) != _comparable(before):
        raise RuntimeGuardError("guarded tree differs after runtime restoration")
    # Final byte verification itself reads files/directories. Attempt access
    # timestamps last. Windows may advance a parent directory's atime when a
    # subsequent child path is inspected, so atime is NOT an exact guarantee.
    # Modification time, mode, full file bytes and names remain mandatory.
    nodes = [(root / Path(*_relative(item["path"]).parts), item) for item in before["files"]]
    nodes += [(root if relative == "" else root / Path(*_relative(relative).parts), meta)
              for relative, meta in sorted(expected_dirs.items(), key=lambda pair: (pair[0].count("/"), len(pair[0])), reverse=True)]
    for path, metadata in nodes:
        checked_path(path)
        try:
            os.utime(path, ns=(metadata["atime_ns"], metadata["mtime_ns"]))
        except OSError:
            # Mode/mtime were already restored above and are verified below.
            # An access-time-only attempt must not widen the exact contract.
            pass
    for path, metadata in nodes:
        actual = _metadata(path)
        if any(actual[key] != metadata[key] for key in ("mode", "mtime_ns")):
            raise RuntimeGuardError("guarded metadata differs after runtime restoration")


def finish():
    require_closed()
    with _locked(checked_path(STATE.parent / "guard-lock")):
        state = _state()
        root, run_dir = checked_path(state["root"]), checked_path(state["run_dir"])
        _backup_matches(state)
        after_run = _tree(root)
        changed = _comparable(after_run) != _comparable(state["before"])
        log = checked_path(root / "Player.log")
        if log.is_file():
            expected = next(item["sha256"] for item in after_run["files"] if item["path"] == "Player.log")
            copied = _copy_file(log, run_dir / ("Player-" + uuid.uuid4().hex + ".log"))
            if copied != expected:
                raise RuntimeGuardError("runtime log changed during private capture")
        def bind_restore_source(event, index):
            if event in {"after_prepare", "before_commit"}:
                _state()  # also reject a replacement of the bound root directory
                _backup_matches(state)
                require_closed()
        # Backup and restore share the SAME run_dir, so the containment contract
        # is satisfied. Restore first takes another private backup of run output.
        result = restore_saves(root, state["backup"], run_dir, fault=bind_restore_source) if changed else {"status": "unchanged"}
        _backup_matches(state)
        _restore_metadata(root, state["before"])
        require_closed()
        probe = _probe(state)
        checks = {check: bool(state.get("marks", {}).get(check, {}).get("run_id") == state["run_id"]
                              and state["marks"][check].get("observed_ms", -1) >= state["began_ms"])
                  for check in CHECKS}
        accepted = (probe["status"] == "current" and probe["loaded"] and probe["save_root_matches"]
                    and probe["working_directory_matches"]
                    and probe["is_playing"] and all(checks.values()))
        record = {"status": "restored_with_runtime_acceptance" if accepted else "restored_without_runtime_acceptance",
                  "run_id": state["run_id"], "backup_verified": True, "runtime_changed_files": changed,
                  "original_save_root_restored_exactly": True,
                  "restoration_scope": "file_bytes_names_directories_mode_mtime",
                  "access_time_restore_policy": "best_effort",
                  "access_times_restore_attempted": True, "access_times_verified_exactly": False,
                  "acceptance_scope": "startup_script_save_path_working_directory_and_f9_checks",
                  "restore_status": result["status"], "runtime_acceptance_passed": accepted,
                  "runtime_probe": probe, "runtime_checks": checks}
        evidence = _evidence_path()
        _mkdir(evidence.parent)
        write(evidence, record)
        write(run_dir / "finished-summary.json", record)
        _replace(checked_path(STATE), run_dir / "finished-state.json")
        print(json.dumps(record))
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("finish")
    release_parser = commands.add_parser("release")
    release_parser.add_argument("--keep-progress", action="store_true", required=True,
                                help="verify and keep current progress; never restore pre-test saves")
    begin_parser = commands.add_parser("begin")
    begin_parser.add_argument("--save-root", required=True)
    mark_parser = commands.add_parser("mark")
    mark_parser.add_argument("check", choices=CHECKS)
    mark_parser.add_argument("--run-id", required=True)
    options = parser.parse_args()
    try:
        if options.command == "begin":
            begin(options.save_root)
        elif options.command == "mark":
            print(json.dumps(mark(options.check, options.run_id)))
        elif options.command == "release":
            release_preserving_progress()
        else:
            finish()
    except Exception:
        # Underlying OS errors can contain account paths. Never expose them in
        # a public console/evidence capture; the private guard/backups remain.
        print(json.dumps({"status": "runtime_guard_stopped", "runtime_acceptance_passed": False,
                          "private_recovery_evidence_retained": True}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
