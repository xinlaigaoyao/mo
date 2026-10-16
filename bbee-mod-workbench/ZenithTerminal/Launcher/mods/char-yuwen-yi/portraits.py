"""Complete, owned Yuwen Yi UI art and its static descriptor interface.

Original TeamImage is a 900x835 composition, not an invented full-body drawing.
All slots preserve its aspect ratio. FightImage supplies head icons. Geometry,
portrait placement and content hashes are frozen during explicit preparation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from body_source import (HERE, ROOT, PREPARED, PRODUCTION, PAK_SHA, read_json, read_reference,
                         plain, image, sha, write_png)

ACTOR = 200901
DONOR = 103701
ATLAS = "ui/atlas/iconpotential200901/iconpotential200901"
ATLAS_DONOR = "ui/atlas/iconpotential103401/iconpotential103401"
ATLAS_DONOR_SHA256 = "c70b21647f16104ee5290db54b5352a2bfa530d23e83c1ebaff4ce7957f4c57a"
UI_FILE = PREPARED / "ui-art.json"
KEYS = ("BattleChallengePrepare", "BreedFinishRoom", "BreedPrepare", "BreedPrepareS", "BreedResult", "FesL", "FesR",
        "FesShadowL", "FesShadowR", "GenericActorDetail", "PvpTeamMatchL", "PvpTeamMatchR")
HEADS = {
    "head": ("HeroHeadIcon", "HeroHeadIcon_200901", (256, 256)),
    "smallhead": ("HeroHeadIcon", "HeroSmallHead_200901", (128, 128)),
    "evohead": ("HeroHeadIcon", "HeroEvoHead_200901", (189, 184)),
    "evohead_off": ("HeroHeadIcon", "HeroEvoHead_Off_200901", (189, 184)),
    "finalbattle": ("HeroHeadIcon", "HeroFinalBattle_200901", (258, 237)),
    "pvpfinish": ("HeroHeadIcon", "HeroPvPFinish_200901", (827, 221)),
    "pda": ("HeroHeadIcon", "HeroPDA_200901", (287, 477)),
    "skill": ("IconSkill", "IconSkill_200901", (256, 256)),
}
ALIASES = {
    "HeroHead_200901": "evohead", "HeroHead_200901_Off": "evohead_off", "HeroPortraitFull_200901_S": "head",
    "PVE_HeroPortraitFull_200901_H": "smallhead", "PVP_HeroPortraitFull_200901": "smallhead",
    "BaseActor_200901": "smallhead", "BaseActor_200901_S": "smallhead", "FesActor_200901k": "smallhead",
    "FesActor_200901k_S": "smallhead", "HeroPortraitFull_200901": "finalbattle",
    "PvPFinish_HeroPortraitFull_200901": "pvpfinish", "PDA_HeroPortraitFull_200901": "pda", "IconSkill_200901": "skill",
}


def fit(im, size):
    scale = min(size[0] / im.width, size[1] / im.height)
    resized = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.alpha_composite(resized, ((size[0] - resized.width) // 2, size[1] - resized.height))
    return result


def taiji_icon(index, size=96):
    """Independently authored vector icons; never stock potential icon pixels."""
    k = 3
    out = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    def xy(points):
        return [(round(x * k), round(y * k)) for x, y in points]
    def box(v):
        return tuple(round(x * k) for x in v)
    cyan, gold, white = (144, 226, 245, 255), (246, 205, 116, 255), (240, 249, 244, 255)
    d.ellipse(box((4, 4, 92, 92)), fill=(15, 31, 43, 245), outline=gold, width=2 * k)
    mode = index % 5
    if mode == 0:  # sword; different wind rings for sword-related potentials
        d.polygon(xy([(31, 67), (58, 27), (70, 18), (69, 35), (40, 72)]), fill=white)
        d.line(xy([(29, 61), (47, 75)]), fill=gold, width=4 * k)
        d.line(xy([(34, 69), (25, 81)]), fill=cyan, width=5 * k)
        d.arc(box((14, 14, 82, 82)), 20 + index * 11, 155 + index * 11, fill=cyan, width=3 * k)
    elif mode == 1:  # yin-yang, constructed from exact geometric halves
        d.ellipse(box((23, 23, 73, 73)), fill=cyan)
        d.pieslice(box((23, 23, 73, 73)), 90, 270, fill=white)
        d.ellipse(box((36, 23, 60, 49)), fill=white)
        d.ellipse(box((36, 47, 60, 73)), fill=cyan)
        d.ellipse(box((44, 31, 52, 39)), fill=cyan)
        d.ellipse(box((44, 57, 52, 65)), fill=white)
    elif mode == 2:  # qi orbit
        for radius in (14, 24, 34):
            d.arc(box((48-radius, 48-radius, 48+radius, 48+radius)), index * 25, 260 + index * 25, fill=cyan if radius != 24 else gold, width=3 * k)
        d.ellipse(box((43, 43, 53, 53)), fill=white)
    elif mode == 3:  # guard seal
        d.polygon(xy([(48, 20), (72, 31), (67, 61), (48, 77), (29, 61), (24, 31)]), fill=(47, 90, 112, 255), outline=gold, width=3 * k)
        d.line(xy([(35, 48), (45, 59), (63, 37)]), fill=white, width=4 * k)
    else:  # palm impulse
        d.rounded_rectangle(box((35, 37, 64, 66)), radius=5*k, fill=cyan)
        for x, top in ((35, 28), (43, 22), (51, 20), (59, 26)):
            d.rounded_rectangle(box((x, top, x+6, 49)), radius=3*k, fill=white)
        d.line(xy([(35, 55), (25, 46), (22, 52), (35, 67), (51, 73)]), fill=gold, width=6*k)
    # Individually visible rank dots distinguish the twelve potential variants.
    if index < 12:
        for n in range(index // 5 + 1):
            x = 40 + n * 8
            d.ellipse(box((x, 82, x+4, 86)), fill=gold)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def placement_rows(team, landmarks):
    table = ROOT / "decoded/tables/HeroPortraitOffsetConfigUI.json"
    if table.with_suffix(table.suffix + ".orig").is_file():
        table = table.with_suffix(table.suffix + ".orig")
    rows = read_json(table, roots=(ROOT / "decoded/tables",))
    if isinstance(rows, dict):
        lists = [v for v in rows.values() if isinstance(v, list)]
        if len(lists) != 1:
            raise ValueError("ambiguous native portrait placement table")
        rows = lists[0]
    reference = {r["Key"]: r for r in rows if r["Id"] == 102901}
    if not set(KEYS).issubset(reference):
        raise ValueError("native reference lacks a required portrait placement key")
    face_x, top, floor = (landmarks[name] for name in ("face_x", "top", "floor"))
    if not all(math.isfinite(v) for v in (face_x, top, floor)) or not 0 <= face_x < team.width or not 0 <= top < floor <= team.height:
        raise ValueError("portrait landmarks must be measured on the original TeamImage")
    result = []
    for key in KEYS:
        r = reference[key]
        # Hibiki's measured portrait reference lines from the established native
        # integration route. Our original composition is framed between those
        # lines, preserving its aspect ratio and face position.
        ref_w, ref_h, ref_top, ref_floor, ref_x = 1480, 1788, 141, 1256, 712
        y_top = ((1 - ref_top / ref_h) - r["PivotY"]) * ref_h * r["Scale"]
        y_floor = ((1 - ref_floor / ref_h) - r["PivotY"]) * ref_h * r["Scale"]
        x_face = (ref_x / ref_w - r["PivotX"]) * ref_w * r["Scale"]
        scale = (y_top - y_floor) / (floor - top)
        px = face_x / team.width - x_face / (scale * team.width)
        py = 1 - top / team.height - y_top / (scale * team.height)
        result.append({"Id": ACTOR, "Key": key, "PivotX": round(px, 6), "PivotY": round(py, 6), "Scale": round(scale, 6), "$append": True})
    return result, {"file": str(table), "sha256": sha(table), "reference_actor": 102901,
                    "scope": "Native UI placement values only; no reference artwork pixels"}


def prepare(output, production):
    output = plain(output)
    manifest_path = Path(production["portrait_manifest"])
    _, outputs = read_reference(manifest_path, "character_portrait_reference", production["portrait_manifest_sha256"])
    ref_path = manifest_path.parent / "portrait-reference.json"
    ref = read_json(ref_path, outputs["portrait-reference.json"]["sha256"])
    selected = {p["field"]: p for p in ref["portraits"] if p["row"] == "Hero_WuDang"}
    if set(selected) != {"TeamImage", "DlgImage", "FightImage"}:
        raise ValueError("complete selected original portrait chain is required")
    original = {}
    for field, entry in selected.items():
        path = manifest_path.parent / entry["png"]
        if entry["sha256"] != outputs[entry["png"]]["sha256"]:
            raise ValueError("portrait output receipt mismatch")
        original[field] = image(path, entry["sha256"])
    review = read_json(production["visual_review"], production["visual_review_sha256"],
                       roots=(HERE / "assets", ROOT.parents[1] / "evidence/yuwen-yi"))
    landmarks = review.get("portrait_landmarks")
    if not landmarks:
        raise ValueError("measured portrait landmarks missing from visual review")
    team, head = original["TeamImage"], original["FightImage"]
    # BC7 texture donor requires dimensions divisible by four. Padding retains
    # every original TeamImage pixel at 1:1; it does not invent missing anatomy.
    full_size = (math.ceil(team.width / 4) * 4, math.ceil(team.height / 4) * 4)
    full = Image.new("RGBA", full_size, (0, 0, 0, 0)); full.paste(team, (0, 0))
    offsets, placement_provenance = placement_rows(full, landmarks)
    slots = {
        "full": ("HeroPortraitFull/HeroPortraitFull_200901", full),
        "lmb": ("HeroPortraitLMB/HeroPortraitFull_200901", fit(team, (1024, 1024))),
        "mb": ("HeroPortraitFullMB/HeroPortraitFull_200901", fit(team, (2048, 2048))),
        "coatarms": ("HeroPortraitCoatArms/HeroPortraitFull_200901", fit(taiji_icon(1, 512), (1024, 1024))),
    }
    banner = fit(original["DlgImage"], HEADS["pvpfinish"][2])
    pda = fit(original["DlgImage"], HEADS["pda"][2])
    for key, (folder, name, size) in HEADS.items():
        if key == "pvpfinish":
            pic = banner
        elif key == "pda":
            pic = pda
        elif key == "skill":
            pic = taiji_icon(0, size[0])
        else:
            pic = fit(head, size)
            if key in ("evohead", "evohead_off"):
                mask = Image.new("L", size, 0)
                ImageDraw.Draw(mask).polygon([(size[0]//2,0),(size[0],size[1]//2),(size[0]//2,size[1]),(0,size[1]//2)], fill=255)
                from PIL import ImageChops
                pic.putalpha(ImageChops.darker(pic.getchannel("A"), mask))
                if key == "evohead_off":
                    grey = ImageOps.grayscale(pic).convert("RGBA"); grey.putalpha(pic.getchannel("A")); pic = grey
        slots[key] = (folder + "/" + name, pic)
    atlas = Image.new("RGBA", (384, 384), (0, 0, 0, 0))
    icon_names = ["Potential_" + str(i) for i in range(209001, 209013)] + ["Talent_209080", "Ywy_Qi", "Ywy_Taiji", "Ywy_Guard"]
    atlas_sprites = []
    atlas_items = []
    for index, name in enumerate(icon_names):
        icon_index = index if index < 13 else {"Ywy_Qi": 2, "Ywy_Taiji": 1, "Ywy_Guard": 3}[name]
        icon = taiji_icon(icon_index)
        x, y = index % 4 * 96, index // 4 * 96
        atlas.paste(icon, (x, y))
        icon_path = output / "icons" / (name + ".png")
        write_png(icon_path, icon)
        atlas_items.append([name, str(icon_path)])
        atlas_sprites.append({"name": name, "file": str(icon_path), "sha256": sha(icon_path),
                              "preview_rect": [x, 384 - y - 96, 96, 96], "pivot": [0.5, 0.5]})
        if index < 12:
            # Detailed potential pages use Texture loading, whereas battle
            # cards use atlas sprites. Supply both native routes from the
            # exact same owned icon pixels, with matching real 96x96 metrics.
            slots["potential_" + str(209001 + index)] = ("IconPotential/" + name, icon.copy())
    preview_path = output / "ui" / "potential_atlas_preview.png"
    write_png(preview_path, atlas)
    textures, metrics = [], []
    for key, (native_path, pic) in slots.items():
        path = output / "ui" / (key + ".png")
        write_png(path, pic)
        logical = "ui/texture/" + native_path.lower()
        textures.append({"key": key, "logical": logical, "native_path": "UI/Texture/" + native_path,
                         "file": str(path), "sha256": sha(path), "size": list(pic.size),
                         "provenance": "Same owned potential icon pixels as atlas sprite " + native_path.rsplit("/", 1)[1] if key.startswith("potential_") else "Original Hero_WuDang Team/Dialog/FightImage aspect-preserving composition; crest/skill/atlas are own geometric drawings"})
        metrics.append({"list": "_entries", "key": "path", "value": {"path": "UI/Texture/" + native_path, "width": pic.width, "height": pic.height}})
    aliases = {name: "tex:UI/Texture/" + HEADS[key][0] + "/" + HEADS[key][1] for name, key in ALIASES.items()}
    return {"schema": 1, "kind": "yuwen_yi_ui_art", "source_pak_sha256": PAK_SHA, "textures": textures,
            "portrait_source_manifest": str(manifest_path), "portrait_source_sha256": production["portrait_manifest_sha256"],
            "placement_provenance": placement_provenance,
            "atlas_preview": {"file": str(preview_path), "sha256": sha(preview_path), "scope": "Preview arrangement only; native atlas donor owns actual packing"},
            "spec": {"spriteAliases": aliases, "metrics": metrics, "HeroPortraitOffsetConfigUI": offsets,
                     "content": {"assets": [{"bundle": "ui/texture/metrics.ab", "asset": "metrics", "appendItems": metrics}]},
                     "potentialAtlas": {"path": ATLAS, "donor": ATLAS_DONOR,
                                        "rename": [["IconPotential103401", "IconPotential200901"]],
                                        "donor_evidence": {"game_build": "25627491", "bundle_sha256": ATLAS_DONOR_SHA256,
                                                           "sprite_objects": 16, "distinct_positions": 16,
                                                           "cell_size": [120, 120], "texture_size": [976, 244],
                                                           "scope": "Stock object layout only; all sixteen icon cells replaced by owned images"},
                                        "items": atlas_items, "sprites": atlas_sprites,
                                        "native_contract": "bundleClones.atlasSprites consumes [name, absolute PNG file]; no source stock icons retained"}}}


def prepared(path=UI_FILE):
    data = read_json(path)
    production = read_json(PRODUCTION)
    if sha(plain(path)) != production.get("ui_manifest_sha256"):
        raise ValueError("prepared UI art differs from production freeze")
    for name, digest in production["producers"].items():
        if sha(HERE / name) != digest:
            raise ValueError("artwork producer changed after freeze")
    if data.get("kind") != "yuwen_yi_ui_art" or data.get("source_pak_sha256") != PAK_SHA:
        raise ValueError("invalid prepared UI artwork manifest")
    expected = {"full", "lmb", "mb", "coatarms", *HEADS, *("potential_" + str(i) for i in range(209001, 209013))}
    if {item["key"] for item in data["textures"]} != expected:
        raise ValueError("prepared UI art does not cover every required slot")
    for entry in data["textures"]:
        if list(image(entry["file"], entry["sha256"]).size) != entry["size"]:
            raise ValueError("prepared UI texture geometry changed")
    icon_names = {"Potential_" + str(i) for i in range(209001, 209013)} | {"Talent_209080", "Ywy_Qi", "Ywy_Taiji", "Ywy_Guard"}
    if {entry["name"] for entry in data["spec"]["potentialAtlas"]["sprites"]} != icon_names:
        raise ValueError("prepared potential atlas does not cover all 16 owned icons")
    for entry in data["spec"]["potentialAtlas"]["sprites"]:
        if image(entry["file"], entry["sha256"]).size != (96, 96):
            raise ValueError("potential icon missing/changed")
        if entry["name"].startswith("Potential_"):
            pid = entry["name"].removeprefix("Potential_")
            texture = next(item for item in data["textures"] if item["key"] == "potential_" + pid)
            expected_path = "UI/Texture/IconPotential/" + entry["name"]
            metrics = [m["value"] for m in data["spec"]["metrics"] if m["value"]["path"] == expected_path]
            if texture["native_path"] != expected_path or texture["size"] != [96, 96] or len(metrics) != 1 or (metrics[0]["width"], metrics[0]["height"]) != (96, 96):
                raise ValueError("native potential Texture path/metrics missing")
            if image(entry["file"], entry["sha256"]).tobytes() != image(texture["file"], texture["sha256"]).tobytes():
                raise ValueError("potential Texture and atlas source pixels differ")
    ref = data["placement_provenance"]
    if sha(plain(ref["file"], (ROOT / "decoded/tables",))) != ref["sha256"]:
        raise ValueError("native UI placement table changed after preparation")
    return data


def spec():
    """Generator consumes this exact static half after whole-asset preparation."""
    return prepared()["spec"]


def build(out_dir, log=print):
    import bbtag_rig
    data = prepared()
    adds = {"names": [], "entries": [], "guids": []}
    src = "ui/texture/heroportraitcoatarms/heroportraitfull_" + str(DONOR)
    for entry in data["textures"]:
        native = entry["native_path"].removeprefix("UI/Texture/")
        folder, name = native.rsplit("/", 1)
        renames = [("HeroPortraitCoatArms", folder), ("HeroPortraitFull_" + str(DONOR), name)]
        result = bbtag_rig.clone_texture(src, entry["logical"], renames,
                                         image(entry["file"], entry["sha256"]), str(out_dir), log)
        for key in adds:
            adds[key] += result[key]
    return adds
