"""Source patch, or a gated local Yuwen Yi build/art delivery.

Never builds, installs, launches a game or reads private/save directories.
The character archive targets the existing fixed-path verified workbench;
it is not a standalone game or an arbitrary-path portable installer.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

import workbench as wb

ORIGINAL = Path(r"C:\Users\MECHREVO\Downloads\ZenithTerminal-0.3.0-alpha (1).zip")
EXPECTED = "b5b3c2548ab61259c6f757b0cbf450a1d3490345ae9172915a5d7a303c36e150"
MODS = ["bbee-sdk", "bbee-actors", "bbee-inspector", "framework-validation-probe", "char-yuwen-yi"]
TEXT = {".py", ".json", ".js", ".cjs", ".md", ".txt"}
SKIP = {"__pycache__", ".git", ".pytest_cache", "private", "game", "Interpreter", "saves", "test-saves"}
MAX_FILE, MAX_TOTAL = 256 * 1024 * 1024, 2 * 1024 * 1024 * 1024


def safe(path):
    path = Path(os.path.abspath(path))
    relative = path.relative_to(wb.ROOT)
    if any(part.casefold() in {p.casefold() for p in SKIP} for part in relative.parts) or path.name.casefold() == "juij_steam.json":
        raise ValueError("Forbidden delivery input: " + str(path))
    for item in [path, *path.parents]:
        if item.exists() and (item.is_symlink() or getattr(item.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Linked delivery input: " + str(item))
        if item == wb.ROOT:
            break
    return path


def files(area, suffixes):
    if not area.is_dir():
        raise ValueError("Required source directory missing: " + str(area))
    result = []
    for current, dirs, names in os.walk(safe(area), followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in dirs:
            safe(Path(current) / name)
        for name in sorted(names):
            if name == ".prepare-state.json" or name.startswith(".prepare-state.json."):
                continue
            path = safe(Path(current) / name)
            if path.suffix.lower() in suffixes:
                result.append(path)
    return result


def mod_folder(mid):
    found = [p for p in (wb.LAUNCHER / "shared" / mid, wb.LAUNCHER / "mods" / mid) if p.is_dir()]
    if len(found) != 1:
        raise ValueError("Missing/ambiguous selected mod: " + mid)
    return found[0]


def source_candidates():
    candidates = list(wb.LAUNCHER.glob("*.py"))
    candidates += list((wb.LAUNCHER / "tests").glob("*.py"))
    for mid in MODS:
        candidates += files(mod_folder(mid), TEXT)
    candidates += list((wb.LAUNCHER / "tools/bbtag").glob("*.py"))
    candidates += [wb.LAUNCHER / "tools" / "savefile.py", wb.LAUNCHER / "README.md",
                   wb.LAUNCHER / "compatibility-contracts.json", wb.LAUNCHER / "build-input-contracts.json",
                   wb.LAUNCHER / "mods" / "framework-validation-probe" / "mod.json",
                   wb.ROOT / "ZenithTerminal" / "Gui" / "zenith_gui" / "controller.py",
                   wb.ROOT / "ZenithTerminal" / "SETUP_GUIDE.md", wb.ROOT / "ZenithTerminal" / "WORKBENCH_FORK.json"]
    for area, pattern in (("scripts", "*.py"), ("docs", "*.md"), ("profiles", "*.json")):
        candidates += list((wb.ROOT / area).rglob(pattern))
    candidates += [wb.ROOT / name for name in ("README.md", ".gitignore", "dependencies.lock.json", "requirements.lock.txt", "requirements.typetree.lock.txt")]
    tool_root = wb.ROOT / "tools" / "Il2CppDumper-6.7.46"
    candidates += [tool_root / "Il2CppDumper" / "Program.cs", tool_root / "Il2CppDumper" / "Utils" / "PELoader.cs", wb.ROOT / "tools" / "NuGet.Config"]
    candidates += list(tool_root.glob("LICENSE*"))
    candidates += [wb.ROOT / "scripts/PACKAGING.md"]
    candidates += [wb.ROOT / "play-yuwen-yi.cmd"]
    return sorted({safe(path) for path in candidates})


def source_patch():
    if wb.sha(ORIGINAL) != EXPECTED:
        raise ValueError("Original source ZIP differs from reviewed input")
    candidates = source_candidates()
    destination = wb.ROOT / "delivery"
    destination.mkdir(exist_ok=True)
    records, diffs, payload = [], [], {}
    with zipfile.ZipFile(ORIGINAL) as original:
        original_names = set(original.namelist())
        for path in sorted(set(candidates)):
            relative = path.relative_to(wb.ROOT).as_posix()
            current = path.read_bytes()
            old = original.read(relative) if relative in original_names else b""
            if old == current:
                continue
            records.append({"path": relative, "status": "modified" if old else "added",
                            "old_sha256": hashlib.sha256(old).hexdigest() if old else None,
                            "sha256": hashlib.sha256(current).hexdigest(), "bytes": len(current)})
            payload[relative] = current
            diffs += difflib.unified_diff(old.decode("utf-8-sig").splitlines(keepends=True),
                                          current.decode("utf-8-sig").splitlines(keepends=True),
                                          fromfile="a/" + relative, tofile="b/" + relative)
    manifest = {"original_zip_sha256": EXPECTED, "scope": "source/test/config/documentation patch only", "files": records}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (destination / "source.patch").write_text("".join(diffs), "utf-8")
    archive = destination / "bbee-infrastructure-patch.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in payload.items():
            output.writestr(name, data)
        output.write(destination / "manifest.json", "PATCH_MANIFEST.json")
        output.write(destination / "source.patch", "SOURCE.patch")
    wb.write_json(destination / "receipt.json", {"files": len(records), "archive_sha256": wb.sha(archive), "bytes": archive.stat().st_size})
    print(f"Source patch exported: {len(records)} files, {archive.stat().st_size} bytes")


def read_json(path):
    path = safe(path)
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Missing/oversized delivery receipt: " + str(path))
    return json.loads(path.read_text("utf-8"))


def character_gate():
    area = wb.EVIDENCE / "yuwen-yi"
    engineering = read_json(area / "engineering-acceptance.json")
    required = {"complete-build", "repeat-complete-build", "install-complete", "update-complete", "withdraw-character", "uninstall", "working-game-restored", "immutable-baseline-unchanged", "source-game-unchanged"}
    profile_path = wb.ROOT / "profiles/yuwen-yi.json"
    if engineering.get("status") != "passed" or engineering.get("build_id") != wb.BUILD or not required.issubset(engineering.get("phases", [])):
        raise ValueError("The complete character engineering/transaction batch has not passed")
    if read_json(profile_path).get("enabled") != MODS or engineering.get("profile", {}).get("sha256") != wb.sha(profile_path):
        raise ValueError("Character engineering receipt does not bind this exact profile")
    output = wb.LAUNCHER / "patch_out"
    build = read_json(output / "_build.json")
    verification = read_json(output / "_verification.json")
    if build.get("gameBuild") != wb.BUILD or list(build.get("mods", {})) != MODS or verification.get("status") != "passed" or verification.get("build_id") != wb.BUILD:
        raise ValueError("Staged output is not the successful complete Yuwen Yi build")
    if verification.get("metadata_hashes", {}).get("_build.json") != wb.sha(output / "_build.json"):
        raise ValueError("Native verification does not bind the current build record")
    expected = {item["path"]: item["sha256"] for item in verification["files"]}
    actual = {p.relative_to(output).as_posix(): wb.sha(p) for p in files(output, {".ab", ".json"}) if p.name != "_verification.json"}
    if actual != expected:
        raise ValueError("Staged native output/metadata differs from complete verification")
    if {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} != set(expected) | {"_verification.json"}:
        raise ValueError("Unexpected files in the staged native delivery")
    for name, digest in verification["metadata_hashes"].items():
        if name not in {"_build.json", "_manifest_add.json"} or actual.get(name) != digest:
            raise ValueError("Unbound staged manifest metadata")
    repro = read_json(area / "reproducibility.json")
    bundles = {name: digest for name, digest in actual.items() if not Path(name).name.startswith("_")}
    if repro.get("status") != "passed" or repro.get("changed") != [] or repro.get("resource_hashes") != bundles or repro.get("resource_count") != len(bundles):
        raise ValueError("Character repeat-build receipt does not bind these native resources")
    sys.path.insert(0, str(wb.LAUNCHER))
    from build_provenance import capture, canonical_sha
    mods = {}
    for mid in MODS:
        folder = mod_folder(mid)
        descriptor = read_json(folder / "mod.json")
        if build["descriptors"].get(mid) != wb.sha(folder / "mod.json"):
            raise ValueError("Character descriptor changed after successful build")
        mods[mid] = {**descriptor, "_dir": str(folder)}
    current = capture(wb.LAUNCHER, MODS, mods, wb.BUILD)
    if current != build.get("input_provenance") or canonical_sha(current) != build.get("input_provenance_sha256"):
        raise ValueError("Character recursive source/art input closure changed after successful build")
    return area, output, build, verification


def runtime_status(area, build, path=None):
    path = safe(path) if path else area / "character-runtime-acceptance.json"
    result = {"status": "pending", "actor_id": 200901, "scope": "No character-specific runtime acceptance supplied; platform runtime receipts are not character evidence."}
    if not path.is_file():
        return result
    value = read_json(path)
    if value.get("actor_id") != 200901 or value.get("build_record_sha256") != wb.sha(wb.LAUNCHER / "patch_out/_build.json") or value.get("profile_sha256") != wb.sha(wb.ROOT / "profiles/yuwen-yi.json"):
        raise ValueError("Runtime receipt is generic, stale or not bound to this character/build/profile")
    status = value.get("status")
    if status not in {"passed", "failed", "pending"}:
        raise ValueError("Unknown character runtime acceptance status")
    checks = value.get("checks", {})
    if not isinstance(checks, dict):
        raise ValueError("Character runtime checks must be a named public status map")
    if status == "passed" and any(checks.get(k) != "passed" for k in ("character_selection", "combat", "reopen")):
        raise ValueError("Passed character runtime receipt must include selection/combat/reopen evidence")
    return {"status": status, "actor_id": 200901, "receipt_sha256": wb.sha(path),
            "build_record_sha256": value["build_record_sha256"], "profile_sha256": value["profile_sha256"],
            "checks": {k: checks.get(k, "pending") for k in ("character_selection", "combat", "reopen")},
            "scope": "Character-specific declared runtime evidence; raw logs/private save data are not packaged."}


def character_package(runtime_receipt=None):
    area, output, build, verification = character_gate()
    runtime = runtime_status(area, build, runtime_receipt)
    selected = {}
    def add(path, digest=None):
        path = safe(path)
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError("Missing/oversized delivery input: " + str(path))
        relative = path.relative_to(wb.ROOT).as_posix()
        current = wb.sha(path)
        if digest and current != digest:
            raise ValueError("Frozen delivery input changed: " + relative)
        selected[relative] = {"path": path, "sha256": current, "bytes": path.stat().st_size}
    for path in source_candidates():
        add(path)
    for path in files(mod_folder("char-yuwen-yi") / "assets", {".png", ".json"}):
        add(path)
    for path in files(output, {".ab", ".json"}):
        add(path)
    for name in ("engineering-acceptance.json", "delivery-closure-acceptance.json", "reproducibility.json", "source-compilation.json", "regression-summary.json", "native-events.json", "body-reference-validation.json", "portrait-reference-validation.json", "authored-poses-visual-review.json", "complete-art-visual-review.json"):
        add(area / name)
    production_path = mod_folder("char-yuwen-yi") / "assets/prepared/production-manifest.json"
    production = read_json(production_path)
    if production.get("kind") != "yuwen_yi_production_art":
        raise ValueError("Complete frozen production art is missing")
    manifests_seen = set()
    def reference(path, digest):
        path = safe(path)
        if not path.is_relative_to(wb.ROOT / "references/wandering-sword"):
            raise ValueError("Reference dependency escapes the reviewed game-reference root")
        add(path, digest)
        if path in manifests_seen:
            return
        manifests_seen.add(path)
        data = read_json(path)
        source_sha = data.get("source", {}).get("source_pak_sha256", data.get("inputs", {}).get("source_pak_sha256"))
        if source_sha != production["source_pak_sha256"]:
            raise ValueError("Reference manifest changed source PAK identity")
        for item in data.get("outputs", []):
            rel = item["file"]
            if "\\" in rel or ":" in rel or ".." in Path(rel).parts or Path(rel).is_absolute():
                raise ValueError("Reference output path escape")
            add(path.parent / rel, item["sha256"])
        for item in data.get("members", []):
            rel = item["output_relative"]
            if rel != "raw/" + item["member"] or ".." in Path(rel).parts or "\\" in rel or ":" in rel:
                raise ValueError("Raw reference member path escape")
            add(path.parent / rel, item["decoded_sha256"])
        for key in ("root_mapping_inputs", "inputs"):
            dependency = data.get(key, {})
            if dependency.get("selected_manifest"):
                reference(Path(dependency["selected_manifest"]), dependency["selected_manifest_sha256"])
    for key in ("body_manifest", "portrait_manifest"):
        reference(Path(production[key]), production[key + "_sha256"])
    for key in ("authored_manifest", "visual_review", "ui_manifest"):
        add(Path(production[key]), production[key + "_sha256"])
    review = read_json(Path(production["visual_review"]))
    for item in review["evidence"]:
        proof = safe(Path(item["file"]))
        if not (proof.is_relative_to(area) or proof.is_relative_to(mod_folder("char-yuwen-yi") / "assets")):
            raise ValueError("Visual review evidence escapes public character/art roots")
        add(proof, item["sha256"])
    # Reproduction needs the actual original texture/Cascade source closure,
    # not just the final adapted PNGs already selected from assets above.
    vfx_path = safe(Path(production["original_vfx_manifest"]))
    if vfx_path != mod_folder("char-yuwen-yi") / "assets/original-vfx/adapted/manifest.json":
        raise ValueError("Unexpected original VFX manifest location")
    add(vfx_path, production["original_vfx_manifest_sha256"])
    vfx = read_json(vfx_path)
    if vfx.get("kind") != "yuwen_original_texture_vfx_adaptation" or vfx.get("source_pak_sha256") != production["source_pak_sha256"]:
        raise ValueError("Original VFX source identity differs")
    reference(Path(vfx["reference_manifest"]), vfx["reference_manifest_sha256"])
    contract_path = safe(Path(vfx["source_contract"]))
    if contract_path != vfx_path.parent.parent / "source-contract.json":
        raise ValueError("Original VFX source contract location differs")
    add(contract_path, vfx["source_contract_sha256"])
    contract = read_json(contract_path)
    if contract.get("source_manifest") != vfx["reference_manifest"] or contract.get("source_manifest_sha256") != vfx["reference_manifest_sha256"]:
        raise ValueError("Original VFX contract does not bind the selected reference")
    add(contract_path.with_name("source_contract.py"), contract["source_code_sha256"])
    add(Path(vfx["producer"]), vfx["producer_sha256"])
    for item in vfx["outputs"]:
        relative = item["file"]
        if "\\" in relative or ":" in relative or ".." in Path(relative).parts or Path(relative).is_absolute():
            raise ValueError("Adapted VFX output path escape")
        add(vfx_path.parent / relative, item["sha256"])
    add(Path(production["contract_file"]), production["contract_sha256"])
    add(wb.LAUNCHER / "tools/bbtag/bbtag_rig.py", production["rig_builder_sha256"])
    for item in production["frames"].values():
        add(Path(item["file"]), item["sha256"])
    ui = read_json(Path(production["ui_manifest"]))
    add(Path(ui["placement_provenance"]["file"]), ui["placement_provenance"]["sha256"])
    for item in ui["textures"] + ui["spec"]["potentialAtlas"]["sprites"] + [ui["atlas_preview"]]:
        add(Path(item["file"]), item["sha256"])
    if sum(item["bytes"] for item in selected.values()) > MAX_TOTAL:
        raise ValueError("Local delivery exceeds bounded archive input cap")
    records = [{"path": name, "sha256": item["sha256"], "bytes": item["bytes"]} for name, item in sorted(selected.items())]
    manifest = {"format": 1, "scope": "Local Yuwen Yi native resources, frozen art/reference closure and reproduction source overlay",
                "workspace_root": str(wb.ROOT), "portable": False, "game_build": wb.BUILD, "actor_id": 200901,
                "requires": ["Existing verified physical BBEE workbench at the exact workspace_root", "Existing immutable baseline and extracted schema", "Existing pinned Python/Node/dependencies"],
                "excluded": ["Game copy and Steam installation", "Interpreter/binary dependencies", "Private state, credentials, proxy config and all saves"],
                "engineering": "passed", "runtime": runtime, "profile_sha256": wb.sha(wb.ROOT / "profiles/yuwen-yi.json"),
                "build_record_sha256": wb.sha(output / "_build.json"), "verification_sha256": wb.sha(output / "_verification.json"), "files": records}
    destination = safe(wb.ROOT / "delivery")
    destination.mkdir(exist_ok=True)
    stem = "bbee-yuwen-yi-local-" + manifest["build_record_sha256"][:16]
    archive = destination / (stem + ".zip")
    pending = destination / (stem + ".zip.pending")
    if archive.exists() or pending.exists():
        raise ValueError("Character delivery already exists; refusing overwrite")
    try:
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with zipfile.ZipFile(pending, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, item in sorted(selected.items()):
                data = item["path"].read_bytes()
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("Delivery input changed while packaging")
                zipped.writestr(name, data)
            zipped.writestr("LOCAL_DELIVERY_MANIFEST.json", manifest_bytes)
        with zipfile.ZipFile(pending) as zipped:
            if set(zipped.namelist()) != set(selected) | {"LOCAL_DELIVERY_MANIFEST.json"}:
                raise ValueError("Archive inventory differs from delivery manifest")
            if zipped.read("LOCAL_DELIVERY_MANIFEST.json") != manifest_bytes:
                raise ValueError("Archive manifest readback differs from frozen records")
            for name, item in selected.items():
                with zipped.open(name) as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError("Archive input readback failed")
        # All source/native inputs must still have the exact successful closure.
        character_gate()
        os.rename(pending, archive)
        receipt = {"archive": archive.name, "archive_sha256": wb.sha(archive), "bytes": archive.stat().st_size,
                   "files": len(records), "engineering": "passed", "runtime": runtime, "game_launch_performed": False}
        wb.write_json(destination / (stem + ".receipt.json"), receipt)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    finally:
        if pending.exists():
            safe(pending).unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", action="store_true", help="Gated local character archive; never builds or installs")
    parser.add_argument("--runtime-receipt", type=Path, help="Explicit character-specific public runtime receipt")
    args = parser.parse_args()
    if args.runtime_receipt and not args.character:
        parser.error("--runtime-receipt requires --character")
    character_package(args.runtime_receipt) if args.character else source_patch()


if __name__ == "__main__":
    main()
