"""Run the framework's regression suite with the same pinned build runtime."""
import json
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=1).run(suite)
summary = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
           "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
           "passed": result.wasSuccessful()}
out = root.parent.parent / "evidence" / "regression-summary.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
raise SystemExit(0 if result.wasSuccessful() else 1)
