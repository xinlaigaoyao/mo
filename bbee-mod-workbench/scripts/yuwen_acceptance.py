"""Concentrated acceptance of the complete, frozen Yuwen Yi character batch.

The platform's earlier acceptance remains a separate historical receipt. This
entry point consumes reviewed art, validates the immutable baseline, and runs
one complete character build/repeat/transaction sequence. Runtime gameplay is
recorded separately; a successful build never implies a playable acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import uuid

import workbench as wb
sys.path.insert(0, str(wb.LAUNCHER))
from install_transaction import FileChange, apply_transaction, checked_path, recover_transactions
from safe_install import require_closed
from save_safety import ensure_private_directory

AREA = wb.EVIDENCE / "yuwen-yi"
CHARACTER = wb.LAUNCHER / "mods/char-yuwen-yi"
PROFILE = wb.ROOT / "profiles/yuwen-yi.json"
SCRIPT_KEY = "scripts/yuwen_acceptance.py"
INDEX_DIRECTORY = "BlazblueEntropyEffect_Data/StreamingAssets/ab"
RESTORATION_PREFIX = [
    "validate-frozen-baseline", "consolidated-source-compilation", "prepare-reviewed-complete-art",
    "prepare-complete-character", "integrated-regression", "character-native-event-contracts",
    "complete-build", "repeat-complete-build", "install-complete", "update-complete",
    "withdrawal-profile-build", "withdraw-character", "uninstall",
]


def local_path(path):
    path = checked_path(path)
    if not path.is_relative_to(wb.ROOT):
        raise ValueError("Restoration path is outside the workbench")
    return path


def read_json(path):
    path = local_path(path)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Restoration receipt is missing or oversized")
    return json.loads(path.read_text("utf-8"))


def record_file(path):
    path = local_path(path)
    return {"path": path.relative_to(wb.ROOT).as_posix(), "sha256": wb.sha(path)}


def source_paths():
    """The same Python source set as the concentrated compiler, without compiling."""
    paths = list(wb.LAUNCHER.glob("*.py"))
    for directory in (wb.LAUNCHER / "mods", wb.LAUNCHER / "shared", wb.LAUNCHER / "tests",
                      wb.LAUNCHER / "tools", wb.LAUNCHER.parent / "Gui", wb.ROOT / "scripts"):
        paths.extend(directory.rglob("*.py"))
    return {p.relative_to(wb.ROOT).as_posix(): local_path(p) for p in paths if "__pycache__" not in p.parts}


def verify_source_snapshot(compiled, allow_orchestrator_change=False):
    paths = source_paths()
    if compiled.get("status") != "passed" or set(paths) != set(compiled.get("files", {})):
        raise ValueError("Python source file set differs from the completed compilation")
    for name, path in paths.items():
        if allow_orchestrator_change and name == SCRIPT_KEY:
            continue
        if wb.sha(path) != compiled["files"][name]:
            raise ValueError("A previously accepted source changed: " + name)


def archive_attempt(receipt):
    """Preserve the failed receipt and exact logs before any continuation writes."""
    receipt = local_path(receipt)
    old_hash = wb.sha(receipt)
    destination = local_path(AREA / "history" / (old_hash + ".json"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    artifacts = list(wb.EVIDENCE.glob("yuwen-*.json")) + list(wb.EVIDENCE.glob("yuwen-*.log"))
    artifacts.append(wb.EVIDENCE / "cleanup.json")
    artifacts += [AREA / name for name in ("native-events.json", "native-events.log", "source-compilation.json",
                  "regression-summary.json", "reproducibility.json", "framework-regression-inputs.json",
                  "framework-regression-reuse.json", "index-pristine-archive.json")]
    archived = {}
    for source, target in [(receipt, destination)] + [
            (p, destination.with_suffix("") / p.name) for p in artifacts if p.is_file()]:
        source, target = local_path(source), local_path(target)
        digest = wb.sha(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and wb.sha(target) != digest:
            raise ValueError("Previous character attempt archive changed")
        if not target.exists():
            shutil.copy2(source, target)
        if wb.sha(target) != digest:
            raise ValueError("Previous character attempt archive differs")
        archived[source.name] = digest
    return {"sha256": old_hash, "archive": destination.relative_to(wb.ROOT).as_posix(), "artifacts": archived}


def verify_working_restored(record):
    manifest = read_json(wb.BASELINE / "manifest.json")
    game = local_path(wb.LAUNCHER / "game")
    expected = {item["path"] for item in manifest["files"]}
    actual = {local_path(path).relative_to(game).as_posix() for path in game.rglob("*")
              if path.is_file() and path.name not in wb.EXCLUDED_NAMES}
    if actual != expected:
        raise ValueError("Working game restored file set differs")
    for item in manifest["files"]:
        if wb.sha(local_path(game / item["path"])) != item["sha256"]:
            raise ValueError("Working game restoration differs: " + item["path"])
    if local_path(wb.LAUNCHER / "mods/installed.json").exists():
        raise ValueError("Uninstall left an installed record")
    record["restored_game_files"] = len(expected)
    record["restored_file_set_exact"] = True


def archive_owned_pristine_indices(record):
    """Archive verified task-copy indices, then transactionally remove only four files."""
    require_closed()
    if wb.BUILD != "25627491" or record.get("build_id") != wb.BUILD:
        raise ValueError("Pristine index cleanup is bound to build 25627491")
    if "uninstall" not in record.get("phases", []) or local_path(wb.LAUNCHER / "mods/installed.json").exists():
        raise ValueError("Pristine cleanup requires this task's completed uninstall")
    baseline = read_json(wb.BASELINE / "manifest.json")
    if baseline.get("build_id") != wb.BUILD:
        raise ValueError("Independent baseline build differs")
    game = local_path(wb.LAUNCHER / "game")
    expected = {item["path"]: item for item in baseline["files"]}
    owned = {INDEX_DIRECTORY + "/" + name + suffix
             for name in ("manifest", "merge.json") for suffix in (".orig", ".orig.build")}
    actual = {local_path(path).relative_to(game).as_posix() for path in game.rglob("*")
              if path.is_file() and path.name not in wb.EXCLUDED_NAMES}
    indices, copies = {}, {}
    for name in ("manifest", "merge.json"):
        relative = INDEX_DIRECTORY + "/" + name
        original = local_path(wb.BASELINE / "game" / relative)
        current = local_path(game / relative)
        backup = local_path(current.with_name(name + ".orig"))
        stamp = local_path(current.with_name(name + ".orig.build"))
        digest = expected[relative]["sha256"]
        if any(not p.is_file() or wb.sha(p) != digest for p in (original, current)):
            raise ValueError("A pristine index differs from the independent baseline: " + name)
        indices[relative] = digest
        copies[backup] = digest
        copies[stamp] = hashlib.sha256(wb.BUILD.encode("ascii")).hexdigest()
    ensure_private_directory(local_path(wb.PRIVATE))
    state = local_path(wb.PRIVATE / "transactions/yuwen-pristine-indices")
    pointer = record.get("pristine_index_archive")
    if pointer:
        if actual - owned != set(expected):
            raise ValueError("Pristine recovery found an unknown extra or missing baseline file")
        plan_path = local_path(wb.ROOT / pointer["path"])
        archive_root = local_path(wb.PRIVATE / "task-owned-index-backups" / wb.BUILD)
        if plan_path.name != "plan.json" or plan_path.parent.parent != archive_root or wb.sha(plan_path) != pointer["sha256"]:
            raise ValueError("Pristine recovery plan ownership/hash differs")
        recovery = read_json(plan_path)
        archive = plan_path.parent
        if recovery.get("schema") != 1 or recovery.get("build_id") != wb.BUILD or recovery.get("indices") != indices or recovery.get("baseline_manifest_sha256") != wb.sha(local_path(wb.BASELINE / "manifest.json")):
            raise ValueError("Pristine recovery plan baseline differs")
        if recovery.get("transaction_id") != archive.name or uuid.UUID(hex=archive.name).hex != archive.name:
            raise ValueError("Pristine recovery transaction ownership differs")
        bindings = recovery["files"]
        expected_bindings = [{"working": source.relative_to(game).as_posix(),
                              "archive": (archive / source.name).relative_to(wb.ROOT).as_posix(), "sha256": digest}
                             for source, digest in copies.items()]
        if bindings != expected_bindings:
            raise ValueError("Pristine recovery plan contains an unknown target/archive")
        for item in bindings:
            if wb.sha(local_path(wb.ROOT / item["archive"])) != item["sha256"]:
                raise ValueError("Private pristine recovery copy changed")
        # Recover only this four-file whitelist. Interrupted deletions roll back
        # before retry; a committed transaction is checked idempotently below.
        require_closed()
        recover_transactions(allowed_targets=list(copies), state_dir=state)
        after_recovery = {local_path(path).relative_to(game).as_posix() for path in game.rglob("*")
                          if path.is_file() and path.name not in wb.EXCLUDED_NAMES}
        if after_recovery not in (set(expected), set(expected) | owned):
            raise ValueError("Pristine recovery did not reach a complete original or committed state")
    else:
        if actual != set(expected) | owned:
            raise ValueError("Pristine cleanup requires exactly the four owned extra files and no missing baseline file")
        if any(not path.is_file() or wb.sha(local_path(path)) != digest for path, digest in copies.items()):
            raise ValueError("Pristine copy or exact build stamp differs")
        archive = local_path(wb.PRIVATE / "task-owned-index-backups" / wb.BUILD / uuid.uuid4().hex)
        archive.mkdir(parents=True, exist_ok=False)
        bindings = []
        for source, digest in copies.items():
            target = local_path(archive / source.name)
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if wb.sha(target) != digest or wb.sha(local_path(source)) != digest:
                raise ValueError("Private pristine index archive readback differs")
            bindings.append({"working": source.relative_to(game).as_posix(),
                             "archive": target.relative_to(wb.ROOT).as_posix(), "sha256": digest})
        recovery = {"schema": 1, "build_id": wb.BUILD, "status": "verified_archive_plan",
                    "transaction_id": archive.name,
                    "baseline_manifest_sha256": wb.sha(local_path(wb.BASELINE / "manifest.json")),
                    "indices": indices, "files": bindings}
        plan_path = local_path(archive / "plan.json")
        wb.write_json(plan_path, recovery)
        record["pristine_index_archive"] = record_file(plan_path)
        # Persist the immutable recovery-plan binding before the first deletion.
        wb.write_json(local_path(AREA / "engineering-acceptance.json"), record)

    def guard(event, index):
        if event in ("before_prepare", "before_apply", "before_commit"):
            require_closed()
            if local_path(wb.LAUNCHER / "mods/installed.json").exists():
                raise ValueError("Installed state appeared during pristine cleanup")
            for relative, digest in indices.items():
                if any(wb.sha(local_path(base / relative)) != digest for base in (game, wb.BASELINE / "game")):
                    raise ValueError("Pristine original index changed during cleanup")
            for item in bindings:
                if wb.sha(local_path(wb.ROOT / item["archive"])) != item["sha256"]:
                    raise ValueError("Private recovery copy changed during cleanup")

    guard("before_prepare", None)
    transaction = apply_transaction([
        FileChange(path, delete=True, expected_before_exists=True, expected_before_sha256=digest)
        for path, digest in copies.items()], allowed_targets=list(copies),
        state_dir=state, transaction_id=recovery["transaction_id"], fault=guard)
    if any(local_path(path).exists() for path in copies):
        raise ValueError("Pristine index cleanup left an owned backup file")
    result = {**recovery, "status": "archived_and_removed", "transaction": transaction,
              "immutable_plan": record_file(plan_path)}
    wb.write_json(local_path(archive / "receipt.json"), result)
    wb.write_json(local_path(AREA / "index-pristine-archive.json"), result)
    record["pristine_index_cleanup_result"] = record_file(AREA / "index-pristine-archive.json")


def verified_build_binding(directory, resources, old_record):
    directory = local_path(directory)
    verification = read_json(directory / "_verification.json")
    build = read_json(directory / "_build.json")
    if verification.get("status") != "passed" or verification.get("build_id") != wb.BUILD or build.get("gameBuild") != wb.BUILD:
        raise ValueError("Previous complete build is not verified for this build")
    if build.get("baseline_manifest_sha256") != old_record["baseline_manifest_sha256"] or verification.get("baseline_manifest_sha256") != old_record["baseline_manifest_sha256"]:
        raise ValueError("Previous build baseline binding differs")
    listed = {}
    for entry in verification["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry["path"] or ":" in entry["path"] or entry["path"] in listed:
            raise ValueError("Noncanonical previous build verification path")
        path = local_path(directory / entry["path"])
        if not path.is_file() or path.stat().st_size != entry["bytes"] or wb.sha(path) != entry["sha256"]:
            raise ValueError("Previous verified build file changed: " + entry["path"])
        listed[entry["path"]] = entry
    actual = {local_path(p).relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != set(listed) | {"_verification.json"} or inventory(directory) != resources:
        raise ValueError("Previous complete resource set differs from its reproducibility receipt")
    if {name: entry["sha256"] for name, entry in listed.items() if entry.get("kind") == "bundle"} != resources:
        raise ValueError("Strict bundle verification does not bind every repeated resource")
    for name, digest in verification["metadata_hashes"].items():
        if wb.sha(local_path(directory / name)) != digest:
            raise ValueError("Previous verified build metadata changed")
    from build_provenance import canonical_sha, capture
    order = old_record["profile"]["enabled"]
    if build.get("input_provenance_sha256") != canonical_sha(build["input_provenance"]):
        raise ValueError("Previous build provenance digest differs")
    mods = {}
    for mid in order:
        candidates = [p for p in (wb.LAUNCHER / "shared" / mid, wb.LAUNCHER / "mods" / mid) if (p / "mod.json").is_file()]
        if len(candidates) != 1:
            raise ValueError("Previous enabled descriptor is missing or ambiguous")
        folder = local_path(candidates[0])
        mods[mid] = {**read_json(folder / "mod.json"), "_dir": str(folder)}
    if capture(wb.LAUNCHER, order, mods, wb.BUILD) != build["input_provenance"]:
        raise ValueError("Accepted build inputs changed; restoration continuation cannot reuse the build")
    return {"build": record_file(directory / "_build.json"),
            "verification": record_file(directory / "_verification.json"), "resources": len(resources)}


def repeat_build_binding(resources, old_record, evidence_area=AREA):
    repeat = local_path(wb.ROOT / "builds/full-repeat")
    if repeat.exists():
        return {"scope": "repeat_files_read_back_now", **verified_build_binding(repeat, resources, old_record)}
    receipt_path = wb.EVIDENCE / "yuwen-repeat.json" if evidence_area == AREA else evidence_area / "yuwen-repeat.json"
    operation = read_json(receipt_path)
    log = local_path(operation["log"] if evidence_area == AREA else evidence_area / "yuwen-repeat.log")
    if operation.get("exit_code") != 0 or wb.sha(log) != operation["log_sha256"]:
        raise ValueError("The cleaned repeat build has no unchanged successful receipt/log")
    if operation.get("cwd") != str(wb.LAUNCHER) or operation.get("game_target") != str(wb.LAUNCHER / "game") or operation["command"][-2:] != [str(wb.LAUNCHER / "bbmod.py"), "build"]:
        raise ValueError("The cleaned repeat receipt is not the expected build operation")
    if log.stat().st_size > 16 * 1024 * 1024 or log.read_text("utf-8").splitlines()[-1] != "build OK -> " + str(repeat):
        raise ValueError("The repeat log does not confirm success at the expected repeat output")
    cleanup_path = wb.EVIDENCE / "cleanup.json" if evidence_area == AREA else evidence_area / "cleanup.json"
    cleanup = read_json(cleanup_path)
    if cleanup.get("status") != "passed" or "builds/full-repeat" not in {name.replace("\\", "/") for name in cleanup.get("removed", [])}:
        raise ValueError("Missing repeat output is not explained by recorded task-owned cleanup")
    return {"scope": "repeat_receipt_reused_after_owned_cleanup", "resources": len(resources),
            "receipt": record_file(receipt_path), "log": record_file(log),
            "cleanup": record_file(cleanup_path), "repeat_files_read_back_now": False,
            "basis": "Original completed repeat phase, unchanged successful output log, passed exact reproducibility hashes and current verified first-build bytes"}


def restoration_bindings(old, evidence_area=AREA):
    if old.get("status") != "failed" or old.get("build_id") != wb.BUILD or old.get("phases") != RESTORATION_PREFIX or old.get("error") != "Working game restored file set differs":
        raise ValueError("--finish-restoration requires the completed build/transaction attempt failing only its final working file set")
    require_closed()
    if local_path(wb.LAUNCHER / "mods/installed.json").exists():
        raise ValueError("Restoration continuation requires an uninstalled game")
    if old["profile"]["path"] != str(PROFILE) or wb.sha(local_path(PROFILE)) != old["profile"]["sha256"] or read_json(PROFILE)["enabled"] != old["profile"]["enabled"]:
        raise ValueError("Accepted character profile changed")
    if wb.sha(local_path(wb.LAUNCHER / "inspect/baseline_manifest.json")) != old["baseline_manifest_sha256"]:
        raise ValueError("Accepted extraction baseline changed")
    review = local_path(old["visual_review"]["path"])
    if wb.sha(review) != old["visual_review"]["sha256"] or read_json(review).get("approved") is not True:
        raise ValueError("Accepted art review changed")
    compiled = read_json(evidence_area / "source-compilation.json")
    if compiled["files"].get(SCRIPT_KEY) != old["acceptance_script_sha256"]:
        raise ValueError("Previous compilation does not bind the failed orchestration attempt")
    verify_source_snapshot(compiled, allow_orchestrator_change=True)
    regression = read_json(evidence_area / "regression-summary.json")
    events = read_json(evidence_area / "native-events.json")
    inputs = read_json(evidence_area / "framework-regression-inputs.json")
    if not regression.get("passed") or regression.get("tests_run", 0) < 270 or regression.get("failures") or regression.get("errors"):
        raise ValueError("Previous complete framework suite did not pass")
    if inputs.get("status") != "passed" or inputs.get("summary_sha256") != wb.sha(local_path(evidence_area / "regression-summary.json")) or inputs.get("files") != framework_test_inputs() or inputs.get("log_sha256") != wb.sha(local_path(wb.EVIDENCE / "yuwen-regression.log")):
        raise ValueError("Previous framework regression inputs/result/log changed")
    if events.get("status") != "passed" or events.get("scenarios", 0) < 19 or events.get("script_sha256") != wb.sha(local_path(CHARACTER / "tests/native_events.cjs")) or events.get("log_sha256") != wb.sha(local_path(evidence_area / "native-events.log")):
        raise ValueError("Previous complete character event contract changed or failed")
    operations = {}
    for label in ("build", "repeat", "install", "update", "withdrawal-build", "withdraw", "uninstall"):
        path = wb.EVIDENCE / ("yuwen-" + label + ".json")
        operation = read_json(path)
        if operation.get("exit_code") != 0 or wb.sha(local_path(operation["log"])) != operation["log_sha256"]:
            raise ValueError("Previous accepted build/transaction receipt changed or failed: " + label)
        operations[label] = record_file(path)
    reproducibility = read_json(evidence_area / "reproducibility.json")
    resources = reproducibility["resource_hashes"]
    if reproducibility.get("status") != "passed" or reproducibility.get("changed") or reproducibility.get("resource_count") != len(resources) or not resources:
        raise ValueError("Previous complete repeat build did not pass")
    return {"source_compilation": record_file(evidence_area / "source-compilation.json"),
            "regression": record_file(evidence_area / "regression-summary.json"), "native_events": record_file(evidence_area / "native-events.json"),
            "reproducibility": record_file(evidence_area / "reproducibility.json"), "operations": operations,
            "first_build": verified_build_binding(wb.LAUNCHER / "patch_out", resources, old),
            "repeat_build": repeat_build_binding(resources, old, evidence_area),
            "tests_reused_without_rerun": regression["tests_run"], "event_scenarios_reused_without_rerun": events["scenarios"]}


def finish_restoration():
    receipt = local_path(AREA / "engineering-acceptance.json")
    current_record = read_json(receipt)
    old, evidence_area = current_record, AREA
    original_attempt = None
    continuation = current_record.get("restoration_continuation")
    if continuation:
        repair_phases = ["restoration-source-compilation", "archive-owned-pristine-indices",
                         "working-game-restored", "immutable-baseline-unchanged", "source-game-unchanged"]
        completed = continuation.get("phases", [])
        if current_record.get("status") not in ("failed", "running") or completed != repair_phases[:len(completed)] or current_record.get("phases") != RESTORATION_PREFIX + completed:
            raise ValueError("Restoration retry has an unknown stage or has already completed")
        original_attempt = continuation.get("original_attempt", continuation["previous_attempt"])
        original_path = local_path(wb.ROOT / original_attempt["archive"])
        if original_path.parent != local_path(AREA / "history") or original_path.name != original_attempt["sha256"] + ".json" or wb.sha(original_path) != original_attempt["sha256"]:
            raise ValueError("Original failed attempt archive binding changed")
        old = read_json(original_path)
        evidence_area = original_path.with_suffix("")
        for name, digest in original_attempt["artifacts"].items():
            if name == "engineering-acceptance.json":
                continue  # The original receipt is stored at its SHA-named sibling.
            if PurePosixPath(name).name != name or "\\" in name or ":" in name or wb.sha(local_path(evidence_area / name)) != digest:
                raise ValueError("Original accepted evidence archive changed: " + name)
    bindings = restoration_bindings(old, evidence_area)
    previous = archive_attempt(receipt)
    original_attempt = original_attempt or previous
    original_evidence = local_path(wb.ROOT / original_attempt["archive"]).with_suffix("")
    for key, filename in (("source_compilation", "source-compilation.json"), ("regression", "regression-summary.json"),
                          ("native_events", "native-events.json"), ("reproducibility", "reproducibility.json")):
        bindings[key] = record_file(original_evidence / filename)
    if bindings["repeat_build"]["scope"] == "repeat_receipt_reused_after_owned_cleanup":
        bindings["repeat_build"]["cleanup"] = record_file(original_evidence / "cleanup.json")
        bindings["repeat_build"]["receipt"] = record_file(original_evidence / "yuwen-repeat.json")
        bindings["repeat_build"]["log"] = record_file(original_evidence / "yuwen-repeat.log")
    record = {**old, "status": "running", "phases": list(old["phases"]),
              "original_attempt_elapsed_seconds": old["elapsed_seconds"],
              "acceptance_script_sha256": wb.sha(Path(__file__)),
              "restoration_continuation": {"original_attempt": original_attempt,
                  "previous_attempt": previous, "accepted_inputs": bindings, "phases": []}}
    for key in ("pristine_index_archive", "pristine_index_cleanup_result"):
        if key in current_record:
            record[key] = current_record[key]
    record.pop("error", None)
    started = time.monotonic()

    def phase(name, operation):
        print("YUWEN RESTORATION PHASE: " + name, flush=True)
        operation()
        record["phases"].append(name)
        record["restoration_continuation"]["phases"].append(name)
        wb.write_json(receipt, record)

    try:
        wb.write_json(receipt, record)
        def compile_repair():
            run("compile_sources.py", [], "finish-compile")
            current = read_json(wb.EVIDENCE / "source-compilation.json")
            expected = dict(read_json(evidence_area / "source-compilation.json")["files"])
            expected[SCRIPT_KEY] = record["acceptance_script_sha256"]
            if current.get("status") != "passed" or current.get("files") != expected:
                raise ValueError("Concentrated restoration compilation changed an unrelated source")
            verify_source_snapshot(current)
            shutil.copy2(wb.EVIDENCE / "source-compilation.json", AREA / "source-compilation.json")
            record["restoration_source_compilation"] = record_file(AREA / "source-compilation.json")
        phase("restoration-source-compilation", compile_repair)
        phase("archive-owned-pristine-indices", lambda: archive_owned_pristine_indices(record))
        phase("working-game-restored", lambda: verify_working_restored(record))
        phase("immutable-baseline-unchanged", wb.verify_baseline)
        phase("source-game-unchanged", lambda: wb.verify_baseline(source=True))
        record.update(status="passed", elapsed_seconds=round(old["elapsed_seconds"] + time.monotonic() - started, 2),
                      runtime="pending separate character selection, combat, reopen and restoration acceptance")
        wb.write_json(receipt, record)
        return 0
    except Exception as exc:
        record.update(status="failed", error=str(exc), restoration_elapsed_seconds=round(time.monotonic() - started, 2))
        wb.write_json(receipt, record)
        print(str(exc), flush=True)
        return 1


def inventory(area):
    return {p.relative_to(area).as_posix(): wb.sha(p) for p in area.rglob("*")
            if p.is_file() and not p.name.startswith("_")}


def run(script, args, label, **kwargs):
    if wb.run_script(script, args, "yuwen-" + label, **kwargs):
        raise RuntimeError("Character acceptance stopped at " + label)


def archive_platform_receipts():
    """Preserve exact earlier receipts before child tools reuse public names."""
    saved = {}
    for name in ("source-compilation.json", "regression-summary.json", "baseline-final.json",
                 "source-game-final.json", "reproducibility.json", "final-acceptance.json"):
        source = wb.EVIDENCE / name
        if not source.is_file():
            continue
        digest = wb.sha(source)
        target = AREA / "prior-receipts" / digest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if wb.sha(target) != digest:
                raise ValueError("Historical receipt archive changed")
        else:
            shutil.copy2(source, target)
            if wb.sha(target) != digest:
                raise ValueError("Historical receipt archive copy differs")
        saved[name] = {"sha256": digest, "archive": str(target.relative_to(wb.ROOT))}
    return saved


def native_events():
    source = CHARACTER / "tests/native_events.cjs"
    log = AREA / "native-events.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(["node", str(source)], cwd=wb.LAUNCHER, env=wb.environment(),
                                stdout=stream, stderr=subprocess.STDOUT)
    lines = log.read_text("utf-8").splitlines()
    outcome = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    passed = result.returncode == 0 and outcome.get("status") == "passed" and outcome.get("scenarios", 0) >= 18
    wb.write_json(AREA / "native-events.json", {"status": "passed" if passed else "failed",
                  "exit_code": result.returncode, "script_sha256": wb.sha(source), "log_sha256": wb.sha(log),
                  "scenarios": outcome.get("scenarios", 0), "scope": "offline native event contract; C# integration unproven"})
    if not passed:
        raise ValueError("Yuwen Yi native event contract scenarios failed")


def validate_prepared_art():
    """Reuse only exact previously prepared pixels, producers and timelines."""
    sys.path.insert(0, str(CHARACTER))
    try:
        import body_source
        import body_clips
        import portraits
        source = body_source.BodySource()
        clips = body_clips.sequences(source)
        portraits.prepared()
        print(json.dumps({"status": "reused_verified_prepared_art", "frames": len(source.frames),
                          "animations": len(clips), "production_sha256": wb.sha(source.path)}), flush=True)
    finally:
        sys.path.pop(0)


def framework_test_inputs():
    compiled = json.loads((AREA / "source-compilation.json").read_text("utf-8"))
    files = {name: value for name, value in compiled["files"].items()
             if not name.startswith("ZenithTerminal/Launcher/mods/char-yuwen-yi/")
             and name != "scripts/yuwen_acceptance.py"}
    # Several Python regressions load real SDK/Inspector JS and descriptors.
    # Python compilation hashes alone cannot prove those inputs stayed exact.
    for area in (wb.LAUNCHER / "shared", wb.LAUNCHER / "tests",
                 wb.LAUNCHER / "mods/framework-validation-probe"):
        for path in area.rglob("*"):
            if path.is_file() and path.suffix in {".js", ".cjs", ".json"}:
                files[path.relative_to(wb.ROOT).as_posix()] = wb.sha(path)
    for name in ("compatibility-contracts.json", "build-input-contracts.json"):
        path = wb.LAUNCHER / name
        files[path.relative_to(wb.ROOT).as_posix()] = wb.sha(path)
    # The framework suite now imports this role-owned UI module. Its bytes are
    # therefore part of a reusable framework result as well as the role build.
    potential_module = CHARACTER / "potential_content.py"
    if potential_module.exists():
        files[potential_module.relative_to(wb.ROOT).as_posix()] = wb.sha(potential_module)
    return files


def fresh_framework_regression():
    before = framework_test_inputs()
    run("tests/run_all.py", [], "regression")
    if framework_test_inputs() != before:
        raise ValueError("Framework test inputs changed while the suite was running")
    shutil.copy2(wb.EVIDENCE / "regression-summary.json", AREA / "regression-summary.json")
    wb.write_json(AREA / "framework-regression-inputs.json", {
        "status": "passed", "files": before, "summary_sha256": wb.sha(AREA / "regression-summary.json"),
        "log_sha256": wb.sha(wb.EVIDENCE / "yuwen-regression.log")})


def reuse_framework_regression(previous):
    """Keep a passed framework result only while every covered source is exact."""
    old_result, old_inputs, old_result_hash, old_inputs_hash = previous
    if not old_result.get("passed") or old_result.get("failures") or old_result.get("errors"):
        raise ValueError("There is no passed framework regression to reuse")
    if old_inputs.get("status") != "passed" or old_inputs.get("summary_sha256") != old_result_hash:
        raise ValueError("Previous framework test input receipt is missing or unbound")
    if old_inputs["files"] != framework_test_inputs():
        raise ValueError("Framework regression inputs changed; rerun without --reuse-framework-regression")
    wb.write_json(AREA / "framework-regression-reuse.json", {
        "status": "passed", "prior_test_inputs_sha256": old_inputs_hash,
        "prior_regression_summary_sha256": old_result_hash, "tests_run": old_result["tests_run"],
        "unchanged_covered_source_and_fixture_files": len(old_inputs["files"]),
        "exclusions": ["role-owned sources have their own native events and complete build acceptance",
                       "this orchestration entry point is validated by its complete execution"],
        "scope": "reuse of exact previous passed framework suite; not a new test execution"})
    print("Reused passed framework regression with unchanged covered source hashes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-review", type=Path)
    parser.add_argument("--finish-restoration", action="store_true",
                        help="resume only a completed character build/transaction attempt failing its final working file set")
    parser.add_argument("--reuse-prepared-art", action="store_true",
                        help="after a code repair, validate every frozen producer/frame/timeline instead of overwriting art")
    parser.add_argument("--reuse-framework-regression", action="store_true",
                        help="for role-only repairs, reuse the passed suite only if all covered source hashes are unchanged")
    args = parser.parse_args()
    if args.finish_restoration:
        if args.visual_review or args.reuse_prepared_art or args.reuse_framework_regression:
            parser.error("--finish-restoration uses the bound previous receipts and takes no preparation/review options")
        return finish_restoration()
    if not args.visual_review:
        parser.error("--visual-review is required for a complete acceptance run")
    review = wb.bounded(args.visual_review, wb.ROOT)
    portrait = wb.ROOT / "references/wandering-sword/20261015T134637Z-890830ca3a1f/manifest.json"
    authored = CHARACTER / "assets/authored-poses.json"
    if not json.loads(review.read_text("utf-8")).get("approved"):
        raise ValueError("The exact art batch has no root visual approval")
    expected = ["bbee-sdk", "bbee-actors", "bbee-inspector", "framework-validation-probe", "char-yuwen-yi"]
    if json.loads(PROFILE.read_text("utf-8"))["enabled"] != expected:
        raise ValueError("Character acceptance profile changed")
    AREA.mkdir(parents=True, exist_ok=True)
    previous_regression = None
    if args.reuse_framework_regression:
        previous_result = AREA / "regression-summary.json"
        previous_inputs = AREA / "framework-regression-inputs.json"
        previous_regression = (json.loads(previous_result.read_text("utf-8")),
            json.loads(previous_inputs.read_text("utf-8")), wb.sha(previous_result), wb.sha(previous_inputs))
    record = {"status": "running", "build_id": wb.BUILD, "phases": [],
              "profile": {"path": str(PROFILE), "sha256": wb.sha(PROFILE), "enabled": expected},
              "visual_review": {"path": str(review), "sha256": wb.sha(review)}}
    receipt = AREA / "engineering-acceptance.json"
    if receipt.exists():
        record["previous_attempt"] = archive_attempt(receipt)
    started = time.monotonic()

    def phase(name, operation):
        print("YUWEN ACCEPTANCE PHASE: " + name, flush=True)
        operation()
        record["phases"].append(name)
        wb.write_json(receipt, record)

    try:
        record["prior_receipts"] = archive_platform_receipts()
        record["frozen_character_inputs"] = {p.relative_to(CHARACTER).as_posix(): wb.sha(p)
            for p in CHARACTER.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        record["acceptance_script_sha256"] = wb.sha(Path(__file__))
        def baseline():
            sys.path.insert(0, str(wb.LAUNCHER))
            from validation_tables import validate_baseline
            validate_baseline(wb.LAUNCHER, wb.BUILD)
            decoded = json.loads((wb.LAUNCHER / "inspect/decode_report.json").read_text("utf-8"))
            if decoded.get("status") != "passed" or not decoded.get("fresh") or not decoded.get("strict"):
                raise ValueError("The extraction is not a passed fresh strict baseline")
            record["baseline_manifest_sha256"] = wb.sha(wb.LAUNCHER / "inspect/baseline_manifest.json")
        phase("validate-frozen-baseline", baseline)
        phase("consolidated-source-compilation", lambda: run("compile_sources.py", [], "compile"))
        shutil.copy2(wb.EVIDENCE / "source-compilation.json", AREA / "source-compilation.json")
        record["prepared_art_mode"] = "revalidate-frozen" if args.reuse_prepared_art else "first-preparation"
        phase("prepare-reviewed-complete-art", validate_prepared_art if args.reuse_prepared_art else
              lambda: run("mods/char-yuwen-yi/import_yuwen.py", ["--prepare", "--portrait-manifest", str(portrait),
                          "--authored-manifest", str(authored), "--visual-review", str(review)], "prepare-art"))
        phase("prepare-complete-character", lambda: run("prepare_mods.py", [], "prepare", profile=PROFILE))
        phase("integrated-regression", (lambda: reuse_framework_regression(previous_regression))
              if args.reuse_framework_regression else fresh_framework_regression)
        phase("character-native-event-contracts", native_events)
        phase("complete-build", lambda: run("bbmod.py", ["build"], "build", profile=PROFILE))
        first = inventory(wb.LAUNCHER / "patch_out")
        repeat = wb.ROOT / "builds/full-repeat"
        phase("repeat-complete-build", lambda: run("bbmod.py", ["build"], "repeat", profile=PROFILE, output=repeat))
        second = inventory(repeat)
        differences = sorted(p for p in set(first) | set(second) if first.get(p) != second.get(p))
        wb.write_json(AREA / "reproducibility.json", {"status": "failed" if differences else "passed",
                      "resource_count": len(first), "changed": differences, "resource_hashes": first})
        if differences:
            raise ValueError("Complete character builds differ")
        phase("install-complete", lambda: run("sandbox_install.py", ["install"], "install"))
        phase("update-complete", lambda: run("sandbox_install.py", ["install"], "update", output=repeat))
        reduced = wb.ROOT / "builds/withdrawal"
        phase("withdrawal-profile-build", lambda: run("bbmod.py", ["build"], "withdrawal-build",
              profile=wb.ROOT / "profiles/framework-runtime.json", output=reduced))
        phase("withdraw-character", lambda: run("sandbox_install.py", ["install"], "withdraw", output=reduced))
        phase("uninstall", lambda: run("sandbox_install.py", ["uninstall"], "uninstall"))
        phase("archive-owned-pristine-indices", lambda: archive_owned_pristine_indices(record))
        phase("working-game-restored", lambda: verify_working_restored(record))
        phase("immutable-baseline-unchanged", wb.verify_baseline)
        phase("source-game-unchanged", lambda: wb.verify_baseline(source=True))
        record.update(status="passed", elapsed_seconds=round(time.monotonic() - started, 2),
                      runtime="pending separate character selection, combat, reopen and restoration acceptance")
        wb.write_json(receipt, record)
        return 0
    except Exception as exc:
        record.update(status="failed", error=str(exc), elapsed_seconds=round(time.monotonic() - started, 2))
        wb.write_json(receipt, record)
        print(str(exc), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
