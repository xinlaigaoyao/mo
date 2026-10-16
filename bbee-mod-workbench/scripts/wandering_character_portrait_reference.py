"""Collect exactly the mapped Hero portraits and original NPC identity text.

Uses the unchanged nine-member fixture for NPCResources roots. Six mapped
Texture2Ds, one zh-Hans locres and the two NPCs master-table members are selected;
the master table is retained as raw evidence, not decoded through a relaxed
package profile. No recursive search, game execution or bulk extraction.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

from wandering_reference import (
    PAK_PATH, EXPECTED_PAK_SHA256, OUTPUT_ROOT, PakV11, ReferenceError,
    member_path, plain_path, output_directory, remove_owned_output, write_json_exclusive,
)
from wandering_decode_reference import read_inputs, npc_hero_mapping, Package, require, locres
from wandering_character_parser import texture
from wandering_character_reference import safe_bytes, png_bytes, object_parts

PREFIX = "Wandering_Sword/Content/"
FIELDS = ("TeamImage", "DlgImage", "FightImage")
IDENTITY_MEMBER = PREFIX + "Localization/Npc/zh-Hans/Npc.locres"
MASTER_MEMBERS = [PREFIX + "JH/Tables/NPCs" + suffix for suffix in (".uasset", ".uexp")]
MIB = 1024 * 1024


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-manifest", required=True, type=Path)
    args = ap.parse_args(argv)
    fixture, input_receipt = read_inputs(args.raw_manifest)
    mapping = npc_hero_mapping(Package(fixture["JH/Tables/NPCResources.uasset"],
                                      fixture["JH/Tables/NPCResources.uexp"]))
    roots = []
    for row_name in ("Hero", "Hero_WuDang"):
        row = mapping["selected_rows"][row_name]
        require(row["Id"]["kind"] == "IntProperty" and row["Id"]["value"] in (0, 1), "Hero Id profile changed")
        for field in FIELDS:
            item = row[field]
            require(item["kind"] == "SoftObjectProperty" and item["value"]["subpath"] == "", "Portrait root layout changed")
            package, obj = object_parts(item["value"]["asset"])
            expected = "T_" + row_name + "_HeadImage" + {"TeamImage": "1", "DlgImage": "2", "FightImage": "3"}[field]
            require(package == "/Game/JH/Characters/Image/" + expected and obj == expected, "Exact reviewed portrait mapping changed")
            roots.append({"row": row_name, "npc_resource_id": row["Id"]["value"], "field": field,
                          "object": item["value"]["asset"], "stem": expected, "package": package})
    from PIL import Image, __version__ as pillow_version
    plain_path(PAK_PATH, stop_at=Path(PAK_PATH.anchor))
    with PAK_PATH.open("rb") as source:
        pak = PakV11(source, EXPECTED_PAK_SHA256)
        raw, receipts, decoded = {}, {}, []
        def selected(member):
            member = member_path(member)
            require(member in pak.entries and member not in raw and len(raw) < 15, "Unexpected/repeated portrait member")
            data, receipt = pak.read_selected(member, 32 * MIB)
            require(sum(map(len, raw.values())) + len(data) <= 64 * MIB, "Portrait source byte cap exceeded")
            raw[member], receipts[member] = data, receipt
            return data
        for root in roots:
            member = PREFIX + root["package"].removeprefix("/Game/")
            package = Package(selected(member + ".uasset"), selected(member + ".uexp"))
            pixels, details = texture(package, root["stem"])
            expected_size = {"TeamImage": (900, 835), "DlgImage": (500, 534), "FightImage": (173, 173)}[root["field"]]
            require((details["width"], details["height"]) == expected_size, "Reviewed portrait dimensions changed")
            image = Image.frombytes("RGBA", expected_size, pixels, "raw", "BGRA", 0, 1)
            require(image.getchannel("A").getbbox() is not None, "Original portrait is empty")
            decoded.append((root, details, image))
        text = locres(selected(IDENTITY_MEMBER))
        focus = [e for e in text["entries"] if e["namespace"] == "NPCs" and e["key"] in {"0_Name", "1_Name", "0_Description", "1_Description"}]
        names = {e["key"]: e["text"] for e in focus}
        require(names.get("0_Name") == names.get("1_Name") == "宇文逸", "Original NPC identity text changed")
        # Retain primary table bytes without pretending the old strict package
        # decoder supports its distinct localization-gather header/schema.
        for member in MASTER_MEMBERS:
            selected(member)
        pak.assert_source_unchanged()
        target = output_directory()
        try:
            outputs, portrait_rows = [], []
            for member, data in raw.items():
                path = target / "raw" / Path(*member.split("/"))
                outputs.append({"file": path.relative_to(target).as_posix(), "kind": "raw_member", **safe_bytes(path, data)})
            for root, details, image in decoded:
                path = target / "portraits" / (root["stem"] + ".png")
                receipt = safe_bytes(path, png_bytes(image))
                outputs.append({"file": path.relative_to(target).as_posix(), "kind": "portrait_png", **receipt})
                portrait_rows.append({**root, **details, "png": path.relative_to(target).as_posix(),
                                      "alpha_bbox": list(image.getchannel("A").getbbox()), **receipt})
            dataset = {"portraits": portrait_rows, "identity_text": focus,
                       "identity_join": "NPCResources Hero.Id=0/Hero_WuDang.Id=1 joined to NPCs namespace 0_Name/1_Name; NPCs master resource relation not decoded",
                       "master_table": {"decoded": False, "reason": "0x80040000 localization-gather profile outside unchanged old decoder", "raw_members": MASTER_MEMBERS},
                       "visual_acceptance": "pending", "portrait_framing": "Original Team/Dialog crops; full-body framing remains a visual question"}
            write_json_exclusive(target / "portrait-reference.json", dataset)
            outputs.append({"file": "portrait-reference.json", "kind": "reference_json",
                            "sha256": hashlib.sha256((target / "portrait-reference.json").read_bytes()).hexdigest()})
            manifest = {"kind": "character_portrait_reference", "captured_utc": datetime.now(timezone.utc).isoformat(),
                        "source": pak.summary(), "root_mapping_inputs": input_receipt, "pillow_version": pillow_version,
                        "source_code": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                        for name in ("wandering_character_portrait_reference.py", "wandering_character_parser.py", "wandering_character_reference.py", "wandering_decode_reference.py", "wandering_reference.py")},
                        "members": [{**receipt, "output_relative": "raw/" + member} for member, receipt in receipts.items()],
                        "outputs": outputs, "counts": {"raw_members": len(raw), "raw_bytes": sum(map(len, raw.values())), "portraits": len(decoded), "locres_entries": text["entries_count"]},
                        "visual_acceptance": "pending", "bbmod_ready": False}
            write_json_exclusive(target / "manifest.json", manifest)
            print(json.dumps({"status": "collected_portrait_reference", "manifest": str(target / "manifest.json"), "counts": manifest["counts"], "visual_acceptance": "pending"}, ensure_ascii=False, indent=2))
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
