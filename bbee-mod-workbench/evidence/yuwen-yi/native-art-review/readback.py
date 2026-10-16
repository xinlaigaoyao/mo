"""Read-only native-art QA snapshot; never imports character producers or builds."""
from __future__ import annotations
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(r"E:\AAA MOD\bbee-mod-workbench")
LAUNCHER = ROOT / "ZenithTerminal/Launcher"
OUT = LAUNCHER / "patch_out"
AREA = ROOT / "evidence/yuwen-yi/native-art-review"
PRODUCTION = LAUNCHER / "mods/char-yuwen-yi/assets/prepared/production-manifest.json"
PPU = 64
sys.path.insert(0, str(LAUNCHER))
sys.argv = ["readonly-native-art-review"]
os.environ["BBMOD_BUILD_ID"] = "25627491"
import bbmod
import UnityPy
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence, __version__ as pillow_version

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def need(value, message):
    if not value:
        raise ValueError(message)

def json_file(path):
    return json.loads(path.read_text("utf-8"))

def safe_output(path):
    need(path.is_relative_to(AREA) and not path.exists(), "QA output exists/outside owned directory")
    for p in [path, *path.parents]:
        if p.exists():
            need(not p.is_symlink() and not getattr(p.stat(), "st_file_attributes", 0) & 0x400, "Linked QA directory")
        if p == ROOT:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def checker(size):
    im = Image.new("RGBA", size, (57, 63, 72, 255))
    draw = ImageDraw.Draw(im)
    for y in range(0, size[1], 12):
        for x in range(0, size[0], 12):
            if (x//12 + y//12) % 2:
                draw.rectangle((x, y, x+11, y+11), fill=(80, 86, 94, 255))
    return im

def main():
    build_path, verify_path = OUT / "_build.json", OUT / "_verification.json"
    frozen = {"build": sha(build_path), "verification": sha(verify_path), "production": sha(PRODUCTION)}
    build, verification, production = json_file(build_path), json_file(verify_path), json_file(PRODUCTION)
    need(verification["status"] == "passed" and build["gameBuild"] == "25627491" and "char-yuwen-yi" in build["mods"], "Complete character build has not passed")
    need(verification["metadata_hashes"]["_build.json"] == frozen["build"], "Unbound build metadata")
    target = AREA / ("build-" + frozen["build"][:16])
    need(not target.exists(), "This build already has native-art QA; refusing overwrite")
    target.mkdir()
    records, inputs, loaded, cabs = [], {}, {}, {}
    verified = {item["path"]: item for item in verification["files"]}
    font = ImageFont.load_default(size=14)
    def save_png(relative, im):
        path = safe_output(target / relative)
        with path.open("xb") as f:
            im.save(f, "PNG")
        with Image.open(path) as restored:
            restored.load()
            need(restored.mode == im.mode and restored.size == im.size and restored.tobytes() == im.tobytes(), "QA PNG pixel readback mismatch")
        records.append({"file": path.relative_to(target).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path), "size": list(im.size)})
        return path.relative_to(target).as_posix()
    def load(logical):
        if logical in loaded:
            return loaded[logical]
        relative = logical + ".ab"
        path = OUT / relative
        need(relative in verified and sha(path) == verified[relative]["sha256"], "Native input changed/unverified: " + relative)
        inputs[relative] = {"sha256": sha(path), "bytes": path.stat().st_size}
        env = UnityPy.load(path.read_bytes())
        env.typetree_generator = bbmod.typetree_gen()
        loaded[logical] = env
        for cab, sf in env.file.files.items():
            if hasattr(sf, "objects"):
                need(cab.lower() not in cabs, "Duplicate native CAB")
                cabs[cab.lower()] = (logical, sf)
        return env
    def mono(logical):
        env = load(logical)
        result = [(sf, obj.read_typetree()) for sf in env.file.files.values() if hasattr(sf, "objects") for obj in sf.objects.values() if obj.type.name == "MonoBehaviour"]
        need(len(result) == 1, "Ambiguous native animation/texture family")
        return result[0]
    additions = json_file(OUT / "_manifest_add.json")
    need(sha(OUT / "_manifest_add.json") == verification["metadata_hashes"]["_manifest_add.json"], "Manifest additions changed")
    guid_map = {guid.lower(): logical for logical, guid in additions["guids"]}
    _, family = mono("actor/texturefamily/ywy_02")
    pages = []
    for pointer in family["textureRefs"]:
        guid = struct.pack("<QQ", pointer["_guid0"], pointer["_guid1"]).hex()
        need(guid in guid_map and guid_map[guid].startswith("actor/sprite/ywy/02/"), "Native family GUID does not resolve to owned color page")
        logical = guid_map[guid]
        tex = [obj.read() for obj in load(logical).objects if obj.type.name == "Texture2D"]
        need(len(tex) == 1, "Native color page has ambiguous texture")
        raw_page = tex[0].image.convert("RGBA")
        # Native sprite color pages are premultiplied by the frozen builder.
        # Standard PNG viewers require straight alpha. This is display-only
        # unpremultiplication; raw native decode hash remains in the sidecar.
        page = Image.frombytes("RGBa", raw_page.size, raw_page.tobytes()).convert("RGBA")
        pages.append((logical, page, {"native_rgba_sha256": hashlib.sha256(raw_page.tobytes()).hexdigest(), "size": list(page.size), "format": int(tex[0].m_TextureFormat)}))
    for logical in additions["names"]:
        if logical.startswith("actor/mesh/ywy/"):
            load(logical)
    contract = json_file(LAUNCHER / "mods/char-yuwen-yi/character-contract.json")
    expected_names = set(contract["clips"]) | set(contract["cinematic_aliases"])
    clip_paths = sorted(name for name in additions["names"] if name.startswith("actor/animation/role/ywy"))
    need(len(clip_paths) == len(expected_names) == 62, "Native clip set differs from all 62 semantic/alias names")
    rendered, unique_frames, signed_count = [], {}, 0
    for logical in clip_paths:
        sf, tree = mono(logical)
        name = tree["m_Name"]
        need(name in expected_names and tree["Context"]["AnimationRoleName"] == "ywy", "Native clip role/name mismatch")
        need(len(tree["Indeces"]) == len(tree["Frames"]) and tree["TotalFrameCount"] == tree["Indeces"][-1]+1, "Native timeline boundary mismatch")
        frames, previous = [], -1
        for frame_index, (frame, end) in enumerate(zip(tree["Frames"], tree["Indeces"])):
            duration = end - previous
            need(duration > 0, "Native key duration is empty")
            start = previous+1; previous = end
            pointer = frame["mesh"]
            file_id, path_id = pointer["m_FileID"], pointer["m_PathID"]
            need(0 < file_id <= len(sf.externals) and path_id != 0, "Invalid native mesh pointer")
            external = str(sf.externals[file_id-1].path).replace("\\", "/")
            match = re.fullmatch(r"archive:/(CAB-[a-f0-9]{32})/\1", external, re.IGNORECASE)
            need(match is not None and match.group(1).lower() in cabs, "Mesh CAB is absent from native stage")
            mesh_logical, mesh_sf = cabs[match.group(1).lower()]
            need(mesh_logical.startswith("actor/mesh/ywy/"), "Native mesh belongs to another actor")
            mesh = mesh_sf.objects.get(path_id)
            need(mesh is not None and mesh.type.name == "Mesh", "Native mesh object absent/wrong class")
            data = mesh.read_typetree()
            vertices = np.frombuffer(bytes(data["m_VertexData"]["m_DataSize"]), dtype="<f4").reshape(-1, 7)
            need(vertices.shape == (4,7) and np.isfinite(vertices).all(), "Invalid native quad geometry")
            need(struct.unpack("<6H", bytes(data["m_IndexBuffer"])) == (0,1,2,0,2,3), "Native quad triangles mismatch")
            page_index = frame["textureIdx"]
            need(0 <= page_index < len(pages), "Native page index outside family")
            page_logical, page, _ = pages[page_index]
            uv = [vertices[:,3].min()*page.width, (1-vertices[:,4].max())*page.height, vertices[:,3].max()*page.width, (1-vertices[:,4].min())*page.height]
            need(all(abs(value-round(value)) < .01 for value in uv), "Native UV is not the packed integer texel region")
            box = tuple(round(float(value)) for value in uv)
            need(0 <= box[0] < box[2] <= page.width and 0 <= box[1] < box[3] <= page.height, "Native crop outside color page")
            x0,x1,y0,y1 = [float(v) for v in (vertices[:,0].min(),vertices[:,0].max(),vertices[:,1].min(),vertices[:,1].max())]
            need(x1>x0 and y1>y0, "Native quad has empty area")
            key = (mesh_logical,path_id,page_logical)
            if key not in unique_frames:
                crop = page.crop(box)
                need(crop.getchannel("A").getbbox() is not None, "Native semantic frame is invisible")
                image = crop.resize((max(1,round((x1-x0)*PPU)),max(1,round((y1-y0)*PPU))),Image.Resampling.NEAREST)
                origin = (round(-x0*PPU),round(y1*PPU))
                file = save_png("frames/" + hashlib.sha256(repr(key).encode()).hexdigest()[:24] + ".png",image)
                unique_frames[key] = {"image":image,"origin":origin,"file":file,"mesh_name":data["m_Name"],"mesh_bundle":mesh_logical,"mesh_path_id":path_id,"page":page_logical,"uv_texel_box":list(box),"world_bounds":[x0,y0,x1,y1]}
            item = unique_frames[key]
            frames.append({"frame_index":frame_index,"ticks_start":start,"ticks_end_inclusive":end,"ticks":duration,"seconds_fraction":[duration,60], **{k:v for k,v in item.items() if k!="image"},"_image":item["image"]})
            signed_count += int(path_id<0)
        expected_duration = contract["clips"][contract["cinematic_aliases"].get(name,name)]["ticks"]
        need(tree["TotalFrameCount"]==expected_duration,"Native duration differs from exact character contract")
        common = tuple(max(frame["origin"][axis] for frame in frames) for axis in (0,1))
        offsets = [(common[0]-fr["origin"][0],common[1]-fr["origin"][1]) for fr in frames]
        size = (max(offset[0]+fr["_image"].width for fr,offset in zip(frames,offsets)),max(offset[1]+fr["_image"].height for fr,offset in zip(frames,offsets)))
        aligned = []
        for fr,offset in zip(frames,offsets):
            canvas = Image.new("RGBA",size,(0,0,0,0));canvas.paste(fr["_image"],offset);aligned.append(canvas)
        runs = []
        for index,(im,fr) in enumerate(zip(aligned,frames)):
            duration_ms = max(1,round(fr["ticks"]*1000/60))
            if runs and runs[-1]["image"].tobytes()==im.tobytes():
                runs[-1]["ms"]+=duration_ms;runs[-1]["native_frame_indices"].append(index)
            else:
                runs.append({"image":im,"ms":duration_ms,"native_frame_indices":[index]})
        preview_path = safe_output(target / ("previews/"+name+".png"))
        if len(runs)==1:
            with preview_path.open("xb") as f:runs[0]["image"].save(f,"PNG")
            representation="static_png"
        else:
            with preview_path.open("xb") as f:
                runs[0]["image"].save(f,"PNG",save_all=True,append_images=[r["image"] for r in runs[1:]],duration=[r["ms"] for r in runs],loop=0,disposal=0,blend=0)
            representation="apng"
        with Image.open(preview_path) as restored:
            need(getattr(restored,"n_frames",1)==len(runs),"Native preview frame count mismatch")
            for index,observed in enumerate(ImageSequence.Iterator(restored)):
                need(observed.convert("RGBA").tobytes()==runs[index]["image"].tobytes(),"Native preview pixel readback mismatch")
                if representation=="apng":need(abs(float(observed.info.get("duration",0))-runs[index]["ms"])<.1,"Native preview timing readback mismatch")
        records.append({"file":preview_path.relative_to(target).as_posix(),"sha256":sha(preview_path),"bytes":preview_path.stat().st_size,"kind":representation})
        rendered.append({"name":name,"logical":logical,"ticks":tree["TotalFrameCount"],"seconds_fraction":[tree["TotalFrameCount"],60],"frames":frames,"aligned":aligned,"common_origin":list(common),"canvas_size":list(size),"preview":preview_path.relative_to(target).as_posix(),"preview_representation":representation,"preview_runs":[{k:v for k,v in r.items() if k!="image"} for r in runs]})
        if len(rendered) % 12 == 0:
            print("Native clip readback: %d/62" % len(rendered), flush=True)
    max_frames = max(len(c["frames"]) for c in rendered)
    cw = max(im.width for c in rendered for im in c["aligned"])+18
    rh = max(im.height for c in rendered for im in c["aligned"])+66
    contact_paths=[]
    for page_index in range(math.ceil(len(rendered)/8)):
        batch=rendered[page_index*8:page_index*8+8]
        sheet=checker((max_frames*cw,len(batch)*rh+38));draw=ImageDraw.Draw(sheet)
        draw.text((12,10),"BUILT native mesh + GUID texture family | 64 pixels/world-unit | red = origin",font=font,fill="white")
        for row,clip in enumerate(batch):
            y=row*rh+38;draw.text((12,y),clip["name"]+" | total "+str(clip["ticks"])+" ticks",font=font,fill=(255,220,136,255))
            for index,(im,fr) in enumerate(zip(clip["aligned"],clip["frames"])):
                x=index*cw+9;sheet.alpha_composite(im,(x,y+48));draw.text((x,y+21),"key%d ticks %d..%d"%(index,fr["ticks_start"],fr["ticks_end_inclusive"]),font=font,fill="white")
                ax=x+clip["common_origin"][0];ay=y+48+clip["common_origin"][1];draw.line((ax-4,ay,ax+4,ay),fill=(255,73,88,255));draw.line((ax,ay-4,ax,ay+4),fill=(255,73,88,255))
        contact_paths.append(save_png("contact-clips-%02d.png"%(page_index+1),sheet))
    atlas_logical="ui/atlas/iconpotential200901/iconpotential200901"
    atlas_env=load(atlas_logical)
    sprites=[obj.read() for obj in atlas_env.objects if obj.type.name=="Sprite"]
    expected_icons={"Potential_"+str(i) for i in range(209001,209013)}|{"Talent_209080","Ywy_Qi","Ywy_Taiji","Ywy_Guard"}
    need({sp.m_Name for sp in sprites}==expected_icons and len(sprites)==16,"Native atlas icon set differs from all16owned")
    icon_sheet=checker((4*180,4*168+40));draw=ImageDraw.Draw(icon_sheet);draw.text((12,10),"BUILT atlas: 16 real Sprite objects / 120x120 native slots",font=font,fill="white");icon_records=[]
    for index,sprite in enumerate(sorted(sprites,key=lambda sp:sp.m_Name)):
        im=sprite.image.convert("RGBA");need(im.getchannel("A").getbbox() is not None,"Native icon is empty")
        file=save_png("icons/"+sprite.m_Name+".png",im);x=index%4*180+30;y=index//4*168+40;icon_sheet.alpha_composite(im,(x,y+25));draw.text((index%4*180+8,y),sprite.m_Name,font=font,fill="white");icon_records.append({"name":sprite.m_Name,"file":file,"size":list(im.size)})
    icon_contact=save_png("contact-native-icons.png",icon_sheet)
    ui=json_file(Path(production["ui_manifest"]))
    need(sha(Path(production["ui_manifest"]))==production["ui_manifest_sha256"],"Frozen UI manifest changed")
    ui_images=[];ui_records=[]
    for item in ui["textures"]:
        textures=[obj.read() for obj in load(item["logical"]).objects if obj.type.name=="Texture2D"]
        need(len(textures)==1,"Native UI texture missing/ambiguous")
        im=textures[0].image.convert("RGBA");need(list(im.size)==item["size"] and im.getchannel("A").getbbox() is not None,"Native UI size/content mismatch")
        file=save_png("ui/"+item["key"]+".png",im);thumb=im.copy();thumb.thumbnail((240,300),Image.Resampling.LANCZOS);ui_images.append((item["key"],thumb));ui_records.append({"key":item["key"],"logical":item["logical"],"file":file,"size":list(im.size),"alpha_bbox":im.getchannel("A").getbbox(),"format":int(textures[0].m_TextureFormat)})
    ui_sheet=checker((4*260,math.ceil(len(ui_images)/4)*340+38));draw=ImageDraw.Draw(ui_sheet);draw.text((12,10),"BUILT native UI Texture2D decodes (straight-alpha UI)",font=font,fill="white")
    for index,(key,im) in enumerate(ui_images):
        x=index%4*260+10;y=index//4*340+38;draw.text((x,y),key,font=font,fill="white");ui_sheet.alpha_composite(im,(x,y+26))
    ui_contact=save_png("contact-native-ui.png",ui_sheet)
    for relative,item in inputs.items():need(sha(OUT/relative)==item["sha256"],"Native input changed during QA readback")
    need(sha(build_path)==frozen["build"] and sha(verify_path)==frozen["verification"] and sha(PRODUCTION)==frozen["production"],"Frozen batch changed during native QA")
    clip_metadata=[{k:([{fk:fv for fk,fv in fr.items() if fk!="_image"} for fr in v] if k=="frames" else v) for k,v in clip.items() if k!="aligned"} for clip in rendered]
    receipt={"status":"passed_native_resource_readback","build_id":"25627491","actor_id":200901,"frozen_inputs":frozen,"reader_sha256":sha(Path(__file__)),"pillow_version":pillow_version,"native_inputs":inputs,"counts":{"clips":len(rendered),"frame_references":sum(len(c['frames']) for c in rendered),"unique_mesh_images":len(unique_frames),"negative_signed_mesh_references":signed_count,"color_pages":len(pages),"atlas_sprites":16,"ui_textures":len(ui_images)},"color_family_pages":[{"logical":logical,**meta} for logical,_,meta in pages],"clips":clip_metadata,"native_icons":icon_records,"native_ui":ui_records,"contacts":contact_paths+[icon_contact,ui_contact],"outputs":records,"scope":{"resource_paths":"Actual built PPtr CAB/PathID and manifest GUID family resolved","body_color_alpha":"Native premultiplied color decoded, unpremultiplied for external PNG viewer","timing":"Native Indeces/TotalFrameCount at60Hz authoritative; APNG milliseconds rounded","transform":"Actual quad world bounds at64px/unit, NEAREST display resampling","lighting_outline_shader":"Not simulated; color-only resource QA","unity_runtime_acceptance":"Not claimed","visual_acceptance":"Pending root review of these exact native contacts/previews"}}
    receipt_path=safe_output(target/'native-review.json')
    with receipt_path.open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
    need(json_file(receipt_path)==json.loads(json.dumps(receipt)),"Native QA JSON readback mismatch")
    print(json.dumps({"status":receipt["status"],"receipt":str(receipt_path),"counts":receipt["counts"],"contacts":receipt["contacts"]},ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":
    main()
