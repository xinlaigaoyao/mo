"""Composed-table preflight regressions; generated fixtures only, no UnityPy."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from table_preflight import TablePreflightError, assert_preflight_unchanged, preflight_tables
from validation_tables import ValidationError, encode_message, encode_table_rows, read_varint


SCHEMA = {
    "T": {"1": ["Id", "uint"], "2": ["Value", "float"], "3": ["Children", "RepeatedField<T.Types.Child>"],
          "4": ["Solo", "T.Types.Child"]},
    "TFixedPoint": {"1": ["Id", "uint"], "2": ["Value", "long"], "3": ["Children", "RepeatedField<TFixedPoint.Types.ChildFixedPoint>"],
                    "4": ["Solo", "TFixedPoint.Types.ChildFixedPoint"]},
    "T.Types.Child": {"1": ["Name", "string"], "2": ["Count", "uint"]},
    "TFixedPoint.Types.ChildFixedPoint": {"1": ["Name", "string"], "2": ["Count", "uint"]},
}


class TablePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ("inspect", "decoded/tables", "extracted_raw/data/xlsxfixed"):
            (self.root / relative).mkdir(parents=True)
        (self.root / "inspect/game_build.txt").write_text("7")
        (self.root / "inspect/proto_schema.json").write_text(json.dumps(SCHEMA))
        self.original = [{"Id": 1, "Value": 0.5, "Children": [{"Name": "first", "Count": 50991}]}]
        fixed = [{"Id": 1, "Value": 1 << 31, "Children": self.original[0]["Children"]}]
        self.current_path = self.root / "decoded/tables/T.json"
        self.current_path.write_text(json.dumps(self.original))
        (self.root / "decoded/tables/T.json.orig").write_text(json.dumps(self.original))
        self.fixed_path = self.root / "extracted_raw/data/xlsxfixed/TFixedPointWrap.bin"
        self.fixed_path.write_bytes(encode_table_rows(fixed, "TFixedPoint", SCHEMA))

    def test_legacy_shape_is_audited_and_both_payloads_verify_without_source_writes(self):
        body = encode_message(self.original[0]["Children"][0], "T.Types.Child", SCHEMA)
        values = []
        pos = 0
        while pos < len(body):
            value, pos = read_varint(body, pos)
            values.append(value)
        current = [dict(self.original[0], Children=values)]
        self.current_path.write_text(json.dumps(current))
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = preflight_tables(self.root, ["T"], schema=SCHEMA, build_id="7")
        self.assertEqual(report["status"], "passed")
        self.assertEqual((report["table_count"], report["fixed_table_count"]), (1, 1))
        self.assertEqual(report["tables"][0]["fixed"]["unchanged_byte_identical_rows"], 1)
        self.assertEqual(len(report["legacy_conversions"]), 1)
        self.assertEqual(report["legacy_conversions"][0]["path"], "T[0].Children")
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        assert_preflight_unchanged(self.root, report)
        self.current_path.write_text("[]")
        with self.assertRaisesRegex(ValidationError, "changed"):
            assert_preflight_unchanged(self.root, report)

    def test_all_failures_are_reported_before_any_game_or_bundle_output(self):
        self.current_path.write_text(json.dumps([{"Id": 1, "Children": [10, 3, 120]}]))
        destination = self.root / "inspect/preflight.json"
        with self.assertRaises(TablePreflightError) as error:
            preflight_tables(self.root, ["T", "Missing"], build_id="7", report_path=destination)
        self.assertEqual({item["table"] for item in error.exception.report["failures"]}, {"T", "Missing"})
        self.assertEqual(json.loads(destination.read_text())["status"], "failed")
        self.assertFalse((self.root / "patch_out").exists())
        self.assertFalse((self.root / "game").exists())

    def test_singular_legacy_body_and_null_unset_share_normal_fixed_preflight(self):
        child = {"Name": "teacher", "Count": 1}
        legacy = encode_message(child, "T.Types.Child", SCHEMA).decode("utf-8")
        current = [{"Id": 1, "Value": None, "Children": None, "Solo": legacy}]
        self.current_path.write_text(json.dumps(current))
        report = preflight_tables(self.root, ["T"], schema=SCHEMA, build_id="7")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["tables"][0]["fixed"]["semantic_roundtrip"], "passed")
        self.assertEqual({item["representation"] for item in report["legacy_conversions"]},
                         {"json_null_unset", "legacy_singular_utf8_body"})
        self.assertEqual(json.loads(self.current_path.read_text()), current)

    def test_missing_fixed_input_or_baseline_count_mismatch_blocks_preflight(self):
        self.fixed_path.unlink()
        with self.assertRaises(TablePreflightError):
            preflight_tables(self.root, ["T"], build_id="7")
        self.fixed_path.write_bytes(b"")
        with self.assertRaises(TablePreflightError) as error:
            preflight_tables(self.root, ["T"], build_id="7")
        self.assertIn("counts differ", str(error.exception))

    def test_wrong_build_or_nonbaseline_schema_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "requested"):
            preflight_tables(self.root, ["T"], build_id="8")
        with self.assertRaisesRegex(ValidationError, "schema differs"):
            preflight_tables(self.root, ["T"], schema={}, build_id="7")


if __name__ == "__main__":
    unittest.main()
