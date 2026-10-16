"""Prepare enabled generated mods under the same lock as bbmod builds.

Generators read decoded current JSON/JS. Restore those files from the verified
immutable baseline before running any generator, so a previous build can never
become the next generator's source data. Cache-only runs do not rewrite them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

from prepare_cache import needs_prepare, mark_prepared
from validation_tables import validate_baseline


class PrepareError(ValueError):
    pass


def _read_descriptor(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise PrepareError(f"cannot read {path}: {ex}") from ex
    if not isinstance(value, dict):
        raise PrepareError(f"descriptor is not an object: {path}")
    return value


def discover_mods(root, extra_dirs=()):
    """Unify terminal-only, published and generated mod dependency declarations.

    Later folders have the loader's precedence: shared, mods, explicit extras.
    A terminal and mod descriptor within one folder contribute both dependency
    lists. This includes an unbuilt dependency that has no mod.json yet.
    """
    root = Path(root).resolve()
    result = {}
    for area in (root / "shared", root / "mods", *(Path(path).resolve() for path in extra_dirs)):
        if not area.is_dir():
            continue
        for folder in sorted(path for path in area.iterdir() if path.is_dir()):
            paths = [folder / name for name in ("terminal.json", "mod.json") if (folder / name).is_file()]
            if not paths:
                continue
            descriptors = [_read_descriptor(path) for path in paths]
            ids = [descriptor.get("id", folder.name) for descriptor in descriptors]
            if any(mid != folder.name for mid in ids):
                raise PrepareError(f"descriptor id must match folder name: {folder}")
            dependencies, scripts = [], []
            for descriptor in descriptors:
                for field, target in (("dependencies", dependencies), ("prepare", scripts)):
                    items = descriptor.get(field, [])
                    if not isinstance(items, list) or any(not isinstance(value, str) or not value for value in items):
                        raise PrepareError(f"{folder}: {field} must be a list of nonempty strings")
                    for item in items:
                        if item not in target:
                            target.append(item)
            result[folder.name] = {"id": folder.name, "folder": folder, "dependencies": dependencies,
                                   "prepare": scripts, "descriptors": descriptors}
    return result


def resolve_order(mods, enabled):
    if not isinstance(enabled, list) or any(not isinstance(mid, str) or not mid for mid in enabled):
        raise PrepareError("profile enabled must be a list of mod IDs")
    order, visited, stack = [], set(), []
    def visit(mid):
        if mid in visited:
            return
        if mid in stack:
            raise PrepareError("dependency cycle: " + " -> ".join(stack + [mid]))
        if mid not in mods:
            raise PrepareError(f"missing mod or terminal '{mid}', required by {stack[-1] if stack else 'profile'}")
        stack.append(mid)
        for dependency in mods[mid]["dependencies"]:
            visit(dependency)
        stack.pop()
        visited.add(mid)
        order.append(mid)
    for mid in enabled:
        visit(mid)
    return order


def generation_dependencies(root):
    root = Path(root)
    return [str(root / relative) for relative in (
        "inspect/game_build.txt", "inspect/baseline_manifest.json", "inspect/decode_report.json",
        "bbmod.py", "make_patch.py", "bbchar.py", "validation_tables.py", "composer_core.py", "native_table_keys.py", "prepare_cache.py",
        "verified_typetrees.py", "js_contracts.py", "reproducibility.py", "build_provenance.py", "table_preflight.py",
        "build-input-contracts.json")]


def restore_current_baseline(root, manifest):
    """Restore only verified .orig JS/tables, preserving identical file mtimes."""
    root = Path(root).resolve()
    restored = []
    immutable_paths = {str(PurePosixPath(relative.replace("\\", "/"))) for relative in manifest["files"]}
    for directory, suffix in (("decoded/tables", ".json"), ("decoded/tables_fixed", ".json"), ("decoded/data/js", ".js")):
        for current in (root / directory).rglob("*" + suffix):
            relative = current.relative_to(root).as_posix()
            if relative + ".orig" not in immutable_paths:
                raise PrepareError(f"current generator input has no verified immutable baseline: {relative}")
    for relative, expected in sorted(manifest["files"].items()):
        name = PurePosixPath(relative.replace("\\", "/"))
        if not relative.endswith(".orig") or not (str(name).startswith(("decoded/tables/", "decoded/tables_fixed/", "decoded/data/js/"))):
            continue
        source = (root / name).resolve()
        target = root / str(name).removesuffix(".orig")
        if not source.is_relative_to(root) or target.is_symlink() or not target.resolve().is_relative_to(root):
            raise PrepareError(f"baseline restoration path escapes root: {relative}")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise PrepareError(f"immutable baseline changed before restoration: {relative}")
        if target.is_file() and target.read_bytes() == raw:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".prepare-baseline-", dir=target.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        restored.append(target.relative_to(root).as_posix())
    return restored


def _script_path(root, script, mod, extra_dirs):
    path = Path(script)
    if path.is_absolute():
        raise PrepareError(f"{mod['id']}: prepare script must be relative to Launcher: {script}")
    path = (root / path).resolve()
    allowed = [root, *(Path(area).resolve() for area in extra_dirs)]
    if path.suffix.lower() != ".py" or not path.is_file() or not any(path.is_relative_to(area) for area in allowed):
        raise PrepareError(f"{mod['id']}: prepare script is missing/outside allowed folders: {script}")
    return path


def prepare_profile(root, profile, build_id, *, extra_dirs=(), force=False, runner=None,
                    validator=validate_baseline, needs=needs_prepare, mark=mark_prepared):
    """Execute inside bbmod.locked(..., 'prepare'); suitable for isolated tests.

    All subprocesses inherit stdout/stderr. Nothing is marked if any prepare
    script fails. Existing cache states remain unchanged until a full successful
    batch; stale fingerprints automatically remain stale after a failure.
    """
    root = Path(root).resolve()
    baseline = validator(root, str(build_id))
    mods = discover_mods(root, extra_dirs)
    if not isinstance(profile, dict):
        raise PrepareError("profile must be an object")
    order = resolve_order(mods, profile.get("enabled", []))
    dependencies = generation_dependencies(root)
    selected, cached, commands, dirty = [], [], {}, set()
    for mid in order:
        mod = mods[mid]
        for descriptor in mod["descriptors"]:
            builds = descriptor.get("gameBuilds", ["*"])
            if not isinstance(builds, list) or ("*" not in builds and str(build_id) not in builds):
                raise PrepareError(f"{mid}: descriptor is not compatible with build {build_id}")
        dependency_changed = any(dependency in dirty for dependency in mod["dependencies"])
        if not mod["prepare"]:
            if dependency_changed:
                dirty.add(mid)
            continue
        commands[mid] = [_script_path(root, script, mod, extra_dirs) for script in mod["prepare"]]
        if dependency_changed or needs(
                str(mod["folder"]), mod["prepare"], str(root), dependencies, first=force):
            selected.append(mid)
            dirty.add(mid)
        else:
            cached.append(mid)
    print(f"Prepare load order: {order}; generate: {selected}; cached: {cached}", flush=True)
    if not selected:
        return {"status": "passed", "build_id": str(build_id), "order": order, "prepared": [],
                "cached": cached, "restored_current_files": []}
    restored = restore_current_baseline(root, baseline)
    print(f"Restored {len(restored)} composed current JS/table files from verified immutable baseline", flush=True)
    runner = subprocess.run if runner is None else runner
    for mid in selected:
        for path in commands[mid]:
            print(f"Preparing {mid}: {path.relative_to(root) if path.is_relative_to(root) else path}", flush=True)
            result = runner([sys.executable, "-E", "-s", "-u", str(path)], cwd=str(root), check=False)
            code = result if isinstance(result, int) else result.returncode
            if code != 0:
                raise PrepareError(f"{mid}: prepare script failed with exit code {code}: {path.name}; no fingerprints were marked")
    # A generator must not mutate .orig/raw/schema inputs and must produce a
    # valid descriptor before any member of this batch receives a new cache.
    validator(root, str(build_id))
    for mid in selected:
        descriptor_path = mods[mid]["folder"] / "mod.json"
        generated = _read_descriptor(descriptor_path)
        if generated.get("id") != mid or any(field not in generated for field in ("name", "version")):
            raise PrepareError(f"{mid}: generator did not create a valid named/versioned mod descriptor")
    refreshed = discover_mods(root, extra_dirs)
    final_order = resolve_order(refreshed, profile.get("enabled", []))
    newly_required = [mid for mid in final_order if mid not in order and refreshed[mid]["prepare"]]
    if newly_required:
        raise PrepareError(f"generators introduced unprepared dependencies {newly_required}; declare them in terminal.json first")
    for mid in selected:
        mod = mods[mid]
        mark(str(mod["folder"]), mod["prepare"], str(root), dependencies)
    return {"status": "passed", "build_id": str(build_id), "order": final_order, "prepared": selected,
            "cached": cached, "restored_current_files": restored}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="prepare every generated mod in the effective profile")
    args = parser.parse_args(argv)
    # Import the loader only in the CLI: reuse its actual profile/build/lock,
    # while tests exercise the dependency-free functions without game I/O.
    import bbmod
    def execute():
        extra = [area for area in (os.environ.get("BBMOD_MODS_EXTRA") or "").split(os.pathsep) if area] if bbmod.STAGING else []
        return prepare_profile(bbmod.ROOT, bbmod.load_profile(), bbmod.game_build(), extra_dirs=extra, force=args.force)
    try:
        report = bbmod.locked(execute, "prepare")
        print("Prepare verified: " + json.dumps(report, ensure_ascii=False), flush=True)
        return 0
    except Exception as ex:
        print(f"PROBLEM: prepare aborted: {ex}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
