"""Run only after implementation is complete: one integrated build/verification/acceptance sequence."""
import hashlib
import json
from pathlib import Path
import sys
import time
import subprocess
import argparse

import workbench as wb


def files(area):
    return {path.relative_to(area).as_posix(): wb.sha(path) for path in area.rglob("*")
            if path.is_file() and not path.name.startswith("_")}


def run(script, args, label, **kwargs):
    code = wb.run_script(script, args, "final-" + label, **kwargs)
    if code:
        raise RuntimeError(f"Acceptance stopped at {label}: exit {code}")


def compile_static_tool():
    source = wb.ROOT / "tools" / "Il2CppDumper-6.7.46" / "Il2CppDumper"
    if "DllImport" in (source / "Utils" / "PELoader.cs").read_text("utf-8"):
        raise ValueError("Static dumper unexpectedly contains the native game DLL loader")
    command = ["dotnet", "build", str(source / "Il2CppDumper.csproj"), "-c", "Release",
               "-p:TargetFrameworks=net6.0", "--configfile", str(wb.ROOT / "tools" / "NuGet.Config"),
               "-o", str(wb.ROOT / "tools" / "Il2CppDumper-static")]
    log = wb.EVIDENCE / "final-static-tool-compile.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=wb.ROOT, env=wb.environment(), stdout=stream, stderr=subprocess.STDOUT)
    wb.write_json(wb.EVIDENCE / "final-static-tool-compile.json", {"command": command, "exit_code": result.returncode,
                  "log_sha256": wb.sha(log), "binary_sha256": wb.sha(wb.ROOT / "tools" / "Il2CppDumper-static" / "Il2CppDumper.dll")})
    if result.returncode:
        raise RuntimeError("Static metadata tool compilation failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-baseline", action="store_true", help="reuse the previous passed strict extraction after validating every immutable input hash")
    parser.add_argument("--profile", help="explicit complete acceptance profile; omitted uses the original enabled mod set")
    options = parser.parse_args()
    started = time.time()
    record = {"status": "running", "build_id": wb.BUILD, "phases": []}
    target_profile = wb.bounded(Path(options.profile), wb.ROOT) if options.profile else None
    if target_profile:
        record["target_profile"] = {"path": str(target_profile.relative_to(wb.ROOT)),
                                    "sha256": wb.sha(target_profile),
                                    "enabled": json.loads(target_profile.read_text("utf-8"))["enabled"]}
    evidence = wb.EVIDENCE / "final-acceptance.json"
    def phase(name, operation):
        print("ACCEPTANCE PHASE: " + name, flush=True)
        operation()
        record["phases"].append(name)
        wb.write_json(evidence, record)
    try:
        phase("static-tool-compile", compile_static_tool)
        phase("compile", lambda: run("compile_sources.py", [], "compile"))
        if options.reuse_baseline:
            def reuse():
                sys.path.insert(0, str(wb.LAUNCHER))
                from validation_tables import validate_baseline
                validate_baseline(wb.LAUNCHER, wb.BUILD)
                report = json.loads((wb.LAUNCHER / "inspect" / "decode_report.json").read_text("utf-8"))
                if report.get("status") != "passed" or not report.get("fresh") or not report.get("strict"):
                    raise ValueError("Previous extraction is not a passed fresh strict baseline")
                record["reused_strict_baseline_sha256"] = wb.sha(wb.LAUNCHER / "inspect" / "baseline_manifest.json")
            phase("validated-existing-strict-baseline", reuse)
        else:
            phase("fresh-strict-baseline", lambda: run("pipeline.py", ["--fresh", "--strict", "--build-id", wb.BUILD], "setup"))
        phase("prepare", lambda: run("prepare_mods.py", [], "prepare", profile=target_profile))
        phase("typetree", lambda: run("typetree_probe.py", [], "typetree"))
        phase("regression", lambda: run("tests/run_all.py", [], "regression"))
        phase("full-build", lambda: run("bbmod.py", ["build"], "build", profile=target_profile))
        first = files(wb.LAUNCHER / "patch_out")
        repeat = wb.ROOT / "builds" / "full-repeat"
        phase("repeat-full-build", lambda: run("bbmod.py", ["build"], "build-repeat", output=repeat, profile=target_profile))
        second = files(repeat)
        if first != second:
            differences = sorted(name for name in set(first) | set(second) if first.get(name) != second.get(name))
            wb.write_json(wb.EVIDENCE / "reproducibility.json", {"status": "failed", "changed": differences})
            raise ValueError("Repeated complete builds have different resource bytes")
        wb.write_json(wb.EVIDENCE / "reproducibility.json", {"status": "passed", "bundle_count": len(first),
                      "resource_hashes": first, "scope": "same published immutable baseline and same pinned inputs; execution-time metadata excluded"})
        phase("install-full", lambda: run("sandbox_install.py", ["install"], "install"))
        phase("update-full", lambda: run("sandbox_install.py", ["install"], "update", output=repeat))
        if target_profile:
            reduced = wb.ROOT / "builds" / "withdrawal"
            profile = wb.ROOT / "profiles" / "validation-probe.json"
            phase("withdrawal-profile-build", lambda: run("bbmod.py", ["build"], "withdrawal-build", profile=profile, output=reduced))
            phase("profile-withdrawal", lambda: run("sandbox_install.py", ["install"], "withdrawal-update", output=reduced))
        else:
            runtime = wb.ROOT / "builds" / "runtime"
            profile = wb.ROOT / "profiles" / "framework-runtime.json"
            phase("framework-profile-build", lambda: run("bbmod.py", ["build"], "framework-build", profile=profile, output=runtime))
            phase("withdraw-character-fixtures", lambda: run("sandbox_install.py", ["install"], "framework-update", output=runtime))
        phase("uninstall", lambda: run("sandbox_install.py", ["uninstall"], "uninstall"))
        snapshot = json.loads((wb.BASELINE / "manifest.json").read_text("utf-8"))
        for item in snapshot["files"]:
            path = wb.LAUNCHER / "game" / item["path"]
            if wb.sha(path) != item["sha256"]:
                raise ValueError("Independent working game failed exact uninstall restoration")
        if (wb.LAUNCHER / "mods" / "installed.json").exists():
            raise ValueError("Uninstall left an installed record")
        phase("independent-baseline", wb.verify_baseline)
        phase("original-game-unchanged", lambda: wb.verify_baseline(source=True))
        record.update(status="passed", elapsed_seconds=round(time.time() - started, 2),
                      runtime_ui="separate acceptance; not implied by build/transaction success")
        wb.write_json(evidence, record)
        return 0
    except Exception as exc:
        record.update(status="failed", error=str(exc), elapsed_seconds=round(time.time() - started, 2))
        wb.write_json(evidence, record)
        print(str(exc), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
