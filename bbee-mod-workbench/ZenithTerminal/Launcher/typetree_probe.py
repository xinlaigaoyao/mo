"""Probe the real embedded-cache route; report native generation independently.

Run during unified verification. Native generation failing a complete object
read remains a documented failure even if the embedded-cache route succeeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from verified_typetrees import CachedTypeTrees, flattened, object_identity, _semantic_hash


def layout_differences(embedded, generated):
    def paths(node):
        result, stack = {}, []
        for value in flattened(node):
            level = value["m_Level"]
            stack = stack[:level]
            stack.append(value["m_Name"])
            result["/".join(stack)] = value
        return result
    original, native = paths(embedded), paths(generated)
    changed = []
    for path in sorted(original.keys() & native.keys()):
        left, right = original[path], native[path]
        if left["m_Type"] != right["m_Type"] or bool(left.get("m_MetaFlag", 0) & 0x4000) != bool(right.get("m_MetaFlag", 0) & 0x4000):
            changed.append({"path": path, "embedded_type": left["m_Type"], "generated_type": right["m_Type"],
                            "embedded_align4": bool(left.get("m_MetaFlag", 0) & 0x4000),
                            "generated_align4": bool(right.get("m_MetaFlag", 0) & 0x4000)})
    return {"embedded_nodes": len(flattened(embedded)), "generated_nodes": len(flattened(generated)),
            "type_or_alignment_differences": changed, "missing_generated_paths": sorted(original.keys() - native.keys()),
            "extra_generated_paths": sorted(native.keys() - original.keys())}


def source_bundle(root, logical):
    from build_verification import unityfs_directory
    ab = Path(root) / "game" / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
    entries = json.loads((ab / "merge.json").read_text(encoding="utf-8"))
    selected = [entry for entry in entries if entry["r"] == logical]
    if len(selected) != 1:
        raise ValueError("TypeTree probe source bundle is not unique")
    entry = selected[0]
    physical = (ab / entry["m"]).resolve()
    if not physical.is_relative_to(ab.resolve()):
        raise ValueError("TypeTree probe physical source escapes baseline")
    start = int(entry["s"])
    ends = [int(other["s"]) for other in entries if other["m"] == entry["m"] and int(other["s"]) > start]
    end = min(ends) if ends else physical.stat().st_size
    with physical.open("rb") as stream:
        directory = unityfs_directory(stream, start, end - start, exact=False)
        stream.seek(start)
        raw = stream.read(directory["length"])
    return raw


def probe(root, build_id, *, logical="actor/logicdata/ph.ab", compare_native=True):
    import UnityPy
    root = Path(root).resolve()
    generator = CachedTypeTrees(root, build_id)
    raw = source_bundle(root, logical)
    bundle_sha = hashlib.sha256(raw).hexdigest()
    environment = UnityPy.load(raw)
    tested = []
    for obj in environment.objects:
        if obj.type.name != "MonoBehaviour" or getattr(obj.serialized_type, "node", None) is None:
            continue
        embedded = obj.read_typetree(check_read=True)
        assembly, fullname = object_identity(obj, embedded)
        if (assembly, fullname) != ("Assembly-CSharp", "GamePlay.ActionLogicGroup"):
            continue
        native_result = {"status": "not_run"}
        if compare_native:
            try:
                candidate = generator.generate_candidate(assembly, fullname)
                native_result = {"status": "generated", "layout_differences": layout_differences(obj.serialized_type.node, candidate)}
                try:
                    actual = obj.read_typetree(nodes=candidate, check_read=True)
                    native_result["complete_read"] = "passed" if _semantic_hash(actual) == _semantic_hash(embedded) else "semantic_mismatch"
                except Exception as ex:
                    native_result["complete_read"] = "failed"
                    native_result["error"] = {"type": type(ex).__name__, "message": str(ex)}
            except Exception as ex:
                native_result = {"status": "unavailable", "error": {"type": type(ex).__name__, "message": str(ex)}}
        info = generator.cache_embedded_object(obj, logical_bundle=logical, bundle_sha256=bundle_sha,
                                              expected_type=(assembly, fullname))
        def prohibited_factory(version):
            raise AssertionError("Verified cache unexpectedly initialized native generation")
        offline = CachedTypeTrees(root, build_id, inputs=generator.inputs, factory=prohibited_factory)
        cached = obj.read_typetree(nodes=offline.get_nodes_up(assembly, fullname), check_read=True)
        if _semantic_hash(cached) != _semantic_hash(embedded):
            raise ValueError("Verified offline cached layout differs from embedded object")
        tested.append({"bundle": logical, "path_id": obj.path_id, "fields": len(embedded),
                       "identity": [assembly, fullname], "native_generation": native_result,
                       "embedded_cache": info, "offline_complete_read": "passed"})
    if not tested:
        raise ValueError("No real ActionLogicGroup with a resolvable embedded layout was verified")
    return {"status": "passed", "verified_route": "embedded-layout-cache", "build_id": str(build_id),
            "inputs": generator.inputs, "objects": tested, "scope": {
                "embedded_and_offline_full_object_read": "passed with check_read=True",
                "native_generator": "independent per-object results above; not claimed generally compatible",
                "other_types_or_game_versions": "not verified by this probe"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", default=os.environ.get("BBMOD_BUILD_ID"))
    parser.add_argument("--no-native", action="store_true")
    args = parser.parse_args(argv)
    if not args.build:
        parser.error("provide --build or BBMOD_BUILD_ID explicitly")
    root = Path(__file__).resolve().parent
    record = probe(root, args.build, compare_native=not args.no_native)
    evidence = root.parent.parent / "evidence" / "typetree-probe.json"
    evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "verified_route": record["verified_route"],
                      "build_id": record["build_id"], "verified_objects": len(record["objects"]),
                      "native_full_reads": [item["native_generation"].get("complete_read", "unavailable") for item in record["objects"]],
                      "offline_complete_reads": [item["offline_complete_read"] for item in record["objects"]]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
