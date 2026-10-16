"""Read-only structure check; never imports or runs code from the Zenith ZIP."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import lz4.frame


ROOT = Path(__file__).resolve().parents[1]
GAME = Path(r"E:\SteamLibrary\steamapps\common\BlazblueEntropyEffect")
SOURCE = Path(r"C:\Users\MECHREVO\Downloads\ZenithTerminal-0.3.0-alpha (1).zip")
AB = GAME / "BlazblueEntropyEffect_Data" / "StreamingAssets" / "ab"


def hash_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_manifest(raw: bytes) -> tuple[list[str], list, list, dict]:
    lines = raw.decode("utf-8").splitlines()
    if lines[0] != "FastManifest V3":
        raise ValueError("Unexpected manifest signature")
    name_count = int(lines[1][2:])
    names = lines[2 : 2 + name_count]
    cursor = 2 + name_count
    sections = []
    counts = []
    for _ in range(2):
        if not lines[cursor].startswith("N:"):
            raise ValueError("Missing manifest section marker")
        counts.append(int(lines[cursor][2:]))
        cursor += 1
        records = []
        while cursor < len(lines) and not lines[cursor].startswith("N:") and lines[cursor] != "----":
            line = lines[cursor]
            if line.startswith(" "):
                if not records:
                    raise ValueError("Value without a manifest record")
                records[-1][1].append(line.strip())
            else:
                records.append([line, []])
            cursor += 1
        sections.append(records)
    return names, sections[0], sections[1], {
        "declared_names": name_count,
        "declared_dependency_records": counts[0],
        "declared_guid_records": counts[1],
        "has_end_marker": cursor < len(lines) and lines[cursor] == "----",
    }


def main() -> None:
    merge = json.loads((AB / "merge.json").read_text("utf-8-sig"))
    manifest = lz4.frame.decompress((AB / "manifest").read_bytes())
    names, entries, guids, declared = parse_manifest(manifest)
    logical = {row["r"] for row in merge}
    merged_names = {name.removesuffix(".ab") for name in logical}
    manifest_names = set(names)
    bad_indexes = []
    for section, records in (("dependencies", entries), ("guids", guids)):
        for key, values in records:
            if not 0 <= int(key, 16) < len(names):
                bad_indexes.append([section, key])
            if section == "dependencies":
                for value in values:
                    if not 0 <= int(value, 16) < len(names):
                        bad_indexes.append([section, key, value])

    with zipfile.ZipFile(SOURCE) as archive:
        schema = json.loads(archive.read("ZenithTerminal/Launcher/tools/schema/25627491/proto_schema_snapshot.json"))["schema"]
        descriptors = []
        for path in archive.namelist():
            if "/Interpreter/" in path or not path.endswith("/mod.json"):
                continue
            mod = json.loads(archive.read(path))
            content = mod.get("content", {})
            tables = list(content.get("tables", {}))
            scripts = {spec["file"].lower() + ".ab" for spec in content.get("js", [])}
            scripts.update(name.lower() + ".ab" for name in content.get("jsFiles", {}))
            clone_sources = {spec["from"].lower() + ".ab" for spec in content.get("bundleClones", [])}
            descriptors.append({
                "id": mod.get("id"),
                "source_path": path,
                "tables_checked": len(tables),
                "missing_table_bundles": [name for name in tables if "data/xlsx/" + name.lower() + ".ab" not in logical],
                "missing_schema_types": [name for name in tables if name not in schema],
                "js_modules_checked": len(scripts),
                "missing_js_bundles": sorted(scripts - logical),
                "bundle_clone_sources_checked": len(clone_sources),
                "bundle_clone_sources_absent_from_live_merge": sorted(clone_sources - logical),
            })

    result = {
        "scope": "read-only manifest/index/schema membership; no TextAsset decode, anchors, build, install or game test",
        "date": "2026-10-15 Asia/Shanghai",
        "game_root": str(GAME),
        "source_archive": str(SOURCE),
        "source_archive_sha256": hash_file(SOURCE),
        "manifest_sha256": hash_file(AB / "manifest"),
        "merge_sha256": hash_file(AB / "merge.json"),
        "manifest": {
            **declared,
            "parsed_names": len(names),
            "parsed_dependency_records": len(entries),
            "parsed_guid_records": len(guids),
            "duplicate_names": len(names) - len(manifest_names),
            "bad_indexes": bad_indexes,
            "merge_logical_count": len(merge),
            "merge_names_absent_from_manifest": sorted(merged_names - manifest_names),
            "manifest_names_without_merge_entry": sorted(manifest_names - merged_names),
        },
        "static_descriptor_membership": descriptors,
        "not_verified": [
            "Actual game table payload matches schema snapshot",
            "JS replacement anchors exist and are unique",
            "Generated Ruby descriptor and assets",
            "Full pipeline decode completeness and encode/decode equivalence",
            "Pristine Steam depot byte identity",
            "Installation, save backup/restore and runtime behavior",
        ],
    }
    destination = ROOT / "evidence" / "baseline_structure.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
