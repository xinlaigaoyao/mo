"""Narrow, hash-bound approvals for intentionally repeated baseline JS anchors."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def bind_spec(spec, mod_id, logical, root, build_id, baseline_bytes):
    result = deepcopy(spec)
    path = Path(root) / "compatibility-contracts.json"
    if not path.exists():
        return result
    contracts = json.loads(path.read_text("utf-8"))
    if contracts.get("status") != "reviewed" or contracts.get("build_id") != str(build_id):
        return result
    baseline_hash = hashlib.sha256(baseline_bytes).hexdigest()
    replacements = []
    for replacement in result.get("replace", []):
        if isinstance(replacement, dict):
            old, new = replacement["old"], replacement["new"]
        else:
            old, new = replacement[:2]
        match = next((item for item in contracts.get("contracts", [])
                      if item["mod"] == mod_id and item["file"] == logical
                      and item["baseline_module_sha256"] == baseline_hash
                      and item["anchor_sha256"] == hashlib.sha256(old.encode()).hexdigest()
                      and item["anchor"] == old and item["replacement"] == new), None)
        if match is not None:
            replacement = {"old": old, "new": new, "expectedCount": match["expectedCount"]}
        replacements.append(replacement)
    result["replace"] = replacements
    return result
