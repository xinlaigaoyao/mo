"""Install a complete staged build with recoverable, whitelisted multi-file transactions."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import lz4.frame

from install_transaction import FileChange, TransactionError, apply_transaction, checked_path, recover_transactions


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_closed() -> None:
    if os.name != "nt":
        return
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq BlazblueEntropyEffect.exe"],
                            capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError("Cannot establish that the game is closed")
    if "blazblueentropyeffect.exe" in result.stdout.lower():
        raise RuntimeError("Close the game before installing, uninstalling or recovering files")


def read_manifest(raw: bytes):
    lines = lz4.frame.decompress(raw).decode("utf-8").splitlines()
    if lines[0] != "FastManifest V3":
        raise ValueError("Unexpected manifest format")
    count = int(lines[1][2:])
    names = lines[2:2 + count]
    cursor = 2 + count
    sections = []
    for _ in range(2):
        expected = int(lines[cursor][2:])
        cursor += 1
        records = []
        while cursor < len(lines) and not lines[cursor].startswith("N:") and lines[cursor] != "----":
            if lines[cursor].startswith(" "):
                if not records:
                    raise ValueError("Manifest child without record")
                records[-1][1].append(lines[cursor].strip())
            else:
                records.append([lines[cursor], []])
            cursor += 1
        if len(records) != expected:
            raise ValueError("Manifest record count mismatch")
        sections.append(records)
    if lines[cursor] != "----" or len(names) != len(set(names)):
        raise ValueError("Incomplete or duplicate manifest names")
    return names, sections[0], sections[1]


def augment_manifest(raw: bytes, additions: dict) -> bytes:
    names, entries, guids = read_manifest(raw)
    indexes = {name: i for i, name in enumerate(names)}
    for name in additions.get("names", []):
        if name not in indexes:
            indexes[name] = len(names)
            names.append(name)
    records = {int(key, 16): deps for key, deps in entries}
    for name, deps in additions.get("entries", []):
        if name not in indexes:
            raise ValueError(f"Manifest entry without declared name: {name}")
        if any(dep not in indexes for dep in deps):
            raise ValueError(f"Manifest dependency without declared name: {name}")
        index = indexes[name]
        encoded = [format(indexes[dep], "x") for dep in deps]
        if index in records and records[index] != encoded:
            raise ValueError(f"Conflicting dependency records: {name}")
        if index not in records:
            entries.append([format(index, "x"), encoded])
            records[index] = encoded
    guid_records = {int(key, 16): values for key, values in guids}
    for name, guid in additions.get("guids", []):
        if name not in indexes or len(guid) != 32:
            raise ValueError("Invalid manifest GUID addition")
        int(guid, 16)
        index = indexes[name]
        if index in guid_records and guid_records[index] != [guid]:
            raise ValueError(f"Conflicting GUID records: {name}")
        if index not in guid_records:
            guids.append([format(index, "x"), [guid]])
            guid_records[index] = [guid]
    for key, dependencies in entries:
        if not 0 <= int(key, 16) < len(names) or any(not 0 <= int(dep, 16) < len(names) for dep in dependencies):
            raise ValueError("Manifest dependency index out of bounds")
    lines = ["FastManifest V3", f"N:{len(names)}", *names, f"N:{len(entries)}"]
    for key, values in entries:
        lines.extend([key, *(" " + value for value in values)])
    lines.append(f"N:{len(guids)}")
    for key, values in guids:
        lines.extend([key, *(" " + value for value in values)])
    lines.extend(["----", ""])
    result = lz4.frame.compress("\r\n".join(lines).encode("utf-8"))
    if read_manifest(result) != (names, entries, guids):
        raise ValueError("Manifest write/read equivalence failed")
    return result


def paths(root: Path):
    from save_safety import ensure_private_directory
    root = root.resolve()
    game = root / "game"
    if game.resolve() != game or not game.is_dir():
        raise ValueError("Install target must be a physical game directory inside this workbench")
    ab = game / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
    state = root.parent.parent / "private" / "transactions"
    ensure_private_directory(state.parent)
    installed = root / "mods" / "installed.json"
    allowed = [ab / name for name in ("m_mod.m", "merge.json", "manifest", "merge.json.orig", "manifest.orig",
                                      "merge.json.orig.build", "manifest.orig.build")]
    allowed.append(installed)
    return ab, state, installed, allowed


def pristine(path: Path, build: str) -> Path:
    backup = path.with_name(path.name + ".orig")
    if backup.exists():
        stamp = backup.with_name(backup.name + ".build")
        if not stamp.exists() or stamp.read_text("utf-8").strip() != build:
            raise ValueError("Refusing stale or unstamped pristine backup")
        return backup
    return path


def capture_before(targets):
    """Capture trusted target preconditions before reading/assembling a plan."""
    result = {}
    for target in targets:
        path = checked_path(target)
        if path.exists():
            if not path.is_file():
                raise TransactionError("installation target is not a regular file")
            result[path] = {"expected_before_exists": True, "expected_before_sha256": digest(path)}
        else:
            result[path] = {"expected_before_exists": False}
    return result


def guarded_fault(before, read_only, fault):
    """Keep existing pristine recovery inputs unchanged without rewriting them."""
    def check(event, index):
        if fault:
            fault(event, index)
        if event in {"after_prepare", "before_commit"}:
            for path in read_only:
                checked_path(path)
                expected = before[path]
                if (path.is_file() != expected["expected_before_exists"] or
                        expected.get("expected_before_sha256") is not None and
                        (not path.is_file() or digest(path) != expected["expected_before_sha256"])):
                    raise TransactionError("pristine recovery input changed during installation planning")
    return check


def bind_baseline(root, record, before):
    path = checked_path(root / "inspect" / "baseline_manifest.json")
    content = path.read_bytes()
    fingerprint = hashlib.sha256(content).hexdigest()
    if record.get("baseline_manifest_sha256") != fingerprint:
        raise ValueError("Independent baseline changed after the verified build")
    before[path] = {"expected_before_exists": True, "expected_before_sha256": fingerprint}
    return path, json.loads(content)


def bound_extra_changes(extra_changes):
    changes = list(extra_changes)
    if any(change.expected_before_exists is None and change.expected_before_sha256 is None for change in changes):
        raise TransactionError("extra transaction changes must explicitly bind their original state")
    return changes


def install(root: str | Path, *, extra_changes=(), extra_allowed=(), fault=None):
    extra_changes = bound_extra_changes(extra_changes)
    require_closed()
    root = Path(root).resolve()
    ab, state, installed, allowed = paths(root)
    game_targets = list(allowed)
    allowed += [Path(path) for path in extra_allowed]
    recover_transactions(allowed_targets=allowed, state_dir=state)
    before = capture_before(game_targets)
    output = Path(os.environ.get("BBMOD_OUT", str(root / "patch_out"))).resolve()
    build_bytes = (output / "_build.json").read_bytes()
    build_record = json.loads(build_bytes)
    build = str(build_record["gameBuild"])
    expected = os.environ.get("BBMOD_BUILD_ID")
    if not expected or build != expected:
        raise ValueError("Explicit build binding missing or differs from staged build")
    verification = json.loads((output / "_verification.json").read_text("utf-8"))
    if verification.get("status") != "passed" or verification.get("build_id") != build:
        raise ValueError("Build output has no successful readback verification")
    metadata = verification.get("metadata_hashes", {})
    if "_build.json" not in metadata:
        raise ValueError("Build verification does not bind metadata")
    metadata_bytes = {}
    for relative, expected_digest in metadata.items():
        path = output / relative
        if relative not in ("_build.json", "_manifest_add.json") or not path.is_file():
            raise ValueError("Staged metadata changed after verification")
        content = build_bytes if relative == "_build.json" else path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_digest:
            raise ValueError("Staged metadata changed after verification")
        metadata_bytes[relative] = content
    if (output / "_manifest_add.json").exists() and "_manifest_add.json" not in metadata:
        raise ValueError("Unexpected unverified manifest additions")
    original_merge = pristine(ab / "merge.json", build)
    original_manifest = pristine(ab / "manifest", build)
    baseline_path, baseline = bind_baseline(root, build_record, before)
    if digest(original_merge) != baseline["source_merge"]["sha256"] or digest(original_manifest) != baseline["source_manifest"]["sha256"]:
        raise ValueError("Install target's pristine indexes differ from verified build input")
    pristine_merge_bytes = original_merge.read_bytes()
    pristine_manifest_bytes = original_manifest.read_bytes()
    if hashlib.sha256(pristine_merge_bytes).hexdigest() != baseline["source_merge"]["sha256"] or hashlib.sha256(pristine_manifest_bytes).hexdigest() != baseline["source_manifest"]["sha256"]:
        raise ValueError("Pristine indexes changed while reading the installation plan")
    merge = json.loads(pristine_merge_bytes)
    if any(row["m"] == "m_mod.m" for row in merge):
        raise ValueError("Pristine index points to mod container")
    indexed = {row["r"]: row for row in merge}
    patch_files = sorted(path for path in output.rglob("*") if path.is_file() and not path.name.startswith("_"))
    if not patch_files:
        raise ValueError("Empty staged build cannot be installed")
    verified = {item["path"]: item["sha256"] for item in verification["files"]}
    expected_files = {item["path"] for item in verification["files"] if item.get("kind") == "bundle"}
    if {path.relative_to(output).as_posix() for path in patch_files} != expected_files:
        raise ValueError("Staged bundle set changed after verification")
    for path in patch_files:
        if path.is_symlink() or verified.get(path.relative_to(output).as_posix()) != digest(path):
            raise ValueError("Staged output changed after verification")
    additions_path = output / "_manifest_add.json"
    additions = json.loads(metadata_bytes["_manifest_add.json"]) if "_manifest_add.json" in metadata_bytes else {}
    manifest_data = augment_manifest(pristine_manifest_bytes, additions)
    manifest_parts = read_manifest(manifest_data)
    manifest_names = set(manifest_parts[0])
    manifest_guids = {guid.lower() for _, values in manifest_parts[2] for guid in values}
    for record in verification["files"]:
        if any(guid.lower() not in manifest_guids for guid in record.get("guid_references", [])):
            raise ValueError("Verified resource references a GUID absent from the resulting manifest")
    with tempfile.TemporaryDirectory(prefix="bbmod-install-", dir=root.parent.parent / "private") as temporary:
        bundle_file = Path(temporary) / "m_mod.m"
        with bundle_file.open("wb") as stream:
            for path in patch_files:
                logical = path.relative_to(output).as_posix()
                if logical.removesuffix(".ab") not in manifest_names:
                    raise ValueError(f"Output absent from resulting manifest: {logical}")
                row = indexed.get(logical)
                if row is None:
                    row = {"r": logical, "m": "m_mod.m", "s": 0}
                    merge.append(row)
                    indexed[logical] = row
                row["m"] = "m_mod.m"
                offset = stream.tell()
                row["s"] = str(offset) if isinstance(row["s"], str) else offset
                copied_hash = hashlib.sha256()
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        copied_hash.update(chunk)
                        stream.write(chunk)
                if copied_hash.hexdigest() != verified[logical]:
                    raise ValueError("Staged bundle changed while assembling installation")
            stream.flush()
            os.fsync(stream.fileno())
        changes = []
        read_only = [baseline_path]
        for original in (ab / "merge.json", ab / "manifest"):
            backup = original.with_name(original.name + ".orig")
            stamp = backup.with_name(backup.name + ".build")
            if not before[backup]["expected_before_exists"]:
                if before[stamp]["expected_before_exists"]:
                    raise ValueError("Orphan pristine build stamp has no matching backup")
                expected_digest = baseline["source_merge" if original.name == "merge.json" else "source_manifest"]["sha256"]
                changes.extend([FileChange(backup, source=original, expected_sha256=expected_digest, **before[backup]),
                                FileChange(stamp, data=build.encode(), expected_sha256=hashlib.sha256(build.encode()).hexdigest(), **before[stamp])])
            else:
                read_only.extend([backup, stamp])
        record = {**build_record, "installed": time_stamp(), "container_sha256": digest(bundle_file),
                  "manifest_sha256": hashlib.sha256(manifest_data).hexdigest()}
        merge_data = json.dumps(merge, separators=(",", ":")).encode()
        installed_data = json.dumps(record, indent=2).encode()
        changes.extend([FileChange(ab / "m_mod.m", source=bundle_file, expected_sha256=record["container_sha256"], **before[ab / "m_mod.m"]),
                        FileChange(ab / "merge.json", data=merge_data, expected_sha256=hashlib.sha256(merge_data).hexdigest(), **before[ab / "merge.json"]),
                        FileChange(ab / "manifest", data=manifest_data, expected_sha256=record["manifest_sha256"], **before[ab / "manifest"]),
                        FileChange(installed, data=installed_data, expected_sha256=hashlib.sha256(installed_data).hexdigest(), **before[installed]), *extra_changes])
        require_closed()
        result = apply_transaction(changes, allowed_targets=allowed, state_dir=state,
                                   fault=guarded_fault(before, read_only, fault))
    return {"transaction": result, "installed_bundles": len(patch_files), "build": build}


def uninstall(root: str | Path, *, extra_changes=(), extra_allowed=(), fault=None):
    extra_changes = bound_extra_changes(extra_changes)
    require_closed()
    root = Path(root).resolve()
    ab, state, installed, allowed = paths(root)
    game_targets = list(allowed)
    allowed += [Path(path) for path in extra_allowed]
    recover_transactions(allowed_targets=allowed, state_dir=state)
    before = capture_before(game_targets)
    build = os.environ.get("BBMOD_BUILD_ID")
    if not build:
        raise ValueError("Explicit build binding required")
    originals = [pristine(ab / name, build) for name in ("merge.json", "manifest")]
    if not installed.exists() and not (ab / "m_mod.m").exists():
        return {"status": "already_uninstalled"}
    if any(not path.name.endswith(".orig") for path in originals):
        raise ValueError("Installed state has no pristine recovery pair")
    installed_bytes = checked_path(installed).read_bytes()
    if hashlib.sha256(installed_bytes).hexdigest() != before[installed]["expected_before_sha256"]:
        raise ValueError("Installed record changed while reading the uninstall plan")
    installed_record = json.loads(installed_bytes)
    if str(installed_record.get("gameBuild")) != build:
        raise ValueError("Installed record belongs to a different build")
    baseline_path, baseline = bind_baseline(root, installed_record, before)
    if digest(originals[0]) != baseline["source_merge"]["sha256"] or digest(originals[1]) != baseline["source_manifest"]["sha256"]:
        raise ValueError("Pristine recovery pair differs from verified independent baseline")
    changes = [FileChange(ab / "merge.json", source=originals[0], expected_sha256=baseline["source_merge"]["sha256"], **before[ab / "merge.json"]),
               FileChange(ab / "manifest", source=originals[1], expected_sha256=baseline["source_manifest"]["sha256"], **before[ab / "manifest"]),
               FileChange(ab / "m_mod.m", delete=True, **before[ab / "m_mod.m"]),
               FileChange(installed, delete=True, **before[installed]), *extra_changes]
    read_only = [baseline_path, *originals, *(path.with_name(path.name + ".build") for path in originals)]
    result = apply_transaction(changes, allowed_targets=allowed, state_dir=state,
                               fault=guarded_fault(before, read_only, fault))
    if digest(ab / "merge.json") != digest(originals[0]) or digest(ab / "manifest") != digest(originals[1]):
        raise ValueError("Uninstall readback differs from pristine backup")
    return {"transaction": result, "status": "uninstalled"}


def time_stamp() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
