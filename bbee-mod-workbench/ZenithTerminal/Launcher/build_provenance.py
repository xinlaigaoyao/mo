"""Bind a build to code, dependency locks and recursive enabled-mod inputs."""
import hashlib
import json
from pathlib import Path
from prepare_cache import prepare_fingerprint


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(root, order, mods, build_id):
    root = Path(root).resolve()
    common = {path.name: _sha(path) for path in sorted(root.glob("*.py"))}
    for name in ("compatibility-contracts.json", "build-input-contracts.json"):
        path = root / name
        common[name] = _sha(path) if path.is_file() else "MISSING"
    workspace = root.parent.parent
    for name in ("dependencies.lock.json", "requirements.lock.txt", "requirements.typetree.lock.txt"):
        common["workbench/" + name] = _sha(workspace / name)
    inputs = {}
    for mid in order:
        folder = Path(mods[mid]["_dir"])
        fingerprint = prepare_fingerprint(str(folder), [], str(root))
        inputs[mid] = {"descriptor_sha256": _sha(folder / "mod.json"),
                       "recursive_input_sha256": fingerprint["sha256"],
                       "input_file_count": len(fingerprint["inputs"]),
                       "input_files": fingerprint["inputs"],
                       "declared_derived_outputs": fingerprint.get("declared_derived_outputs", [])}
    return {"format": 2, "build_id": str(build_id), "workspace_root": str(root),
            "load_order": order, "common_sources": common, "mods": inputs}


def canonical_sha(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
