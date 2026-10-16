"""Package already-generated transparent Yuwen Yi candidate poses.

Only split/crop, one fixed NEAREST scale per source sheet and transparent-canvas
placement are allowed. Alpha thresholds measure geometry; source alpha is never
rewritten. Originals, provenance and a checkerboard QA sheet are preserved.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ZenithTerminal/Launcher/mods/char-yuwen-yi/assets"
EVIDENCE = ROOT / "evidence/yuwen-yi"
BODY_MANIFEST = ROOT / "references/wandering-sword/20261015T133053Z-487eeab89890/manifest.json"
BODY_SHA = "c53f67f143e03b8cbb598671368de13f241e2dcfb60870bc8c9a054c46f253dc"
PAK_SHA = "5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff"
GENERATED = Path(r"C:\Users\MECHREVO\.codex\generated_images\01a13ea9-89fc-7050-8218-e39c2804cf76")
SHEETS = [
    {"source": GENERATED / "exec-290a49bb-218e-41e6-a8e4-00b4dd35900d.png",
     "sha256": "678c858745cc3c997f8d7e32a84b990ccc6a09654acd23c8f56f2f32c4e74a19",
     "copy": "hurt-recovery.png", "size": [1024, 1536],
     "semantics": ["behit", "behit_air", "tumble", "down", "getup", "dead"],
     "calibration": "getup_3"},
    {"source": GENERATED / "exec-f18c7470-41fa-4fbd-ad4d-e5e2d874f781.png",
     "sha256": "f95680e44fdef513e8a6af7cd84cb06f131e14f180ee8ab391d42042286c667b",
     "copy": "crouch-guard-meditate-salute.png", "size": [1293, 1217],
     "semantics": ["crouch", "guard_charge", "meditate", "salute"],
     "calibration": "salute_0"},
]
CANVAS = (52, 64)
ANCHOR = (26, 56)
MEASURE_ALPHA = 128
CONNECTED_ALPHA = 32
MARGIN = 2


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physical(path):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.exists():
            require(not part.is_symlink() and not (getattr(part.lstat(), "st_file_attributes", 0) & 0x400),
                    "Linked authored input/output path refused")
    return path


def runs(values):
    padded = np.pad(np.asarray(values, dtype=np.int8), (1, 1))
    changes = np.diff(padded)
    return list(zip(np.flatnonzero(changes == 1).tolist(), np.flatnonzero(changes == -1).tolist()))


def separators(segments, limit):
    require(all(right[0] - left[1] >= 8 for left, right in zip(segments, segments[1:])),
            "No reliable transparent separation between measured subjects")
    return [0, *[(left[1] + right[0]) // 2 for left, right in zip(segments, segments[1:])], limit]


def bounds(mask):
    ys, xs = np.nonzero(mask)
    require(len(xs) > 0, "Measured sprite is empty")
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def connected_contour(alpha):
    """Measure low-alpha fringe connected to ALL visible core pieces.

    This returns a measurement mask only; the original RGBA crop is exported.
    Unconnected low-alpha sheet noise is not treated as a hair/hand/foot.
    """
    core = alpha >= MEASURE_ALPHA
    visited = core.copy()
    allowed = alpha >= CONNECTED_ALPHA
    height, width = alpha.shape
    queue = deque(map(int, np.flatnonzero(core)))
    require(bool(queue), "No visible sprite core")
    while queue:
        value = queue.popleft()
        y, x = divmod(value, width)
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width and allowed[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                queue.append(ny * width + nx)
    return core, visited


def split_geometry(image, semantics):
    alpha = np.asarray(image.getchannel("A"))
    row_segments = runs(np.any(alpha >= MEASURE_ALPHA, axis=1))
    require(len(row_segments) == len(semantics), "Unexpected measured source row count")
    row_cuts = separators(row_segments, image.height)
    result = []
    coverage = np.zeros(alpha.shape, dtype=np.uint8)
    for row, ((begin, end), semantic) in enumerate(zip(row_segments, semantics)):
        columns = runs(np.any(alpha[begin:end] >= MEASURE_ALPHA, axis=0))
        require(len(columns) == 4, "Unexpected measured subject count in source row")
        cuts = separators(columns, image.width)
        for column in range(4):
            left, top, right, bottom = cuts[column], row_cuts[row], cuts[column + 1], row_cuts[row + 1]
            cell = alpha[top:bottom, left:right]
            core, contour = connected_contour(cell)
            core_box, measured = bounds(core), bounds(contour)
            require(measured[0] > 0 and measured[1] > 0 and measured[2] < cell.shape[1] and measured[3] < cell.shape[0],
                    "A connected subject touches a separator; refusing an uncertain crop")
            local = [max(0, measured[0] - MARGIN), max(0, measured[1] - MARGIN),
                     min(cell.shape[1], measured[2] + MARGIN), min(cell.shape[0], measured[3] + MARGIN)]
            crop_box = [local[0] + left, local[1] + top, local[2] + left, local[3] + top]
            global_core = [core_box[0] + left, core_box[1] + top, core_box[2] + left, core_box[3] + top]
            coverage[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]] += 1
            result.append({"semantic": semantic, "index": column, "row": row, "column": column,
                           "key": semantic + "_" + str(column), "source_cell": [left, top, right, bottom],
                           "source_core_bbox_alpha128": global_core, "source_crop_bbox": crop_box,
                           "source_visible_core_pixels": int(core.sum()),
                           "source_connected_measurement_pixels": int(contour.sum())})
    require(np.all(coverage <= 1), "Authored sprite source crops overlap")
    require(np.all(coverage[alpha >= MEASURE_ALPHA] == 1), "Visible hair/hand/foot pixels were left outside the crops")
    return result, {"row_segments_alpha128": [list(pair) for pair in row_segments],
                    "row_separators": row_cuts, "sprites": len(result),
                    "source_alpha128_pixels": int(np.count_nonzero(alpha >= MEASURE_ALPHA)),
                    "visible_core_coverage": "exactly_once", "crop_overlap_pixels": 0}


def save_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def checkerboard_contact(frames):
    zoom, gap, label = 4, 12, 28
    cw, ch = CANVAS[0] * zoom + gap * 2, CANVAS[1] * zoom + label + gap * 2
    image = Image.new("RGB", (cw * 4, ch * 10), "#22272e")
    draw = ImageDraw.Draw(image)
    for row, (semantic, sequence) in enumerate(frames.items()):
        for column, frame in enumerate(sequence):
            x, y = column * cw + gap, row * ch + label
            for yy in range(0, CANVAS[1] * zoom, 8):
                for xx in range(0, CANVAS[0] * zoom, 8):
                    color = "#d0d0d0" if (xx // 8 + yy // 8) % 2 else "#909090"
                    draw.rectangle((x + xx, y + yy, x + xx + 7, y + yy + 7), fill=color)
            pose = frame.resize((CANVAS[0] * zoom, CANVAS[1] * zoom), Image.Resampling.NEAREST)
            image.paste(pose, (x, y), pose)
            draw.text((column * cw + gap, row * ch + 6), semantic + "_" + str(column), fill="white")
            ax, ay = x + ANCHOR[0] * zoom, y + ANCHOR[1] * zoom
            draw.line((ax - 5, ay, ax + 5, ay), fill="#ff375f")
            draw.line((ax, ay - 5, ax, ay + 5), fill="#ff375f")
    return image


def main():
    body_path = physical(BODY_MANIFEST)
    require(sha(body_path) == BODY_SHA, "Source body manifest differs from its approved snapshot")
    body = json.loads(body_path.read_bytes())
    require(body["source"]["source_pak_sha256"] == PAK_SHA, "Source PAK binding differs")
    physical(ASSETS)
    physical(EVIDENCE)
    for path in (ASSETS / "authored", ASSETS / "authored-sheets", ASSETS / "authored-poses.json",
                 EVIDENCE / "authored-poses-contact-sheet.png", EVIDENCE / "authored-poses-validation.json"):
        require(not path.exists(), "Refusing to overwrite existing authored artifacts")
    scratch = physical(ROOT / "private/temp")
    scratch.mkdir(parents=True, exist_ok=True)
    outputs, images, provenance, sheet_geometry = {}, {}, [], []
    with tempfile.TemporaryDirectory(prefix="yuwen-authored-package-", dir=scratch) as directory:
        staging = Path(directory).resolve()
        require(staging.is_relative_to(scratch.resolve()), "Authored staging escapes workspace")
        (staging / "authored").mkdir()
        (staging / "authored-sheets").mkdir()
        for spec in SHEETS:
            source = physical(spec["source"])
            require(sha(source) == spec["sha256"], "Generated source PNG changed")
            with Image.open(source) as opened:
                opened.load()
                require(opened.mode == "RGBA" and list(opened.size) == spec["size"], "Unexpected generated sheet mode/size")
                image = opened.copy()
            require(image.getchannel("A").getextrema()[0] == 0, "Source sheet has no transparent pixels")
            geometry, geometry_summary = split_geometry(image, spec["semantics"])
            calibration = next(item for item in geometry if item["key"] == spec["calibration"])
            upright_height = calibration["source_core_bbox_alpha128"][3] - calibration["source_core_bbox_alpha128"][1]
            scale = 38.0 / upright_height
            source_copy = staging / "authored-sheets" / spec["copy"]
            shutil.copyfile(source, source_copy)
            require(sha(source_copy) == spec["sha256"], "Preserved source copy hash mismatch")
            sheet_record = {"source_generated_png": str(source), "preserved_copy": "authored-sheets/" + spec["copy"],
                            "sha256": spec["sha256"], "source_size": spec["size"], "scale": scale,
                            "scale_fraction": [38, upright_height], "calibration_frame": spec["calibration"],
                            "calibration_core_bbox_alpha128": calibration["source_core_bbox_alpha128"],
                            "calibration_visible_height": upright_height, "target_upright_height": 38,
                            "scale_policy": "One fixed scale for all frames of this source sheet; no per-frame height normalization"}
            provenance.append(sheet_record)
            for item in geometry:
                crop = image.crop(item["source_crop_bbox"])
                resized_size = tuple(max(1, round(value * scale)) for value in crop.size)
                resized = crop.resize(resized_size, Image.Resampling.NEAREST)
                position = (ANCHOR[0] - resized.width // 2, ANCHOR[1] - resized.height)
                require(position[0] >= 0 and position[1] >= 0 and position[0] + resized.width <= CANVAS[0]
                        and position[1] + resized.height <= CANVAS[1], "Fixed sheet scale does not fit the authored canvas")
                canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
                canvas.paste(resized, position)  # No alpha mask: preserve RGBA exactly.
                relative = "authored/" + item["key"] + ".png"
                destination = staging / relative
                with destination.open("xb") as stream:
                    canvas.save(stream, format="PNG")
                with Image.open(destination) as restored:
                    restored.load()
                    require(restored.mode == "RGBA" and restored.size == CANVAS and restored.tobytes() == canvas.tobytes(),
                            "Packaged authored frame readback differs")
                    require(np.count_nonzero(np.asarray(restored.getchannel("A")) >= MEASURE_ALPHA) > 0,
                            "Packaged pose has no visible core")
                # Independently rebuild the allowed transform to bind alpha and canvas placement.
                require(canvas.crop((position[0], position[1], position[0] + resized.width,
                                     position[1] + resized.height)).tobytes() == resized.tobytes(),
                        "Canvas placement altered source alpha or pixels")
                frame = {"file": relative, "sha256": sha(destination), "anchor": list(ANCHOR), "weight": 1,
                         "canvas": list(CANVAS), "scale": scale,
                         "provenance": {**item, "sheet": sheet_record["preserved_copy"],
                                        "source_sha256": spec["sha256"], "scale_fraction": [38, upright_height],
                                        "resized_size": list(resized_size), "canvas_position": list(position),
                                        "processing": "Original RGBA crop -> uniform-sheet NEAREST resize -> transparent canvas; alpha never rewritten"}}
                outputs.setdefault(item["semantic"], []).append(frame)
                images.setdefault(item["semantic"], []).append(canvas)
            sheet_geometry.append({"sheet": spec["copy"], **geometry_summary})
        require(len(outputs) == 10 and all(len(value) == 4 for value in outputs.values()), "Expected ten complete four-frame clips")
        script_sha = sha(Path(__file__))
        manifest = {"schema": 1, "source_pak_sha256": PAK_SHA, "source_body_manifest_sha256": BODY_SHA,
                    "provenance": {"origin": "Root-reviewed imagegen candidate sheets; authored poses, not original-game frames",
                                   "processing_script_sha256": script_sha, "sheets": provenance,
                                   "geometry_measurement": {"alpha_core": MEASURE_ALPHA,
                                                            "connected_fringe_measurement_alpha": CONNECTED_ALPHA,
                                                            "source_crop_margin_pixels": MARGIN,
                                                            "thresholds_modify_alpha": False}},
                    "visual_acceptance": "pending_root_contact_sheet_review", "candidate_only": True,
                    "canvas": list(CANVAS), "anchor": list(ANCHOR), "clips": outputs}
        save_json(staging / "authored-poses.json", manifest)
        contact = checkerboard_contact(images)
        contact.save(staging / "authored-poses-contact-sheet.png", format="PNG")
        # Final group readback occurs before publishing any candidate file.
        parsed = json.loads((staging / "authored-poses.json").read_bytes())
        require(parsed == manifest, "Authored manifest readback mismatch")
        for sequence in parsed["clips"].values():
            for frame in sequence:
                require(sha(staging / frame["file"]) == frame["sha256"], "Authored frame hash changed before publication")
        for sheet in provenance:
            require(sha(staging / sheet["preserved_copy"]) == sheet["sha256"], "Preserved source changed before publication")
        require(all(sha(spec["source"]) == spec["sha256"] for spec in SHEETS), "Original generated PNG changed")
        validation = {"status": "candidate_packaged_pending_visual_qa", "captured_utc": datetime.now(timezone.utc).isoformat(),
                      "processing_script_sha256": script_sha, "manifest_sha256": sha(staging / "authored-poses.json"),
                      "source_body_manifest_sha256": BODY_SHA, "source_pak_sha256": PAK_SHA,
                      "clips": 10, "frames": 40, "source_copies": provenance, "geometry": sheet_geometry,
                      "mechanical_checks": {"source_hashes_preserved": True, "complete_visible_core_coverage": True,
                                            "source_crop_overlap_pixels": 0, "same_scale_within_each_sheet": True,
                                            "original_rgba_alpha_preserved_through_allowed_transform": True,
                                            "all_frame_hashes_read_back": True, "fixed_canvas_and_anchor": True,
                                            "source_sheet_count_and_frame_count": True},
                      "contact_sheet": str(EVIDENCE / "authored-poses-contact-sheet.png"),
                      "contact_sheet_sha256": sha(staging / "authored-poses-contact-sheet.png"),
                      "visual_qa_completed": False, "identity_acceptance": "pending", "bbmod_ready": False,
                      "limits": ["Alpha thresholds only measure visible geometry; original crop alpha remains intact.",
                                 "Low-alpha disconnected sheet noise outside measured crop is excluded by cropping, not recolored or erased.",
                                 "Each source resolution has one upright calibration; down/tumble/crouch heights are not normalized individually.",
                                 "AI candidate poses still require root visual acceptance and actual clip/timing integration."]}
        save_json(staging / "authored-poses-validation.json", validation)
        ASSETS.mkdir(parents=True, exist_ok=True)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        for leaf in ("authored", "authored-sheets", "authored-poses.json"):
            require(not (ASSETS / leaf).exists(), "Authored destination appeared during publication")
            os.rename(staging / leaf, ASSETS / leaf)
        for leaf in ("authored-poses-contact-sheet.png", "authored-poses-validation.json"):
            require(not (EVIDENCE / leaf).exists(), "Authored evidence appeared during publication")
            os.rename(staging / leaf, EVIDENCE / leaf)
    print(json.dumps({"status": "candidate_packaged_pending_visual_qa", "manifest": str(ASSETS / "authored-poses.json"),
                      "source_copies": [str(ASSETS / sheet["preserved_copy"]) for sheet in provenance],
                      "contact_sheet": str(EVIDENCE / "authored-poses-contact-sheet.png"),
                      "validation": str(EVIDENCE / "authored-poses-validation.json"), "frames": 40, "clips": 10}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
