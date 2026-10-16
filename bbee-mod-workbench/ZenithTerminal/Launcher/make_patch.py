r"""
make_patch.py  -- rebuild game bundles from edited data and stage them for the patch folder.

  python make_patch.py table <TableName> [<TableName> ...]     encode decoded\tables\<Name>.json -> bundle
  python make_patch.py js <data/js/path/Name> [...]              re-encode decoded\data\js\...\Name.js -> bundle
  python make_patch.py install <PatchAssetBundleDir>             copy everything in patch_out into the game's patch folder (non-merge builds)
  python make_patch.py install-steam                              Steam/merged-AB build: write patch_out bundles into ab\m_mod.m + repoint merge.json
  python make_patch.py uninstall-steam                            restore merge.json.orig and delete m_mod.m

Outputs go to C:\BBEE_Steam\patch_out\<logical bundle path>  (e.g. patch_out\data\xlsx\playerbattletriggerdetail.ab)
"""
import os, sys, json, struct, re, shutil, collections


ROOT = os.path.dirname(os.path.abspath(globals().get("__file__") or getattr(sys.modules["__main__"], "__file__", None)
                                       or os.path.join(os.getcwd(), "make_patch.py")))
while not os.path.exists(os.path.join(ROOT, "make_patch.py")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
AB = os.path.join(ROOT, r"game\BlazblueEntropyEffect_Data\StreamingAssets\ab")
DEC = os.path.join(ROOT, "decoded"); OUT = os.environ.get("BBMOD_OUT") or os.path.join(ROOT, "patch_out")
SCHEMA = json.load(open(os.path.join(ROOT, r"inspect\proto_schema.json"))) if os.path.exists(os.path.join(ROOT, r"inspect\proto_schema.json")) else {}
JSKEYS = json.load(open(os.path.join(ROOT, r"inspect\js_keys.json"))) if os.path.exists(os.path.join(ROOT, r"inspect\js_keys.json")) else {}
import UnityPy

def _steam_manifest(root):
    """<library>/steamapps/common/<game>  ->  <library>/steamapps/appmanifest_2273430.acf (any Steam library)"""
    try:
        g = os.path.realpath(os.path.join(root, "game"))
        cand = os.path.join(os.path.dirname(os.path.dirname(g)), "appmanifest_2273430.acf")
        if os.path.exists(cand): return cand
    except Exception: pass
    return r"C:\Program Files (x86)\Steam\steamapps\appmanifest_2273430.acf"
STEAM_MANIFEST = _steam_manifest(ROOT)
def current_build():
    if os.environ.get("BBMOD_BUILD_ID"):
        return os.environ["BBMOD_BUILD_ID"]
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', open(STEAM_MANIFEST, encoding="utf-8").read()); return m.group(1) if m else None
    except OSError: return None
def backup_state(bak):
    """None = no backup; True = stamped for the installed build; False = stale (unstamped or another build)"""
    if not os.path.exists(bak): return None
    st = bak + ".build"
    return os.path.exists(st) and open(st, encoding="utf-8").read().strip() == (current_build() or "?")
def require_usable_backup(bak, what):
    if backup_state(bak) is False:
        stamp = open(bak + ".build", encoding="utf-8").read().strip() if os.path.exists(bak + ".build") else "unstamped (pre-guard)"
        raise SystemExit(
            f"REFUSING to {what}: {bak} is from game build {stamp}, but the installed game is build {current_build()}.\n"
            f"  Steam replaced the live index when it patched the game; this backup would write the OLD index back.\n"
            f"  Retire the stale backup (rename it, e.g. add .b<oldbuild>) so a fresh one is taken from the current game,\n"
            f"  then re-extract data for the new build before building mods. See docs/BUILD_UPDATE.md.")
def make_backup(src, bak):
    shutil.copy2(src, bak); open(bak + ".build", "w", encoding="utf-8").write(current_build() or "?")
def pristine_merge_path():
    live = os.path.join(AB, "merge.json"); bak = live + ".orig"
    if backup_state(bak): return bak
    if os.path.exists(live):
        if '"m_mod.m"' in open(live, encoding="utf-8").read():
            raise SystemExit("REFUSING to read bundles: merge.json contains modded entries and there is no backup for build "
                             f"{current_build()} to read pristine data from.")
        return live
    return None
_mp = pristine_merge_path()
merge = json.load(open(_mp, encoding="utf-8")) if _mp and os.path.exists(_mp) else []
by_file = collections.defaultdict(list)
for e in merge: by_file[e["m"]].append(e)
for m in by_file: by_file[m].sort(key=lambda e: e["s"])
def slice_bundle(entry):
    lst = by_file[entry["m"]]; i = lst.index(entry)
    p = os.path.join(AB, entry["m"]); end = lst[i+1]["s"] if i+1 < len(lst) else os.path.getsize(p)
    with open(p, "rb") as f: f.seek(entry["s"]); return f.read(end - entry["s"])
def find_entry(logical):
    return next(e for e in merge if e["r"] == logical)


from validation_tables import (classify as _classify, write_varint as wv,
    encode_scalar as _encode_scalar, encode_message as _encode_message,
    validate_table_payload, expected_fixed_rows, encode_fixed_table_rows, to_fixed_row as _to_fixed_row,
    read_varint as _read_varint, split_table, canonical_message, validate_opaque_preserved, ValidationError)

def tag(fnum, wt): return wv((fnum << 3) | wt)
def classify(pt): return _classify(pt, SCHEMA)
def enc_scalar(kind, base, value): return _encode_scalar(kind, base, value, SCHEMA)
def encode(obj, cls): return _encode_message(obj, cls, SCHEMA)

def encode_table(name):
    rows = json.load(open(os.path.join(DEC, "tables", name + ".json"), encoding="utf-8"))
    cls = name if name in SCHEMA else None
    if cls is None: raise SystemExit(f"no schema for {name}")
    return b"".join(struct.pack("<I", len(b := encode(r, cls))) + b for r in rows)


def noah_xor(payload, key):
    k = key.to_bytes(4, "little"); out = bytearray(payload)
    for i in range(len(out)): out[i] ^= k[(i + (i >> 2)) & 3]
    return bytes(out)

def rebuild_bundle(logical, asset_name, new_bytes):
    entry = find_entry(logical)
    env = UnityPy.load(slice_bundle(entry))
    hit = False
    for obj in env.objects:
        if obj.type.name != "TextAsset": continue
        d = obj.read()
        if d.m_Name.lower() != asset_name.lower(): continue
        d.m_Script = new_bytes.decode("utf-8", "surrogateescape")
        d.save(); hit = True
    if not hit: raise SystemExit(f"TextAsset {asset_name} not found in {logical}")
    data = env.file.save(packer="lz4")
    outp = os.path.join(OUT, *logical.split("/"))
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    open(outp, "wb").write(data)
    print(f"wrote {outp}  ({len(data)} bytes, original {entry['m']}@{entry['s']})")

def verify_table(name, raw):
    """Decode actual encoded bytes and compare against intended JSON rows."""
    fixed = name.endswith("FixedPointWrap")
    table = name[:-len("FixedPointWrap")] if fixed else name
    cls = table + "FixedPoint" if fixed else table
    current_path = os.path.join(DEC, "tables", table + ".json")
    original_path = current_path + ".orig"
    with open(current_path, encoding="utf-8") as stream: current = json.load(stream)
    if not os.path.isfile(original_path):
        raise ValidationError(f"{table}: no fresh .orig baseline; rerun setup")
    with open(original_path, encoding="utf-8") as stream: original = json.load(stream)
    validate_opaque_preserved(original, current)
    if fixed:
        baseline_path = os.path.join(ROOT, "extracted_raw", "data", "xlsxfixed", name + ".bin")
        with open(baseline_path, "rb") as stream: baseline_raw = stream.read()
        expected = expected_fixed_rows(current, original, baseline_raw, table, SCHEMA)
    else:
        expected = current
    result = validate_table_payload(raw, expected, cls, SCHEMA, len(original))
    # Splicing promises unchanged fixed-point records remain byte-identical.
    if fixed:
        from collections import defaultdict, deque
        untouched = defaultdict(deque)
        def fingerprint(row):
            return json.dumps(canonical_message(row, table, SCHEMA), sort_keys=True, ensure_ascii=False)
        for row, body in zip(original, split_table(baseline_raw)):
            untouched[fingerprint(row)].append(body)
        preserved = 0
        for row, body in zip(current, split_table(raw)):
            candidates = untouched[fingerprint(row)]
            if candidates:
                if candidates.popleft() != body:
                    raise ValidationError(f"{name}: unchanged fixed-point row was rewritten")
                preserved += 1
        result["unchanged_byte_identical_rows"] = preserved
    report_dir = os.path.join(ROOT, "inspect", "table_verification", str(current_build()))
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, name + ".json"), "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=1)
    print(f"  {name}: {result['rows']} rows, {result['bytes']} bytes; semantic roundtrip verified, row delta {result['row_delta']:+d}")
    return result


RAW = os.path.join(ROOT, "extracted_raw")
def to_fixed_row(r, cls):
    return _to_fixed_row(r, cls, SCHEMA)

def read_varint(b, i):
    return _read_varint(b, i)

def row_key(b, keys):
    """extract key field values (field numbers) from a protobuf row (varints only)"""
    i = 0; got = {}
    while i < len(b):
        t, i = read_varint(b, i); f, wt = t >> 3, t & 7
        if wt == 0: v, i = read_varint(b, i); got[f] = v
        elif wt == 2: ln, i = read_varint(b, i); i += ln
        elif wt == 5: i += 4
        elif wt == 1: i += 8
        else: raise ValueError(wt)
    return tuple(got.get(k, 0) for k in keys)
def encode_fixed_table(name, keyfields=None):
    """Use the shared semantic/body splicer; legacy keyfields never choose rows."""
    if name + "FixedPoint" not in SCHEMA:
        raise ValidationError(f"no FixedPoint schema for {name}")
    current_path = os.path.join(DEC, "tables", name + ".json")
    with open(current_path, encoding="utf-8") as stream:
        current = json.load(stream)
    with open(current_path + ".orig", encoding="utf-8") as stream:
        original = json.load(stream)
    with open(os.path.join(RAW, "data", "xlsxfixed", name + "FixedPointWrap.bin"), "rb") as stream:
        baseline = stream.read()
    output, result = encode_fixed_table_rows(current, original, baseline, name, SCHEMA)
    print(f"  {name}FixedPoint: {result['unchanged_byte_identical_rows']} unchanged rows byte-preserved, "
          f"{result['edited_or_new_rows']} edited/new rows encoded, {result['unused_original_bodies']} original bodies unused; "
          f"row delta {result['row_delta']:+d}")
    return output



MERGE = os.path.join(AB, "merge.json"); MERGE_BAK = MERGE + ".orig"; MODFILE = "m_mod.m"
def install_steam():
    from entry_point import install
    return install([])
def uninstall_steam():
    from entry_point import uninstall
    return uninstall([])

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "table":
    for name in sys.argv[2:]:
        raw = encode_table(name); verify_table(name, raw)
        rebuild_bundle(f"data/xlsx/{name.lower()}.ab", name, raw)
        if name + "FixedPoint" in SCHEMA and os.path.exists(os.path.join(RAW, "data", "xlsxfixed", name + "FixedPointWrap.bin")):
            fraw = encode_fixed_table(name); verify_table(name + "FixedPointWrap", fraw)
            rebuild_bundle(f"data/xlsxfixed/{name.lower()}fixedpointwrap.ab", name + "FixedPointWrap", fraw)
elif cmd == "js":
    for lp in sys.argv[2:]:
        src = open(os.path.join(DEC, *lp.split("/")) + ".js", "rb").read()
        key = JSKEYS.get(lp)
        payload = b"NOAH" + noah_xor(src, int(key, 16)) if key else src
        rebuild_bundle(lp.lower() + ".ab", lp.split("/")[-1], payload)
elif cmd == "install":
    raise SystemExit("Non-merged direct-copy installation is disabled in this build. Use entry_point.py install.")
elif cmd == "install-steam": install_steam()
elif cmd == "uninstall-steam": uninstall_steam()
else:
    print(__doc__)
