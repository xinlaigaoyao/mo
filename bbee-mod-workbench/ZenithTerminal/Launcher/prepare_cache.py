"""Content fingerprints for generated mod descriptors, shared by CLI and GUI.

API: needs_prepare(folder, scripts, launcher, dependency_files=(), first=False)
and mark_prepared(folder, scripts, launcher, dependency_files=()).  Mark only
after every prepare script for that mod exited successfully. No game/save I/O.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

STATE_NAME = ".prepare-state.json"
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}


class InputContractError(RuntimeError):
    """A reviewed exclusion no longer matches its exact producer/reader inputs."""
    pass


def _digest(path):
    sha = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _contract_path(value):
    if not isinstance(value, str) or not value or any(character in value for character in "\\:*?[]"):
        raise InputContractError("derived input contracts require exact, relative POSIX paths without patterns")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != value:
        raise InputContractError("derived input contract path escapes or is not canonical: " + value)
    return value


def _derived_contract(folder, launcher):
    """Load only a reviewed, build-bound, exact-file output declaration.

    Every declared producer/possible consumer is hash-bound. A code change must
    be reviewed again rather than silently reusing an old output exclusion.
    RuntimeError intentionally escapes needs_prepare's stale-cache handling.
    """
    path = Path(launcher) / "build-input-contracts.json"
    if not path.exists():
        return set(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise InputContractError(f"cannot read build input contracts: {ex}") from ex
    if not isinstance(data, dict) or data.get("format") != 1 or data.get("status") != "reviewed" or not isinstance(data.get("mods"), dict):
        raise InputContractError("build input contracts must use reviewed format 1")
    marker = Path(launcher) / "inspect" / "game_build.txt"
    if not marker.is_file() or data.get("build_id") != marker.read_text(encoding="utf-8").strip():
        raise InputContractError("build input contract does not match the verified baseline build")
    entry = data["mods"].get(Path(folder).name)
    if entry is None:
        return set(), None
    if not isinstance(entry, dict) or not isinstance(entry.get("derived_outputs"), list) or not isinstance(entry.get("bound_sources"), dict) or not entry["bound_sources"]:
        raise InputContractError("derived output contract needs exact outputs and hash-bound producer/reader sources")
    outputs = set()
    for output in entry["derived_outputs"]:
        if not isinstance(output, dict) or output.get("phase") != "build-diagnostic":
            raise InputContractError("derived output contract must explicitly declare build-diagnostic phase")
        relative = _contract_path(output.get("path"))
        if relative in ("mod.json", STATE_NAME) or relative in outputs:
            raise InputContractError("invalid or duplicate derived output path: " + relative)
        outputs.add(relative)
    area = Path(folder).resolve()
    for relative, expected in entry["bound_sources"].items():
        relative = _contract_path(relative)
        source = area / relative
        if relative in outputs or source.is_symlink() or not source.resolve().is_relative_to(area) or not source.is_file():
            raise InputContractError("invalid hash-bound derived output producer/reader: " + relative)
        if not isinstance(expected, str) or len(expected) != 64 or _digest(source) != expected.lower():
            raise InputContractError("derived output producer/reader changed; review its input contract: " + relative)
    return outputs, _digest(path)


def prepare_fingerprint(folder, scripts, launcher, dependency_files=()):
    """Hash recursive inputs and names, detecting additions, deletions and edits.

    The generated mod.json and this cache are excluded. Generated side assets
    remain inputs unless one exact, reviewed, source-hash-bound diagnostic
    output declaration applies. Whole gen directories are never ignored.
    Explicit prepare scripts outside the mod folder are hashed as well.
    """
    inputs = {}
    derived, contract_sha = _derived_contract(folder, launcher)
    for current, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        if any(os.path.islink(os.path.join(current, name)) for name in dirs):
            raise ValueError("prepare input directory contains a symlink; declare and fingerprint its inputs explicitly")
        for name in sorted(files):
            path = os.path.join(current, name)
            relative = os.path.relpath(path, folder).replace("\\", "/")
            if os.path.islink(path):
                raise InputContractError("mod input or declared diagnostic output must not be a symlink: " + relative)
            if relative in ("mod.json", STATE_NAME) or name.startswith(STATE_NAME + "."):
                continue
            if relative in derived:
                continue
            inputs["mod/" + relative] = _digest(path)
    if contract_sha is not None:
        inputs["contract/build-input-contracts.json"] = contract_sha
    for position, script in enumerate(scripts):
        path = os.path.abspath(os.path.join(launcher, *str(script).split("/")))
        inputs[f"script/{position}/{script}"] = _digest(path) if os.path.isfile(path) else "MISSING"
    for position, path in enumerate(dependency_files):
        inputs[f"dependency/{position}/{os.path.abspath(path)}"] = _digest(path) if os.path.isfile(path) else "MISSING"
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    result = {"version": 2 if contract_sha is not None else 1,
              "sha256": hashlib.sha256(canonical).hexdigest(), "inputs": inputs}
    if contract_sha is not None:
        result["declared_derived_outputs"] = sorted(derived)
    return result


def needs_prepare(folder, scripts, launcher, dependency_files=(), first=False):
    if not scripts:
        return False
    if first or not os.path.isfile(os.path.join(folder, "mod.json")):
        return True
    try:
        with open(os.path.join(folder, STATE_NAME), encoding="utf-8") as stream:
            previous = json.load(stream)
        return previous != prepare_fingerprint(folder, scripts, launcher, dependency_files)
    except (OSError, ValueError):
        return True


def mark_prepared(folder, scripts, launcher, dependency_files=()):
    if not os.path.isfile(os.path.join(folder, "mod.json")):
        raise ValueError(f"prepare finished without creating {os.path.join(folder, 'mod.json')}")
    state = prepare_fingerprint(folder, scripts, launcher, dependency_files)
    if any(value == "MISSING" for key, value in state["inputs"].items() if key.startswith("script/")):
        raise ValueError("prepare script missing; cannot record successful generation")
    destination = os.path.join(folder, STATE_NAME)
    fd, temporary = tempfile.mkstemp(prefix=STATE_NAME + ".", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, sort_keys=True, ensure_ascii=False, indent=1)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return state
