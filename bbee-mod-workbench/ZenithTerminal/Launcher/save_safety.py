"""Explicitly bound, byte-preserving private save backups and verified restore.

No discovery of accounts, no save decoding, and no default game save path.
The caller must deliberately bind save_root. Paths/account names and file bytes
stay inside private_dir; returned evidence contains only aggregate counts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import uuid

from install_transaction import (FileChange, TransactionError, apply_transaction,
                                 checked_path, recover_transactions, _copy_file,
                                 _hash, _key, _locked, _mkdir, _replace, _write_json)


class SaveSafetyError(TransactionError):
    """A save operation failed closed without treating missing saves as success."""


def ensure_private_directory(path) -> None:
    """Create/restrict a local evidence directory without inspecting user files."""
    _restrict_private(checked_path(path))


def _binding(root: Path) -> str:
    return hashlib.sha256(_key(root).encode("utf-8")).hexdigest()


def _within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _roots(save_root, private_dir) -> tuple[Path, Path]:
    if save_root is None or private_dir is None:
        raise SaveSafetyError("explicit save_root and private_dir are required")
    root, private = checked_path(save_root), checked_path(private_dir)
    if root == Path(root.anchor) or not root.is_dir():
        raise SaveSafetyError("save_root must explicitly name an existing non-root directory")
    if _within(private, root) or _within(root, private):
        raise SaveSafetyError("save and private backup directories must not overlap")
    return root, private


def _restrict_private(path: Path) -> None:
    """Use a user/SYSTEM-only protected Windows DACL or a POSIX 0700 directory."""
    _mkdir(path)
    if os.name != "nt":
        os.chmod(path, 0o700)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    security.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    security.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    security.ConvertSidToStringSidW.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    security.GetSecurityDescriptorDacl.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                                                   ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL))
    security.SetNamedSecurityInfoW.argtypes = (wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
                                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    security.SetNamedSecurityInfoW.restype = wintypes.DWORD
    token, sid_text, descriptor = wintypes.HANDLE(), wintypes.LPWSTR(), ctypes.c_void_p()
    try:
        if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise SaveSafetyError("could not restrict private backup directory permissions")
        required = wintypes.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        buffer = ctypes.create_string_buffer(required.value)
        if not security.GetTokenInformation(token, 1, buffer, required.value, ctypes.byref(required)):
            raise SaveSafetyError("could not identify the current backup owner")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        if not security.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise SaveSafetyError("could not identify the current backup owner")
        sddl = f"D:P(A;OICI;FA;;;{sid_text.value})(A;OICI;FA;;;SY)"
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise SaveSafetyError("could not build private backup permissions")
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        if not security.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise SaveSafetyError("could not build private backup permissions")
        if security.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
            raise SaveSafetyError("could not restrict private backup directory permissions")
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        if sid_text:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if token:
            kernel.CloseHandle(token)


def _scan(root: Path) -> list[dict]:
    result = []
    def unreadable(exc):
        raise SaveSafetyError("save tree could not be fully inspected") from exc
    for parent, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
        checked_path(parent)
        for name in directories:
            checked_path(Path(parent) / name)  # reject links instead of silently skipping
        for name in files:
            path = checked_path(Path(parent) / name)
            if not path.is_file():
                raise SaveSafetyError("save tree contains a non-regular file")
            meta = path.stat()
            result.append({"path": path.relative_to(root).as_posix(), "size": meta.st_size,
                           "mtime_ns": meta.st_mtime_ns})
    return sorted(result, key=lambda item: item["path"])


def _relative(value) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise SaveSafetyError("backup manifest contains an invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in value.split("/") or "" in value.split("/"):
        raise SaveSafetyError("backup manifest contains an invalid relative path")
    return path


def _load_backup(backup_dir) -> tuple[Path, dict]:
    backup = checked_path(backup_dir)
    if not backup.is_dir():
        raise SaveSafetyError("backup directory does not exist")
    try:
        manifest = json.loads(checked_path(backup / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("save_root_digest", "")):
            raise SaveSafetyError("unrecognized save backup manifest")
        entries = manifest["files"]
        if not entries:
            raise SaveSafetyError("empty save backup is not a successful backup")
        seen = set()
        for entry in entries:
            relative = _relative(entry["path"])
            normalized = os.path.normcase(relative.as_posix())
            if normalized in seen:
                raise SaveSafetyError("duplicate file in backup manifest")
            seen.add(normalized)
            if not isinstance(entry["size"], int) or entry["size"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise SaveSafetyError("invalid backup file metadata")
            payload = checked_path(backup / "payload" / Path(*relative.parts))
            if not payload.is_file() or payload.stat().st_size != entry["size"] or _hash(payload) != entry["sha256"]:
                raise SaveSafetyError("save backup failed read-back hash verification")
        if {os.path.normcase(item["path"]) for item in _scan(backup / "payload")} != seen:
            raise SaveSafetyError("save backup payload differs from manifest")
        return backup, manifest
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise SaveSafetyError("save backup manifest could not be verified") from exc


def verify_backup(backup_dir) -> dict:
    """Read every backed-up byte and report aggregate hash-verification evidence."""
    backup, manifest = _load_backup(backup_dir)
    return {"status": "verified", "file_count": len(manifest["files"]),
            "bytes": sum(entry["size"] for entry in manifest["files"]),
            "manifest_sha256": _hash(backup / "manifest.json")}


def _backup_locked(root: Path, private: Path, files: list[dict]) -> dict:
    if not files:
        return {"status": "no_saves", "file_count": 0, "bytes": 0, "backup_dir": None}
    name = "save-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
    temporary, destination = private / (".incomplete-" + name), private / name
    _mkdir(temporary / "payload")
    manifest = {"version": 1, "save_root_digest": _binding(root),
                "created_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    try:
        for item in files:
            source, target = checked_path(root / Path(*_relative(item["path"]).parts)), temporary / "payload" / item["path"]
            _mkdir(target.parent)
            digest = _copy_file(source, target)
            if source.stat().st_size != item["size"] or _hash(source) != digest:
                raise SaveSafetyError("save changed during backup; incomplete backup rejected")
            manifest["files"].append({"path": item["path"], "size": item["size"], "sha256": digest})
        if _scan(root) != files:
            raise SaveSafetyError("save tree changed during backup; incomplete backup rejected")
        _write_json(temporary / "manifest.json", manifest)
        verification = verify_backup(temporary)
        _replace(temporary, destination)
        return {**verification, "status": "backed_up", "backup_dir": str(destination)}
    except Exception:
        # Only this newly created private staging directory can be removed.
        checked_path(temporary)
        if temporary.exists():
            for parent, directories, names in os.walk(temporary):
                checked_path(parent)
                for filename in directories + names:
                    checked_path(Path(parent) / filename)
            shutil.rmtree(temporary)
        raise


def backup_saves(save_root, private_dir, *, dry_run: bool = False) -> dict:
    """Back up all files beneath the explicit root; empty roots return no_saves.

    Dry-run inspects relative names and sizes only, without creating private_dir
    or reading save contents. No save bytes, names or root path are printed.
    """
    root, private = _roots(save_root, private_dir)
    files = _scan(root)
    if not files:
        return {"status": "no_saves", "file_count": 0, "bytes": 0, "backup_dir": None}
    if dry_run:
        return {"status": "dry_run", "file_count": len(files), "bytes": sum(item["size"] for item in files)}
    _restrict_private(private)
    with _locked(private / ("save-lock-" + _binding(root))):
        return _backup_locked(root, private, _scan(root))


def _pending_targets(root: Path, state: Path) -> set[Path]:
    targets = set()
    if not state.exists():
        return targets
    for directory in state.iterdir():
        checked_path(directory)
        journal_path = checked_path(directory / "journal.json") if directory.is_dir() else None
        if journal_path is None or not journal_path.is_file():
            continue
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal.get("state") in {"committed", "rolled_back"}:
            continue
        for entry in journal.get("entries", []):
            target = checked_path(entry["target"])
            if target == root or not _within(target, root):
                raise SaveSafetyError("pending restore target escapes the explicitly bound save root")
            targets.add(target)
    return targets


def restore_saves(save_root, backup_dir, private_dir, *, dry_run: bool = False,
                  allow_rebind: bool = False, fault=None) -> dict:
    """Verify, snapshot the current tree, then restore the complete backed-up tree.

    Files absent from the backup are deleted within the same recoverable group.
    The existing tree is backed up before any writes. Different-root clone
    restoration requires the caller's explicit allow_rebind=True. The default
    refuses a backup bound to a different save_root.
    """
    root, private = _roots(save_root, private_dir)
    backup, manifest = _load_backup(backup_dir)
    if not _within(backup, private):
        raise SaveSafetyError("backup must be inside the explicitly chosen private directory")
    if not allow_rebind and manifest["save_root_digest"] != _binding(root):
        raise SaveSafetyError("backup is bound to a different save root")
    files = _scan(root)
    originals = {root / Path(*_relative(entry["path"]).parts): entry for entry in manifest["files"]}
    current = {root / Path(*_relative(entry["path"]).parts) for entry in files}
    if dry_run:
        return {"status": "dry_run", "write_count": len(originals), "delete_count": len(current - originals.keys()),
                "before_restore_file_count": len(files)}
    _restrict_private(private)
    with _locked(private / ("save-lock-" + _binding(root))):
        state = private / ("restore-transactions-" + _binding(root))
        pending = _pending_targets(root, state)
        if pending:
            recover_transactions(allowed_targets=pending, state_dir=state)
        files = _scan(root)
        current = {root / Path(*_relative(entry["path"]).parts) for entry in files}
        before = _backup_locked(root, private, files)
        # Bind every operation to the exact tree that was just backed up. A
        # cloud sync after that snapshot must fail rather than become a new
        # implicit original that the restore is permitted to overwrite.
        before_hashes = {}
        if before["status"] == "backed_up":
            _, before_manifest = _load_backup(before["backup_dir"])
            before_hashes = {root / Path(*_relative(entry["path"]).parts): entry["sha256"]
                             for entry in before_manifest["files"]}
        changes = [FileChange(target, source=backup / "payload" / target.relative_to(root),
                              expected_sha256=entry["sha256"],
                              expected_before_exists=target in before_hashes,
                              expected_before_sha256=before_hashes.get(target)) for target, entry in originals.items()]
        changes.extend(FileChange(target, delete=True, expected_before_exists=True,
                                  expected_before_sha256=before_hashes[target])
                       for target in sorted(current - originals.keys()))
        def verify_before_commit(event, index):
            # A complete-tree check belongs before commit so a failure restores
            # the preceding state instead of returning a failed-but-committed restore.
            if event == "before_commit":
                restored = _scan(root)
                if {item["path"] for item in restored} != {entry["path"] for entry in manifest["files"]}:
                    raise SaveSafetyError("restored tree contains unexpected files; pre-restore backup retained")
                for target, entry in originals.items():
                    if _hash(target) != entry["sha256"]:
                        raise SaveSafetyError("restored save failed hash verification; pre-restore backup retained")
            if fault:
                fault(event, index)
        result = apply_transaction(changes, allowed_targets=set(originals) | current,
                                   state_dir=state, fault=verify_before_commit)
        return {"status": "restored", "file_count": len(originals), "bytes": sum(item["size"] for item in manifest["files"]),
                "before_restore": before, "transaction_id": result["transaction_id"]}
