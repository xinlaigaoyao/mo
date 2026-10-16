"""One consolidated, in-memory Python compilation pass with a source receipt."""
import hashlib
import json
import importlib.metadata
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
workspace = root.parent.parent
paths = list(root.glob("*.py"))
for directory in (root / "mods", root / "shared", root / "tests", root / "tools", root.parent / "Gui", workspace / "scripts"):
    paths.extend(directory.rglob("*.py"))
sources = {}
for path in sorted(set(paths)):
    if "__pycache__" in path.parts:
        continue
    raw = path.read_bytes()
    compile(raw, str(path), "exec")
    sources[path.relative_to(workspace).as_posix()] = hashlib.sha256(raw).hexdigest()
record = {"status": "passed", "compiled_files": len(sources), "files": sources}
lock = json.loads((workspace / "dependencies.lock.json").read_text("utf-8"))
actual = {item["name"]: importlib.metadata.version(item["name"]) for item in lock["packages"]}
if any(actual[item["name"]] != item["version"] for item in lock["packages"]):
    raise ValueError("Installed dependency versions differ from the workbench lock")
node = subprocess.check_output(["node", "--version"], text=True).strip()
if node != lock["node"]:
    raise ValueError("Node version differs from the workbench lock")
record["runtime"] = {"python": sys.version, "packages": actual, "node": node}
(workspace / "evidence" / "source-compilation.json").write_text(json.dumps(record, indent=2), "utf-8")
print(f"Consolidated compilation passed: {len(sources)} Python sources")
