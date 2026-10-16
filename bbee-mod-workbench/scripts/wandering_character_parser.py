"""Bounded UE4.26 Paper2D reference parsing; no game/plugin execution.

Package framing stays in the previously verified strict Package class. This module
adds explicit tagged layouts for PaperFlipbook/PaperSprite and inline BGRA8 only.
It does not change or broaden the original nine-member decoder's input profile.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import io
import math
import struct

from wandering_reference import checked_read, unpack, fstring, ReferenceError
from wandering_decode_reference import Package, require, consume_end, finish_uobject


def tag(package: Package, stream: io.BytesIO) -> dict | None:
    name = package.fname(stream)
    if name == "None":
        return None
    kind = package.fname(stream)
    size, array_index = unpack(stream, "<ii")
    require(0 <= size <= 32 * 1024 * 1024 and array_index == 0, "Unsupported property size/array index")
    extra = {}
    if kind == "StructProperty":
        extra["struct"] = package.fname(stream)
        require(checked_read(stream, 16) == bytes(16), "Nonzero struct GUID is outside this profile")
    elif kind == "BoolProperty":
        (value,) = unpack(stream, "<B")
        require(value in (0, 1), "Invalid boolean property")
        extra["boolean"] = bool(value)
    elif kind in {"ByteProperty", "EnumProperty"}:
        extra["enum"] = package.fname(stream)
    elif kind == "ArrayProperty":
        extra["inner"] = package.fname(stream)
    else:
        require(kind in {"FloatProperty", "IntProperty", "ObjectProperty", "NameProperty"},
                "Unknown Paper2D property tag kind: " + kind)
    require(unpack(stream, "<B")[0] == 0, "Property GUIDs are outside this profile")
    return {"name": name, "kind": kind, "raw": checked_read(stream, size), **extra}


def properties(package: Package, stream: io.BytesIO, allowed: set[str]) -> dict:
    result = {}
    for _ in range(128):
        entry = tag(package, stream)
        if entry is None:
            return result
        name = entry["name"]
        require(name in allowed and name not in result, "Unknown/repeated Paper2D field: " + name)
        result[name] = entry
    raise ReferenceError("Paper2D property count exceeds limit")


def scalar(entry: dict, fmt: str):
    require(len(entry["raw"]) == struct.calcsize(fmt), "Scalar property byte count mismatch")
    values = struct.unpack(fmt, entry["raw"])
    require(all(not isinstance(v, float) or math.isfinite(v) for v in values), "Nonfinite Paper2D scalar")
    return values[0] if len(values) == 1 else list(values)


def typed_scalar(props: dict, name: str, kind: str, fmt: str):
    require(name in props and props[name]["kind"] == kind, "Missing/wrong Paper2D field: " + name)
    return scalar(props[name], fmt)


def export_index(package: Package, object_name: str, class_name: str) -> int:
    found = [i for i, entry in enumerate(package.exports)
             if entry["name"] == object_name and package.resolve(entry["class_index"])["object"] == class_name]
    require(len(found) == 1, "Exact object/class export was not uniquely resolved")
    return found[0]


def reference(package: Package, index: int, expected_class: str) -> str:
    require(index != 0, "A required Paper2D reference is null")
    obj = package.resolve(index)
    if index > 0:
        entry = package.exports[index - 1]
        require(package.resolve(entry["class_index"])["object"] == expected_class, "Local reference class mismatch")
        # Local cross-export visual references are deliberately unsupported until
        # an exact owning-package identity is supplied by a caller.
        raise ReferenceError("Local visual cross-export references require an explicit owner; unsupported")
    require(obj["class"] == expected_class, "Imported visual reference class mismatch")
    parent = package.resolve(obj["outer_index"])
    require(parent is not None and parent["class"] == "Package" and parent["object"].startswith("/Game/"),
            "Visual import has no exact /Game package outer")
    return parent["object"] + "." + obj["object"]


def struct_array(package: Package, entry: dict, struct_name: str) -> tuple[int, io.BytesIO]:
    require(entry["kind"] == "ArrayProperty" and entry["inner"] == "StructProperty", "Expected struct array")
    stream = io.BytesIO(entry["raw"])
    (count,) = unpack(stream, "<i")
    require(0 < count <= 512, "Paper2D struct-array count exceeds limit")
    inner = tag(package, stream)
    require(inner is not None and inner["name"] == entry["name"] and inner["kind"] == "StructProperty"
            and inner["struct"] == struct_name, "Struct-array inner tag mismatch")
    consume_end(stream, len(entry["raw"]), "struct-array envelope")
    return count, io.BytesIO(inner["raw"])


def flipbook(package: Package, object_name: str) -> dict:
    index = export_index(package, object_name, "PaperFlipbook")
    stream = package.export(index)
    props = properties(package, stream, {"FramesPerSecond", "KeyFrames", "DefaultMaterial", "CollisionSource"})
    finish_uobject(stream)
    consume_end(stream, package.exports[index]["size"], "PaperFlipbook export")
    # Native class default documented in Epic's PaperFlipbook.cpp; it is recorded
    # explicitly when a serialized tag is omitted, never inferred from file names.
    fps = typed_scalar(props, "FramesPerSecond", "FloatProperty", "<f") if "FramesPerSecond" in props else 15.0
    require(0 < fps <= 120, "Unsupported animation FPS")
    require("KeyFrames" in props, "Flipbook has no serialized keyframes")
    count, rows = struct_array(package, props["KeyFrames"], "PaperFlipbookKeyFrame")
    frames = []
    fps_ratio = Fraction.from_float(fps)
    for _ in range(count):
        row = properties(package, rows, {"Sprite", "FrameRun"})
        ptr = typed_scalar(row, "Sprite", "ObjectProperty", "<i")
        run = typed_scalar(row, "FrameRun", "IntProperty", "<i") if "FrameRun" in row else 1
        require(1 <= run <= 600, "Invalid/oversized FrameRun")
        duration = Fraction(run, 1) / fps_ratio
        frames.append({"sprite": reference(package, ptr, "PaperSprite"), "frame_run": run,
                       "duration_seconds": float(duration), "duration_fraction": [duration.numerator, duration.denominator],
                       "frame_run_default_used": "FrameRun" not in row})
    consume_end(rows, len(rows.getbuffer()), "PaperFlipbook keyframe rows")
    return {"fps": fps, "fps_float32_hex": struct.pack("<f", fps).hex(), "keyframes": frames,
            "total_frame_runs": sum(frame["frame_run"] for frame in frames),
            "duration_seconds": sum(frame["duration_seconds"] for frame in frames),
            "fps_native_default_used": "FramesPerSecond" not in props,
            "material_scope": "Serialized material reference retained in raw package; shader/lighting not evaluated"}


def sprite(package: Package, object_name: str) -> dict:
    index = export_index(package, object_name, "PaperSprite")
    stream = package.export(index)
    allowed = {"BakedSourceUV", "BakedSourceDimension", "BakedSourceTexture", "PixelsPerUnrealUnit",
               "BodySetup", "BakedRenderData", "DefaultMaterial", "AlternateMaterial", "AlternateMaterialSplitIndex",
               "SpriteCollisionDomain", "AdditionalSourceTextures", "Sockets"}
    props = properties(package, stream, allowed)
    finish_uobject(stream)
    consume_end(stream, package.exports[index]["size"], "PaperSprite export")
    require("Sockets" not in props and "AdditionalSourceTextures" not in props,
            "Socket/additional-texture PaperSprite layouts require separate research")
    if "AlternateMaterialSplitIndex" in props:
        require(typed_scalar(props, "AlternateMaterialSplitIndex", "IntProperty", "<i") == -1,
                "Multiple-material sprite geometry is unsupported")
    dimension = typed_scalar(props, "BakedSourceDimension", "StructProperty", "<ff")
    require(props["BakedSourceDimension"]["struct"] == "Vector2D", "Wrong sprite dimension struct")
    source_uv = typed_scalar(props, "BakedSourceUV", "StructProperty", "<ff") if "BakedSourceUV" in props else [0.0, 0.0]
    if "BakedSourceUV" in props:
        require(props["BakedSourceUV"]["struct"] == "Vector2D", "Wrong sprite UV struct")
    ppu = typed_scalar(props, "PixelsPerUnrealUnit", "FloatProperty", "<f")
    require(0 < ppu <= 1000, "Unsupported PixelsPerUnrealUnit")
    texture = reference(package, typed_scalar(props, "BakedSourceTexture", "ObjectProperty", "<i"), "Texture2D")
    require("BakedRenderData" in props, "Sprite has no baked render geometry")
    count, vertices_raw = struct_array(package, props["BakedRenderData"], "Vector4")
    require(count >= 3 and count % 3 == 0, "Sprite render vertices are not triangles")
    vertices = [list(unpack(vertices_raw, "<ffff")) for _ in range(count)]
    require(all(math.isfinite(x) for vertex in vertices for x in vertex), "Nonfinite sprite vertex")
    consume_end(vertices_raw, len(vertices_raw.getbuffer()), "baked sprite vertices")
    return {"texture": texture, "source_uv": source_uv, "source_dimension": dimension,
            "source_uv_zero_default_used": "BakedSourceUV" not in props, "pixels_per_unreal_unit": ppu,
            "baked_vertices_xyuv": vertices, "physics_export_decoded": False,
            "material_scope": "Raw texels and baked geometry only; original shader lighting is not reproduced"}


def texture(package: Package, object_name: str) -> tuple[bytes, dict]:
    index = export_index(package, object_name, "Texture2D")
    stream = package.export(index)
    props = properties(package, stream, {"ImportedSize", "LightingGuid", "NeverStream", "CompressionSettings",
                                        "LODGroup", "Filter", "SRGB", "MipGenSettings"})
    finish_uobject(stream)
    require(checked_read(stream, 2) == b"\x01\x00" and checked_read(stream, 2) == b"\x01\x00",
            "Unsupported Texture2D source/strip flags")
    require(unpack(stream, "<i")[0] == 1, "Body texture is not cooked")
    require(package.fname(stream) == "PF_B8G8R8A8", "Only observed inline BGRA8 body atlases are supported")
    (skip,) = unpack(stream, "<q")
    width, height, slices = unpack(stream, "<iiI")
    require(0 < width <= 8192 and 0 < height <= 8192 and width * height <= 16_777_216 and slices == 1,
            "Body atlas dimensions exceed limits")
    require(typed_scalar(props, "ImportedSize", "StructProperty", "<ii") == [width, height], "Texture imported size mismatch")
    require(fstring(stream) == "PF_B8G8R8A8", "Body atlas pixel format mismatch")
    require(unpack(stream, "<iii") == (0, 1, 1), "Only observed single cooked mip body atlases are supported")
    flags, count, stored, offset = unpack(stream, "<Iiiq")
    require(flags == 0x48 and count == stored == width * height * 4, "Unknown/external/compressed body bulk data")
    require(offset == package.exports[index]["offset"] + stream.tell(), "Body pixel bulk offset mismatch")
    pixels = checked_read(stream, stored)
    require(unpack(stream, "<iii") == (width, height, 1) and unpack(stream, "<i")[0] == 0,
            "Body mip dimensions/virtual-texture flag mismatch")
    require(package.exports[index]["offset"] + stream.tell() == skip, "Body cooked-platform boundary mismatch")
    require(package.fname(stream) == "None", "Additional cooked texture formats are unsupported")
    consume_end(stream, package.exports[index]["size"], "body Texture2D export")
    return pixels, {"width": width, "height": height, "format": "PF_B8G8R8A8", "mips": 1,
                    "pixel_sha256_bgra": hashlib.sha256(pixels).hexdigest()}


def sprite_region(sprite_data: dict, texture_data: dict) -> dict:
    width, height = texture_data["width"], texture_data["height"]
    values = sprite_data["source_uv"] + sprite_data["source_dimension"]
    require(all(math.isfinite(v) and abs(v - round(v)) <= 1e-4 for v in values), "Noninteger sprite source rectangle")
    x, y, w, h = [round(v) for v in values]
    require(w > 0 and h > 0 and 0 <= x <= width - w and 0 <= y <= height - h,
            "Sprite source rectangle leaves its actual referenced atlas")
    ppu = sprite_data["pixels_per_unreal_unit"]
    pivots = []
    for px, pz, u, v in sprite_data["baked_vertices_xyuv"]:
        tex_x, tex_y = u * width, v * height
        require(x - 0.002 <= tex_x <= x + w + 0.002 and y - 0.002 <= tex_y <= y + h + 0.002,
                "Baked geometry UV leaves source rectangle")
        pivots.append([tex_x - px * ppu, tex_y + pz * ppu])
    absolute = [sum(p[i] for p in pivots) / len(pivots) for i in range(2)]
    require(all(abs(p[i] - absolute[i]) <= 0.002 for p in pivots for i in range(2)),
            "Rotated/skewed sprite UVs cannot use the verified axis-aligned pixel mapping")
    pivot = [absolute[0] - x, absolute[1] - y]
    # Preserve measured pivot values; never substitute center/bottom-center.
    return {"rectangle_xywh": [x, y, w, h], "pivot_pixels_from_crop_top_left": pivot,
            "pivot_absolute_texture_pixels": absolute, "pixels_per_unreal_unit": ppu,
            "pivot_method": "All baked XY/UV vertices solve texX = X*PPU + pivotX; texY = pivotY - Z*PPU",
            "pixel_scope": "Full declared source rectangle; material/mesh clipping/lighting not evaluated"}
