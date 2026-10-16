"""Run the locally compiled static-only dumper against the isolated game copy."""
import json
import subprocess
from pathlib import Path

from workbench import ROOT, LAUNCHER, BUILD, EVIDENCE, environment, sha

tool = ROOT / "tools" / "Il2CppDumper-static" / "Il2CppDumper.dll"
game = LAUNCHER / "game"
assembly = game / "GameAssembly.dll"
metadata = game / "BlazblueEntropyEffect_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat"
output = LAUNCHER / "dump"
output.mkdir(exist_ok=True)
env = environment()
env.update({"DOTNET_CLI_HOME": str(ROOT / "private" / "dotnet-profile"),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false"})
command = ["dotnet", str(tool), str(assembly), str(metadata), str(output)]
log = EVIDENCE / "static-metadata-dump.log"
with log.open("w", encoding="utf-8") as stream:
    completed = subprocess.run(command, cwd=tool.parent, env=env, stdin=subprocess.DEVNULL,
                               stdout=stream, stderr=subprocess.STDOUT, timeout=600)
print(log.read_text("utf-8", errors="replace"))
dump = output / "dump.cs"
if completed.returncode or not dump.is_file() or not (output / "DummyDll").is_dir():
    raise SystemExit("Static dump did not produce required artifacts; no build stamp written")
(output / "game_build.txt").write_text(BUILD, "utf-8")
record = {"build_id": BUILD, "command": command, "tool_sha256": sha(tool),
          "gameassembly_sha256": sha(assembly), "metadata_sha256": sha(metadata),
          "dump_sha256": sha(dump), "exit_code": completed.returncode,
          "safety": "PE LoadLibrary fallback removed in local source build"}
(output / "provenance.json").write_text(json.dumps(record, indent=2), "utf-8")
print("Scoped dump produced and bound to build", BUILD)
