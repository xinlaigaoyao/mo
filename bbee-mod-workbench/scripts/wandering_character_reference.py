"""Collect the selected Hero Paper2D reference chain, not a BBEE character mod.

Roots come from exact fields in the nine-member verified NPCResources fixture.
Only their actual Flipbook -> Sprite -> Texture2D references are followed.
No directory/bulk extraction, automatic skill-name guessing, external execution,
overwrite, new dependencies, original-game writes or save access is provided.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import html
import io
import json
import math
from pathlib import Path
import struct
import sys

from wandering_reference import (
    PAK_PATH, EXPECTED_PAK_SHA256, OUTPUT_ROOT, WORKBENCH, PakV11,
    ReferenceError, plain_path, member_path, output_directory,
    remove_owned_output, write_json_exclusive,
)
from wandering_decode_reference import read_inputs, npc_hero_mapping, Package, require
from wandering_character_parser import flipbook, sprite, texture, sprite_region

MIB = 1024 * 1024
MAX_MEMBERS = 1024
MAX_RAW_BYTES = 256 * MIB
MAX_TEXTURE_PIXEL_BYTES = 128 * MIB
MAX_FRAME_PIXEL_BYTES = 128 * MIB
MAX_SPRITES = 512
MAX_TEXTURES = 32
SCALAR_ACTIONS = ["IdleLeftFlipbook", "IdleRightFlipbook", "RunLeftFlipbook", "RunRightFlipbook",
                  "FightIdleLeftFlipbook", "FightIdleRightFlipbook", "QingGongSSStartLeftFlipbooks",
                  "QingGongSSStartRightFlipbooks", "QingGongSSLoopLeftFlipbooks", "QingGongSSLoopRightFlipbooks",
                  "QingGongSSEndLeftFlipbooks", "QingGongSSEndRightFlipbooks"]


def object_parts(value: str) -> tuple[str, str]:
    require(value.startswith("/Game/") and value.count(".") == 1, "Noncanonical /Game object reference")
    package, obj = value.rsplit(".", 1)
    member_path(package.removeprefix("/Game/"))
    require(obj and "/" not in obj and "\\" not in obj and ":" not in obj, "Invalid object name")
    return package, obj


class SourceGraph:
    def __init__(self, pak: PakV11, rows: list[str]):
        self.pak, self.rows = pak, rows
        self.packages, self.raw, self.member_receipts = {}, {}, {}
        self.raw_bytes = 0

    def package(self, object_path: str) -> tuple[Package, str]:
        path, obj = object_parts(object_path)
        roots = ["/Game/JH/Characters/TongYong/" + row + "/" for row in self.rows]
        require(any(path.startswith(root) for root in roots), "Body reference escapes selected Hero row roots")
        if path not in self.packages:
            require(len(self.packages) < 512, "Reference package graph exceeds limit")
            short = "Wandering_Sword/Content/" + path.removeprefix("/Game/")
            parts = []
            for suffix in (".uasset", ".uexp"):
                member = member_path(short + suffix)
                require(member in self.pak.entries, "Exact referenced package companion is absent: " + member)
                require(len(self.raw) < MAX_MEMBERS, "Selected reference member cap reached")
                entry = self.pak.entries[member]
                require(self.raw_bytes + entry.uncompressed_bytes <= MAX_RAW_BYTES,
                        "Selected reference byte cap reached")
                data, receipt = self.pak.read_selected(member, 64 * MIB)
                self.raw[member] = data
                self.member_receipts[member] = receipt
                self.raw_bytes += len(data)
                parts.append(data)
            self.packages[path] = Package(*parts)
        return self.packages[path], obj


def selected_actions(mapping: dict, rows: list[str], swords: list[int], fists: list[int]) -> tuple[list[dict], list[dict]]:
    result, gaps = [], []
    for row_name in rows:
        row = mapping["selected_rows"][row_name]
        def add(field: str, slot: int | None = None) -> None:
            require(field in row, "Expected NPCResources action field is absent")
            entry = row[field]
            value = entry["value"] if slot is None else entry["value"][slot]
            if value["asset"] == "None":
                gaps.append({"row": row_name, "field": field, "slot": slot, "reason": "Explicit null source reference"})
                return
            require(value["subpath"] == "", "Subobject visual references are unsupported")
            require(entry["kind"] == ("SoftObjectProperty" if slot is None else "ArrayProperty"), "NPC action kind changed")
            result.append({"row": row_name, "field": field, "slot": slot, "flipbook": value["asset"],
                           "semantic_scope": "NPCResources field/slot only; not a specific martial-arts skill identity"})
        for field in SCALAR_ACTIONS:
            add(field)
        for weapon, slots in (("Sword", swords), ("Fist", fists)):
            for side in ("Left", "Right"):
                for slot in slots:
                    add(weapon + side + "Flipbooks", slot)
        for side in ("Left", "Right"):
            field = "Attack" + side + "Flipbooks"
            valid = [i for i, value in enumerate(row[field]["value"]) if value["asset"] != "None"]
            if valid:
                add(field, valid[0])
            else:
                gaps.append({"row": row_name, "field": field, "reason": "All source basic-attack slots null"})
            death = "Died" + side + "Flipbook"
            if row[death]["value"]["asset"] != "None":
                add(death)
            else:
                gaps.append({"row": row_name, "field": death, "reason": "No source death/knockdown clip mapped"})
        hit_fields = [field for field in row if any(word in field.casefold() for word in ("hurt", "hitreact", "damage", "injur"))]
        require(not hit_fields, "Unexpected hit-reaction fields need explicit mapping review")
        gaps.append({"row": row_name, "field": "hit_reaction", "reason": "No hit-reaction field in the decoded NPCResourceSetting layout; no QT slot guessed"})
    require(len(result) <= 64, "Explicit action root count exceeds limit")
    return result, gaps


def safe_bytes(path: Path, data: bytes) -> dict:
    plain_path(path, stop_at=OUTPUT_ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    plain_path(path, stop_at=OUTPUT_ROOT)
    with path.open("xb") as stream:
        stream.write(data)
    digest = hashlib.sha256(data).hexdigest()
    require(path.stat().st_size == len(data) and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            "Reference output readback mismatch")
    return {"bytes": len(data), "sha256": digest}


def png_bytes(image) -> bytes:
    from PIL import Image
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    encoded = stream.getvalue()
    with Image.open(io.BytesIO(encoded)) as restored:
        restored.load()
        require(restored.mode == "RGBA" and restored.size == image.size and restored.tobytes() == image.tobytes(),
                "PNG conversion did not preserve original pixels")
    return encoded


def short_id(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]


def animation_preview(frames: list[dict], images: dict) -> tuple[bytes | None, dict]:
    from PIL import Image, ImageSequence
    exact_duration = sum((Fraction(*frame["duration_fraction"]) for frame in frames), Fraction(0, 1))
    metadata = {"authoritative_timing": "FrameRun/FPS and exact fractions in clip JSON; APNG rounds to milliseconds",
                "source_duration_fraction": [exact_duration.numerator, exact_duration.denominator],
                "source_duration_seconds": float(exact_duration), "input_keyframes": len(frames),
                "source_frame_runs": [frame["frame_run"] for frame in frames]}
    pivots = [frame["region"]["pivot_pixels_from_crop_top_left"] for frame in frames]
    ppus = [frame["region"]["pixels_per_unreal_unit"] for frame in frames]
    if max(ppus) - min(ppus) > 1e-6:
        return None, {**metadata, "status": "unavailable", "reason": "Nonuniform source PPU requires explicit resampling policy"}
    anchor = [max(p[i] for p in pivots) for i in range(2)]
    offsets = [[anchor[i] - p[i] for i in range(2)] for p in pivots]
    if any(abs(value - round(value)) > 0.004 for pair in offsets for value in pair):
        return None, {**metadata, "status": "unavailable", "reason": "Subpixel pivot differences preserved; no automatic resampling"}
    offsets = [[round(value) for value in pair] for pair in offsets]
    width = max(images[frame["sprite"]].width + offset[0] for frame, offset in zip(frames, offsets))
    height = max(images[frame["sprite"]].height + offset[1] for frame, offset in zip(frames, offsets))
    require(width * height * len(frames) * 4 <= 64 * MIB, "Animation preview canvas exceeds memory limit")
    canvases = []
    for frame, offset in zip(frames, offsets):
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(images[frame["sprite"]], tuple(offset))
        canvases.append(canvas)
    durations = [max(1, round(frame["duration_seconds"] * 1000)) for frame in frames]
    # Pillow merges consecutive byte-identical frames, and writes an ordinary PNG
    # with no acTL/fcTL/duration when only one visible state remains. Make that
    # representation explicit instead of requiring nonexistent animation timing
    # or inventing a second frame. Original keyframes/runs remain in the sidecar.
    visual_runs = []
    previous_pixels = None
    for index, (canvas, duration) in enumerate(zip(canvases, durations)):
        pixels = canvas.tobytes()
        if pixels == previous_pixels:
            visual_runs[-1]["duration_ms"] += duration
            visual_runs[-1]["source_keyframes"].append(index)
        else:
            visual_runs.append({"image": canvas, "duration_ms": duration, "source_keyframes": [index]})
        previous_pixels = pixels
    metadata.update({"canvas_size": [width, height], "common_pivot_pixels": anchor,
                     "rounded_duration_ms": sum(durations), "visual_states": len(visual_runs),
                     "visual_runs": [{"duration_ms": run["duration_ms"], "source_keyframes": run["source_keyframes"]}
                                     for run in visual_runs]})
    if len(visual_runs) == 1:
        encoded = png_bytes(visual_runs[0]["image"])
        with Image.open(io.BytesIO(encoded)) as restored:
            require(not getattr(restored, "is_animated", False) and getattr(restored, "n_frames", 1) == 1,
                    "Single-state preview must be a static PNG")
        return encoded, {**metadata, "status": "encoded_and_read_back", "representation": "static_png",
                         "timing_storage": "sidecar_only", "codec_duration_ms": None,
                         "scope": "Single visible source state; true source duration is retained in sidecar, not encoded in PNG"}
    if any(value > 60_000 for value in durations):
        return None, {**metadata, "status": "unavailable", "reason": "APNG preview duration cap; exact original duration retained in JSON"}
    if any(run["duration_ms"] > 60_000 for run in visual_runs):
        return None, {**metadata, "status": "unavailable", "reason": "Merged APNG duration cap; exact original timing retained in JSON"}
    stream = io.BytesIO()
    visual_runs[0]["image"].save(stream, format="PNG", save_all=True,
                                 append_images=[run["image"] for run in visual_runs[1:]],
                                 duration=[run["duration_ms"] for run in visual_runs], loop=0, disposal=0, blend=0)
    encoded = stream.getvalue()
    with Image.open(io.BytesIO(encoded)) as restored:
        require(getattr(restored, "is_animated", False) and restored.n_frames == len(visual_runs),
                "Multiple visible states must produce a complete animated PNG")
        observed_duration = 0.0
        for index, observed in enumerate(ImageSequence.Iterator(restored)):
            observed.load()
            require(observed.convert("RGBA").tobytes() == visual_runs[index]["image"].tobytes(),
                    "APNG preview pixels differ from aligned source frame")
            duration = float(observed.info.get("duration", 0))
            require(duration > 0, "APNG preview has no frame duration")
            require(abs(duration - visual_runs[index]["duration_ms"]) < 0.1,
                    "APNG preview individual frame timing mismatch")
            observed_duration += duration
        require(abs(observed_duration - sum(durations)) < 0.1, "APNG preview total timing mismatch")
    return encoded, {**metadata, "status": "encoded_and_read_back", "representation": "apng",
                     "timing_storage": "codec_and_exact_sidecar", "codec_duration_ms": sum(durations),
                     "scope": "Transparent source rectangle animation; visual review pending"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-manifest", required=True, type=Path, help="The original exact nine-member selected-export manifest")
    parser.add_argument("--row", action="append", required=True, choices=["Hero", "Hero_WuDang"])
    parser.add_argument("--sword-slot", action="append", type=int, help="Explicit source Sword array slot; defaults to 0")
    parser.add_argument("--fist-slot", action="append", type=int, help="Explicit source Fist array slot; defaults to 0")
    args = parser.parse_args(argv)
    require(len(set(args.row)) == len(args.row), "Repeated row selection")
    swords, fists = args.sword_slot or [0], args.fist_slot or [0]
    for values in (swords, fists):
        require(len(values) <= 8 and len(values) == len(set(values)) and all(0 <= value < 62 for value in values),
                "Choose at most eight distinct explicit weapon slots in 0..61")
    fixtures, input_receipt = read_inputs(args.raw_manifest)
    npc = Package(fixtures["JH/Tables/NPCResources.uasset"], fixtures["JH/Tables/NPCResources.uexp"])
    mapping = npc_hero_mapping(npc)
    actions, gaps = selected_actions(mapping, args.row, swords, fists)
    from PIL import Image, __version__ as pillow_version
    plain_path(PAK_PATH, stop_at=Path(PAK_PATH.anchor))
    with PAK_PATH.open("rb") as source_stream:
        pak = PakV11(source_stream, EXPECTED_PAK_SHA256)
        graph = SourceGraph(pak, args.row)
        clips, sprites, textures, atlas_images, sprite_images = {}, {}, {}, {}, {}
        texture_bytes = frame_bytes = 0
        for action in actions:
            root = action["flipbook"]
            if root not in clips:
                package, object_name = graph.package(root)
                clip = flipbook(package, object_name)
                require(sum(len(item["keyframes"]) for item in clips.values()) + len(clip["keyframes"]) <= 4096,
                        "Selected animation keyframe count exceeds limit")
                clips[root] = clip
                for frame in clip["keyframes"]:
                    sprite_path = frame["sprite"]
                    if sprite_path not in sprites:
                        require(len(sprites) < MAX_SPRITES, "Selected sprite cap reached")
                        sprite_package, sprite_name = graph.package(sprite_path)
                        sprite_data = sprite(sprite_package, sprite_name)
                        texture_path = sprite_data["texture"]
                        if texture_path not in textures:
                            require(len(textures) < MAX_TEXTURES, "Selected atlas cap reached")
                            texture_package, texture_name = graph.package(texture_path)
                            pixels, texture_data = texture(texture_package, texture_name)
                            texture_bytes += len(pixels)
                            require(texture_bytes <= MAX_TEXTURE_PIXEL_BYTES, "Decoded atlas byte cap reached")
                            textures[texture_path] = texture_data
                            atlas_images[texture_path] = Image.frombytes("RGBA", (texture_data["width"], texture_data["height"]),
                                                                         pixels, "raw", "BGRA", 0, 1)
                        region = sprite_region(sprite_data, textures[texture_path])
                        x, y, width, height = region["rectangle_xywh"]
                        frame_bytes += width * height * 4
                        require(frame_bytes <= MAX_FRAME_PIXEL_BYTES, "Decoded sprite byte cap reached")
                        sprite_images[sprite_path] = atlas_images[texture_path].crop((x, y, x + width, y + height))
                        sprites[sprite_path] = {**sprite_data, "region": region}
                    frame["region"] = sprites[sprite_path]["region"]
        pak.assert_source_unchanged()
        target = output_directory()
        try:
            outputs = []
            for member, data in graph.raw.items():
                destination = target / "raw" / Path(*member.split("/"))
                receipt = safe_bytes(destination, data)
                outputs.append({"file": destination.relative_to(target).as_posix(), **receipt, "kind": "raw_member"})
            for object_path, image in atlas_images.items():
                path = target / "atlases" / (short_id(object_path) + ".png")
                receipt = safe_bytes(path, png_bytes(image))
                textures[object_path]["png"] = path.relative_to(target).as_posix()
                outputs.append({"file": path.relative_to(target).as_posix(), **receipt, "kind": "atlas_png"})
            for object_path, image in sprite_images.items():
                path = target / "frames" / (short_id(object_path) + ".png")
                receipt = safe_bytes(path, png_bytes(image))
                sprites[object_path]["png"] = path.relative_to(target).as_posix()
                outputs.append({"file": path.relative_to(target).as_posix(), **receipt, "kind": "sprite_png"})
            previews = {}
            for clip_path, clip in clips.items():
                preview, metadata = animation_preview(clip["keyframes"], sprite_images)
                metadata["timing_sidecar"] = {"file": "body-reference.json", "flipbook_object": clip_path}
                if preview is not None:
                    path = target / "previews" / (short_id(clip_path) + ".png")
                    receipt = safe_bytes(path, preview)
                    metadata["png"] = path.relative_to(target).as_posix()
                    outputs.append({"file": path.relative_to(target).as_posix(), **receipt,
                                    "kind": "animation_apng" if metadata["representation"] == "apng" else "static_preview_png"})
                previews[clip_path] = metadata
                for frame in clip["keyframes"]:
                    frame["png"] = sprites[frame["sprite"]]["png"]
            dataset = {"source_rows": args.row, "actions": actions, "unavailable_actions": gaps,
                       "flipbooks": clips, "sprites": sprites, "textures": textures, "animation_previews": previews,
                       "visual_acceptance": "pending", "bbmod_ready": False,
                       "limitations": ["Source NPC fields/slots do not prove martial-arts skill identities.",
                                       "No authored hit reaction or mapped death clips were invented.",
                                       "Original shaders, physics, trajectories and hitboxes are not evaluated.",
                                       "Original frame timing/pivots are references; BBEE action timing is a separate implementation."]}
            write_json_exclusive(target / "body-reference.json", dataset)
            outputs.append({"file": "body-reference.json", "kind": "source_graph_json",
                            "sha256": hashlib.sha256((target / "body-reference.json").read_bytes()).hexdigest()})
            cards = []
            for action in actions:
                preview = previews[action["flipbook"]]
                label = action["row"] + " / " + action["field"] + ("[" + str(action["slot"]) + "]" if action["slot"] is not None else "")
                visual = '<img src="' + html.escape(preview["png"], quote=True) + '">' if "png" in preview else '<p>Preview unavailable: ' + html.escape(preview["reason"]) + '</p>'
                cards.append("<figure><figcaption>" + html.escape(label) + "</figcaption>" + visual + "</figure>")
            page = ('<!doctype html><meta charset="utf-8"><title>Wandering Sword source body reference</title>'
                    '<style>body{background:#20242b;color:#eee;font:16px sans-serif;padding:20px}main{display:flex;flex-wrap:wrap;gap:16px}'
                    'figure{margin:0;padding:12px;background:#303640;min-width:260px}img{image-rendering:pixelated;width:288px;height:216px;'
                    'object-fit:contain;background:repeating-conic-gradient(#777 0% 25%,#555 0% 50%) 0/20px 20px}figcaption{margin-bottom:8px}</style>'
                    '<h1>Source body reference — visual review pending</h1><p>Original field/slot labels. No BBEE integration, hurt/death invention or skill identity claim.</p><main>'
                    + "".join(cards) + "</main>")
            receipt = safe_bytes(target / "preview.html", page.encode("utf-8"))
            outputs.append({"file": "preview.html", "kind": "offline_preview", **receipt})
            pak.assert_source_unchanged()
            manifest = {"kind": "character_body_reference", "captured_utc": datetime.now(timezone.utc).isoformat(),
                        "source": pak.summary(), "root_mapping_inputs": input_receipt,
                        "source_code": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                        for name in ["wandering_character_reference.py", "wandering_character_parser.py",
                                                     "wandering_reference.py", "wandering_decode_reference.py"]},
                        "selection": {"rows": args.row, "sword_slots": swords, "fist_slots": fists,
                                      "mode": "Exact mapping roots and actual referenced dependencies only"},
                        "members": [{**value, "output_relative": "raw/" + name}
                                    for name, value in graph.member_receipts.items()], "outputs": outputs,
                        "counts": {"action_roots": len(actions), "flipbooks": len(clips), "sprites": len(sprites),
                                   "textures": len(textures), "raw_members": len(graph.raw), "raw_bytes": graph.raw_bytes,
                                   "keyframes": sum(len(clip["keyframes"]) for clip in clips.values()),
                                   "encoded_previews": sum("png" in value for value in previews.values()),
                                   "animation_previews": sum(value.get("representation") == "apng" for value in previews.values()),
                                   "static_previews": sum(value.get("representation") == "static_png" for value in previews.values())},
                        "unavailable_actions": gaps, "visual_acceptance": "pending", "bbmod_ready": False}
            write_json_exclusive(target / "manifest.json", manifest)
            print(json.dumps({"status": "collected_source_body_reference", "output": str(target),
                              "manifest": str(target / "manifest.json"), "counts": manifest["counts"],
                              "unavailable_actions": gaps, "visual_acceptance": "pending", "bbmod_ready": False},
                             ensure_ascii=False, indent=2))
        except BaseException:
            remove_owned_output(target)
            raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReferenceError, OSError, ValueError, KeyError, TypeError, IndexError, struct.error, UnicodeError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
