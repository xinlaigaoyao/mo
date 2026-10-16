r"""bbmod.py -- BlazBlue Entropy Effect mod loader / composer (Steam build, merged-AssetBundle route).

usage:  python bbmod.py status                 game build, installed state, enabled mods
        python bbmod.py list                   all mods in mods\, enabled or not
        python bbmod.py enable <id> [<id>..]   / disable <id>..     edit mods\profile.json
        python bbmod.py build                  compose enabled mods -> patch_out (conflict detection, node --check)
        python bbmod.py install                build + write ab\m_mod.m + repoint merge.json (game must be closed)
        python bbmod.py uninstall              restore pristine merge.json, delete m_mod.m
        python bbmod.py doctor                 sanity checks + last Player.log / modlog errors
        python bbmod.py new <id>               scaffold mods\<id>\mod.json

A mod is a folder mods\<id>\ with mod.json:
{ "id": "my-mod", "name": "...", "version": "0.1.0", "author": "...", "description": "...",
  "gameBuilds": ["24904166"],            # Steam buildids this mod was verified on ("*" = any, warns)
  "dependencies": ["bbee-devtools"],    # load order = dependencies first
  "content": {
    "tables": { "BlessConf": [ { "Id": 3222, "Faction": 302, ... } ] },   # row overrides, matched by key fields
                                                                          # (Idx+Lvl, Id[+Quality]); "$delete": true removes; "$new": true inserts
    "locale": { "enu": { "TriggerName_32221": "Attack Speed Boon" }, "chs": {...} },
    "js": [ { "file": "data/js/core/ActorUtil", "replace": [["old exact text", "new text"]], "append": "code", "appendFile": "files/x.js" } ],
    "jsFiles": { "data/js/window/PdAssistant": "files/PdAssistant.js" }      # whole-file replacement (conflicts with any other edit of that file)
  } }
Conflicts (two mods writing the same row field / locale key / js anchor / js file) abort the build with a report.
"""
import tempfile, os, sys, json, shutil, subprocess, re, struct, glob, time
from composer_core import compose_table, apply_js_replacements
from native_table_keys import KEY_OVERRIDES, NATIVE_KEY_DEFAULTS, validate_native_keys

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(errors="backslashreplace")
    except Exception: pass
ROOT = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(ROOT, "shared")
MODS = os.path.join(ROOT, "mods"); INSTALLED = os.path.join(MODS, "installed.json")


PROFILE = os.environ.get("BBMOD_PROFILE") or os.path.join(MODS, "profile.json")
STAGING = bool(os.environ.get("BBMOD_PROFILE") or os.environ.get("BBMOD_OUT"))
DEC = os.path.join(ROOT, "decoded"); TABLES = os.path.join(DEC, "tables"); JSDIR = os.path.join(DEC, "data", "js")
OUT = os.environ.get("BBMOD_OUT") or os.path.join(ROOT, "patch_out"); RAW = os.path.join(ROOT, "extracted_raw")
AB = os.path.join(ROOT, "game", "BlazblueEntropyEffect_Data", "StreamingAssets", "ab")
def _steam_manifest(root):
    """<library>/steamapps/common/<game>  ->  <library>/steamapps/appmanifest_2273430.acf (any Steam library)"""
    try:
        g = os.path.realpath(os.path.join(root, "game"))
        cand = os.path.join(os.path.dirname(os.path.dirname(g)), "appmanifest_2273430.acf")
        if os.path.exists(cand): return cand
    except Exception: pass
    return r"C:\Program Files (x86)\Steam\steamapps\appmanifest_2273430.acf"
STEAM_MANIFEST = _steam_manifest(ROOT)
PLAYER_LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\91Act\BlazblueEntropyEffect\Player.log")
NODE = "node"


sys.argv_backup = sys.argv; sys.argv = ["make_patch.py"]
_mp = {"__file__": os.path.join(ROOT, "make_patch.py")}
exec(open(_mp["__file__"], encoding="utf-8").read().split("\ncmd = ")[0], _mp)
sys.argv = sys.argv_backup
encode_table, verify_table, encode_fixed_table = _mp["encode_table"], _mp["verify_table"], _mp["encode_fixed_table"]
rebuild_bundle, slice_bundle, find_entry, noah_xor = _mp["rebuild_bundle"], _mp["slice_bundle"], _mp["find_entry"], _mp["noah_xor"]
SCHEMA, JSKEYS = _mp["SCHEMA"], _mp["JSKEYS"]

def game_build():
    if os.environ.get("BBMOD_BUILD_ID"):
        return os.environ["BBMOD_BUILD_ID"]
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', open(STEAM_MANIFEST, encoding="utf-8").read()); return m.group(1) if m else "?"
    except OSError: return "?"


def load_profile():
    if os.environ.get("BBMOD_PROFILE"):
        if os.path.exists(PROFILE): return json.load(open(PROFILE, encoding="utf-8"))
        return {"enabled": []}
    enabled, seen = [], set()
    for p in (os.path.join(SHARED, "profile.json"), os.path.join(MODS, "profile.json")):
        if os.path.exists(p):
            for m in json.load(open(p, encoding="utf-8")).get("enabled", []):
                if m not in seen:
                    seen.add(m)
                    enabled.append(m)
    return {"enabled": enabled}
MOD_DIRS = {}
def mdir(mid):
    if mid in MOD_DIRS: return MOD_DIRS[mid]
    if os.path.isdir(os.path.join(SHARED, mid)): return os.path.join(SHARED, mid)
    return os.path.join(MODS, mid)
def save_profile(p): os.makedirs(MODS, exist_ok=True); json.dump(p, open(PROFILE, "w", encoding="utf-8"), indent=1)
def load_mods():
    mods = {}


    extra = [d for d in (os.environ.get("BBMOD_MODS_EXTRA") or "").split(os.pathsep) if d] if STAGING else []
    for mj in sorted(glob.glob(os.path.join(SHARED, "*", "mod.json"))) + sorted(glob.glob(os.path.join(MODS, "*", "mod.json"))) + [p for d in extra for p in sorted(glob.glob(os.path.join(d, "*", "mod.json")))]:
        m = json.load(open(mj, encoding="utf-8")); m["_dir"] = os.path.dirname(mj); MOD_DIRS[m["id"]] = m["_dir"]
        for k in ("id", "name", "version"): assert k in m, f"{mj}: missing '{k}'"
        assert m["id"] == os.path.basename(m["_dir"]), f"{mj}: id must equal folder name"
        mods[m["id"]] = m
    return mods
def resolve_order(mods, enabled):
    order, seen, stack = [], set(), []
    def visit(i):
        if i in seen: return
        if i in stack: raise SystemExit(f"dependency cycle at {i}")
        if i not in mods: raise SystemExit(f"missing mod '{i}' (required by {stack[-1] if stack else 'profile'})")
        stack.append(i)
        for d in mods[i].get("dependencies", []): visit(d)
        stack.pop(); seen.add(i); order.append(i)
    for i in enabled: visit(i)
    return order


def table_keys(name, rows):
    if name in KEY_OVERRIDES: return list(KEY_OVERRIDES[name])
    f = rows[0] if rows else {}
    ks = ["Idx"] if "Idx" in f else ["Id"] if "Id" in f else []
    for extra in ("Lvl", "Quality"):
        if extra in f and ks: ks.append(extra)
    return ks
def depends_on(mods, mid, target, seen=None):
    """True if mod `mid` (transitively) declares `target` as a dependency -> it may override target's values."""
    seen = seen or set()
    for d in mods.get(mid, {}).get("dependencies", []):
        if d == target or (d not in seen and (seen.add(d) or depends_on(mods, d, target, seen))): return True
    return False
def ensure_orig(path):
    if not os.path.exists(path + ".orig"): shutil.copy2(path, path + ".orig")
def compose_tables(order, mods, report):
    touched = {}
    for mid in order:
        for tname, rows in mods[mid].get("content", {}).get("tables", {}).items():
            touched.setdefault(tname, []).append((mid, rows))
    for tname, edits in touched.items():
        p = os.path.join(TABLES, tname + ".json"); assert os.path.exists(p), f"unknown table {tname}"
        ensure_orig(p); base = json.load(open(p + ".orig", encoding="utf-8")); ks = table_keys(tname, base)
        base = compose_table(tname, base, ks, edits, mods, report,
                             key_defaults=NATIVE_KEY_DEFAULTS.get(tname))
        validate_native_keys(tname, base)
        json.dump(base, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  table {tname}: {sum(len(r) for _, r in edits)} row edits from {[m for m, _ in edits]}")
    return list(touched)


def js_path(logical): return os.path.join(JSDIR, *logical.split("/")[2:]) + ".js"
REGISTRY_MODULE = "data/js/Example"
def registry_code(order, mods):
    from reproducibility import resource_timestamp
    aliases = {}
    for mid in order:
        for k, v in mods[mid].get("content", {}).get("spriteAliases", {}).items(): aliases[k] = v
    modlist = [{"id": m, "name": mods[m]["name"], "version": mods[m]["version"]} for m in order]
    taliases = {}
    for mid in order:
        for k, v in mods[mid].get("content", {}).get("textureAliases", {}).items(): taliases[k] = v
    return ("/* ===== generated by bbmod: ModRegistry ===== */\n"
            "exports.ModRegistry={mods:" + json.dumps(modlist, ensure_ascii=False) + ",spriteAlias:" + json.dumps(aliases, ensure_ascii=False) + ",textureAlias:" + json.dumps(taliases, ensure_ascii=False) +
            ",gameBuild:" + json.dumps(game_build()) + ",built:" + json.dumps(resource_timestamp(ROOT)) + "};")
def compose_js(order, mods, report):
    touched = {}
    for mid in order:
        c = mods[mid].get("content", {})
        for spec in c.get("js", []): touched.setdefault(spec["file"], []).append((mid, spec))
        for logical, rel in c.get("jsFiles", {}).items(): touched.setdefault(logical, []).append((mid, {"wholeFile": os.path.join(mods[mid]["_dir"], rel)}))
    if order: touched.setdefault(REGISTRY_MODULE, []).append(("bbmod", {"append": registry_code(order, mods)}))
    for logical, specs in touched.items():
        p = js_path(logical); assert os.path.exists(p), f"unknown js module {logical}"
        ensure_orig(p); s = open(p + ".orig", encoding="utf-8").read(); anchors = {}
        whole = [m for m, sp in specs if "wholeFile" in sp]
        if whole:
            if len(specs) > 1: report.append(f"CONFLICT js {logical}: whole-file replacement by {whole} plus other edits by {[m for m, _ in specs if m not in whole]}")
            whole_spec = next(sp for _, sp in specs if "wholeFile" in sp)
            s = open(whole_spec["wholeFile"], encoding="utf-8").read()
        else:
            appends = []
            for mid, sp in specs:
                from js_contracts import bind_spec
                sp = bind_spec(sp, mid, logical, ROOT, game_build(), open(p + ".orig", "rb").read())
                s = apply_js_replacements(s, sp.get("replace", []), mid, logical, report, anchors, mods, ROOT, sp)
                if sp.get("append"): appends.append(sp["append"])
                if sp.get("appendFile"): appends.append(open(os.path.join(mods[mid]["_dir"], sp["appendFile"]), encoding="utf-8").read())
            if appends:

                appends = [x.replace("@ROOT@", ROOT.replace("\\", "/")) for x in appends]
                marker = "\n//# sourceMappingURL="; i = s.rfind(marker)
                s = (s[:i] + "\n" + "\n".join(appends) + s[i:]) if i >= 0 else s + "\n" + "\n".join(appends)
        open(p, "w", encoding="utf-8", newline="\n").write(s)
        if shutil.which(NODE) is None:
            report.append(f"ERROR js {logical}: Node.js is required for syntax validation; no executable found for {NODE!r}")
            continue
        r = subprocess.run([NODE, "--check", p], capture_output=True, text=True,
                           env={key: value for key, value in os.environ.items() if not key.upper().startswith("NODE_")}, timeout=30)
        if r.returncode != 0: report.append(f"ERROR js {logical}: syntax check failed:\n{r.stderr[:400]}")
        print(f"  js {logical}: {len(specs)} edit set(s) from {[m for m, _ in specs]}  {'OK' if r.returncode == 0 else 'SYNTAX ERROR'}")
    return list(touched)






_gen = None
def typetree_gen():
    global _gen
    if _gen is None:
        from verified_typetrees import CachedTypeTrees
        _gen = CachedTypeTrees(ROOT, game_build())
    return _gen
def resolve_path(obj, path):
    """returns (container, key) for the last segment so callers can get/set"""
    toks = re.findall(r"\[([^\]]+)\]|([^.\[\]]+)", path); cur = obj; last = None
    for i, (sel, name) in enumerate(toks):
        if last is not None: cur = last[0][last[1]]
        if name: last = (cur, name)
        elif "=" in sel:
            f, v = sel.split("=", 1); idx = next((j for j, e in enumerate(cur) if str(e.get(f)) == v), None)
            if idx is None: raise KeyError(f"no element with {f}={v} in {path}")
            last = (cur, idx)
        else: last = (cur, int(sel))
    return last
def apply_asset_ops(tree, spec, mid, report):
    if spec.get("treeFile"):
        p = os.path.join(mdir(mid), spec["treeFile"])
        if not os.path.exists(p): report.append(f"ERROR asset {spec['bundle']} ({mid}): treeFile {spec['treeFile']} missing"); return
        src = json.load(open(p, encoding="utf-8"))
        for k, v in src.items():
            if not k.startswith("m_") or k == "m_Name": tree[k] = v
    if spec.get("copyTreeFrom"):
        import UnityPy
        src = spec["copyTreeFrom"]; env = UnityPy.load(slice_bundle(find_entry(src["bundle"]))); env.typetree_generator = typetree_gen(); st = None
        for o in env.objects:
            if o.type.name == "MonoBehaviour":
                t = o.read_typetree()
                if t.get("m_Name") == src["asset"]: st = t; break
        if st is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): copyTreeFrom source {src} not found"); return
        for k, v in st.items():
            if not k.startswith("m_") or k == "references": tree[k] = json.loads(json.dumps(v))
        if "references" in tree: tree["references"]["RefIds"] = [r for r in tree["references"]["RefIds"] if r.get("type", {}).get("class") != ""]
    for op in spec.get("set", []):
        c, k = resolve_path(tree, op["path"]); c[k] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
    for cp in spec.get("copyActions", []):
        src = next((a for a in tree["_actions"] if a["Name"] == cp["from"]), None)
        if src is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): copyActions source '{cp['from']}' not found"); continue
        new = json.loads(json.dumps(src)); new["Name"] = cp["name"]
        for op in cp.get("set", []):
            c, k = resolve_path(new, op["path"]); c[k] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
        tree["_actions"] = [a for a in tree["_actions"] if a["Name"] != cp["name"]] + [new]
    for a in spec.get("addActions", []): tree["_actions"] = [x for x in tree["_actions"] if x["Name"] != a["Name"]] + [a]
    for im in spec.get("importActions", []):
        import UnityPy
        src = im["from"]; env = UnityPy.load(slice_bundle(find_entry(src["bundle"]))); env.typetree_generator = typetree_gen(); sa = None
        for o in env.objects:
            if o.type.name != "MonoBehaviour": continue
            t = o.read_typetree()
            if t.get("m_Name") == src["asset"]:
                sa = next((x for x in t.get("_actions", []) if x["Name"] == src["action"]), None); break
        if sa is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): importActions source {src} not found"); continue
        if sa.get("AddRoles"): report.append(f"ERROR asset {spec['bundle']} ({mid}): '{src['action']}' spawns bullet actors (AddRoles) and cannot be imported")
        new = json.loads(json.dumps(sa))
        def _scrub(o):
            if isinstance(o, dict):
                if "Conditions" in o and isinstance(o["Conditions"], list): o["Conditions"] = []
                for x in o.values(): _scrub(x)
            elif isinstance(o, list):
                for x in o: _scrub(x)
        _scrub(new)




        tgt = next((x for x in tree["_actions"] if x["Name"] == im["name"]), None)
        for f in ("ActionSwitchs", "Interrupt"):
            if f in new: new[f] = []
        for f in ("NextAction", "DropAction", "DropEndAction", "DropEndHighAction",
                  "OnGroundAction", "BeginFallAction", "DeadAction"):
            if f in new: new[f] = (tgt or {}).get(f, "")
        new["Name"] = im["name"]
        if im.get("animate"): new["Animate"] = im["animate"]
        rn = next((x.get("RoleName") for x in tree["_actions"] if x.get("RoleName")), None)
        if rn: new["RoleName"] = rn
        for op in im.get("set", []):
            c, k = resolve_path(new, op["path"]); c[k] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
        tree["_actions"] = [x for x in tree["_actions"] if x["Name"] != im["name"]] + [new]
        print(f"    {mid}: imported {src['asset']}.{src['action']} -> {im['name']} (anim {new.get('Animate')})")

    for cp in spec.get("copyItems", []):
        c, k = resolve_path(tree, cp["list"]); lst = c[k]; key = cp.get("key", "Name")
        src = next((e for e in lst if e.get(key) == cp["from"]), None)
        if src is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): copyItems source {key}={cp['from']} not found in {cp['list']}"); continue
        new = json.loads(json.dumps(src)); new[key] = cp["to"]
        for op in cp.get("set", []):
            cc, kk = resolve_path(new, op["path"]); cc[kk] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
        lst[:] = [e for e in lst if e.get(key) != cp["to"]] + [new]
    for ap in spec.get("appendItems", []):
        c, k = resolve_path(tree, ap["list"]); lst = c[k]; key = ap.get("key", "Name"); v = ap["value"]
        lst[:] = [e for e in lst if e.get(key) != v.get(key)] + [v]
def compose_assets(order, mods, report):
    import UnityPy
    touched = {}
    for mid in order:
        for spec in mods[mid].get("content", {}).get("assets", []): touched.setdefault((spec["bundle"], spec["asset"]), []).append((mid, spec))
    for (bundle, asset), specs in touched.items():
        gen = typetree_gen()
        staged = os.path.join(OUT, *bundle.split("/"))
        env = UnityPy.load(staged if os.path.exists(staged) else slice_bundle(find_entry(bundle))); env.typetree_generator = gen
        obj = tree = None
        for o in env.objects:
            if o.type.name != "MonoBehaviour": continue
            t = o.read_typetree()
            if t.get("m_Name") == asset: obj, tree = o, t; break
        if obj is None: report.append(f"ERROR asset {bundle}: asset '{asset}' not found"); continue
        if "references" in tree: tree["references"]["RefIds"] = [r for r in tree["references"]["RefIds"] if r.get("type", {}).get("class") != ""]
        for mid, spec in specs: apply_asset_ops(tree, spec, mid, report)
        obj.save_typetree(tree); data = env.file.save(packer="lz4")
        dst = os.path.join(OUT, *bundle.split("/")); os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, "wb").write(data)
        print(f"  asset {bundle}::{asset}: {sum(len(s.get('set', [])) + len(s.get('copyActions', [])) + len(s.get('addActions', [])) for _, s in specs)} ops from {[m for m, _ in specs]} -> {len(data)} bytes")


M32 = 0xFFFFFFFF
def tag_hash(s):
    h = 0x1234567
    for c in s: h = (((ord(c) & 0xFF) ^ h) * 0x89ABCDEF) & M32
    return struct.pack("<I", (h * 0x89ABCDEF) & M32)
def compose_locale(order, mods, report):
    merged = {}; owner = {}
    for mid in order:
        for lang, table in mods[mid].get("content", {}).get("locale", {}).items():
            for k, v in table.items():
                if (lang, k) in owner and owner[(lang, k)] != mid and merged[lang][k] != v: report.append(f"CONFLICT locale {lang}/{k}: {owner[(lang, k)]} vs {mid}")
                merged.setdefault(lang, {})[k] = v; owner[(lang, k)] = mid
    return merged
def build_locale(merged):
    import UnityPy
    for lang, table in merged.items():
        logical = f"data/localization/localization_{lang}.ab"; name = f"localization_{lang}"
        env = UnityPy.load(slice_bundle(find_entry(logical)))
        raw = next(o.read().m_Script.encode("utf-8", "surrogateescape") for o in env.objects if o.type.name == "TextAsset")
        entries = []; p = 0
        while p + 8 <= len(raw):
            h = raw[p:p+4]; n = struct.unpack("<I", raw[p+4:p+8])[0]; entries.append([h, raw[p+8:p+8+n]]); p += 8 + n
        idx = {e[0]: e for e in entries}; upd = add = 0
        for k, text in table.items():
            h = tag_hash(k)
            if h in idx: idx[h][1] = text.encode("utf-8"); upd += 1
            else: entries.append([h, text.encode("utf-8")]); add += 1
        rebuild_bundle(logical, name, b"".join(h + struct.pack("<I", len(v)) + v for h, v in entries))
        print(f"  locale {lang}: {upd} updated, {add} added")


def build():
    import hashlib
    mods = load_mods(); prof = load_profile(); order = resolve_order(mods, prof["enabled"]); build_id = game_build()
    from pathlib import Path
    from validation_tables import validate_baseline
    baseline = validate_baseline(ROOT, build_id)
    from build_provenance import capture, canonical_sha
    inputs = capture(ROOT, order, mods, build_id)
    output_path = Path(OUT).resolve()
    workspace = Path(ROOT).resolve().parent.parent
    if not output_path.is_relative_to(workspace) or output_path in (workspace, Path(ROOT).resolve()):
        raise SystemExit("Build output must be a dedicated directory inside this workbench")
    print(f"game build {build_id}; load order: {order}")
    for mid in order:
        gb = mods[mid].get("gameBuilds", ["*"])
        if "*" not in gb and build_id not in gb:
            raise SystemExit(f"REFUSING {mid}: target builds {gb}, bound game is {build_id}")
    report = []
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    print("tables:"); tnames = compose_tables(order, mods, report)
    print("js:"); jsnames = compose_js(order, mods, report)
    locale = compose_locale(order, mods, report)
    errs = [r for r in report if r.startswith(("CONFLICT", "ERROR"))]
    if errs:
        print("\nBUILD ABORTED before resource generation:\n  " + "\n  ".join(errs))
        return False
    from table_preflight import preflight_tables, assert_preflight_unchanged
    preflight = preflight_tables(ROOT, tnames, schema=SCHEMA, build_id=build_id,
                                report_path=Path(ROOT) / "inspect" / "table_verification" / str(build_id) / "preflight.json")
    verified_tables = {item["table"]: item for item in preflight["tables"]}
    js_payloads = {logical: Path(js_path(logical)).read_bytes() for logical in jsnames}
    print("rigs:")
    rig_specs = [(m, r) for m in order for r in mods[m].get("content", {}).get("rigClones", [])]
    rig_specs += [(m, dict(r, _kind="bundle")) for m in order for r in mods[m].get("content", {}).get("bundleClones", [])]
    if rig_specs:

        spec_file = os.path.join(tempfile.gettempdir(), "bbmod_rigspecs_%d.json" % os.getpid())
        with open(spec_file, "w", encoding="utf-8") as f: json.dump(rig_specs, f)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "_rigs", "@" + spec_file], capture_output=True, text=True)
        try: os.remove(spec_file)
        except OSError: pass
        print(r.stdout.rstrip())
        if r.returncode != 0: report.append("ERROR rigs: child process failed (rc %d): %s" % (r.returncode, r.stderr[-800:]))



    for mid in order:
        for spec in mods[mid].get("content", {}).get("importers", []):
            print("importer %s: %s" % (mid, spec["script"]))
            addp = os.path.join(tempfile.gettempdir(), "bbmod_import_%s_%d.json" % (mid, os.getpid()))
            r = subprocess.run([sys.executable, os.path.join(mdir(mid), spec["script"])] + list(spec.get("args", [])) + ["--out", OUT, "--adds", addp],
                               capture_output=True, text=True, env=dict(os.environ, BBMOD_OUT=OUT))
            print("\n".join(r.stdout.rstrip().splitlines()[-25:]))
            if r.returncode != 0 or not os.path.exists(addp):
                report.append("ERROR importer %s: rc %d: %s" % (mid, r.returncode, (r.stderr or r.stdout)[-800:])); continue
            add = json.load(open(addp, encoding="utf-8")); os.remove(addp)
            madd = os.path.join(OUT, "_manifest_add.json")
            cur = json.load(open(madd)) if os.path.exists(madd) else {"names": [], "entries": [], "guids": []}
            for k in ("names", "entries", "guids"): cur[k] += add.get(k, [])
            json.dump(cur, open(madd, "w"), indent=1)
    print("assets:")
    if any(mods[m].get("content", {}).get("assets") for m in order):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "_assets", json.dumps(order)], capture_output=True, text=True)
        print(r.stdout.rstrip()); [report.append(l) for l in r.stdout.splitlines() if l.startswith(("CONFLICT", "ERROR"))]
        if r.returncode != 0: report.append("ERROR assets: child process failed (rc %d): %s" % (r.returncode, r.stderr[-600:]))
    errs = [r for r in report if r.startswith(("CONFLICT", "ERROR"))]
    if errs: print("\nBUILD ABORTED:\n  " + "\n  ".join(errs)); return False
    assert_preflight_unchanged(ROOT, preflight)
    if any(Path(js_path(logical)).read_bytes() != content for logical, content in js_payloads.items()):
        raise ValueError("Composed JS changed during resource generation")
    print("encoding:")
    for name in tnames:
        raw = encode_table(name)
        if hashlib.sha256(raw).hexdigest() != verified_tables[name]["normal"]["sha256"]:
            raise ValueError(f"{name}: encoded payload differs from the composition preflight")
        verify_table(name, raw); rebuild_bundle(f"data/xlsx/{name.lower()}.ab", name, raw)
        if name + "FixedPoint" in SCHEMA and os.path.exists(os.path.join(RAW, "data", "xlsxfixed", name + "FixedPointWrap.bin")):
            fraw = encode_fixed_table(name, KEY_OVERRIDES.get(name))
            if hashlib.sha256(fraw).hexdigest() != verified_tables[name]["fixed"]["sha256"]:
                raise ValueError(f"{name}: fixed payload differs from the composition preflight")
            verify_table(name + "FixedPointWrap", fraw)
            rebuild_bundle(f"data/xlsxfixed/{name.lower()}fixedpointwrap.ab", name + "FixedPointWrap", fraw)
    for lp in jsnames:
        src = js_payloads[lp]; key = JSKEYS.get(lp)
        rebuild_bundle(lp.lower() + ".ab", lp.split("/")[-1], (b"NOAH" + noah_xor(src, int(key, 16))) if key else src)
    build_locale(locale)
    if capture(ROOT, order, mods, build_id) != inputs:
        raise ValueError("Build inputs changed during composition/resource generation; no installable build receipt was written")
    assert_preflight_unchanged(ROOT, preflight)
    if any(Path(js_path(logical)).read_bytes() != content for logical, content in js_payloads.items()):
        raise ValueError("Composed JS changed during encoding")
    json.dump({"gameBuild": build_id, "mods": {m: mods[m]["version"] for m in order}, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
               "baseline_manifest_sha256": hashlib.sha256(open(os.path.join(ROOT, "inspect", "baseline_manifest.json"), "rb").read()).hexdigest(),
               "descriptors": {m: hashlib.sha256(open(os.path.join(mdir(m), "mod.json"), "rb").read()).hexdigest() for m in order},
               "input_provenance": inputs, "input_provenance_sha256": canonical_sha(inputs),
               "composed_payload_sha256": {
                   "tables": {name: {kind: row[kind]["sha256"] for kind in ("normal", "fixed") if kind in row}
                              for name, row in verified_tables.items()},
                   "js": {logical: hashlib.sha256(content).hexdigest() for logical, content in js_payloads.items()}}},
              open(os.path.join(OUT, "_build.json"), "w"), indent=1)
    from build_verification import verify_build
    verification = verify_build(ROOT, OUT, build_id, typetree_generator=typetree_gen())
    json.dump(verification, open(os.path.join(OUT, "_verification.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("build OK ->", OUT); return True

def game_running():
    """True while BlazblueEntropyEffect.exe runs. 2026-09-28: the game was started during an install; it read the old
    merge.json, then bundles from the rewritten m_mod.m at the old offsets, lost the mod rows of BaseActorConf, and its
    login crashed on the save's mod characters ('reading special'), reporting every save as corrupted."""
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq BlazblueEntropyEffect.exe"], capture_output=True, text=True).stdout
        return "blazblueentropyeffect.exe" in out.lower()
    except Exception:
        return False

def gameslot_block():
    """2026-09-30: installs are scheduled (tools/gameslot.py): refuse while ANOTHER session holds the game slot.
    Set BBEE_SLOT=<your workstream> after `python tools/gameslot.py acquire <name> "<purpose>"`."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools")); import gameslot
        return gameslot.check(os.environ.get("BBEE_SLOT", ""))
    except Exception:
        return None

def install():
    # The verified entry owns backup/save planning; its child build takes the build lock.
    from entry_point import install as verified_install
    verified_install([])
    return True
def uninstall():
    from entry_point import uninstall as verified_uninstall
    verified_uninstall([])
    return True

def status():
    prof = load_profile(); mods = load_mods()
    print("game build:", game_build(), "| merge.json.orig present:", os.path.exists(os.path.join(AB, "merge.json.orig")), "| m_mod.m present:", os.path.exists(os.path.join(AB, "m_mod.m")))
    print("installed:", json.load(open(INSTALLED)) if os.path.exists(INSTALLED) else "nothing recorded")
    print("enabled:", prof["enabled"]); print("available:", sorted(mods))
def list_mods():
    prof = load_profile()
    for mid, m in load_mods().items():
        c = m.get("content", {})
        print(f"[{'x' if mid in prof['enabled'] else ' '}] {mid} v{m['version']} - {m['name']}  (tables {list(c.get('tables', {}))}, js {len(c.get('js', []))}+{len(c.get('jsFiles', {}))}, locale {list(c.get('locale', {}))}, deps {m.get('dependencies', [])})")
def doctor():
    status()
    if os.path.exists(PLAYER_LOG):
        log = open(PLAYER_LOG, encoding="utf-8", errors="replace").read().splitlines()
        bad = [l for l in log if re.search(r"SyntaxError|c# exception|ReferenceError|TypeError: |is not a function|Cannot read", l)]
        print(f"Player.log: {len(log)} lines; JS-ish errors: {len(bad)}"); [print("  ", l[:200]) for l in bad[:10]]
    ml = os.path.join(ROOT, "modlog.txt")
    if os.path.exists(ml):
        lines = open(ml, encoding="utf-8", errors="replace").read().splitlines(); print(f"modlog.txt: {len(lines)} lines; last:"); [print("  ", l[:160]) for l in lines[-8:]]
def report():
    """compact session report: errors/exceptions from Player.log + the full modlog, written to reports/<timestamp>.md"""
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True); out = os.path.join(ROOT, "reports", time.strftime("%Y%m%d-%H%M%S") + ".md")
    lines = ["# BBEE session report " + time.strftime("%Y-%m-%d %H:%M"), ""]
    if os.path.exists(PLAYER_LOG):
        log = open(PLAYER_LOG, encoding="utf-8", errors="replace").read().splitlines()
        lines += [f"## Player.log ({len(log)} lines)", ""]
        keep = re.compile(r"SyntaxError|c# exception|Exception: |TypeError|ReferenceError|unhandledRejection|\|Error\||Missing localization|Texture Original Size|表格.*没有找到|AcquireWindow (?!Instructions|InputLock|OverlayInfoUI|FloatingUI|MessageRoller)")
        i = 0; shown = 0
        while i < len(log) and shown < 400:
            l = log[i]
            if keep.search(l):
                block = [l.strip()]
                for j in range(1, 6):
                    if i + j < len(log) and log[i + j].startswith("    at "): block.append(log[i + j].strip())
                lines.append("- " + " ⏎ ".join(block)[:600]); shown += 1
            i += 1
    ml = os.path.join(ROOT, "modlog.txt")
    if os.path.exists(ml):
        mlines = open(ml, encoding="utf-8", errors="replace").read().splitlines()
        lines += ["", f"## modlog.txt ({len(mlines)} lines)", ""] + ["    " + l for l in mlines[-5000:]]
    lines += ["", "## installed", "", "    " + json.dumps(json.load(open(INSTALLED)) if os.path.exists(INSTALLED) else {})]
    open(out, "w", encoding="utf-8").write("\n".join(lines)); print("report written:", out, f"({len(lines)} lines)")
def new_mod(mid):
    d = os.path.join(MODS, mid); os.makedirs(os.path.join(d, "files"), exist_ok=True)
    json.dump({"id": mid, "name": mid, "version": "0.1.0", "author": "", "description": "", "gameBuilds": [game_build()], "dependencies": [],
               "content": {"tables": {}, "locale": {"enu": {}}, "js": [], "jsFiles": {}}}, open(os.path.join(d, "mod.json"), "w", encoding="utf-8"), indent=1)
    print("created", d)





LOCK = os.path.join(MODS, ".bbmod.lock")
def _pid_alive(pid):
    if not pid: return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h: return False
        code = ctypes.c_ulong(); ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259
    try: os.kill(int(pid), 0); return True
    except OSError: return False
def acquire_lock(what, wait_s=900):
    import time
    t0 = time.time(); said = 0
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "cmd": what, "since": time.strftime("%H:%M:%S")}).encode()); os.close(fd)
            return True
        except FileExistsError:
            try: info = json.load(open(LOCK, encoding="utf-8"))
            except Exception: info = {}
            if not _pid_alive(info.get("pid")):
                print(f"  (clearing a stale build lock from pid {info.get('pid')})");
                try: os.remove(LOCK)
                except OSError: pass
                continue
            if time.time() - t0 > wait_s:
                print(f"refusing: another session's bbmod {info.get('cmd')} (pid {info.get('pid')}, since {info.get('since')}) "
                      f"still holds {LOCK} after {wait_s}s"); return False
            if time.time() - said > 15:
                print(f"  waiting: another session's bbmod {info.get('cmd')} is running (pid {info.get('pid')}, since {info.get('since')})")
                said = time.time()
            time.sleep(2)
def release_lock():
    try:
        info = json.load(open(LOCK, encoding="utf-8"))
        if info.get("pid") == os.getpid(): os.remove(LOCK)
    except Exception: pass
def locked(fn, what):
    if not acquire_lock(what): sys.exit(1)
    try: return fn()
    finally: release_lock()

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "status": status()
    elif cmd == "list": list_mods()
    elif cmd == "enable": p = load_profile(); [p["enabled"].append(i) for i in sys.argv[2:] if i not in p["enabled"]]; save_profile(p); print(p)
    elif cmd == "disable": p = load_profile(); p["enabled"] = [i for i in p["enabled"] if i not in sys.argv[2:]]; save_profile(p); print(p)
    elif cmd == "build": sys.exit(0 if locked(build, "build") else 1)
    elif cmd == "install": sys.exit(0 if install() else 1)
    elif cmd == "uninstall": sys.exit(0 if uninstall() else 1)
    elif cmd == "doctor": doctor()
    elif cmd == "new": new_mod(sys.argv[2])
    elif cmd == "report": report()
    elif cmd == "_rigs":
        import bbchar; adds = {"names": [], "entries": [], "guids": []}; rep = []
        arg = sys.argv[2]
        for mid, spec in (json.load(open(arg[1:], encoding="utf-8")) if arg.startswith("@") else json.loads(arg)):
            if spec.get("_kind") == "bundle":
                img = spec.get("image") and os.path.join(mdir(mid), spec["image"])
                a = bbchar.clone_bundle(spec["from"], spec["to"], OUT, tuple(spec["rename"]) if spec.get("rename") else None, img, None, spec.get("refTypesFrom"),
                                        bool(spec.get("renameObjects")),
                                        [(n, ip if ip is None or ip.startswith("sprite:") else os.path.join(mdir(mid), ip)) for n, ip in spec["atlasSprites"]] if spec.get("atlasSprites") else None,
                                        recolor=spec.get("recolor"), remap_deps=spec.get("remapDeps"))


                if spec.get("guid"): a["guids"] = list(a.get("guids", [])) + [[spec["to"], spec["guid"]]]
            else:
                a = bbchar.clone_rig(spec["from"], spec["to"], OUT, rep, spec.get("logicFrom"))
            for k in ("names", "entries", "guids"): adds[k] += a[k]
            if spec.get("rigSpec"):
                import bbrig; bbrig.inject(os.path.join(mdir(mid), spec["rigSpec"]), OUT)
        json.dump(adds, open(os.path.join(OUT, "_manifest_add.json"), "w"), indent=1); [print(l) for l in rep]
    elif cmd == "_assets":
        rep = []; compose_assets(json.loads(sys.argv[2]), load_mods(), rep); [print(l) for l in rep]; sys.exit(1 if any(l.startswith("ERROR") for l in rep) else 0)
    else: print(__doc__)
