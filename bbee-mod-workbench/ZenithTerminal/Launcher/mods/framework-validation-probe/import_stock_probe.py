"""Stage one neutral stock-resource clone to exercise the importer contract.

No actor registration, new artwork, action edits or dependency remapping. The
clone gets a distinct infrastructure path/CAB and a new manifest record, while
all non-AssetBundle object bytes and the original stock dependency list remain
unchanged. The normal strict build verifier must read every staged object and
resolve its external references; this importer grants no verification waiver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


SOURCE = "actor/logicdata/rg"
DESTINATION = "infra/validation/stock_logic_rg"
ROOT = Path(__file__).resolve().parents[2]


def _payloads(environment):
    result = {}
    for obj in environment.objects:
        if obj.type.name == "AssetBundle":
            continue
        identity = (obj.type.name, int(obj.path_id))
        if identity in result:
            raise ValueError("stock probe encountered a duplicate object identity")
        result[identity] = obj.get_raw_data()
    if not result or not any(kind == "MonoBehaviour" for kind, _ in result):
        raise ValueError("stock logic probe has no MonoBehaviour payload to verify")
    return result


def stage_stock_probe(output):
    sys.path.insert(0, str(ROOT))
    import bbchar

    output = Path(output).resolve()
    workbench = ROOT.parents[1]
    game = (ROOT / "game").resolve()
    if not output.is_relative_to(workbench) or output == game or output.is_relative_to(game):
        raise ValueError("framework probe output must be a staging directory in this workbench, outside game")
    if output in (workbench, ROOT):
        raise ValueError("framework probe output must not be a source root")
    bound_output = os.environ.get("BBMOD_OUT")
    if bound_output and Path(bound_output).resolve() != output:
        raise ValueError("framework probe output differs from the parent build binding")
    source_raw = bbchar.bbmod.slice_bundle(bbchar.bbmod.find_entry(SOURCE + ".ab"))
    source_env = bbchar.UnityPy.load(source_raw)
    original_payloads = _payloads(source_env)
    additions = bbchar.clone_bundle(
        SOURCE, DESTINATION, str(output),
        # A complete resource path avoids replacing the short token 'rg' in
        # unrelated names. MonoBehaviour payloads remain byte-identical.
        rename=[(SOURCE, DESTINATION)], rename_objects=False,
    )
    expected_cab = "CAB-" + hashlib.md5(DESTINATION.encode()).hexdigest()
    path = output.joinpath(*DESTINATION.split("/")).with_suffix(".ab")
    clone_raw = path.read_bytes()
    clone_env = bbchar.UnityPy.load(clone_raw)
    if expected_cab not in clone_env.file.files or _payloads(clone_env) != original_payloads:
        raise ValueError("framework clone changed stock object content or has an unexpected CAB")
    names, entries, _ = bbchar.read_manifest()
    source_index = names.index(SOURCE)
    source_dependencies = next(deps for key, deps in entries if int(key, 16) == source_index)
    expected_dependencies = [names[int(value, 16)] for value in source_dependencies]
    if additions["names"] != [DESTINATION] or additions["entries"] != [(DESTINATION, expected_dependencies)]:
        raise ValueError("framework clone did not preserve the complete stock dependency contract")
    if additions.get("guids"):
        raise ValueError("neutral stock clone unexpectedly generated new GUIDs")
    print(json.dumps({"scope": "neutral_infrastructure_stock_clone", "source": SOURCE,
                      "destination": DESTINATION, "cab": expected_cab,
                      "source_sha256": hashlib.sha256(source_raw).hexdigest(),
                      "clone_sha256": hashlib.sha256(clone_raw).hexdigest(),
                      "unchanged_non_bundle_objects": len(original_payloads),
                      "stock_dependencies": len(expected_dependencies),
                      "strict_readback": "required_by_parent_build_verifier"}, sort_keys=True), flush=True)
    return additions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--adds", required=True)
    args = parser.parse_args()
    additions = stage_stock_probe(args.out)
    destination = Path(args.adds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(additions, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
