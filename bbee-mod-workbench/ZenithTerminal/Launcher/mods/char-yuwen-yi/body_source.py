"""Hash-bound, complete Yuwen Yi pixels for the native sprite rig builder.

Preparation is explicit and separate from a build. A build consumes immutable
prepared art and never extracts source game files, synthesizes missing poses,
changes mod.json, applies a manifest or changes character timings.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import stat

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKBENCH = ROOT.parents[1]
ASSETS = HERE / "assets"
PREPARED = ASSETS / "prepared"
PRODUCTION = PREPARED / "production-manifest.json"
CONTRACT = HERE / "character-contract.json"
PAK_SHA = "5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff"
BODY_MANIFEST = WORKBENCH / "references/wandering-sword/20261015T133053Z-487eeab89890/manifest.json"
BODY_SHA = "c53f67f143e03b8cbb598671368de13f241e2dcfb60870bc8c9a054c46f253dc"
REFERENCE_ROOT = WORKBENCH / "references/wandering-sword"
UPSCALE = 8
TARGET_HEIGHT = 1.8


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(path, roots=(ASSETS, REFERENCE_ROOT)):
    path = Path(os.path.abspath(path))
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError("asset path is outside the explicit reference/art roots: " + str(path))
    for item in [path, *path.parents]:
        if item.exists() and (item.is_symlink() or getattr(item.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("asset path contains a link/reparse point: " + str(item))
        if item == WORKBENCH:
            break
    return path


def read_json(path, expected=None, roots=(ASSETS, REFERENCE_ROOT)):
    path = plain(path, roots)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("asset manifest missing/oversized: " + str(path))
    if expected and sha(path) != expected:
        raise ValueError("asset manifest SHA256 mismatch: " + str(path))
    return json.loads(path.read_text("utf-8"))


def image(path, expected):
    path = plain(path)
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024 or sha(path) != expected:
        raise ValueError("artwork missing/changed/oversized: " + str(path))
    with Image.open(path) as opened:
        if opened.format != "PNG" or opened.mode != "RGBA" or opened.width * opened.height > 4_194_304 or getattr(opened, "n_frames", 1) != 1:
            raise ValueError("expected a bounded, single RGBA PNG: " + str(path))
        opened.load()
        out = opened.copy()
    if out.getchannel("A").getbbox() is None:
        raise ValueError("empty artwork is forbidden: " + str(path))
    return out


def read_reference(path, kind, expected=None):
    receipt = read_json(path, expected)
    if receipt.get("kind") != kind or receipt.get("source", {}).get("source_pak_sha256") != PAK_SHA:
        raise ValueError("reference source/profile mismatch")
    outputs = {}
    for item in receipt["outputs"]:
        key = item["file"]
        if key in outputs or Path(key).is_absolute() or ".." in Path(key).parts or "\\" in key or ":" in key:
            raise ValueError("noncanonical reference output path")
        outputs[key] = item
    return receipt, outputs


def record(path, anchor, provenance):
    path = plain(path)
    digest = sha(path)
    im = image(path, digest)
    if len(anchor) != 2 or any(not math.isfinite(v) or abs(v) > 8192 for v in anchor):
        raise ValueError("invalid source sprite pivot")
    # The shared rig cache stores integer pixel anchors. All observed source
    # pivots are integral within float serialization noise; reject real
    # subpixel positions instead of silently rounding them away.
    scaled = [v * UPSCALE for v in anchor]
    if any(abs(v - round(v)) > 0.04 for v in scaled):
        raise ValueError("source pivot needs unsupported subpixel resampling")
    return {"file": str(path), "sha256": digest, "size": list(im.size), "anchor": anchor,
            "upscaled_anchor": [round(v) for v in scaled], "alpha_bbox": list(im.getchannel("A").getbbox()),
            "provenance": provenance}


def write_png(path, im):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        im.save(stream, "PNG")
    restored = image(path, sha(path))
    if restored.size != im.size or restored.tobytes() != im.tobytes():
        raise ValueError("prepared PNG readback mismatch")


def effect_frames(kind, vfx):
    """Consume frozen original-texture layers; never synthesize placeholders."""
    import original_vfx
    sequence = vfx["clips"][kind]["sequence"]
    results = []
    for index, item in enumerate(sequence):
        path = plain(original_vfx.MANIFEST.parent / item["file"], (ASSETS,))
        if sha(path) != item["sha256"]:
            raise ValueError("original texture effect frame changed")
        key = "effect:" + kind + ":" + str(index)
        entry = record(path, item["anchor"],
            {"kind": "original_texture_cross_engine_vfx", "producer": "original_vfx.py", "effect": kind, "index": index,
             "vfx_manifest_sha256": sha(original_vfx.MANIFEST), "source_reference_sha256": vfx["reference_manifest_sha256"],
             "scope": vfx["adaptation"], "not_lossless_cascade_copy": True})
        entry["world_scale_multiplier"] = item["world_scale_multiplier"]
        results.append((key, entry))
    return results


def prepare(output, portrait_manifest, authored_manifest, visual_review):
    """Prepare every clip in one batch; caller owns exclusive output cleanup."""
    import body_clips
    import original_vfx
    output = plain(output, (ASSETS,))
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError("prepare requires an empty, exclusively owned artwork directory")
    contract = read_json(CONTRACT, roots=(HERE,))
    if (contract["actor_id"], contract["role"], contract["skin"], contract["simulation_hz"]) != (200901, "ywy", "02", 60):
        raise ValueError("unexpected character contract identity")
    receipt, body_outputs = read_reference(BODY_MANIFEST, "character_body_reference", BODY_SHA)
    dataset_path = BODY_MANIFEST.parent / "body-reference.json"
    dataset = read_json(dataset_path, body_outputs["body-reference.json"]["sha256"])
    portrait_manifest = plain(portrait_manifest, (REFERENCE_ROOT,))
    portrait_receipt, _ = read_reference(portrait_manifest, "character_portrait_reference")
    # Human visual review is a separate source from structural metadata.
    review_path = plain(visual_review, (ASSETS, WORKBENCH / "evidence/yuwen-yi"))
    review = read_json(review_path, roots=(ASSETS, WORKBENCH / "evidence/yuwen-yi"))
    if review.get("body_manifest_sha256") != BODY_SHA or review.get("portrait_manifest_sha256") != sha(portrait_manifest) or review.get("approved") is not True or review.get("source_row") != "Hero_WuDang" or review.get("faces_positive_x") is not True:
        raise ValueError("complete body/portrait visual review must bind this exact source batch")
    authored_path = plain(authored_manifest, (ASSETS,))
    authored = read_json(authored_path)
    if review.get("authored_manifest_sha256") != sha(authored_path):
        raise ValueError("visual review must bind the exact newly authored poses")
    vfx = original_vfx.prepared()
    if review.get("original_vfx_manifest_sha256") != sha(original_vfx.MANIFEST) or review.get("approved_original_vfx") is not True:
        raise ValueError("complete art review must approve the exact original-texture VFX adaptation")
    if authored.get("schema") != 1 or authored.get("source_pak_sha256") != PAK_SHA or authored.get("source_body_manifest_sha256") != BODY_SHA or not authored.get("provenance"):
        raise ValueError("authored pose provenance/source binding is incomplete")
    authored_keys = {name for name, _ in body_clips.AUTHORED_PLAN.values()}
    if not authored_keys.issubset(authored.get("clips", {})):
        raise ValueError("authored visible poses missing: " + ", ".join(sorted(authored_keys - set(authored.get("clips", {})))))
    frames, plans, mapping_notes = {}, {}, {}
    actions = {(a["field"], a["slot"]): a for a in dataset["actions"] if a["row"] == "Hero_WuDang"}
    for semantic, (field, slot, selection) in body_clips.SOURCE_PLAN.items():
        action = actions[(field, slot)]
        keys = dataset["flipbooks"][action["flipbook"]]["keyframes"]
        indices = list(range(len(keys))) if selection is None else selection
        selected = []
        for index in indices:
            if not 0 <= index < len(keys):
                raise ValueError("source clip changed; selected keyframe out of range")
            fr = keys[index]
            key = "source:" + hashlib.sha256(fr["sprite"].encode()).hexdigest()[:24]
            path = BODY_MANIFEST.parent / fr["png"]
            if sha(plain(path)) != body_outputs[fr["png"]]["sha256"]:
                raise ValueError("source frame differs from verified reference output")
            if key not in frames:
                frames[key] = record(path, fr["region"]["pivot_pixels_from_crop_top_left"],
                                     {"kind": "original_sprite", "row": "Hero_WuDang", "sprite": fr["sprite"], "manifest_sha256": BODY_SHA})
            weight = Fraction(*fr["duration_fraction"])
            selected.append({"key": key, "weight": str(weight)})
        plans["ywy_" + semantic] = selected
        mapping_notes[semantic] = {"field": field, "slot": slot, "indices": indices,
                                   "scope": "BBEE adaptation and retiming; no original named-martial-art identity asserted"}
        if semantic in body_clips.EXPLICIT_SOURCE_TICKS:
            exact = body_clips.EXPLICIT_SOURCE_TICKS[semantic]
            definition = contract["clips"]["ywy_" + semantic]
            if definition.get("source_keyframe_indices") != indices or definition.get("source_keyframe_ticks") != exact or len(exact) != len(selected) or sum(exact) != definition["ticks"]:
                raise ValueError("explicit sword exposure differs from the complete character contract")
            for item, tick in zip(selected, exact):
                item["source_weight"] = item["weight"]
                item["exact_ticks"] = tick
            mapping_notes[semantic]["explicit_retiming_ticks"] = exact
            mapping_notes[semantic]["chain_after_ticks"] = definition["chain_after_ticks"]
            mapping_notes[semantic]["retiming_reason"] = "Source keys 0/1/2 are windup; actual forward sword keys 3/4/5 must all appear before combo cancel. Last source pose remains visible at least two ticks."
    for semantic in body_clips.AUTHORED_REQUIRED:
        source_name, indices = body_clips.AUTHORED_PLAN[semantic]
        sequence = authored["clips"][source_name]
        if not sequence or len(sequence) > 120:
            raise ValueError("empty/oversized authored pose sequence: " + semantic)
        indices = list(range(len(sequence))) if indices is None else indices
        selected = []
        for index in indices:
            if not 0 <= index < len(sequence):
                raise ValueError("authored keyframe selection out of range: " + semantic)
            item = sequence[index]
            relative = Path(item["file"])
            if relative.is_absolute() or ".." in relative.parts or ":" in item["file"]:
                raise ValueError("authored pose path escape")
            path = plain(authored_path.parent / relative, (ASSETS,))
            if sha(path) != item["sha256"] or not item.get("provenance"):
                raise ValueError("authored pose hash/provenance missing: " + semantic)
            key = "authored:" + source_name + ":" + str(index)
            frames[key] = record(path, item["anchor"], {"kind": "derived_character_pose", "source": authored["provenance"], "pose": item["provenance"], "not_original_animation": True})
            selected.append({"key": key, "weight": str(Fraction(item.get("weight", 1)))})
        plans["ywy_" + semantic] = selected
        mapping_notes[semantic] = {"authored_sequence": source_name, "indices": indices,
                                   "scope": "New visibly authored pose; BBEE adaptation, not original game animation"}
    for semantic in body_clips.EFFECTS:
        generated = effect_frames(semantic, vfx)
        frames.update(generated)
        definition = vfx["clips"][semantic]
        if contract["clips"]["ywy_" + semantic]["ticks"] != definition["ticks"] or contract["clips"]["ywy_" + semantic]["loop"] != definition["loop"]:
            raise ValueError("native VFX timing differs from frozen visual lifetime")
        plans["ywy_" + semantic] = [{"key": key, "weight": str(item["ticks"])} for (key, _), item in zip(generated, definition["sequence"])]
        mapping_notes[semantic] = {"original_texture_manifest_sha256": sha(original_vfx.MANIFEST), "scope": vfx["adaptation"]}
    if set(plans) != set(contract["clips"]):
        raise ValueError("asset plan does not cover exactly the semantic contract")
    stand = frames[plans["ywy_stand"][0]["key"]]
    visible_height = stand["alpha_bbox"][3] - stand["alpha_bbox"][1]
    if not 20 <= visible_height <= 80:
        raise ValueError("standing source calibration has unexpected visible height")
    manifest = {"schema": 1, "kind": "yuwen_yi_production_art", "source_pak_sha256": PAK_SHA,
                "contract_file": str(CONTRACT), "contract_sha256": sha(CONTRACT),
                "body_manifest": str(BODY_MANIFEST), "body_manifest_sha256": BODY_SHA,
                "portrait_manifest": str(portrait_manifest), "portrait_manifest_sha256": sha(portrait_manifest),
                "authored_manifest": str(authored_path), "authored_manifest_sha256": sha(authored_path),
                "visual_review": str(review_path), "visual_review_sha256": sha(review_path),
                "original_vfx_manifest": str(original_vfx.MANIFEST), "original_vfx_manifest_sha256": sha(original_vfx.MANIFEST),
                "upscale": UPSCALE, "standing_visible_source_pixels": visible_height, "target_height_units": TARGET_HEIGHT,
                "world_units_per_upscaled_pixel": TARGET_HEIGHT / (visible_height * UPSCALE),
                "frames": frames, "clip_frames": plans, "source_mapping_notes": mapping_notes,
                "rig_builder_sha256": sha(ROOT / "tools/bbtag/bbtag_rig.py"),
                "producers": {name: sha(HERE / name) for name in ("body_source.py", "body_clips.py", "portraits.py", "import_yuwen.py", "original_vfx.py")}}
    return manifest


class BodySource:
    def __init__(self, manifest_path=PRODUCTION):
        self.path = plain(manifest_path, (ASSETS,))
        self.manifest = read_json(self.path)
        data = self.manifest
        if data.get("kind") != "yuwen_yi_production_art" or data.get("source_pak_sha256") != PAK_SHA or data.get("upscale") != UPSCALE or data.get("target_height_units") != TARGET_HEIGHT:
            raise ValueError("invalid prepared art profile")
        self.contract = read_json(CONTRACT, data["contract_sha256"], roots=(HERE,))
        if sha(ROOT / "tools/bbtag/bbtag_rig.py") != data["rig_builder_sha256"]:
            raise ValueError("native rig builder changed after artwork freeze")
        for name, expected in data["producers"].items():
            if name not in {"body_source.py", "body_clips.py", "portraits.py", "import_yuwen.py", "original_vfx.py"} or sha(HERE / name) != expected:
                raise ValueError("producer changed after artwork freeze; prepare the whole batch again")
        for field in ("body_manifest", "portrait_manifest", "authored_manifest", "visual_review", "original_vfx_manifest"):
            path = plain(data[field], (ASSETS, REFERENCE_ROOT, WORKBENCH / "evidence/yuwen-yi"))
            if sha(path) != data[field + "_sha256"]:
                raise ValueError("prepared art input changed: " + field)
        import original_vfx
        original_vfx.prepared()
        ui_path = plain(data["ui_manifest"], (ASSETS,))
        if sha(ui_path) != data["ui_manifest_sha256"]:
            raise ValueError("UI artwork manifest changed after production freeze")
        self.frames = data["frames"]
        self._images = {}
        if not self.frames or len(self.frames) > 512:
            raise ValueError("prepared art frame limits exceeded")
        image_bytes = 0
        for key, entry in self.frames.items():
            im = image(entry["file"], entry["sha256"])
            if list(im.size) != entry["size"] or list(im.getchannel("A").getbbox()) != entry["alpha_bbox"]:
                raise ValueError("prepared frame geometry changed: " + key)
            image_bytes += im.width * im.height * 4
            if image_bytes > 64 * 1024 * 1024:
                raise ValueError("prepared artwork exceeds memory cap")
            self._images[key] = im
        self.scale = data["world_units_per_upscaled_pixel"]
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("invalid unified character scale")
        self.scale_mul = []
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.code = "ywy_" + digest[:24]
        self.palette = digest
        self.reserved_key = data["clip_frames"]["ywy_stand"][0]["key"]

    def mul(self, key):
        # A fixed sampling multiplier applies only to each original-texture
        # effect clip. Body poses retain their shared original pixel scale.
        scale = self.frames.get(key, {}).get("world_scale_multiplier", 1.0)
        if not math.isfinite(scale) or not 1.0 <= scale <= 2.0 or scale != 1 and not key.startswith("effect:"):
            raise ValueError("invalid or non-effect sampling scale")
        return scale

    def frame(self, key):
        # Shared build_rig unconditionally reserves 'null'. Give that unused
        # reservation a visible owned frame. sequences() forbids it in clips,
        # preflight/cache checks forbid any missing key from reaching fallback.
        if key == "null":
            key = self.reserved_key
        if key not in self.frames:
            raise ValueError("required character frame absent: " + key)
        im = self._images[key]
        out = im.resize((im.width * UPSCALE, im.height * UPSCALE), Image.Resampling.NEAREST)
        return np.array(out, dtype=np.uint8), tuple(self.frames[key]["upscaled_anchor"])

    def validate_cache(self, rig, clips):
        """Verify reused cache pages against every source pixel and pivot."""
        keys = sorted({key for sequence in clips.values() for key, _ in sequence} | {"null"})
        cdir, meta = rig.build_frames(self, keys)
        if set(meta["frames"]) != set(keys) or not 1 <= meta["pages"] <= 16:
            raise ValueError("rig frame cache incomplete/oversized")
        pages = {}
        for index in range(meta["pages"]):
            path = plain(Path(cdir) / ("page_%02d.png" % index), (ROOT / "local_only/cache",))
            with Image.open(path) as opened:
                opened.load()
                if opened.mode != "RGBA" or opened.size != (rig.PAGE, rig.PAGE):
                    raise ValueError("invalid cached character page")
                pages[index] = opened.copy()
        for key in keys:
            pixels, anchor = self.frame(key)
            pixels = np.pad(pixels, ((rig.FRAME_MARGIN, rig.FRAME_MARGIN), (rig.FRAME_MARGIN, rig.FRAME_MARGIN), (0, 0)))
            entry = meta["frames"][key]
            if entry["size"] != [pixels.shape[1], pixels.shape[0]] or entry["anchor"] != [int(a + rig.FRAME_MARGIN) for a in anchor]:
                raise ValueError("cached frame pivot/size differs from owned source")
            page, x, y = entry["place"]
            actual = pages[page].crop((x, y, x + pixels.shape[1], y + pixels.shape[0]))
            if actual.tobytes() != pixels.tobytes():
                raise ValueError("cached frame pixels differ from owned source")
        return len(keys)
