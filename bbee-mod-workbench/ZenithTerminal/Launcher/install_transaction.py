"""Crash-recoverable, whitelist-only transactions for a group of local files.

The caller must supply trusted *physical* target paths (no symlink/junction
components), close the game, and keep state_dir on a private local filesystem.
Files can be on different volumes: replacement is staged beside each target.
The journal is durable before any target changes, and failed/incomplete groups
roll back together. This is recoverable atomicity, not filesystem-wide atomic
visibility; a running game must never observe an applying transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Iterable
import uuid


class TransactionError(RuntimeError):
    """Invalid plan or a transaction that could not safely complete."""


class RecoveryError(TransactionError):
    """Recovery needs attention; the journal and backups have been retained."""


class TransactionLocked(TransactionError):
    """Another process owns the transaction directory lock."""


@dataclass(frozen=True)
class FileChange:
    target: str | os.PathLike
    source: str | os.PathLike | None = None
    data: bytes | None = None
    delete: bool = False
    expected_sha256: str | None = None
    expected_before_sha256: str | None = None
    expected_before_exists: bool | None = None


def checked_path(value: str | os.PathLike) -> Path:
    """Return an absolute local path, rejecting links/reparse points throughout."""
    raw = os.fspath(value)
    p = Path(raw)
    if not p.is_absolute() or ".." in p.parts:
        raise TransactionError("an absolute path without parent traversal is required")
    if os.name == "nt":
        if raw.startswith(("\\\\", "//")) or ":" in p.as_posix()[2:]:
            raise TransactionError("UNC, device and alternate-stream paths are not allowed")
    p = Path(os.path.abspath(p))
    chain = list(reversed(p.parents)) + [p]
    for component in chain:
        try:
            meta = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(meta.st_mode) or getattr(meta, "st_file_attributes", 0) & 0x400:
            raise TransactionError("symlink/junction/reparse-point paths are not allowed")
        if component != p and not stat.S_ISDIR(meta.st_mode):
            raise TransactionError("a parent path is not a directory")
    return p


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _hash(path: Path) -> str:
    checked_path(path)
    if not path.is_file():
        raise TransactionError("expected a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sync_dir(path: Path) -> None:
    # Windows does not expose a portable directory fsync. File data and journal
    # data still use FlushFileBuffers via os.fsync before os.replace.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _replace(source: Path, target: Path) -> None:
    """Same-volume replacement with write-through metadata on Windows."""
    checked_path(source)
    checked_path(target)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        kernel.MoveFileExW.restype = wintypes.BOOL
        if not kernel.MoveFileExW(str(source), str(target), 0x00000001 | 0x00000008):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, target)
    _sync_dir(target.parent)


def _mkdir(path: Path) -> list[str]:
    checked_path(path)
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    created = []
    for item in reversed(missing):
        checked_path(item)
        try:
            item.mkdir(mode=0o700)
        except FileExistsError:
            checked_path(item)
            if not item.is_dir():
                raise TransactionError("a parent path is not a directory")
        else:
            created.append(str(item))
        _sync_dir(item.parent)
    return created


def _write_json(path: Path, value: dict) -> None:
    checked_path(path)
    temp = path.with_name(path.name + ".pending-" + uuid.uuid4().hex)
    checked_path(temp)
    with temp.open("xb") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    _replace(temp, path)


def _copy_file(source: Path, target: Path, on_created=None) -> str:
    checked_path(source)
    checked_path(target)
    digest = hashlib.sha256()
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        if on_created:
            on_created()
        for block in iter(lambda: incoming.read(1024 * 1024), b""):
            outgoing.write(block)
            digest.update(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return digest.hexdigest()


@contextmanager
def _locked(state_dir: Path):
    _mkdir(state_dir)
    lock = checked_path(state_dir / ".transaction.lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    held = False
    try:
        if os.fstat(fd).st_nlink != 1:
            raise TransactionError("hard-linked transaction locks are not allowed")
        if os.fstat(fd).st_size == 0:
            os.write(fd, b" ")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise TransactionLocked("another process owns the transaction lock") from exc
        held = True
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps({"pid": os.getpid(), "created": time.time()}).encode())
        os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
        os.fsync(fd)
        yield
    finally:
        if held:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)  # OS releases the lock even after process death.


def _allowed(values: Iterable[str | os.PathLike]) -> set[str]:
    allowed = {_key(checked_path(value)) for value in values}
    if not allowed:
        raise TransactionError("the target whitelist is empty")
    return allowed


def _target(value, allowed: set[str]) -> Path:
    p = checked_path(value)
    if _key(p) not in allowed:
        raise TransactionError("target is outside the exact-path whitelist")
    if p.exists() and not p.is_file():
        raise TransactionError("targets must be regular files or absent")
    return p


def _stage(target: Path, transaction_id: str, index: int) -> Path:
    return target.with_name(f".{target.name}.bbee-stage-{transaction_id}-{index}")


def _snapshot(target: Path) -> dict:
    checked_path(target)
    if not target.exists():
        return {"exists": False}
    meta = target.stat()
    return {"exists": True, "sha256": _hash(target), "mode": stat.S_IMODE(meta.st_mode),
            "mtime_ns": meta.st_mtime_ns, "atime_ns": meta.st_atime_ns}


def _matches(target: Path, expected: dict) -> bool:
    checked_path(target)
    if not expected["exists"]:
        return not target.exists()
    return target.is_file() and _hash(target) == expected["sha256"]


def _read_journal(directory: Path, allowed: set[str]) -> dict:
    checked_path(directory)
    journal = json.loads(checked_path(directory / "journal.json").read_text(encoding="utf-8"))
    if journal.get("version") != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", journal.get("transaction_id", "")):
        raise RecoveryError("unrecognized transaction journal")
    if journal.get("state") not in {"preparing", "prepared", "applying", "committed", "rolled_back"}:
        raise RecoveryError("unrecognized transaction state")
    seen = set()
    for entry in journal["entries"]:
        p = _target(entry["target"], allowed)
        if _key(p) in seen:
            raise RecoveryError("duplicate target in transaction journal")
        seen.add(_key(p))
    for directory_name in journal.get("created_directories", []):
        p = checked_path(directory_name)
        if not any(p == Path(entry["target"]).parent or p in Path(entry["target"]).parents for entry in journal["entries"]):
            raise RecoveryError("invalid directory in transaction journal")
    return journal


def _clean_stages(journal: dict) -> None:
    for index, entry in enumerate(journal["entries"]):
        path = checked_path(_stage(Path(entry["target"]), journal["transaction_id"], index))
        if path.exists() and (entry.get("stage_owned") or entry.get("stage_reserved")):
            if not path.is_file():
                raise RecoveryError("transaction stage is not a regular file")
            path.unlink()
            _sync_dir(path.parent)


def _rollback(directory: Path, journal: dict, allowed: set[str]) -> None:
    if journal["state"] != "preparing":
        # Validate the entire group and every backup before restoring any file.
        for index, entry in enumerate(journal["entries"]):
            target = _target(entry["target"], allowed)
            original, desired = entry["original"], entry["desired"]
            if not (_matches(target, original) or _matches(target, desired)):
                raise RecoveryError("target changed outside the transaction; backups retained")
            if original["exists"]:
                backup = checked_path(directory / "backups" / f"{index:06d}.bin")
                if _hash(backup) != original["sha256"]:
                    raise RecoveryError("original backup failed hash verification; recovery stopped")
        for index in reversed(range(len(journal["entries"]))):
            entry = journal["entries"][index]
            target, original = _target(entry["target"], allowed), entry["original"]
            if _matches(target, original):
                continue
            if original["exists"]:
                backup = directory / "backups" / f"{index:06d}.bin"
                stage = checked_path(_stage(target, journal["transaction_id"], index))
                if stage.exists():
                    stage.unlink()
                _copy_file(backup, stage)
                os.chmod(stage, original["mode"])
                os.utime(stage, ns=(original["atime_ns"], original["mtime_ns"]))
                _target(target, allowed)
                _replace(stage, target)
            elif target.exists():
                target.unlink()
            _sync_dir(target.parent)
        if any(not _matches(_target(entry["target"], allowed), entry["original"]) for entry in journal["entries"]):
            raise RecoveryError("post-rollback verification failed")
    _clean_stages(journal)
    for name in reversed(journal.get("created_directories", [])):
        path = checked_path(name)
        try:
            path.rmdir()  # only empty transaction-created directories
        except (FileNotFoundError, OSError):
            pass
    journal["state"] = "rolled_back"
    _write_json(directory / "journal.json", journal)


def _recover_locked(state_dir: Path, allowed: set[str]) -> list[dict]:
    results = []
    for directory in sorted(state_dir.iterdir()):
        checked_path(directory)
        if not directory.is_dir() or not (directory / "journal.json").exists():
            continue
        try:
            # Terminal records do not authorize any writes and may belong to an
            # earlier, broader whitelist. Only pending records require recovery.
            raw = json.loads(checked_path(directory / "journal.json").read_text(encoding="utf-8"))
            if raw.get("state") in {"committed", "rolled_back"}:
                continue
            journal = _read_journal(directory, allowed)
            _rollback(directory, journal, allowed)
            results.append({"transaction_id": journal["transaction_id"], "status": "rolled_back"})
        except (OSError, ValueError, KeyError, TypeError, TransactionError) as exc:
            raise RecoveryError("pending transaction cannot be recovered safely; evidence retained") from exc
    return results


def recover_transactions(*, allowed_targets: Iterable[str | os.PathLike], state_dir: str | os.PathLike) -> list[dict]:
    """Roll back interrupted groups; committed groups remain intact."""
    allowed, state = _allowed(allowed_targets), checked_path(state_dir)
    with _locked(state):
        return _recover_locked(state, allowed)


def apply_transaction(changes: Iterable[FileChange], *, allowed_targets: Iterable[str | os.PathLike],
                      state_dir: str | os.PathLike, transaction_id: str | None = None,
                      fault: Callable[[str, int | None], None] | None = None,
                      dry_run: bool = False) -> dict:
    """Write/delete a whole group, automatically rolling back ordinary failures.

    An optional stable transaction_id makes retries idempotent. Reusing that ID
    for different bytes is rejected. ``fault(event, index)`` is a test hook;
    events: before_prepare, after_backup, after_stage, after_prepare,
    before_apply, after_apply, before_commit, after_commit.
    Exceptions roll back; process death leaves a journal for the next invocation.
    Dry-run validates the plan but creates no directory, lock, journal or stage.
    """
    allowed, state = _allowed(allowed_targets), checked_path(state_dir)
    txid = transaction_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", txid):
        raise TransactionError("invalid transaction id")
    plans, seen = [], set()
    for change in changes:
        target = _target(change.target, allowed)
        if _key(target) in seen:
            raise TransactionError("duplicate target in transaction")
        if state == target or state in target.parents or target in state.parents:
            raise TransactionError("transaction state must be separate from target files")
        seen.add(_key(target))
        if change.delete:
            if change.source is not None or change.data is not None or change.expected_sha256 is not None:
                raise TransactionError("delete cannot include new content")
            desired = {"exists": False}
        else:
            if (change.source is None) == (change.data is None):
                raise TransactionError("write requires exactly one of source or data")
            if change.data is not None and not isinstance(change.data, bytes):
                raise TransactionError("transaction data must be bytes")
            desired = {"exists": True, "sha256": _hash(checked_path(change.source)) if change.source is not None
                       else hashlib.sha256(change.data).hexdigest()}
            if change.expected_sha256 is not None:
                if not re.fullmatch(r"[0-9a-f]{64}", change.expected_sha256) or desired["sha256"] != change.expected_sha256:
                    raise TransactionError("new content does not match the required SHA256")
        plan = {"target": str(target), "desired": desired}
        if change.expected_before_exists is not None and not isinstance(change.expected_before_exists, bool):
            raise TransactionError("expected_before_exists must be a boolean")
        if change.expected_before_sha256 is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", change.expected_before_sha256) or change.expected_before_exists is False:
                raise TransactionError("invalid original-content precondition")
            plan["precondition"] = {"exists": True, "sha256": change.expected_before_sha256}
        elif change.expected_before_exists is not None:
            plan["precondition"] = {"exists": change.expected_before_exists}
        plans.append((change, plan))
    if not plans:
        raise TransactionError("transaction has no file operations")
    fingerprint = hashlib.sha256(json.dumps([plan for _, plan in plans], sort_keys=True).encode()).hexdigest()
    if dry_run:
        return {"status": "dry_run", "transaction_id": txid, "file_count": len(plans)}
    with _locked(state):
        recovered = _recover_locked(state, allowed)
        directory = checked_path(state / txid)
        if directory.exists():
            if (directory / "journal.json").exists():
                old = _read_journal(directory, allowed)
                if old["fingerprint"] != fingerprint:
                    raise TransactionError("transaction id was already used for different content")
                if old["state"] == "committed":
                    if not all(_matches(_target(entry["target"], allowed), entry["desired"]) for entry in old["entries"]):
                        raise TransactionError("committed transaction targets changed; use a new transaction id")
                    return {"status": "already_committed", "transaction_id": txid, "file_count": len(plans), "recovered": recovered}
            # A process may die after mkdir but before the initial journal. No
            # target writes can have occurred; retain that orphan as an attempt.
            archived = state / f"{txid}.attempt-{uuid.uuid4().hex}"
            _replace(directory, archived)
        for index, (_, entry) in enumerate(plans):
            stage = checked_path(_stage(Path(entry["target"]), txid, index))
            if stage.exists():
                raise FileExistsError("a reserved transaction stage already exists")
        _mkdir(directory / "backups")
        journal = {"version": 1, "transaction_id": txid, "fingerprint": fingerprint,
                   "state": "preparing", "created_directories": [], "entries": [plan for _, plan in plans]}
        _write_json(directory / "journal.json", journal)
        try:
            if fault:
                fault("before_prepare", None)
            for index, (change, entry) in enumerate(plans):
                target = _target(entry["target"], allowed)
                entry["original"] = _snapshot(target)
                precondition = entry.get("precondition")
                if precondition is not None:
                    if entry["original"]["exists"] != precondition["exists"] or (
                            precondition.get("sha256") is not None and entry["original"].get("sha256") != precondition["sha256"]):
                        raise TransactionError("target no longer matches the original-content precondition")
                if entry["original"]["exists"]:
                    saved = _copy_file(target, directory / "backups" / f"{index:06d}.bin")
                    if saved != entry["original"]["sha256"] or not _matches(target, entry["original"]):
                        raise TransactionError("target changed during original backup")
                created = _mkdir(target.parent)
                journal["created_directories"].extend(created)
                _write_json(directory / "journal.json", journal)
                if fault:
                    fault("after_backup", index)
                if entry["desired"]["exists"]:
                    stage = checked_path(_stage(target, txid, index))
                    entry["stage_reserved"] = True
                    _write_json(directory / "journal.json", journal)
                    def stage_created():
                        entry["stage_owned"] = True
                        _write_json(directory / "journal.json", journal)
                    try:
                        if change.source is not None:
                            staged_hash = _copy_file(checked_path(change.source), stage, on_created=stage_created)
                        else:
                            with stage.open("xb") as stream:
                                stage_created()
                                stream.write(change.data)
                                stream.flush()
                                os.fsync(stream.fileno())
                            staged_hash = _hash(stage)
                    except FileExistsError:
                        # An unrelated writer raced our reservation. Do not
                        # remove its file while unwinding this transaction.
                        entry["stage_reserved"] = False
                        _write_json(directory / "journal.json", journal)
                        raise
                    if staged_hash != entry["desired"]["sha256"]:
                        raise TransactionError("source changed during staging")
                    if entry["original"]["exists"]:
                        os.chmod(stage, entry["original"]["mode"])
                    _sync_dir(stage.parent)
                    if fault:
                        fault("after_stage", index)
            journal["state"] = "prepared"
            _write_json(directory / "journal.json", journal)
            if fault:
                fault("after_prepare", None)
            journal["state"] = "applying"
            _write_json(directory / "journal.json", journal)
            for index, (_, entry) in enumerate(plans):
                target = _target(entry["target"], allowed)
                if not _matches(target, entry["original"]):
                    raise TransactionError("target changed after preparation")
                if fault:
                    fault("before_apply", index)
                # Hooks model a concurrent writer after preparation. Recheck
                # immediately before mutation rather than trusting the earlier
                # check or silently adopting the hook's newer content.
                if not _matches(target, entry["original"]):
                    raise TransactionError("target changed immediately before applying the transaction")
                if entry["desired"]["exists"]:
                    stage = checked_path(_stage(target, txid, index))
                    if _hash(stage) != entry["desired"]["sha256"]:
                        raise TransactionError("staged content failed hash verification")
                    _target(target, allowed)
                    if not _matches(target, entry["original"]):
                        raise TransactionError("target changed while staged content was being verified")
                    _replace(stage, target)
                elif target.exists():
                    if not _matches(target, entry["original"]):
                        raise TransactionError("target changed immediately before deletion")
                    target.unlink()
                _sync_dir(target.parent)
                if not _matches(target, entry["desired"]):
                    raise TransactionError("applied file failed hash verification")
                if fault:
                    fault("after_apply", index)
            if fault:
                fault("before_commit", None)
            if any(not _matches(_target(entry["target"], allowed), entry["desired"])
                   for entry in journal["entries"]):
                raise TransactionError("a target changed before group commit")
            journal["state"] = "committed"
            _write_json(directory / "journal.json", journal)
        except Exception:
            _rollback(directory, journal, allowed)
            raise
        if fault:
            fault("after_commit", None)
        return {"status": "committed", "transaction_id": txid, "file_count": len(plans), "recovered": recovered}
