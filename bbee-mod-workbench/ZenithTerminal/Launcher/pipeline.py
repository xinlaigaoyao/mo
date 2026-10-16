"""Strict fresh extraction; publish only validated complete outputs.

python pipeline.py [root] [--strict] [--fresh] [--build-id BUILD]
An optional --allow-failures JSON maps exact logical bundles to objects with
build_id and reason. Required inputs can never be exempted.
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
from validation_tables import ValidationError, decode_table, encode_table_rows, validate_table_payload


def dump_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_id(root, explicit=None):
    if explicit:
        if not re.fullmatch(r"\d+", explicit):
            raise ValidationError("build id must be numeric")
        return explicit
    acf = (root / "game").resolve().parent.parent / "appmanifest_2273430.acf"
    if not acf.is_file():
        raise ValidationError("No appmanifest beside linked game. Use --build-id for an explicitly identified sandbox copy.")
    match = re.search(r'"buildid"\s+"(\d+)"', acf.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise ValidationError(f"No buildid in {acf}")
    return match.group(1)


def required_inputs(root):
    tables, scripts = set(), set()
    manifests = sorted((root / "shared").glob("*/mod.json")) + sorted((root / "mods").glob("*/mod.json"))
    for path in manifests:
        content = json.loads(path.read_text(encoding="utf-8")).get("content", {})
        tables.update(content.get("tables", {}))
        scripts.update(spec["file"] for spec in content.get("js", []))
        scripts.update(content.get("jsFiles", {}))
    if manifests:
        scripts.add("data/js/Example")
    return tables, scripts


def parse_dump_schema(text):
    """Keep namespace and full nested scope; never overwrite equal leaf names."""
    declarations = []
    for block in re.split(r"(?m)^(?=// Namespace:)", text):
        match = re.search(r"(?m)^[^\n]*?(class|struct|enum|interface)\s+([\w\.]+)[^\n]*// TypeDefIndex: (\d+)", block)
        if not match:
            continue
        namespace_match = re.search(r"(?m)^// Namespace:[ \t]*([^\r\n]*)", block)
        namespace = namespace_match.group(1).strip() if namespace_match else ""
        name = match.group(2)
        full = namespace + "." + name if namespace else name
        numbers = dict(re.findall(r"public const int (\w+)FieldNumber = (\d+);", block))
        props = {m.group(2): m.group(1) for m in re.finditer(r"public ([\w\.<>\[\], `]+?) (\w+) \{ get;", block)}
        declarations.append((namespace, name, full, match.group(1), numbers, props))
    full_types = {full for _, _, full, kind, nums, _ in declarations if kind != "enum" and nums}
    enum_types = {full for _, _, full, kind, _, _ in declarations if kind == "enum"}
    enum_aliases = collections.defaultdict(set)
    for _, name, full, kind, _, _ in declarations:
        if kind == "enum":
            enum_aliases[name].add(full)
    aliases = collections.defaultdict(set)
    for namespace, name, full, kind, numbers, props in declarations:
        if kind != "enum" and numbers:
            aliases[name].add(full)
    def qualify(pt, namespace):
        def replace(match):
            token = match.group(0)
            local = namespace + "." + token if namespace else token
            if token in full_types:
                return token
            if local in full_types:
                return local
            if token in enum_types or local in enum_types or len(enum_aliases.get(token, set())) == 1:
                return "int"  # protobuf enum's signed int32 wire contract
            candidates = aliases.get(token, set())
            return next(iter(candidates)) if len(candidates) == 1 else token
        return re.sub(r"[A-Za-z_][\w.]*", replace, pt)
    schema = {}
    for namespace, name, full, kind, numbers, props in declarations:
        if kind == "enum" or not numbers:
            continue
        if full in schema:
            raise ValidationError(f"duplicate full schema declaration {full}")
        fields = {number: (field, qualify(props.get(field, "?"), namespace)) for field, number in numbers.items()}
        schema[full] = fields
    for alias, targets in aliases.items():
        if len(targets) == 1 and alias not in schema:
            schema[alias] = schema[next(iter(targets))]
    return schema


def load_schema(root, build):
    source = root / "tools" / "schema" / build / "proto_schema_snapshot.json"
    dump = root / "dump" / "dump.cs"
    stamp = dump.parent / "game_build.txt"
    if dump.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == build:
        text = dump.read_text(encoding="utf-8", errors="replace")
        schema = parse_dump_schema(text)
        return schema, {"kind": "stamped_dump", "path": str(dump), "sha256": sha(dump)}
    if not source.is_file():
        raise ValidationError(f"No build-keyed schema for {build}; an unstamped dump cannot establish provenance")
    return json.loads(source.read_text(encoding="utf-8"))["schema"], {"kind": "build_snapshot", "path": str(source), "sha256": sha(source)}


def noah_xor(payload, key):
    keybytes = key.to_bytes(4, "little")
    return bytes(byte ^ keybytes[(i + (i >> 2)) & 3] for i, byte in enumerate(payload))


def decode_noah_script(payload):
    """Recover keys from complete known JS headers, never a score guess.

    The original game route has a 12-byte strict-mode header: all four key
    bytes are determined by the first four bytes and checked again by the
    remaining eight. UTF-8 and exact inverse encoding complete this route's
    extraction contract. Script syntax is checked by the build verifier.
    Short alternative headers additionally require unique Node syntax proof.
    """
    if len(payload) < 8 or not payload.startswith(b"NOAH"):
        raise ValidationError("truncated or invalid NOAH header")
    strict = b'"use strict"'
    strict_key = int.from_bytes(bytes(payload[4 + i] ^ strict[i] for i in range(4)), "little")
    strict_plain = noah_xor(payload[4:], strict_key)
    if strict_plain.startswith(strict):
        try:
            strict_plain.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            if b"NOAH" + noah_xor(strict_plain, strict_key) == payload:
                return strict_plain, strict_key, {"known_header": strict.decode(), "syntax_mode": "strict_header",
                                                  "key_contract": "unique_from_strong_12_byte_header", "roundtrip": "passed"}
    headers = (b'(this["define"] || function', b'/*\r\n',
               b'/*!\n', b'\xef\xbb\xbf/*', b'const ', b'\n//# sourceMappingURL=')
    candidates = {}
    for header in headers:
        key = int.from_bytes(bytes(payload[4 + i] ^ header[i] for i in range(4)), "little")
        plain = noah_xor(payload[4:], key)
        if not plain.startswith(header):
            continue
        try:
            plain.decode("utf-8")
        except UnicodeDecodeError:
            continue
        mode = None
        if header != b'"use strict"':
            node = shutil.which("node")
            if node is None:
                raise ValidationError("Node.js is required to validate a non-strict NOAH JavaScript header")
            for syntax_mode in ("commonjs", "module"):
                check = subprocess.run([node, "--input-type=" + syntax_mode, "--check"], input=plain,
                                       capture_output=True, timeout=20)
                if check.returncode == 0:
                    mode = syntax_mode
                    break
            if mode is None:
                continue
        if b"NOAH" + noah_xor(plain, key) == payload:
            candidates[key] = (plain, {"known_header": header.decode("utf-8", "replace"),
                                       "syntax_mode": mode or "strict_header", "roundtrip": "passed"})
    if len(candidates) != 1:
        raise ValidationError(f"NOAH key has {len(candidates)} validated candidates; exactly one is required")
    key, (plain, metadata) = next(iter(candidates.items()))
    return plain, key, metadata


def parts(value):
    result = value.replace("\\", "/").split("/")
    if not result or any(x in ("", ".", "..") or ":" in x for x in result):
        raise ValidationError(f"unsafe resource path {value!r}")
    return result


def publish(root, stage, build):
    history = root / ".baseline_history" / (build + "_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    history.mkdir(parents=True)
    old, new = [], []
    try:
        for name in ("extracted_raw", "decoded", "inspect"):
            target = root / name
            if target.exists():
                if target.is_symlink():
                    raise ValidationError(f"refusing to replace linked output directory {target}")
                target.rename(history / name)
                old.append(name)
            (stage / name).rename(target)
            new.append(name)
    except Exception:
        for name in reversed(new):
            (root / name).rename(stage / name)
        for name in reversed(old):
            (history / name).rename(root / name)
        raise
    return str(history)


def run(args):
    root = Path(args.root).resolve()
    stage = Path(tempfile.mkdtemp(prefix=".decode-", dir=root))
    raw, dec, ins = stage / "extracted_raw", stage / "decoded", stage / "inspect"
    for path in (raw, dec / "tables", dec / "tables_fixed", ins):
        path.mkdir(parents=True, exist_ok=True)
    report = {"format": 1, "status": "failed", "strict": True, "fresh": True,
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "stage": str(stage),
              "failures": [], "allowed_failures": [], "skipped": [], "extraction": [], "scripts": [], "tables": [], "fixed_tables": []}
    allowlist = {}
    def failure(category, logical, error, required=False):
        item = {"category": category, "logical": logical, "error": str(error), "required": required}
        if logical in allowlist and not required:
            item["reason"] = allowlist[logical]["reason"]
            report["allowed_failures"].append(item)
        else:
            report["failures"].append(item)
    try:
        build = build_id(root, args.build_id or os.environ.get("BBMOD_BUILD_ID"))
        report["build_id"] = build
        tables_required, scripts_required = required_inputs(root)
        logical_required = ({"data/xlsx/" + n.lower() + ".ab" for n in tables_required}
                            | {"data/xlsxfixed/" + n.lower() + "fixedpointwrap.ab" for n in tables_required}
                            | {n.lower() + ".ab" for n in scripts_required})
        report.update(required_tables=sorted(tables_required), required_scripts=sorted(scripts_required))
        if args.allow_failures:
            allowlist = json.loads(Path(args.allow_failures).read_text(encoding="utf-8"))
            for logical, waiver in allowlist.items():
                if waiver.get("build_id") != build or not waiver.get("reason", "").strip():
                    raise ValidationError(f"allowlist {logical} needs current build_id and reason")
                if logical in logical_required:
                    raise ValidationError(f"required asset cannot be exempted: {logical}")
        schema, provenance = load_schema(root, build)
        dump_json(ins / "proto_schema.json", schema)
        report.update(schema_source=provenance, schema_types=len(schema))
        ab = root / "game" / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
        merge_path = ab / "merge.json"
        merge = json.loads(merge_path.read_text(encoding="utf-8"))
        manifest = ab / "manifest"
        if any(e["m"] == "m_mod.m" for e in merge):
            for name in ("merge.json", "manifest"):
                backup, stamp = ab / (name + ".orig"), ab / (name + ".orig.build")
                if not backup.is_file() or not stamp.is_file() or stamp.read_text().strip() != build:
                    raise ValidationError(f"modded index has no pristine {name} backup for build {build}")
            merge_path, manifest = ab / "merge.json.orig", ab / "manifest.orig"
            merge = json.loads(merge_path.read_text(encoding="utf-8"))
        report["source_merge"] = {"path": str(merge_path), "sha256": sha(merge_path), "entries": len(merge)}
        report["source_manifest"] = {"path": str(manifest), "sha256": sha(manifest)}
        (ins / "logical_bundles.txt").write_text("\n".join(sorted(e["r"] for e in merge)), encoding="utf-8")
        import UnityPy
        import lz4.frame
        (ins / "manifest_decoded.txt").write_bytes(lz4.frame.decompress(manifest.read_bytes()))
        by_file = collections.defaultdict(list)
        for entry in merge:
            parts(entry["r"])
            parts(entry["m"])
            by_file[entry["m"]].append(entry)
        bounds = {}
        for filename, entries in by_file.items():
            entries.sort(key=lambda e: int(e["s"]))
            total = (ab / filename).stat().st_size
            for index, entry in enumerate(entries):
                start = int(entry["s"])
                end = int(entries[index + 1]["s"]) if index + 1 < len(entries) else total
                if not 0 <= start < end <= total:
                    raise ValidationError(f"invalid slice: {filename}@{start}..{end}/{total}")
                if entry["r"] in bounds:
                    raise ValidationError(f"duplicate logical bundle {entry['r']}")
                bounds[entry["r"]] = (start, end)
        logical_by_raw = {}
        for entry in merge:
            logical = entry["r"]
            if not logical.startswith("data/"):
                continue
            try:
                start, end = bounds[logical]
                with (ab / entry["m"]).open("rb") as stream:
                    stream.seek(start)
                    blob = stream.read(end - start)
                env, count = UnityPy.load(blob), 0
                for obj in env.objects:
                    if obj.type.name != "TextAsset":
                        continue
                    data = obj.read()
                    payload = data.m_Script
                    payload = payload.encode("utf-8", "surrogateescape") if isinstance(payload, str) else bytes(payload)
                    if len(parts(data.m_Name)) != 1:
                        raise ValidationError(f"TextAsset name has directory components: {data.m_Name}")
                    relative = Path(*parts(logical)[:-1]) / (data.m_Name + ".bin")
                    output = raw / relative
                    if output.exists():
                        raise ValidationError(f"two TextAssets map to {relative}")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(payload)
                    logical_by_raw[relative.as_posix()] = logical
                    count += 1
                report["extraction"].append({"logical": logical, "text_assets": count, "bytes": len(blob)})
            except Exception as ex:
                failure("extract", logical, ex, logical in logical_required)
        print(f"Extracted {len(logical_by_raw)} TextAssets from {len(report['extraction'])} data bundles", flush=True)
        keys, scripts_found = {}, set()
        for path in sorted(raw.rglob("*.bin")):
            rel = path.relative_to(raw)
            logical = logical_by_raw[rel.as_posix()]
            base = dec / rel.with_suffix("")
            base.parent.mkdir(parents=True, exist_ok=True)
            payload, js = path.read_bytes(), rel.as_posix().startswith("data/js/")
            try:
                if payload.startswith(b"NOAH"):
                    plain, key, metadata = decode_noah_script(payload)
                    Path(str(base) + ".js").write_bytes(plain)
                    module = rel.as_posix()[:-4]
                    keys[module] = f"0x{key:08x}"
                    scripts_found.add(module)
                    report["scripts"].append({"module": module, "encrypted": True, **metadata})
                elif js:
                    payload.decode("utf-8")
                    Path(str(base) + ".js").write_bytes(payload)
                    module = rel.as_posix()[:-4]
                    scripts_found.add(module)
                    report["scripts"].append({"module": module, "encrypted": False})
                else:
                    extension = ".json" if payload[:1] in (b"{", b"[") else ".bin"
                    Path(str(base) + extension).write_bytes(payload)
            except Exception as ex:
                failure("decode_js" if js else "decode_noah", logical, ex, logical in logical_required)
        dump_json(ins / "js_keys.json", keys)
        for module in sorted(scripts_required - scripts_found):
            failure("required_js_missing", module.lower() + ".ab", "required module was not decoded", True)
        tables_found = set()
        for folder, fixed in (("xlsx", False), ("xlsxfixed", True)):
            for path in sorted((raw / "data" / folder).glob("*.bin")):
                name = path.stem
                cls = name.removesuffix("Wrap") if fixed else name
                logical = logical_by_raw[path.relative_to(raw).as_posix()]
                required = (cls.removesuffix("FixedPoint") if fixed else cls) in tables_required
                if cls not in schema:
                    if required:
                        failure("missing_schema", logical, f"no schema for {cls}", True)
                    else:
                        report["skipped"].append({"logical": logical, "category": "unknown_table_schema", "reason": f"no schema for {cls}; this table is unavailable for editing and is not verified"})
                    continue
                try:
                    data = path.read_bytes()
                    rows = decode_table(data, cls, schema)
                    result = validate_table_payload(encode_table_rows(rows, cls, schema), rows, cls, schema)
                    result.update(logical=logical, source_sha256=sha(path), source_bytes=len(data))
                    dump_json(dec / ("tables_fixed" if fixed else "tables") / (cls + ".json"), rows)
                    report["fixed_tables" if fixed else "tables"].append(result)
                    if not fixed:
                        tables_found.add(name)
                except Exception as ex:
                    failure("decode_fixed_table" if fixed else "decode_table", logical, ex, required)
        for name in sorted(tables_required - tables_found):
            failure("required_table_missing", "data/xlsx/" + name.lower() + ".ab", f"required table {name} was not decoded", True)
        fixed_verified = {r["schema"] for r in report["fixed_tables"]}
        normal_counts = {r["schema"]: r["rows"] for r in report["tables"]}
        for fixed_result in report["fixed_tables"]:
            normal_name = fixed_result["schema"].removesuffix("FixedPoint")
            if normal_name in normal_counts and normal_counts[normal_name] != fixed_result["rows"]:
                failure("fixed_count_mismatch", fixed_result["logical"],
                        f"normal/fixed baseline row counts differ: {normal_counts[normal_name]}/{fixed_result['rows']}",
                        normal_name in tables_required)
        for name in sorted(tables_required):
            if name + "FixedPoint" in schema and name + "FixedPoint" not in fixed_verified:
                failure("required_fixed_missing", "data/xlsxfixed/" + name.lower() + "fixedpointwrap.ab", f"required fixed table for {name} was not decoded", True)
        print(f"Decoded {len(report['tables'])} tables, {len(report['fixed_tables'])} fixed tables, {len(report['scripts'])} scripts; failures: {len(report['failures'])}", flush=True)
        if report["failures"]:
            raise ValidationError(f"strict extraction has {len(report['failures'])} unresolved failure(s)")
        for path in sorted(dec.rglob("*")):
            if path.is_file() and (path.suffix == ".js" or (path.parent.name in ("tables", "tables_fixed") and path.suffix == ".json")):
                shutil.copyfile(path, str(path) + ".orig")
        (ins / "game_build.txt").write_text(build, encoding="utf-8")
        files = {}
        for path in list(raw.rglob("*")) + list(dec.rglob("*.orig")) + [ins / "proto_schema.json", ins / "js_keys.json"]:
            if path.is_file():
                files[path.relative_to(stage).as_posix()] = sha(path)
        dump_json(ins / "baseline_manifest.json", {"format": 1, "build_id": build,
                  "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "schema_source": provenance,
                  "source_merge": report["source_merge"], "source_manifest": report["source_manifest"], "files": files})
        report.update(status="passed", finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        dump_json(ins / "decode_report.json", report)
        history = publish(root, stage, build)
        print(f"Fresh baseline published for build {build}; previous output archived at {history}", flush=True)
        return 0
    except Exception as ex:
        report.update(status="failed", fatal_error=str(ex), finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        dump_json(ins / "decode_report.json", report)
        (root / "inspect").mkdir(exist_ok=True)
        dump_json(root / "inspect" / "decode_report.failed.json", report)
        print(f"FAILED: {ex}\nDiagnostic report: {ins / 'decode_report.json'}", flush=True)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--fresh", action="store_true", default=True)
    parser.add_argument("--build-id")
    parser.add_argument("--allow-failures")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
