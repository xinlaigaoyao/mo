"""Decode the nine reviewed raw Wandering Sword reference members only.

Supports the two exact BGRA8 avatar Texture2Ds, tagged NPCResources rows,
and the version-3 Chinese skill locres. No schema guessing, code execution,
external bulk data, plugin loading, general UE compatibility or mod production.
The CLI requires a verified selected-export manifest under the reference root.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import sys

from wandering_reference import (
    EXPECTED_PAK_SHA256, OUTPUT_ROOT, WORKBENCH, ReferenceError,
    checked_read, fstring, unpack, plain_path, member_path,
    output_directory, remove_owned_output, write_json_exclusive,
)

PREFIX = "Wandering_Sword/Content/"
LOCKED_MEMBERS = {
    "JH/Characters/Image/T_Hero_HeadImage.uasset": "eee4ce5764178d06e96603cccf473073f1693791747846c906a5f7be139d8b52",
    "JH/Characters/Image/T_Hero_HeadImage.uexp": "720f6f2c7ae5923213e117d16dfdf8d56361267e86561371fe2fb4dd83e67f47",
    "JH/Characters/Image/T_Hero_WuDang_HeadImage.uasset": "c22be78133e8c5150bb866b9a57df76b8d4cbec9c6589825c4d4e2847c14ce4e",
    "JH/Characters/Image/T_Hero_WuDang_HeadImage.uexp": "4f0b3220ca5d441a61b6f1e86b39ddd3f9f8791d2574ba172bfa6e14b1ce5c9f",
    "JH/Tables/NPCResources.uasset": "dacbdb6ebb998e48f47bc40e9092eebc1f47765a7675c031ec691897031d9220",
    "JH/Tables/NPCResources.uexp": "e872fd05305ec2a660623396132673c0fe9c157f2fc1a42274f2a2a935e453c3",
    "Localization/Skills技能表/zh-Hans/Skills技能表.locres": "e90093d2d12918d48040c3915ba19dd9fb2e3ef4087bba2ad8e275750883fec4",
    "JH/Skills/WD_N_LiuYunTaiJi/GA_WD_N_LiuYunTaiJi.uasset": "670fdb88d934cd409b078da13f481921ea91ee2e222b1a78301919119702ee78",
    "JH/Skills/WD_N_LiuYunTaiJi/GA_WD_N_LiuYunTaiJi.uexp": "6be358ed23789a7523b16386252fc3e5dc7f7b518eaad9f1f1d96f8cc28f35b8",
}
MAGIC = 0x9E2A83C1


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReferenceError(reason)


def consume_end(stream: io.BytesIO, length: int, what: str) -> None:
    require(stream.tell() == length, f"Trailing/truncated bytes in {what}")


def read_inputs(manifest_path: Path) -> tuple[dict[str, bytes], dict]:
    manifest_path = Path(manifest_path.absolute())
    plain_path(manifest_path, stop_at=Path(WORKBENCH.anchor))
    manifest_path.relative_to(OUTPUT_ROOT)
    require(manifest_path.name == "manifest.json", "Expected a selected-export manifest.json")
    require(manifest_path.stat().st_size <= 1024 * 1024, "Oversized manifest")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    require(manifest.get("source", {}).get("source_pak_sha256") == EXPECTED_PAK_SHA256,
            "Manifest source differs from reviewed base PAK")
    entries = manifest.get("members", [])
    require(len(entries) == len(LOCKED_MEMBERS) == manifest.get("selected_count"),
            "This decoder requires exactly the nine reviewed reference members")
    data = {}
    receipts = []
    for entry in entries:
        name = member_path(entry["member"])
        require(name.startswith(PREFIX), "Unexpected member root")
        short = name[len(PREFIX):]
        require(short in LOCKED_MEMBERS and short not in data, "Unsupported or repeated selected member")
        relative = "raw/" + name
        require(entry["output_relative"] == relative, "Noncanonical raw member location")
        path = manifest_path.parent / Path(*relative.split("/"))
        plain_path(path, stop_at=OUTPUT_ROOT)
        require(path.stat().st_size == entry["uncompressed_bytes"] <= 16 * 1024 * 1024,
                "Raw member size changed/exceeds decoder limit")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == LOCKED_MEMBERS[short] == entry["decoded_sha256"],
                "Raw member hash differs from the reviewed fixture")
        data[short] = raw
        receipts.append({"member": name, "bytes": len(raw), "sha256": digest})
    return data, {"selected_manifest": str(manifest_path),
                  "selected_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                  "source_pak_sha256": EXPECTED_PAK_SHA256, "members": receipts}


class Package:
    """Specific UE4.26 tagged traditional-package profile, fully bounded."""

    def __init__(self, asset: bytes, uexp: bytes):
        self.asset, self.uexp = asset, uexp
        stream = io.BytesIO(asset)
        tag, legacy, ue3, ue4, licensee, custom_count = unpack(stream, "<Iiiiii")
        require((tag, legacy, ue3, ue4, licensee, custom_count) == (MAGIC, -7, 0, 0, 0, 0),
                "Unsupported package version/custom-version profile")
        (self.header_size,) = unpack(stream, "<i")
        require(self.header_size == len(asset), "Split package header size mismatch")
        require(fstring(stream) == "None", "Unexpected package folder")
        self.flags, name_count, name_offset = unpack(stream, "<Iii")
        require(self.flags == 0x80000000, "Unsupported package flags/unversioned property layout")
        gather_count, gather_offset, export_count, export_offset, import_count, import_offset = unpack(stream, "<iiiiii")
        require(gather_count == gather_offset == 0, "Unexpected gatherable text table")
        require(0 < name_count <= 100_000 and 0 < export_count <= 16 and 0 < import_count <= 128,
                "Package table count exceeds reviewed profile")
        require(0 <= name_offset < import_offset < export_offset < len(asset), "Invalid package table order")
        stream.seek(name_offset)
        self.names = []
        for _ in range(name_count):
            self.names.append(fstring(stream))
            checked_read(stream, 4)  # Serialized comparison/display name hashes, preserved in locked asset.
        require(stream.tell() == import_offset, "Name-map boundary mismatch")
        self.imports = []
        for _ in range(import_count):
            class_package = self.fname(stream)
            class_name = self.fname(stream)
            (outer,) = unpack(stream, "<i")
            object_name = self.fname(stream)
            self.imports.append({"class_package": class_package, "class": class_name,
                                 "outer_index": outer, "object": object_name})
        require(stream.tell() == export_offset, "Import-map boundary mismatch")
        self.exports = []
        previous_end = len(asset)
        for _ in range(export_count):
            export_raw = checked_read(stream, 104)
            row = io.BytesIO(export_raw)
            class_index, super_index, template_index, outer_index = unpack(row, "<iiii")
            name = self.fname(row)
            flags, size, offset = unpack(row, "<Iqq")
            require(offset == previous_end and size >= 0 and offset + size <= len(asset) + len(uexp) - 4,
                    "Export byte ranges are incomplete/overlapping")
            previous_end = offset + size
            self.exports.append({"class_index": class_index, "super_index": super_index,
                                 "template_index": template_index, "outer_index": outer_index,
                                 "name": name, "flags": flags, "size": size, "offset": offset})
        require(previous_end == len(asset) + len(uexp) - 4, "Split package export coverage mismatch")
        require(uexp[-4:] == struct.pack("<I", MAGIC), "Missing split package trailer")

    def fname(self, stream: io.BytesIO) -> str:
        index, number = unpack(stream, "<ii")
        require(0 <= index < len(self.names) and 0 <= number < 1_000_000, "Invalid FName reference")
        return self.names[index] + ("_" + str(number - 1) if number else "")

    def resolve(self, index: int) -> dict | None:
        if index == 0:
            return None
        if index < 0:
            require(-index <= len(self.imports), "Invalid import reference")
            return self.imports[-index - 1]
        require(index <= len(self.exports), "Invalid export reference")
        return {"object": self.exports[index - 1]["name"], "class": "export"}

    def export(self, index: int = 0) -> io.BytesIO:
        entry = self.exports[index]
        start = entry["offset"] - self.header_size
        return io.BytesIO(self.uexp[start:start + entry["size"]])

    def summary(self) -> dict:
        return {"stored_package_version": 0, "explicit_reading_profile": "UE4.26",
                "unversioned_properties": False, "package_flags": hex(self.flags),
                "name_count": len(self.names), "import_count": len(self.imports),
                "exports": [{**entry, "class_object": self.resolve(entry["class_index"])} for entry in self.exports]}

    def properties(self, stream: io.BytesIO, allowed: set[str]) -> dict:
        result = {}
        for _ in range(1000):
            name = self.fname(stream)
            if name == "None":
                return result
            kind = self.fname(stream)
            size, array_index = unpack(stream, "<ii")
            require(kind in allowed and 0 <= size <= 4 * 1024 * 1024 and array_index == 0,
                    f"Unsupported tagged property layout: {name}/{kind}")
            require(name not in result, "Repeated property name")
            extra = {}
            if kind == "StructProperty":
                extra["struct"] = self.fname(stream)
                extra["struct_guid"] = checked_read(stream, 16).hex()
            elif kind == "BoolProperty":
                (boolean,) = unpack(stream, "<B")
                require(boolean in (0, 1), "Invalid tagged boolean")
                extra["boolean"] = bool(boolean)
            elif kind == "ArrayProperty":
                extra["inner"] = self.fname(stream)
            (has_guid,) = unpack(stream, "<B")
            require(has_guid == 0, "Property GUIDs are outside the reviewed profile")
            raw = checked_read(stream, size)
            result[name] = {"kind": kind, "value": self.value(raw, kind, extra), **extra}
        raise ReferenceError("Tagged property count exceeds limit")

    def soft_path(self, stream: io.BytesIO) -> dict:
        return {"asset": self.fname(stream), "subpath": fstring(stream)}

    def value(self, raw: bytes, kind: str, extra: dict):
        stream = io.BytesIO(raw)
        if kind == "BoolProperty":
            value = extra["boolean"]
        elif kind in {"IntProperty", "ObjectProperty"}:
            (value,) = unpack(stream, "<i")
        elif kind == "SoftObjectProperty":
            value = self.soft_path(stream)
        elif kind == "ArrayProperty":
            require(extra["inner"] == "SoftObjectProperty", "Unsupported NPC array inner type")
            (count,) = unpack(stream, "<i")
            require(0 <= count <= 10_000, "NPC soft-reference array exceeds limit")
            value = [self.soft_path(stream) for _ in range(count)]
        elif kind == "StructProperty":
            if extra["struct"] == "IntPoint":
                value = list(unpack(stream, "<ii"))
            elif extra["struct"] == "Guid":
                value = checked_read(stream, 16).hex()
            else:
                raise ReferenceError("Unsupported avatar struct type")
        else:
            raise ReferenceError("Unsupported property value type")
        consume_end(stream, len(raw), "property value")
        return value


def finish_uobject(stream: io.BytesIO) -> None:
    require(unpack(stream, "<i")[0] == 0, "Unexpected UObject GUID")


def avatar(package: Package) -> tuple[bytes, dict]:
    require(len(package.exports) == 1 and package.resolve(package.exports[0]["class_index"])["object"] == "Texture2D",
            "Avatar is not a single Texture2D export")
    stream = package.export()
    props = package.properties(stream, {"StructProperty", "BoolProperty"})
    require(set(props) == {"ImportedSize", "LightingGuid", "NeverStream"}, "Unexpected avatar properties")
    finish_uobject(stream)
    require(checked_read(stream, 2) == b"\x01\x00", "Texture source/editor strip layout changed")
    require(checked_read(stream, 2) == b"\x01\x00", "Texture2D strip layout changed")
    require(unpack(stream, "<i")[0] == 1, "Expected a cooked Texture2D")
    require(package.fname(stream) == "PF_B8G8R8A8", "Only reviewed uncompressed BGRA8 avatars are supported")
    (skip_offset,) = unpack(stream, "<q")
    width, height, slices = unpack(stream, "<iiI")
    require(0 < width <= 4096 and 0 < height <= 4096 and slices == 1, "Unsupported avatar dimensions/slices")
    require(props["ImportedSize"]["value"] == [width, height], "Imported/platform size mismatch")
    require(fstring(stream) == "PF_B8G8R8A8", "Pixel format name mismatch")
    first_mip, mip_count, cooked_mip = unpack(stream, "<iii")
    require((first_mip, mip_count, cooked_mip) == (0, 1, 1), "Only the reviewed single cooked mip is supported")
    bulk_flags, element_count, stored_size, bulk_offset = unpack(stream, "<Iiiq")
    require(bulk_flags == 0x48, "Only reviewed inline/single-use uncompressed bulk data is supported")
    require(element_count == stored_size == width * height * 4, "BGRA8 pixel byte count mismatch")
    require(bulk_offset == package.header_size + stream.tell(), "Inline pixel absolute offset mismatch")
    pixels = checked_read(stream, element_count)
    require(unpack(stream, "<iii") == (width, height, 1), "Mip dimension mismatch")
    require(unpack(stream, "<i")[0] == 0, "Virtual textures are unsupported")
    require(package.header_size + stream.tell() == skip_offset, "Cooked platform-data boundary mismatch")
    require(package.fname(stream) == "None", "Unexpected additional cooked texture format")
    consume_end(stream, package.exports[0]["size"], "avatar export")
    return pixels, {"width": width, "height": height, "format": "PF_B8G8R8A8", "mips": 1,
                    "bulk_flags": hex(bulk_flags), "pixel_sha256_bgra": hashlib.sha256(pixels).hexdigest(),
                    "scope": "145px source avatar; not full portrait or character animation"}


def npc_hero_mapping(package: Package) -> dict:
    require(len(package.exports) == 1 and package.resolve(package.exports[0]["class_index"])["object"] == "DataTable",
            "NPCResources is not a single DataTable export")
    stream = package.export()
    props = package.properties(stream, {"ObjectProperty"})
    require(set(props) == {"RowStruct"}, "Unexpected DataTable properties")
    row_struct = package.resolve(props["RowStruct"]["value"])
    require(row_struct["object"] == "NPCResourceSetting" and row_struct["class"] == "ScriptStruct",
            "NPCResources row struct differs from reviewed profile")
    finish_uobject(stream)
    (count,) = unpack(stream, "<i")
    require(0 < count <= 10_000, "NPC row count exceeds limit")
    rows, row_names, kinds = {}, set(), Counter()
    for _ in range(count):
        name = package.fname(stream)
        require(name not in row_names, "Repeated NPC row")
        row_names.add(name)
        row = package.properties(stream, {"IntProperty", "BoolProperty", "SoftObjectProperty", "ArrayProperty"})
        kinds.update(prop["kind"] for prop in row.values())
        if name in {"Hero", "Hero_WuDang"}:
            rows[name] = row
    consume_end(stream, package.exports[0]["size"], "NPCResources export")
    require(set(rows) == {"Hero", "Hero_WuDang"}, "Expected Hero mapping rows are absent")
    return {"source_row_struct": "NPCResourceSetting", "all_rows_read": count,
            "property_kind_counts": dict(kinds), "selected_rows": rows,
            "scope": "Exact declared asset/flipbook references; referenced assets/frames have not been loaded"}


def locres(data: bytes) -> dict:
    stream = io.BytesIO(data)
    require(checked_read(stream, 16) == bytes.fromhex("0e147475674a03fc4a15909dc3377f1b"), "Invalid locres magic")
    require(unpack(stream, "<B")[0] == 3, "Only reviewed locres version 3 is supported")
    (strings_offset,) = unpack(stream, "<q")
    require(33 <= strings_offset < len(data), "Invalid localized-string table offset")
    entry_start = stream.tell()
    stream.seek(strings_offset)
    (string_count,) = unpack(stream, "<i")
    require(0 < string_count <= 100_000, "Localized string count exceeds limit")
    strings, refcounts = [], []
    for _ in range(string_count):
        strings.append(fstring(stream))
        (count,) = unpack(stream, "<i")
        require(0 <= count <= 100_000, "Invalid localized string reference count")
        refcounts.append(count)
    consume_end(stream, len(data), "localized string array")
    stream.seek(entry_start)
    entry_count, namespace_count = unpack(stream, "<II")
    require(entry_count <= 100_000 and 0 < namespace_count <= 1000, "Locres entry/namespace limits exceeded")
    entries, references, seen = [], Counter(), set()
    for _ in range(namespace_count):
        (namespace_hash,) = unpack(stream, "<I")
        namespace = fstring(stream)
        (count,) = unpack(stream, "<I")
        require(count <= entry_count, "Namespace count exceeds declared entries")
        for _ in range(count):
            (key_hash,) = unpack(stream, "<I")
            key = fstring(stream)
            source_hash, index = unpack(stream, "<Ii")
            require(0 <= index < string_count, "Locres string index is out of range")
            require((namespace, key) not in seen, "Repeated locres namespace/key")
            seen.add((namespace, key))
            references[index] += 1
            entries.append({"namespace": namespace, "key": key, "text": strings[index],
                            "namespace_hash_stored": namespace_hash, "key_hash_stored": key_hash,
                            "source_string_hash_stored": source_hash, "localized_string_index": index})
    require(len(entries) == entry_count and stream.tell() == strings_offset, "Locres entry region is incomplete")
    require(all(references[index] == count for index, count in enumerate(refcounts)), "Locres string refcount mismatch")
    return {"version": 3, "entries_count": entry_count, "localized_strings_count": string_count,
            "namespace_count": namespace_count, "entries": entries,
            "hash_scope": "Exact raw file SHA256 verified; namespace/key/source hash fields preserved, not recomputed"}


def focused_skills(decoded: dict) -> dict:
    terms = ["流云太极", "太极剑法", "真武剑气", "梯云纵", "太极拳", "太极神功"]
    direct = [entry for entry in decoded["entries"] if any(term in entry["text"] for term in terms)]
    ids = {entry["key"].split("_", 1)[0] for entry in direct if entry["key"].split("_", 1)[0].isdigit()}
    related = [entry for entry in decoded["entries"] if entry["key"].split("_", 1)[0] in ids]
    return {"terms": terms, "matching_skill_key_prefixes": sorted(ids), "entries": related,
            "scope": "Original localized wording, including rich-text tags/placeholders; not a BBEE mechanic specification"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    source, input_receipt = read_inputs(args.manifest)
    packages = {}
    for short in source:
        if short.endswith(".uasset"):
            packages[short[:-7]] = Package(source[short], source[short[:-7] + ".uexp"])
    avatar_data = []
    for stem in ("T_Hero_HeadImage", "T_Hero_WuDang_HeadImage"):
        package = packages["JH/Characters/Image/" + stem]
        pixels, details = avatar(package)
        avatar_data.append((stem, pixels, details))
    mapping = npc_hero_mapping(packages["JH/Tables/NPCResources"])
    skills = locres(source["Localization/Skills技能表/zh-Hans/Skills技能表.locres"])
    from PIL import Image, __version__ as pillow_version
    target = output_directory()
    try:
        outputs = []
        for stem, pixels, details in avatar_data:
            image = Image.frombytes("RGBA", (details["width"], details["height"]), pixels, "raw", "BGRA", 0, 1)
            path = target / (stem + ".png")
            with path.open("xb") as stream:
                image.save(stream, format="PNG")
            with Image.open(path) as restored:
                restored.load()
                require(restored.mode == "RGBA" and restored.size == image.size and restored.tobytes() == image.tobytes(),
                        "PNG decoded pixels differ from the original BGRA conversion")
            outputs.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **details})
        for name, data in (("hero-resource-mapping.json", mapping), ("skill-text.json", skills),
                           ("skill-text-focus.json", focused_skills(skills))):
            write_json_exclusive(target / name, data)
            outputs.append({"file": name, "sha256": hashlib.sha256((target / name).read_bytes()).hexdigest()})
        receipt = {"kind": "decoded_reference", "captured_utc": datetime.now(timezone.utc).isoformat(),
                   "inputs": input_receipt, "decoder_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "pillow_version": pillow_version, "package_structures": {key: pkg.summary() for key, pkg in packages.items()},
                   "outputs": outputs, "visual_identity_review": "pending; structural/pixel checks do not confirm identity",
                   "limitations": ["Two small avatars only; no full portrait, body sprites or animation frames.",
                                   "NPC mapping points to assets that remain unexported/unread.",
                                   "Original localized skill text is not proof of runtime mechanics or BBEE balance.",
                                   "No GA/CDO mechanics, Blueprint bytecode or third-party binaries executed."]}
        write_json_exclusive(target / "manifest.json", receipt)
        print(json.dumps({"status": "decoded_reference", "output": str(target), "manifest": str(target / "manifest.json"),
                          "avatar_count": 2, "npc_rows_read": mapping["all_rows_read"],
                          "skill_text_entries": skills["entries_count"], "visual_identity_review": "pending"}, ensure_ascii=False, indent=2))
    except BaseException:
        remove_owned_output(target)
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReferenceError, OSError, ValueError, KeyError, TypeError, struct.error, UnicodeError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
