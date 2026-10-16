import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from reproducibility import rig_guid, resource_timestamp


class ReproducibilityTests(unittest.TestCase):
    def test_rig_identity_is_stable_and_bound_to_inputs(self):
        values = ["1", "source", "target", "logic", ["abc", "def"]]
        identity = rig_guid(*values)
        self.assertEqual(identity, rig_guid(*values))
        for index, value in enumerate(("2", "other_source", "other_target", "other_logic", ["abc", "changed"])):
            modified = list(values)
            modified[index] = value
            self.assertNotEqual(identity, rig_guid(*modified))

    def test_resource_time_uses_baseline_or_explicit_epoch(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            (root / "inspect").mkdir()
            (root / "inspect" / "baseline_manifest.json").write_text(json.dumps({"created_utc": "fixed"}), "utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(resource_timestamp(root), "fixed")
            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}, clear=True):
                self.assertEqual(resource_timestamp(root), "1970-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
