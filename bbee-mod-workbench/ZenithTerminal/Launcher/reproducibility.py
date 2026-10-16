"""Stable resource identities; wall-clock execution times belong in evidence only."""
import datetime
import json
import os
from pathlib import Path
import uuid


def resource_timestamp(root):
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).isoformat()
    manifest = json.loads((Path(root) / "inspect" / "baseline_manifest.json").read_text("utf-8"))
    return manifest["created_utc"]


def rig_guid(build_id, source, target, logic_source, source_hashes):
    material = json.dumps([str(build_id), source, target, logic_source, source_hashes], separators=(",", ":"))
    return uuid.uuid5(uuid.NAMESPACE_URL, "bbee-workbench/rig/v1/" + material).hex
