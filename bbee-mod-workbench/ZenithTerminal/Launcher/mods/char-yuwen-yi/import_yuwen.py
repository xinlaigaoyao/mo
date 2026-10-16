"""Explicit art preparation, or read-only-input native bundle import.

Build mode writes only the bound staging directory and private additions file.
Preparation must finish and be frozen before generator/build/acceptance runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKBENCH = ROOT.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "tools/bbtag")]
import body_source
import body_clips
import portraits


def atomic_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError("asset JSON readback mismatch")


def prepare(args):
    output = body_source.plain(body_source.PREPARED, (body_source.ASSETS,))
    if output.exists():
        raise ValueError("prepared art directory already exists; preserve/review it before a new preparation")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    try:
        production = body_source.prepare(output, args.portrait_manifest, args.authored_manifest, args.visual_review)
        ui = portraits.prepare(output, production)
        atomic_json(output / "ui-art.json", ui)
        production["ui_manifest"] = str(output / "ui-art.json")
        production["ui_manifest_sha256"] = body_source.sha(output / "ui-art.json")
        atomic_json(output / "production-manifest.json", production)
        # Read all frozen inputs/frames and exact timelines together, before
        # announcing preparation. No Unity build occurs in this phase.
        source = body_source.BodySource()
        clips = body_clips.sequences(source)
        portraits.prepared()
        print(json.dumps({"status": "art_prepared", "production": str(body_source.PRODUCTION),
                          "production_sha256": body_source.sha(body_source.PRODUCTION), "semantic_clips": len(source.contract["clips"]),
                          "animation_bundles": len(clips), "frames": len(source.frames), "world_height": 1.8,
                          "acceptance": "Native build and in-game review still required"}, ensure_ascii=False, indent=2))
    except BaseException:
        # Single shell/process end-to-end cleanup; exact owned path is verified
        # again before recursive removal. No source/reference path is removed.
        checked = body_source.plain(output, (body_source.ASSETS,))
        if checked != body_source.PREPARED or checked.parent != body_source.ASSETS:
            raise ValueError("refusing cleanup outside the exclusively owned prepared art directory")
        shutil.rmtree(checked)
        raise


def staged_readback(out, adds, source, clips):
    import bbtag_rig
    bbmod, unity = bbtag_rig._unity()
    if len(adds["names"]) != len(set(adds["names"])) or set(adds["names"]) != {path for path, _ in adds["entries"]}:
        raise ValueError("import additions have duplicate/incomplete bundle records")
    loaded, cabs = {}, {}
    for logical in adds["names"]:
        path = out / Path(*(logical + ".ab").split("/"))
        if not path.is_file() or path.stat().st_size < 32:
            raise ValueError("staged bundle missing/empty: " + logical)
        env = unity.load(path.read_bytes())
        env.typetree_generator = bbmod.typetree_gen()
        if not list(env.objects):
            raise ValueError("staged native bundle has no objects")
        loaded[logical] = env
        for cab, sf in env.file.files.items():
            if not hasattr(sf, "objects"):
                continue
            if cab.lower() in cabs:
                raise ValueError("duplicate owned serialized CAB in staged resources")
            cabs[cab.lower()] = (logical, sf)
    mesh_targets, mesh_frames, negative_mesh_frames = set(), 0, 0
    sheet_count = len([name for name in adds["names"] if name.startswith("actor/sprite/ywy/02/ywy_page_")])
    for logical, env in loaded.items():
        if logical.startswith("actor/animation/role/"):
            name = next((name for name in clips if "actor/animation/role/" + name.lower() == logical), None)
            if name is None:
                raise ValueError("unplanned native animation bundle")
            candidates = []
            for sf in env.file.files.values():
                if not hasattr(sf, "objects"):
                    continue
                for obj in sf.objects.values():
                    if obj.type.name != "MonoBehaviour":
                        continue
                    tree = obj.read_typetree()
                    if tree.get("m_Name") == name and "Frames" in tree:
                        candidates.append((sf, tree))
            if len(candidates) != 1:
                raise ValueError("native animation export not uniquely identified")
            sf, data = candidates[0]
            ends, tick = [], 0
            for _, duration in clips[name]:
                tick += duration; ends.append(tick - 1)
            if data["TotalFrameCount"] != tick or data["Indeces"] != ends or len(data["Frames"]) != len(clips[name]):
                raise ValueError("native clip lost exact source timeline: " + name)
            if data["Context"]["AnimationRoleName"] != source.contract["role"]:
                raise ValueError("native clip contains the wrong animation role: " + name)
            for frame, (key, _) in zip(data["Frames"], clips[name]):
                pointer = frame["mesh"]
                file_id, path_id = pointer["m_FileID"], pointer["m_PathID"]
                if type(file_id) is not int or file_id < 0 or type(path_id) is not int or not -(1 << 63) <= path_id < (1 << 63) or path_id == 0:
                    raise ValueError("native frame contains an invalid/null signed mesh PPtr: " + name)
                if file_id == 0:
                    target_logical, target_sf = logical, sf
                else:
                    if file_id > len(sf.externals):
                        raise ValueError("mesh PPtr external file index is outside the serialized file")
                    external = str(sf.externals[file_id - 1].path).replace("\\", "/")
                    match = re.fullmatch(r"archive:/(CAB-[a-f0-9]{32})/\1", external, re.IGNORECASE)
                    if match is None or match.group(1).lower() not in cabs:
                        raise ValueError("mesh PPtr does not resolve to a staged owned CAB: " + external)
                    target_logical, target_sf = cabs[match.group(1).lower()]
                if not target_logical.startswith("actor/mesh/ywy/"):
                    raise ValueError("animation mesh PPtr resolves outside this character's mesh bundles")
                mesh = target_sf.objects.get(path_id)
                if mesh is None or mesh.type.name != "Mesh":
                    raise ValueError("mesh PPtr resolves to an absent/wrong-class object")
                tree = mesh.read_typetree()
                if tree["m_Name"] != key or tree["m_VertexData"]["m_VertexCount"] != 4 or tree["m_IndexFormat"] != 0:
                    raise ValueError("resolved owned mesh does not match the expected source frame quad")
                vertices = bytes(tree["m_VertexData"]["m_DataSize"])
                indices = bytes(tree["m_IndexBuffer"])
                if len(vertices) != 4 * 7 * 4 or len(indices) != 12 or struct.unpack("<6H", indices) != (0, 1, 2, 0, 2, 3):
                    raise ValueError("resolved owned mesh vertex/index payload is empty or malformed")
                points = struct.unpack("<28f", vertices)
                if not all(math.isfinite(v) for v in points) or max(points[0::7]) <= min(points[0::7]) or max(points[1::7]) <= min(points[1::7]):
                    raise ValueError("resolved owned mesh quad has nonfinite or empty geometry")
                if type(frame["textureIdx"]) is not int or not 0 <= frame["textureIdx"] < sheet_count:
                    raise ValueError("native mesh frame selects an absent owned texture page")
                mesh_targets.add((target_logical, path_id))
                mesh_frames += 1
                negative_mesh_frames += int(path_id < 0)
    return {"bundles_read_back": len(adds["names"]), "animation_timelines_read_back": len(clips),
            "mesh_pptrs_resolved": mesh_frames, "unique_mesh_objects_resolved": len(mesh_targets),
            "negative_signed_mesh_pptrs_resolved": negative_mesh_frames,
            "complete_body_frames": len(source.frames), "strict_reference_closure": "Still required by parent full build verifier"}


def build(args):
    out = Path(os.path.abspath(args.out))
    bound = os.environ.get("BBMOD_OUT")
    if not bound or Path(os.path.abspath(bound)) != out:
        raise ValueError("--out must equal the parent BBMOD_OUT binding")
    if not out.is_relative_to(WORKBENCH) or out in (WORKBENCH, ROOT) or out.is_relative_to(ROOT / "game") or out.is_relative_to(HERE):
        raise ValueError("import output must be the workbench staging directory")
    body_source.plain(out, (WORKBENCH,))
    adds_path = Path(os.path.abspath(args.adds))
    if adds_path.is_relative_to(out) or adds_path.is_relative_to(HERE) or not adds_path.parent.is_dir() or adds_path.exists():
        raise ValueError("--adds must be a new private temporary JSON outside artwork/output")
    body_source.plain(adds_path, (WORKBENCH, Path(os.environ.get("TEMP", "C:/Windows/Temp"))))
    source = body_source.BodySource()
    if body_source.sha(Path(source.manifest["ui_manifest"])) != source.manifest["ui_manifest_sha256"]:
        raise ValueError("UI art changed after production freeze")
    clips = body_clips.sequences(source)
    import bbtag_rig
    checked = source.validate_cache(bbtag_rig, clips)
    # Every frame is already present and cache-verified, so build_rig's loose
    # missing-frame branch cannot replace any semantic frame with 'null'.
    adds = bbtag_rig.build_rig(source, clips, str(out), "ywy", "02", print)
    result = portraits.build(out, print)
    for key in adds:
        adds[key] += result[key]
    evidence = staged_readback(out, adds, source, clips)
    atomic_json(adds_path, adds)
    print(json.dumps({"status": "owned_art_staged", "adds": str(adds_path), "cache_frames_read_back": checked, **evidence}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", nargs="?", default="all", choices=["all"])
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--portrait-manifest", type=Path)
    ap.add_argument("--authored-manifest", type=Path)
    ap.add_argument("--visual-review", type=Path)
    ap.add_argument("--out")
    ap.add_argument("--adds")
    args = ap.parse_args()
    if args.prepare:
        if not all((args.portrait_manifest, args.authored_manifest, args.visual_review)) or args.out or args.adds:
            ap.error("--prepare requires portrait/authored/review paths and forbids build outputs")
        prepare(args)
    else:
        if not args.out or not args.adds or any((args.portrait_manifest, args.authored_manifest, args.visual_review)):
            ap.error("build mode requires --out and --adds only")
        build(args)


if __name__ == "__main__":
    main()
