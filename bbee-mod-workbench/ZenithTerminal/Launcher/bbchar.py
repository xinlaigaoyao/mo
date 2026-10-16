"""bbchar.py -- custom character rig tooling (Spine route).

clone_rig(src, dst, out_dir) : clones a Spine rig bundle set actor/spine/<src>/* (+ actor/logicdata/<src>) to actor/spine/<dst>/* and
actor/logicdata/<dst>, with NEW archive (CAB) ids, rewritten externals / AssetBundle names / dependencies, a NEW SkeletonDataAsset GUID
in the cloned ActionLogicGroup, and returns the manifest additions {names, entries(deps), guids}.
Used by bbmod (content.rigClones) -- writes bundles into patch_out and patch_out/_manifest_add.json; bbmod.install applies the manifest.
"""
import os, sys, re, json, hashlib, struct, uuid, lz4.frame
_BBCHAR_ARGV = list(sys.argv); sys.argv = ["x"]
import bbmod
sys.argv = _BBCHAR_ARGV
import UnityPy
AB = bbmod.AB; MANIFEST = os.path.join(AB, "manifest"); MANIFEST_BAK = MANIFEST + ".orig"

SET = ["{s}", "{s}.skel", "{s}.atlas", "{s}_skeletondata", "{s}_atlas", "{s}_material"]

_MAN = None
def read_manifest():
    global _MAN
    if _MAN is None: _MAN = _read_manifest()
    return [list(_MAN[0]), [[i, list(d)] for i, d in _MAN[1]], [[i, list(g)] for i, g in _MAN[2]]]
def _read_manifest():
    use_bak = bbmod._mp["backup_state"](MANIFEST_BAK)
    if use_bak is False: bbmod._mp["pristine_merge_path"]()
    raw = lz4.frame.decompress(open(MANIFEST_BAK if use_bak else MANIFEST, "rb").read()).decode("utf-8")
    L = raw.split("\r\n"); assert L[0] == "FastManifest V3"
    n1 = int(L[1][2:]); names = L[2:2 + n1]; i = 2 + n1; n2 = int(L[i][2:]); i += 1; entries = []
    while i < len(L) and not L[i].startswith("N:"):
        if L[i].startswith(" "): entries[-1][1].append(L[i].strip())
        else: entries.append([L[i], []])
        i += 1
    n3 = int(L[i][2:]); i += 1; guids = []
    while i < len(L) and L[i] != "----":
        if L[i].startswith(" "): guids[-1][1].append(L[i].strip())
        else: guids.append([L[i], []])
        i += 1
    return names, entries, guids
def write_manifest(names, entries, guids):
    raise RuntimeError("Standalone manifest writes are disabled; use entry_point.py install for the whole verified transaction")
def restore_manifest():
    raise RuntimeError("Standalone manifest restore is disabled; use entry_point.py uninstall for the whole verified transaction")

def guid_pack(hexguid):
    """Unity GUID hex (32 chars) -> the (_guid0,_guid1) uint64 pair used by SkeletonDataAssetRef. Scheme verified against ICEY."""
    b = bytes.fromhex(hexguid)
    return struct.unpack("<QQ", b)
def guid_scheme_check():
    names, entries, guids = read_manifest(); idx = names.index("actor/spine/icey/icey_skeletondata")
    hexg = next(g for i, gs in guids for g in gs if int(i, 16) == idx)
    icey = json.load(open(os.path.join(bbmod.ROOT, "decoded", "assets", "actor_logicdata_icey.ab__icey.json"), encoding="utf-8"))
    ref = icey["SkeletonDataAssetRefList"][0]; cand = {}
    b = bytes.fromhex(hexg); sw = bytes(((x & 0xF) << 4) | (x >> 4) for x in b)
    for nm, bb in (("raw", b), ("swap", sw)):
        for order in ("<", ">"):
            cand[nm + order] = struct.unpack(order + "QQ", bb)
    hit = [k for k, v in cand.items() if v == (ref["_guid0"], ref["_guid1"])]
    return hexg, ref, hit

def clone_rig(src, dst, out_dir, report, logic_from=None):
    """returns manifest additions; writes bundles into out_dir"""
    logic_from = logic_from or src
    names, entries, guids = read_manifest(); name_idx = {n: i for i, n in enumerate(names)}
    old_bundles = ["actor/spine/%s/%s" % (src, t.format(s=src)) for t in SET] + ["actor/logicdata/" + logic_from]
    new_bundles = ["actor/spine/%s/%s" % (dst, t.format(s=dst)) for t in SET] + ["actor/logicdata/" + dst]
    cabmap = {}; envs = {}; source_hashes = []
    for ob, nb in zip(old_bundles, new_bundles):
        raw_source = bbmod.slice_bundle(bbmod.find_entry(ob + ".ab"))
        source_hashes.append(hashlib.sha256(raw_source).hexdigest())
        env = UnityPy.load(raw_source); env.typetree_generator = bbmod.typetree_gen()
        for cab in list(env.file.files.keys()): cabmap[cab.lower()] = "CAB-" + hashlib.md5(nb.encode()).hexdigest()
        envs[nb] = (ob, env)
    from reproducibility import rig_guid
    newguid = rig_guid(bbmod.game_build(), src, dst, logic_from, source_hashes)
    add_names = []; add_entries = []; add_guids = []
    for nb, (ob, env) in envs.items():
        files = env.file.files; cab = list(files.keys())[0]; sf = files[cab]; newcab = cabmap[cab.lower()]
        env.file.files = {newcab: sf}
        for e in sf.externals:


            for oc, nc in cabmap.items(): e.path = re.sub(re.escape(oc), nc, e.path, flags=re.I)
        for o in env.objects:
            if o.type.name == "AssetBundle":
                t = o.read_typetree(); t["m_Name"] = nb + ".ab"
                t["m_Container"] = [[re.sub(re.escape(src), dst, k, flags=re.I), v] for k, v in t["m_Container"]]
                t["m_Dependencies"] = [cabmap.get(d.lower(), d).lower() for d in t["m_Dependencies"]]
                if "m_AssetBundleName" in t and t["m_AssetBundleName"]: t["m_AssetBundleName"] = nb + ".ab"
                o.save_typetree(t)
            elif o.type.name == "MonoBehaviour" and nb.startswith("actor/logicdata/"):
                t = o.read_typetree()
                if "SkeletonDataAssetRefList" in t:
                    t["m_Name"] = dst; g0, g1 = guid_pack(newguid)
                    t["SkeletonDataAssetRefList"] = [{"_guid0": g0, "_guid1": g1}]
                    if "references" in t: t["references"]["RefIds"] = [r for r in t["references"]["RefIds"] if r.get("type", {}).get("class") != ""]
                    o.save_typetree(t)
        data = env.file.save(packer="lz4"); dstp = os.path.join(out_dir, *(nb + ".ab").split("/")); os.makedirs(os.path.dirname(dstp), exist_ok=True); open(dstp, "wb").write(data)

        oi = name_idx[ob]; deps = next(d for i, d in entries if int(i, 16) == oi)
        rem = []
        for d in deps:
            dn = names[int(d, 16)]
            rem.append(dn.replace("actor/spine/%s/" % src, "actor/spine/%s/" % dst).replace("actor/spine/%s/%s" % (dst, src), "actor/spine/%s/%s" % (dst, dst)) if dn.startswith("actor/spine/%s/" % src) else dn)
        add_names.append(nb); add_entries.append((nb, rem))
        if nb.endswith("_skeletondata"): add_guids.append((nb, newguid))
        print(f"  rig clone {ob} -> {nb} ({len(data)} bytes, {newcab})")
    return {"names": add_names, "entries": add_entries, "guids": add_guids, "guid": newguid}

def apply_manifest_additions(adds):
    names, entries, guids = read_manifest(); name_idx = {n: i for i, n in enumerate(names)}
    for nb in adds["names"]:
        if nb not in name_idx: names.append(nb); name_idx[nb] = len(names) - 1
    have = {int(i, 16) for i, _ in entries}
    for nb, deps in adds["entries"]:
        for d in deps:
            if d not in name_idx: names.append(d); name_idx[d] = len(names) - 1
        if name_idx[nb] not in have: entries.append([format(name_idx[nb], "x"), [format(name_idx[d], "x") for d in deps]]); have.add(name_idx[nb])
    for nb, g in adds["guids"]: guids.append([format(name_idx[nb], "x"), [g]])
    write_manifest(names, entries, guids); print(f"manifest: +{len(adds['names'])} names, +{len(adds['entries'])} entries, +{len(adds['guids'])} guids")

if __name__ == "__main__":
    if sys.argv[1:2] == ["guidcheck"]: print(guid_scheme_check())
    elif sys.argv[1:2] == ["restore-manifest"]: restore_manifest(); print("manifest restored")





RECOLOR_TYPES = ("ParticleSystem", "TrailRenderer", "LineRenderer", "SpriteRenderer", "Light", "MonoBehaviour", "Material")
def recolor_rgb(r, g, b, spec):
    import colorsys
    m = max(r, g, b)
    if m <= 0: return r, g, b
    k = m if m > 1 else 1.0
    if spec.get("bands"):
        import numpy as np
        o = band_map(np.array([[[r / k, g / k, b / k]]], np.float32), spec["bands"])[0, 0]
        return float(o[0]) * k, float(o[1]) * k, float(o[2]) * k
    h, s, v = colorsys.rgb_to_hsv(r / k, g / k, b / k)
    if s < spec.get("minSat", 0.12): return r, g, b
    s = min(1.0, s * spec.get("satScale", 1.0)); v = min(1.0, v * spec.get("valScale", 1.0))
    nr, ng, nb = colorsys.hsv_to_rgb((spec["hue"] % 360) / 360.0, s, v)
    return nr * k, ng * k, nb * k
def recolor_tree(t, spec, hits=None, path=""):
    """Recolour every {r,g,b,a} dict inside a read_typetree() result, in place. Returns the list of changed paths."""
    if hits is None: hits = []
    if isinstance(t, dict):
        if len(t) == 4 and set(t) == {"r", "g", "b", "a"} and all(isinstance(t[c], (int, float)) for c in "rgba"):
            nr, ng, nb = recolor_rgb(t["r"], t["g"], t["b"], spec)
            if (nr, ng, nb) != (t["r"], t["g"], t["b"]): t["r"], t["g"], t["b"] = nr, ng, nb; hits.append(path)
            return hits
        for k, v in t.items(): recolor_tree(v, spec, hits, path + "." + str(k))
    elif isinstance(t, list):
        for i, v in enumerate(t): recolor_tree(v, spec, hits, path + "[%d]" % i)
    return hits
MASK_FORMATS = {"Alpha8", "R8", "R16", "RHalf", "RFloat", "BC4", "EAC_R", "EAC_R_SIGNED"}
def is_mask_format(fmt):
    """Single-channel textures (effect masks such as mask_003_1c) carry no colour: never hue-shift them."""
    if isinstance(fmt, int):
        from UnityPy.enums import TextureFormat
        try: fmt = TextureFormat(fmt)
        except ValueError: return False
    return getattr(fmt, "name", str(fmt)) in MASK_FORMATS
def _hex3(h):
    h = h.lstrip("#"); return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
def band_map(rgb, bands):
    """A palette map on baked RGB (docs/ex/research/PALETTE_VFX.md 4.1, L2). bands: [{"hue": centre, "width": deg,
    "smin": min sat, "smax": max sat, "vmin": min value, "vref": the band's lit value, "stops": [[t, "#hex"], ...]}].
    Each pixel in a band becomes the ramp colour at t = value / vref (its shading position), blended by a soft band
    membership, so shading and anti-aliasing survive: red lit, red shadow and near-black each get their own colour."""
    import numpy as np
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]; dd = np.maximum(d, 1e-6)
    h = np.where(d < 1e-6, 0, np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4))) * 60
    out = rgb.copy()
    for bd in bands:
        w = np.ones_like(mx)
        if "hue" in bd: dh = np.abs((h - bd["hue"] + 180) % 360 - 180); w *= np.clip(1 - (dh - bd["width"]) / 12.0, 0, 1)
        if "smin" in bd: w *= np.clip((s - bd["smin"]) / 0.12, 0, 1)
        if "smax" in bd: w *= np.clip((bd["smax"] - s) / 0.08, 0, 1)
        if "vmin" in bd: w *= np.clip((mx - bd["vmin"]) / 0.1, 0, 1)
        ts = np.array([float(x[0]) for x in bd["stops"]], np.float32); cs = np.array([_hex3(x[1]) for x in bd["stops"]], np.float32)
        t = np.clip(mx / bd["vref"], ts[0], ts[-1]); tgt = np.stack([np.interp(t, ts, cs[:, c]) for c in range(3)], -1)
        out = out * (1 - w[..., None]) + tgt * w[..., None]
    return out

def recolor_image(img, spec):
    """Hue-set an RGBA PIL image (pixels with saturation >= minSat), keeping alpha and brightness. A spec with "bands"
    is a palette map instead (band_map)."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("RGBA")).astype(np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:]
    if spec.get("bands"):
        out = np.clip(band_map(rgb, spec["bands"]), 0, 1)
        return Image.fromarray((np.concatenate([out, al], -1) * 255).round().astype(np.uint8), "RGBA")
    mx, mn = rgb.max(-1), rgb.min(-1); s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    v = np.clip(mx * spec.get("valScale", 1.0), 0, 1); s2 = np.clip(s * spec.get("satScale", 1.0), 0, 1)
    h = (spec["hue"] % 360) / 60.0; i = int(h) % 6; f = h - int(h)
    p, q, tt = v * (1 - s2), v * (1 - s2 * f), v * (1 - s2 * (1 - f))
    rgb2 = [np.stack(x, -1) for x in ((v, tt, p), (q, v, p), (p, v, tt), (p, q, v), (tt, p, v), (v, p, q))][i]
    out = np.where((s >= spec.get("minSat", 0.12))[..., None], rgb2, rgb)
    return Image.fromarray((np.concatenate([out, al], -1) * 255).round().astype(np.uint8), "RGBA")

def stock_sprite_image(spec):
    """The pixels of a stock atlas sprite, "<atlas bundle>#<sprite name>", read from the player's install."""
    bundle, name = spec.split("#", 1)
    env = UnityPy.load(bbmod.slice_bundle(bbmod.find_entry(bundle + ".ab")))
    for o in env.objects:
        if o.type.name == "Sprite" and o.read().m_Name == name: return o.read().image.convert("RGBA")
    raise SystemExit("no sprite %s in %s" % (name, bundle))

def move_sprite(t, W, H, H2, new_xy):
    """A quad sprite of a sprite-sheet page (no SpriteAtlas object): move it to new_xy (pixels from the page's bottom
    left) and/or re-express it on a page grown from H to H2 pixels tall. Rewrites m_Rect, the render data's texture
    rect and uvTransform (its y / w are the rect's centre in pixels) and the UV channel of its mesh."""
    rd = t["m_RD"]; tr = rd["textureRect"]
    dx, dy = (new_xy[0] - tr["x"], new_xy[1] - tr["y"]) if new_xy else (0.0, 0.0)
    for r_ in (t["m_Rect"], tr): r_["x"] += dx; r_["y"] += dy
    ut = rd.get("uvTransform")
    if ut: ut["y"] += dx; ut["w"] += dy
    vd = rd["m_VertexData"]; n = vd["m_VertexCount"]; ch = vd["m_Channels"]
    if len(ch) < 5 or not ch[4]["dimension"]: return
    if ch[4]["format"] != 0: raise SystemExit("sprite %s: UVs are not float32" % t.get("m_Name"))
    stride = {}
    for c in ch:
        if c["dimension"]: stride[c["stream"]] = max(stride.get(c["stream"], 0), c["offset"] + 4 * (c["dimension"] & 0xF))
    base, off = {}, 0
    for st in sorted(stride): base[st] = off; off = (off + stride[st] * n + 15) // 16 * 16
    raw = bytearray(bytes(vd["m_DataSize"]))
    for i in range(n):
        q = base[ch[4]["stream"]] + i * stride[ch[4]["stream"]] + ch[4]["offset"]
        u, v = struct.unpack_from("<2f", raw, q)
        struct.pack_into("<2f", raw, q, (u * W + dx) / W, (v * H + dy) / H2)
    vd["m_DataSize"] = list(raw) if isinstance(vd["m_DataSize"], list) else bytes(raw)

def clone_bundle(src, dst, out_dir, rename=None, image=None, scale=None, ref_types_from=None, rename_objects=False,
                 atlas_sprites=None, recolor=None, remap_deps=None, material_props=None):
    """Clone ONE bundle (src logical path, no .ab) to dst with a new CAB id, renamed AssetBundle/container/objects,
    and optionally a replacement Texture2D image. `rename` = (old_token, new_token) applied case-insensitively to
    container paths and object names; defaults to the last path segment of src -> that of dst.
    `ref_types_from` = other bundles whose SerializeReference type declarations (SerializedFile.ref_types) are merged in
    when missing, so a generated tree may use condition classes the donor file never declared.
    `rename_objects` also renames MonoBehaviour m_Name (an animation clip is looked up by that name, e.g. a clone
    ph_stand -> ph_stand_inherit for the Evotype cinematic).
    `atlas_sprites` = [(sprite name, image path), ...] turns a donor sprite-sheet atlas (one Texture2D page + quad
    Sprites, e.g. ui/atlas/iconpotential<actor>) into a NEW atlas: the page is redrawn blank, each listed image is
    fitted into one donor sprite's rect (in rect order) and that sprite takes the listed name. C#-side UI (battle HUD
    Potential list, skill buttons) loads sprites from real atlases only, so SDK tex: aliases can't reach it.
    An entry's image may also be None (keep the donor sprite of that name, pixels and all, e.g. the shared
    Potential_5000 Unleashed hexagon) or "sprite:<atlas bundle>#<sprite name>" (copy a stock sprite's pixels from the
    player's install at build time, so no game pixels ship in a mod). When more icons are asked for than the donor has
    distinct positions, its spare duplicate Sprite objects move to free grid cells, rows are added on top of the page if
    needed, and each moved sprite's rect, texture rect, uvTransform and mesh UVs are rewritten (every sprite's UVs when
    the page grows). Donors without duplicates, or asks within the distinct positions, are unchanged.
    `recolor` = a recolour spec (see recolor_rgb): hue-sets every colour value in particle systems, renderers, lights,
    MonoBehaviours and materials, and (with "textures": true) the pixels of every Texture2D in the bundle.
    `remap_deps` = {donor dependency bundle: our cloned bundle}: the clone references our recoloured material/texture
    clone instead of the stock one (external CAB path and manifest dependency both switched).
    `material_props` = {"colors": {prop: [r, g, b, a]}, "floats": {prop: value}} set on every Material in the bundle:
    how Boons Plus effects get their colour and glow (official effects use white particles x HDR material tints).
    Returns a manifest addition dict, same shape as clone_rig's."""
    if rename is None: rename = [(src.rsplit("/", 1)[-1], dst.rsplit("/", 1)[-1])]
    if isinstance(rename[0], str): rename = [rename]
    def retok(v):
        for a, b in rename: v = re.sub(re.escape(a), b, v, flags=re.I)
        return v
    names, entries, guids = read_manifest(); name_idx = {n: i for i, n in enumerate(names)}
    deps = next(d for i, d in entries if int(i, 16) == name_idx[src])
    remap_deps = dict(remap_deps or {})
    adds = {"names": [dst], "entries": [(dst, [remap_deps.get(names[int(d, 16)], names[int(d, 16)]) for d in deps])], "guids": []}
    dstp = os.path.join(out_dir, *(dst + ".ab").split("/")); os.makedirs(os.path.dirname(dstp), exist_ok=True)


    h = hashlib.sha1(repr(("clone_bundle/5" if atlas_sprites else "clone_bundle/4", src, dst, [tuple(r) for r in rename], scale, list(ref_types_from or []))
                          + (("objects",) if rename_objects else ())
                          + ((("atlas",) + tuple(n for n, _ in atlas_sprites)) if atlas_sprites else ())
                          + (("recolor", json.dumps(recolor, sort_keys=True)) if recolor else ())
                          + (("remap", json.dumps(remap_deps, sort_keys=True)) if remap_deps else ())
                          + (("matprops", json.dumps(material_props, sort_keys=True)) if material_props else ())).encode())
    for _, ip in atlas_sprites or []:
        if ip is None: h.update(b"keep")
        elif ip.startswith("sprite:"): h.update(ip.encode()); h.update(bbmod.slice_bundle(bbmod.find_entry(ip[7:].split("#")[0] + ".ab")))
        else: h.update(open(ip, "rb").read())
    h.update(bbmod.slice_bundle(bbmod.find_entry(src + ".ab")))
    if image: h.update(open(image, "rb").read())
    cache = os.path.join(bbmod.ROOT, "tools", "clonecache", h.hexdigest() + ".ab")
    if os.path.exists(cache):
        import shutil; shutil.copyfile(cache, dstp); return adds
    env = UnityPy.load(bbmod.slice_bundle(bbmod.find_entry(src + ".ab"))); env.typetree_generator = bbmod.typetree_gen()
    cab = list(env.file.files.keys())[0]; sf = env.file.files[cab]
    newcab = "CAB-" + hashlib.md5(dst.encode()).hexdigest(); env.file.files = {newcab: sf}
    for e in sf.externals: e.path = re.sub(re.escape(cab), newcab, e.path, flags=re.I)
    for old, new in remap_deps.items():
        ocab = list(UnityPy.load(bbmod.slice_bundle(bbmod.find_entry(old + ".ab"))).file.files.keys())[0]
        ncab = "CAB-" + hashlib.md5(new.encode()).hexdigest()
        for e in sf.externals: e.path = re.sub(re.escape(ocab), ncab, e.path, flags=re.I)
    for other in ref_types_from or []:
        oenv = UnityPy.load(bbmod.slice_bundle(bbmod.find_entry(other + ".ab"))); of = list(oenv.file.files.values())[0]
        have = {(t.m_NameSpace, t.m_ClassName) for t in sf.ref_types}
        for t in of.ref_types:
            if (t.m_NameSpace, t.m_ClassName) not in have: sf.ref_types.append(t); have.add((t.m_NameSpace, t.m_ClassName))
    img = None
    if image:
        from PIL import Image
        img = Image.open(image).convert("RGBA")
    atlas_names = {}; atlas_moved = {}; atlas_page = [None, 0, 0]
    if atlas_sprites:
        from PIL import Image
        sprs = [o for o in env.objects if o.type.name == "Sprite"]
        rects = sorted(((o.read().m_Rect, o.path_id) for o in sprs), key=lambda rp: (-rp[0].y, rp[0].x))



        seen, uniq, dup = set(), [], []
        box = lambda r: (int(round(r.x)), int(round(r.y)), int(round(r.width)), int(round(r.height)))
        for r, pid in rects:
            key = box(r)
            if key not in seen: seen.add(key); uniq.append((key, pid))
            else: dup.append((key, pid))
        names_of = {o.path_id: o.read().m_Name for o in sprs}
        tex = next(o for o in env.objects if o.type.name == "Texture2D").read()
        W, H = tex.m_Width, tex.m_Height
        kept = {}
        for nm, ip in atlas_sprites:
            if ip is None:
                hit = next(((k, pid) for k, pid in uniq if names_of[pid] == nm), None)
                if hit is None: raise SystemExit("atlas %s: no donor sprite %s to keep" % (src, nm))
                kept[nm] = hit
        slots = [(k, pid) for k, pid in uniq if pid not in {p_ for _, p_ in kept.values()}]
        want = [(nm, ip) for nm, ip in atlas_sprites if ip is not None]
        if len(want) > len(slots):
            need = len(want) - len(slots)
            if need > len(dup): raise SystemExit("atlas %s has %d distinct sprite positions and %d spare sprite objects, %d requested"
                                                 % (src, len(uniq), len(dup), len(atlas_sprites)))
            sizes = {(k[2], k[3]) for k, _ in uniq}
            if len(sizes) != 1: raise SystemExit("atlas %s: growing it needs one cell size, found %s" % (src, sizes))
            cw, ch = sizes.pop(); xs = sorted({k[0] for k, _ in uniq}); ys = sorted({k[1] for k, _ in uniq})
            sx = xs[1] - xs[0] if len(xs) > 1 else cw + 2; sy = ys[1] - ys[0] if len(ys) > 1 else ch + 2
            occ = {(k[0], k[1]) for k, _ in uniq}
            free = [(x, y) for y in ys for x in xs if (x, y) not in occ]; y = ys[-1] + sy
            while len(free) < need: free += [(x, y) for x in xs]; y += sy
            for (k, pid), (x, y) in zip(dup[:need], free[:need]):
                atlas_moved[pid] = (x, y); slots.append(((x, y, cw, ch), pid))
            top = max(y + ch + 1 for x, y in atlas_moved.values())
            if top > H: atlas_page[0] = (top + 3) // 4 * 4
        H2 = atlas_page[0] or H
        atlas_page[1:] = [W, H]
        page = Image.new("RGBA", (W, H2), (0, 0, 0, 0))
        if kept:
            donor = tex.image.convert("RGBA")
            for nm, ((x, y, w, hh), pid) in kept.items():
                page.paste(donor.crop((x, H - y - hh, x + w, H - y)), (x, H2 - y - hh)); atlas_names[pid] = nm
        for ((x, y, w, hh), pid), (nm, ip) in zip(slots, want):
            if ip.startswith("sprite:"):
                icon = stock_sprite_image(ip[7:])
            else:
                icon = Image.open(ip).convert("RGBA")
            icon = icon.resize((w, hh), Image.LANCZOS)


            page.paste(icon, (x, H2 - y - hh))
            atlas_names[pid] = nm
        img = page
    for o in env.objects:
        if o.type.name == "AssetBundle":
            t = o.read_typetree(); t["m_Name"] = dst + ".ab"
            t["m_Container"] = [[retok(k), v] for k, v in t["m_Container"]]
            if t.get("m_AssetBundleName"): t["m_AssetBundleName"] = dst + ".ab"
            o.save_typetree(t)
        elif o.type.name == "Texture2D":
            d = o.read(); d.m_Name = retok(d.m_Name)
            if img is not None:
                im = img if scale is None else img.resize((d.m_Width, d.m_Height), Image.NEAREST)
                d.set_image(im, target_format=d.m_TextureFormat)
            elif recolor and recolor.get("textures") and not is_mask_format(d.m_TextureFormat):
                d.set_image(recolor_image(d.image, recolor), target_format=d.m_TextureFormat)
            d.save()
        elif o.type.name == "Sprite":
            if o.path_id in atlas_moved or atlas_page[0]:
                t = o.read_typetree()
                move_sprite(t, atlas_page[1], atlas_page[2], atlas_page[0] or atlas_page[2], atlas_moved.get(o.path_id))
                t["m_Name"] = atlas_names.get(o.path_id) or retok(t["m_Name"]); o.save_typetree(t)
            else:
                d = o.read(); d.m_Name = atlas_names.get(o.path_id) or retok(d.m_Name); d.save()
        elif o.type.name == "MonoBehaviour" and rename_objects:
            t = o.read_typetree(); hit = bool(recolor and recolor_tree(t, recolor))
            if t.get("m_Name"): t["m_Name"] = retok(t["m_Name"]); hit = True
            if hit: o.save_typetree(t)
        elif material_props and o.type.name == "Material":
            t = o.read_typetree(); sp = t["m_SavedProperties"]
            if recolor: recolor_tree(t, recolor)
            for prop, rgba in (material_props.get("colors") or {}).items():
                col = dict(zip("rgba", [float(x) for x in rgba]))
                for pair in sp["m_Colors"]:
                    if pair[0] == prop: pair[1].update(col); break
                else: sp["m_Colors"].append([prop, col])
            for prop, val in (material_props.get("floats") or {}).items():
                for i, pair in enumerate(sp["m_Floats"]):
                    if pair[0] == prop: sp["m_Floats"][i] = type(pair)((pair[0], float(val))); break
                else: sp["m_Floats"].append([prop, float(val)])
            o.save_typetree(t)
        elif recolor and o.type.name in RECOLOR_TYPES:
            t = o.read_typetree()
            if recolor_tree(t, recolor): o.save_typetree(t)
    data = env.file.save(packer="lz4")
    open(dstp, "wb").write(data)
    os.makedirs(os.path.dirname(cache), exist_ok=True); open(cache, "wb").write(data)
    print(f"  bundle clone {src} -> {dst} ({len(data)} bytes, {newcab}{', image' if image else ''})")
    return adds
