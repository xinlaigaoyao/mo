"""Read staged bundles back before installation; no loader imports or writes.

Checks structural references, table/JS payloads and hashes. This is a static
resource gate, not a substitute for starting the game and checking its behavior.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import io
import json
import ntpath
from pathlib import Path, PurePosixPath
import re
import struct

from validation_tables import (ValidationError, validate_baseline,
    validate_table_payload, expected_fixed_rows)


class BuildVerificationError(ValidationError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read(stream, count):
    value = stream.read(count)
    if len(value) != count:
        raise BuildVerificationError(f"truncated resource: requested {count}, read {len(value)}")
    return value


def _cstring(stream, limit=4096):
    value = bytearray()
    for _ in range(limit):
        byte = _read(stream, 1)
        if byte == b"\0":
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError as ex:
                raise BuildVerificationError("invalid UTF-8 archive name") from ex
        value += byte
    raise BuildVerificationError("archive string exceeds limit")


def _unpack(stream, fmt):
    return struct.unpack(fmt, _read(stream, struct.calcsize(fmt)))


def unityfs_directory(stream, offset=0, length=None, exact=True):
    """Read only the header/compressed block-info directory, not asset blocks.

    ``offset`` allows indexing the game's merged m_*.m files without loading or
    decompressing every bundle. Returned node bounds refer to the uncompressed
    asset stream. UnityPy subsequently validates actual staged block contents.
    """
    stream.seek(offset)
    if _cstring(stream) != "UnityFS":
        raise BuildVerificationError("resource is not UnityFS")
    version, = _unpack(stream, ">I")
    player, engine = _cstring(stream), _cstring(stream)
    declared, compressed, uncompressed, flags = _unpack(stream, ">QIII")
    if length is not None and (declared > length or (exact and declared != length)):
        raise BuildVerificationError(f"UnityFS declared length {declared} != available {length}")
    if declared < stream.tell() - offset or compressed > declared or uncompressed > (1 << 28):
        raise BuildVerificationError("invalid UnityFS header sizes")
    if flags & 0x1400:
        raise BuildVerificationError("encrypted UnityFS is unsupported by the verification gate")
    aligned = version >= 7 or (engine.startswith("2019.") and tuple(map(int, re.findall(r"\d+", engine)[:3])) >= (2019, 4, 15))
    if aligned:
        stream.seek(offset + ((stream.tell() - offset + 15) // 16 * 16))
    header_end = stream.tell() - offset
    info_position = declared - compressed if flags & 0x80 else header_end
    if info_position < header_end or info_position + compressed > declared:
        raise BuildVerificationError("UnityFS block-info is outside the resource")
    stream.seek(offset + info_position)
    packed = _read(stream, compressed)
    compression = flags & 0x3f
    if compression == 0:
        raw = packed
    elif compression in (1, 2, 3):
        from UnityPy.helpers import CompressionHelper
        raw = (CompressionHelper.decompress_lzma(packed) if compression == 1
               else CompressionHelper.decompress_lz4(packed, uncompressed))
    else:
        raise BuildVerificationError(f"unsupported block-info compression {compression}")
    if len(raw) != uncompressed:
        raise BuildVerificationError("UnityFS block-info decompressed size differs")
    info = io.BytesIO(raw)
    _read(info, 16)
    block_count, = _unpack(info, ">i")
    if not 0 <= block_count <= 1000000:
        raise BuildVerificationError("invalid UnityFS block count")
    blocks = [_unpack(info, ">IIH") for _ in range(block_count)]
    data_start = header_end if flags & 0x80 else header_end + compressed
    if flags & 0x200:
        data_start = (data_start + 15) // 16 * 16
    data_end = declared - compressed if flags & 0x80 else declared
    if data_start + sum(block[1] for block in blocks) != data_end:
        raise BuildVerificationError("UnityFS compressed block lengths do not consume the data region")
    total = sum(block[0] for block in blocks)
    count, = _unpack(info, ">i")
    if not 0 <= count <= 1000000:
        raise BuildVerificationError("invalid UnityFS directory count")
    nodes, seen = [], set()
    for _ in range(count):
        start, size, node_flags = _unpack(info, ">qqI")
        path = _cstring(info)
        if not path or path in seen or start < 0 or size < 0 or start + size > total:
            raise BuildVerificationError(f"invalid/duplicate UnityFS node {path!r}")
        seen.add(path)
        nodes.append({"path": path, "offset": start, "size": size, "flags": node_flags})
    if info.tell() != len(raw):
        raise BuildVerificationError("UnityFS block-info has unconsumed bytes")
    previous = 0
    for node in sorted(nodes, key=lambda node: node["offset"]):
        if node["size"] and node["offset"] < previous:
            raise BuildVerificationError("UnityFS directory nodes overlap")
        previous = max(previous, node["offset"] + node["size"])
    return {"format": version, "engine": engine, "player": player, "length": declared,
            "blocks": len(blocks), "uncompressed_bytes": total, "nodes": nodes}


def _walk(value, path="$", skip_ref_definitions=False):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            if skip_ref_definitions and key == "references":
                continue
            yield from _walk(child, f"{path}.{key}", skip_ref_definitions)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]", skip_ref_definitions)


def validate_managed_references(tree, label):
    definitions = tree.get("references", {}).get("RefIds", []) if isinstance(tree, dict) else []
    if not isinstance(definitions, list):
        raise BuildVerificationError(f"{label}: managed RefIds must be a list")
    ids = set()
    for entry in definitions:
        rid = entry.get("rid")
        if type(rid) is not int:
            raise BuildVerificationError(f"{label}: managed reference id is not an integer")
        if rid <= 0:
            continue
        if rid in ids or not entry.get("type", {}).get("class"):
            raise BuildVerificationError(f"{label}: duplicate or typeless managed definition {rid}")
        ids.add(rid)
    uses = 0
    for path, value in _walk(tree):
        if "rid" not in value:
            continue
        rid = value["rid"]
        if type(rid) is not int or (rid > 0 and rid not in ids) or rid < -2:
            raise BuildVerificationError(f"{label}{path}: unresolved managed reference {rid!r}")
        if rid > 0:
            uses += 1
    return {"definitions": len(ids), "positive_id_occurrences": uses}


def _serialized_files(environment):
    from UnityPy.files.SerializedFile import SerializedFile
    def descend(file):
        if isinstance(file, SerializedFile):
            yield file
        else:
            for child in getattr(file, "files", {}).values():
                yield from descend(child)
    for file in environment.files.values():
        yield from descend(file)


def _object_directory(assets):
    """Replay metadata so duplicate IDs cannot be hidden by UnityPy's dict."""
    from UnityPy.streams import EndianBinaryReader
    from UnityPy.files.SerializedFile import SerializedType
    from UnityPy.files.ObjectReader import ObjectReader
    reader = EndianBinaryReader(assets.reader.bytes)
    version = assets.header.version
    reader.Position = 48 if version >= 22 else 20 if version >= 9 else 16
    reader.endian = assets.header.endian
    if version < 9:
        reader.Position = assets.header.file_size - assets.header.metadata_size + 1
    if version >= 7:
        reader.read_string_to_null()
    if version >= 8:
        reader.read_int()
    enabled = reader.read_boolean() if version >= 13 else True
    count = reader.read_int()
    if count < 0 or count > 1000000:
        raise BuildVerificationError("invalid serialized type count")
    saved = assets._enable_type_tree
    try:
        assets._enable_type_tree = enabled
        for _ in range(count):
            SerializedType(reader, assets, False)
    finally:
        assets._enable_type_tree = saved
    if 7 <= version < 14:
        reader.read_int()
    count = reader.read_int()
    if count < 0 or count > 1000000:
        raise BuildVerificationError("invalid serialized object count")
    ids, bounds = set(), []
    for _ in range(count):
        obj = ObjectReader.from_reader(assets, reader)
        if not obj.path_id or obj.path_id in ids:
            raise BuildVerificationError(f"duplicate/null object ID {obj.path_id} in {assets.name}")
        if obj.byte_start < assets.header.data_offset or obj.byte_size < 0 or obj.byte_start + obj.byte_size > reader.Length:
            raise BuildVerificationError(f"object {obj.path_id} data is out of bounds in {assets.name}")
        ids.add(obj.path_id)
        bounds.append((obj.byte_start, obj.byte_start + obj.byte_size))
    previous = 0
    for start, end in sorted(bounds):
        if start < previous and end > start:
            raise BuildVerificationError(f"overlapping objects in {assets.name}")
        previous = max(previous, end)
    if ids != set(assets.objects):
        raise BuildVerificationError(f"parsed object IDs differ from metadata in {assets.name}")
    if assets.header.file_size != reader.Length:
        raise BuildVerificationError(f"serialized file size differs in {assets.name}")
    return ids


def _cab_name(path):
    return ntpath.basename(str(path).replace("/", "\\")).lower()


class ExternalResolver:
    """Resolve staged CABs first; lazily load targets from a header-only baseline index."""
    def __init__(self, root, staged, generator=None):
        self.root, self.staged, self.generator = Path(root), staged, generator
        self.index = None
        self.cache = {}
        self.checked = 0
        self.builtin_unchecked = set()
        self.indexed_bundles = 0
        self.non_bundle_segments = []

    @staticmethod
    def _raw_metadata_kind(logical, prefix):
        """The merged source index also contains three non-bundle metadata blobs.

        Only these exact logical names and observed format signatures qualify.
        Unknown data, or a malformed UnityFS, must not become a silent skip.
        Staged output validation never calls this classifier.
        """
        if logical == "manifest" and prefix.startswith(b"\x04\x22\x4d\x18"):
            return "lz4_fast_manifest_metadata"
        if logical == "shadervariantinfos" and prefix.startswith(b"s:"):
            return "shader_variant_text_metadata"
        if logical == "buildlogtep.json" and prefix.lstrip().startswith(b"{"):
            return "build_log_json_metadata"
        return None

    def _index(self):
        ab = self.root / "game" / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"
        entries = json.loads((ab / "merge.json").read_text(encoding="utf-8"))
        manifest_path = self.root / "inspect" / "baseline_manifest.json"
        baseline = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_merge = baseline.get("source_merge", {}).get("sha256")
        if source_merge and sha256((ab / "merge.json").read_bytes()) != source_merge:
            raise BuildVerificationError("baseline merge changed before external CAB indexing")
        by_file = defaultdict(list)
        for entry in entries:
            relative = PurePosixPath(entry["m"].replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                raise BuildVerificationError("baseline merge physical path escapes ab")
            by_file[str(relative)].append(entry)
        index = defaultdict(list)
        for relative, grouped in by_file.items():
            physical = ab / relative
            if not physical.resolve().is_relative_to(ab.resolve()):
                raise BuildVerificationError("baseline merge physical target escapes ab")
            grouped.sort(key=lambda entry: int(entry["s"]))
            physical_size = physical.stat().st_size
            offsets = sorted(set(int(entry["s"]) for entry in grouped))
            end_by_start = {start: offsets[position + 1] if position + 1 < len(offsets) else physical_size
                            for position, start in enumerate(offsets)}
            aliases = defaultdict(list)
            for entry in grouped:
                aliases[int(entry["s"])].append(entry["r"])
            with physical.open("rb") as stream:
                seen = set()
                for entry in grouped:
                    start = int(entry["s"])
                    if start in seen:
                        continue
                    seen.add(start)
                    length = end_by_start[start] - start
                    if start < 0 or length <= 0 or start + length > physical_size:
                        raise BuildVerificationError(f"invalid baseline merge slice bounds: {entry['r']}")
                    stream.seek(start)
                    prefix = _read(stream, min(32, length))
                    if not prefix.startswith(b"UnityFS\0"):
                        kinds = [self._raw_metadata_kind(logical, prefix) for logical in aliases[start]]
                        if not kinds or any(kind is None for kind in kinds):
                            raise BuildVerificationError(f"unrecognized non-UnityFS baseline segment {aliases[start]} "
                                                         f"at {relative}@{start}: {prefix[:16].hex()}")
                        self.non_bundle_segments.append({"logical_names": aliases[start], "physical": relative,
                            "offset": start, "bytes": length, "classifications": kinds,
                            "scope": "source metadata format classified; contains no indexable CAB"})
                        continue
                    directory = unityfs_directory(stream, start, length, exact=False)
                    self.indexed_bundles += 1
                    for node in directory["nodes"]:
                        cab = _cab_name(node["path"])
                        if cab.startswith("cab-") and not cab.endswith((".ress", ".resource")):
                            index[cab].append((str(physical), start, directory["length"]))
        self.index = index

    def resolve(self, external):
        cab = _cab_name(external.path)
        if cab in self.staged:
            return self.staged[cab]
        if cab in self.cache:
            return self.cache[cab]
        if cab in {"unity_builtin_extra", "unity default resources"}:
            self.builtin_unchecked.add(cab)
            return None
        if self.index is None:
            self._index()
        candidates = self.index.get(cab, [])
        if len(candidates) != 1:
            raise BuildVerificationError(f"external CAB {external.path!r} has {len(candidates)} baseline targets")
        physical, start, length = candidates[0]
        with open(physical, "rb") as stream:
            stream.seek(start)
            raw = _read(stream, length)
        import UnityPy
        env = UnityPy.load(raw)
        if self.generator is not None:
            env.typetree_generator = self.generator
        targets = [file for file in _serialized_files(env) if _cab_name(file.name) == cab]
        if len(targets) != 1:
            raise BuildVerificationError(f"external CAB {cab} cannot be loaded uniquely")
        target = targets[0]
        _object_directory(target)
        self.cache[cab] = target
        return target

    def validate_pptrs(self, tree, assets, label):
        local, external, null = 0, 0, 0
        for path, value in _walk(tree):
            if not {"m_FileID", "m_PathID"} <= set(value):
                continue
            file_id, path_id = value["m_FileID"], value["m_PathID"]
            if type(file_id) is not int or type(path_id) is not int or file_id < 0:
                raise BuildVerificationError(f"{label}{path}: invalid PPtr integer fields")
            if not path_id:
                null += 1
                continue
            if file_id == 0:
                if path_id not in assets.objects:
                    raise BuildVerificationError(f"{label}{path}: dangling local PPtr {path_id}")
                local += 1
            else:
                if file_id > len(assets.externals):
                    raise BuildVerificationError(f"{label}{path}: external file index {file_id} is out of range")
                target = self.resolve(assets.externals[file_id - 1])
                if target is not None:
                    if path_id not in target.objects:
                        raise BuildVerificationError(f"{label}{path}: dangling external PPtr {file_id}:{path_id}")
                    self.checked += 1
                    external += 1
        return {"local": local, "external": external, "null": null}


def validate_manifest_additions(additions, output_paths):
    if not isinstance(additions, dict) or set(additions) - {"names", "entries", "guids", "guid"}:
        raise BuildVerificationError("manifest additions must use names/entries/guids")
    for key in ("names", "entries", "guids"):
        if not isinstance(additions.get(key, []), list):
            raise BuildVerificationError(f"manifest additions {key} is not a list")
    names = additions.get("names", [])
    def valid_name(name):
        return isinstance(name, str) and bool(name) and not name.endswith(".ab") and not name.startswith("/") and ".." not in name.split("/") and "\\" not in name and ":" not in name
    if any(not valid_name(name) for name in names) or len(names) != len(set(names)):
        raise BuildVerificationError("manifest additions contain invalid or duplicate names")
    absent = [name for name in names if name + ".ab" not in output_paths]
    if absent:
        raise BuildVerificationError(f"new manifest names have no staged bundle: {absent[:8]}")
    seen = set()
    for entry in additions.get("entries", []):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise BuildVerificationError("manifest dependency entry must be a pair")
        name, dependencies = entry
        if not valid_name(name) or name not in names or name in seen or not isinstance(dependencies, list) or any(not valid_name(dep) for dep in dependencies):
            raise BuildVerificationError(f"invalid/duplicate manifest dependency entry {name!r}")
        seen.add(name)
    if set(names) != seen:
        raise BuildVerificationError("new manifest names do not all have dependency entries")
    guid_pairs = []
    for entry in additions.get("guids", []):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise BuildVerificationError("manifest GUID entry must be a pair")
        name, guid = entry
        if name not in names or not isinstance(guid, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", guid):
            raise BuildVerificationError(f"invalid manifest GUID for {name!r}")
        guid_pairs.append((name, guid.lower()))
    if len(guid_pairs) != len(set(guid_pairs)) or len({guid for _, guid in guid_pairs}) != len(guid_pairs):
        raise BuildVerificationError("duplicate manifest GUID additions")
    return {"names": names, "entries": additions.get("entries", []), "guids": additions.get("guids", [])}


def _text_payload(obj):
    return obj.read().m_Script.encode("utf-8", "surrogateescape")


def _noah_xor(payload, key):
    digits = key.to_bytes(4, "little")
    return bytes(byte ^ digits[(index + (index >> 2)) & 3] for index, byte in enumerate(payload))


def _verify_payload(root, relative, text_assets, schema, js_keys):
    logical = relative.removesuffix(".ab")
    if relative.startswith(("data/xlsx/", "data/xlsxfixed/")):
        fixed = relative.startswith("data/xlsxfixed/")
        candidates = [name for name in schema if ("data/xlsxfixed/" + name.lower() + "wrap.ab" if name.endswith("FixedPoint")
                       else "data/xlsx/" + name.lower() + ".ab") == relative]
        if len(candidates) != 1:
            raise BuildVerificationError(f"{relative}: cannot map bundle uniquely to a table schema")
        cls = candidates[0]
        name = cls.removesuffix("FixedPoint") if fixed else cls
        expected_name = name + "FixedPointWrap" if fixed else name
        objects = [obj for obj in text_assets if obj.read().m_Name == expected_name]
        if len(objects) != 1:
            raise BuildVerificationError(f"{relative}: expected exactly one TextAsset named {expected_name}")
        current = json.loads((root / "decoded" / "tables" / (name + ".json")).read_text(encoding="utf-8"))
        original = json.loads((root / "decoded" / "tables" / (name + ".json.orig")).read_text(encoding="utf-8"))
        expected = expected_fixed_rows(current, original,
            (root / "extracted_raw" / "data" / "xlsxfixed" / (name + "FixedPointWrap.bin")).read_bytes(), name, schema) if fixed else current
        return {"kind": "fixed_table" if fixed else "table", **validate_table_payload(_text_payload(objects[0]), expected, cls, schema, len(original))}
    if relative.startswith("data/js/"):
        expected_paths = [path for path in (root / "decoded" / "data" / "js").rglob("*.js")
                          if ("data/js/" + path.relative_to(root / "decoded" / "data" / "js").as_posix().removesuffix(".js")).lower() == logical]
        if len(expected_paths) != 1:
            raise BuildVerificationError(f"{relative}: cannot uniquely map decoded JS module")
        path = expected_paths[0]
        key_name = "data/js/" + path.relative_to(root / "decoded" / "data" / "js").as_posix().removesuffix(".js")
        matching = [obj for obj in text_assets if obj.read().m_Name.lower() == path.stem.lower()]
        if len(matching) != 1:
            raise BuildVerificationError(f"{relative}: expected one JS TextAsset {path.stem}")
        payload = _text_payload(matching[0])
        encrypted = payload.startswith(b"NOAH")
        if encrypted:
            key = js_keys.get(key_name)
            if key is None:
                raise BuildVerificationError(f"{relative}: NOAH key is missing")
            payload = _noah_xor(payload[4:], int(key, 16))
        if payload != path.read_bytes():
            raise BuildVerificationError(f"{relative}: JS payload does not equal composed decoded source")
        return {"kind": "js", "bytes": len(payload), "sha256": sha256(payload), "noah": encrypted, "semantic_roundtrip": "passed"}
    return None


def verify_build(root, output, build_id, typetree_generator=None):
    """Return a JSON report or raise; caller writes _verification.json on success."""
    if Path(output).is_symlink():
        raise BuildVerificationError("staged output root must not be a symlink")
    root, output = Path(root).resolve(), Path(output).resolve()
    baseline = validate_baseline(root, str(build_id))
    build_meta = json.loads((output / "_build.json").read_text(encoding="utf-8"))
    if str(build_meta.get("gameBuild")) != str(build_id):
        raise BuildVerificationError("staged _build.json targets a different game build")
    schema = json.loads((root / "inspect" / "proto_schema.json").read_text(encoding="utf-8"))
    js_keys = json.loads((root / "inspect" / "js_keys.json").read_text(encoding="utf-8"))
    import UnityPy
    files, bundles, staged, environments = [], [], {}, []
    metadata_hashes = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise BuildVerificationError(f"staged output contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        if relative == "_verification.json":
            continue
        raw = path.read_bytes()
        record = {"path": relative, "sha256": sha256(raw), "bytes": len(raw)}
        if path.name.startswith("_"):
            if relative not in {"_build.json", "_manifest_add.json"}:
                raise BuildVerificationError(f"unexpected staged metadata {relative}")
            metadata_hashes[relative] = record["sha256"]
            record["kind"] = "metadata"
            files.append(record)
            continue
        if not relative.endswith(".ab"):
            raise BuildVerificationError(f"staged resource is not an AssetBundle: {relative}")
        directory = unityfs_directory(io.BytesIO(raw), length=len(raw))
        try:
            env = UnityPy.load(raw)
            if typetree_generator is not None:
                env.typetree_generator = typetree_generator
            assets_files = list(_serialized_files(env))
            if not assets_files:
                raise BuildVerificationError(f"{relative}: no serialized asset file loaded")
            for assets in assets_files:
                _object_directory(assets)
                cab = _cab_name(assets.name)
                if cab in staged:
                    raise BuildVerificationError(f"duplicate staged serialized/CAB name {assets.name}")
                staged[cab] = assets
        except Exception as ex:
            raise BuildVerificationError(f"{relative}: UnityPy resource read failed: {ex}") from ex
        environments.append(env)  # keep object readers/dependency ownership alive
        record.update({"kind": "bundle", "unityfs": directory, "serialized_files": len(assets_files),
                       "objects": sum(len(assets.objects) for assets in assets_files)})
        files.append(record)
        bundles.append((record, assets_files))
    output_paths = {record["path"] for record, _ in bundles}
    additions_path = output / "_manifest_add.json"
    additions = validate_manifest_additions(json.loads(additions_path.read_text(encoding="utf-8")), output_paths) if additions_path.exists() else {"names": [], "entries": [], "guids": []}
    resolver = ExternalResolver(root, staged, typetree_generator)
    for record, assets_files in bundles:
        record["pointers"] = {"local": 0, "external": 0, "null": 0}
        record["managed"] = {"definitions": 0, "positive_id_occurrences": 0}
        guid_references = set()
        text_assets = []
        for assets in assets_files:
            for obj in assets.objects.values():
                label = f"{record['path']}::{assets.name}::{obj.path_id}"
                try:
                    tree = obj.read_typetree(check_read=True)
                    pptrs = resolver.validate_pptrs(tree, assets, label)
                    managed = validate_managed_references(tree, label)
                except Exception as ex:
                    raise BuildVerificationError(f"{label}: object validation failed: {ex}") from ex
                for key, value in pptrs.items():
                    record["pointers"][key] += value
                for key, value in managed.items():
                    record["managed"][key] += value
                for _, value in _walk(tree):
                    if {"_guid0", "_guid1"} <= set(value):
                        a, b = value["_guid0"], value["_guid1"]
                        if type(a) is not int or type(b) is not int or not (0 <= a < 1 << 64 and 0 <= b < 1 << 64):
                            raise BuildVerificationError(f"{label}: invalid managed asset GUID")
                        if a or b:
                            guid_references.add(struct.pack("<QQ", a, b).hex())
                if obj.type.name == "TextAsset":
                    text_assets.append(obj)
        record["guid_references"] = sorted(guid_references)
        payload = _verify_payload(root, record["path"], text_assets, schema, js_keys)
        if payload is not None:
            record["payload"] = payload
    return {"format": 1, "status": "passed", "build_id": str(build_id), "files": files,
            "metadata_hashes": metadata_hashes, "bundle_count": len(bundles),
            "baseline_manifest_sha256": sha256((root / "inspect" / "baseline_manifest.json").read_bytes()),
            "baseline_build_id": baseline["build_id"], "manifest_additions": additions,
            "external_pointers": {"checked": resolver.checked, "lazy_loaded_cabs": len(resolver.cache),
                                  "header_indexed_bundles": resolver.indexed_bundles,
                                  "non_bundle_source_segments": resolver.non_bundle_segments,
                                  "builtin_targets_not_object_checked": sorted(resolver.builtin_unchecked)},
            "scope": {"bundle_readback": "passed", "local_pptr": "passed", "managed_rid": "passed",
                      "table_js_payload": "passed", "external_pptr": "checked except listed Unity builtin targets",
                      "cross_manifest_dependencies_and_guids": "caller must validate against pristine manifest",
                      "runtime_game_behavior": "not tested"}}
