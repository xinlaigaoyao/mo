"""Operate on the workbench's physical game copy, never the Steam installation."""
import json
import sys
from pathlib import Path

from safe_install import install, uninstall

root = Path(__file__).resolve().parent
if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
    raise SystemExit("Usage: sandbox_install.py install|uninstall")
result = install(root) if sys.argv[1] == "install" else uninstall(root)
print(json.dumps(result, ensure_ascii=False, indent=2))
