"""Run without UnityPy: python -m unittest discover -s tests -p test_table_validation.py -v"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline
from validation_tables import (ValidationError, assert_semantic_equal, canonical_message,
    decode_message, decode_table, encode_message, encode_table_rows, expected_fixed_rows,
    read_varint, split_table, to_fixed_row, validate_baseline, validate_table_payload, write_varint,
    validate_opaque_preserved, normalize_message, legacy_repeated_messages, legacy_singular_message)

SCHEMA = {
    "Sample": {"1": ["Id", "uint"], "2": ["Value", "float"], "3": ["Big", "long"],
        "4": ["Ints", "RepeatedField<int>"], "5": ["Child", "Outer.Types.Child"],
        "6": ["Map", "MapField<string, Child>"], "7": ["Blobs", "RepeatedField<ByteString>"],
        "8": ["Enabled", "bool"], "9": ["Flags", "RepeatedField<bool>"],
        "10": ["Doubles", "RepeatedField<double>"], "11": ["BoolMap", "MapField<bool, long>"]},
    "SampleFixedPoint": {"1": ["Id", "uint"], "2": ["Value", "long"], "3": ["Big", "long"],
        "4": ["Ints", "RepeatedField<int>"], "5": ["Child", "ChildFixedPoint"]},
    "Child": {"1": ["Text", "string"], "2": ["Num", "int"]},
    "ChildFixedPoint": {"1": ["Text", "string"], "2": ["Num", "int"]},
}


class CodecTests(unittest.TestCase):
    @staticmethod
    def legacy_values(raw):
        values = []
        pos = 0
        while pos < len(raw):
            value, pos = read_varint(raw, pos)
            values.append(value)
        return values

    def test_real_legacy_icon_array_has_exact_native_normal_and_fixed_semantics(self):
        schema = json.loads((ROOT / "tools/schema/25627491/proto_schema_snapshot.json").read_text())["schema"]
        native = [{"Atlas": "UI/Atlas/IconNineHud200401/IconNineHud200401", "Sprite": "IconSkill_200401"},
                  {"Atlas": "UI/Atlas/IconNineHud200401/IconNineHud200401", "Sprite": "IconSkill_200401OFF"}]
        body = b"".join(encode_message(icon, "SkillActivate.Types.AtlasSprite", schema) for icon in native)
        legacy = self.legacy_values(body)
        # This is the actual legacy generator shape observed at composed row
        # 2452 (ActorId 200401, Group 2, Order 1), not a new role design.
        self.assertEqual(legacy[:4], [10, 44, 85, 73])
        legacy_row = {"ActorId": 200401, "Group": 2, "Order": 1, "Action": "nine_void", "Icon": legacy}
        expected = dict(legacy_row, Icon=native)
        conversions = []
        normalized = normalize_message(legacy_row, "SkillActivate", schema, conversions=conversions)
        self.assertEqual(normalized, expected)
        self.assertEqual(conversions[0]["messages"], 2)
        actual = decode_table(encode_table_rows([legacy_row], "SkillActivate", schema), "SkillActivate", schema)
        assert_semantic_equal([legacy_row], actual, "SkillActivate", schema)
        self.assertEqual(actual, [expected])
        fixed = to_fixed_row(legacy_row, "SkillActivateFixedPoint", schema)
        self.assertEqual(fixed["Icon"], native)
        self.assertEqual(decode_message(encode_message(fixed, "SkillActivateFixedPoint", schema), "SkillActivateFixedPoint", schema)["Icon"], native)
        self.assertEqual(legacy_row["Icon"], legacy)  # normalization never mutates the source

    def test_real_legacy_trigger_array_preserves_multibyte_varints(self):
        schema = json.loads((ROOT / "tools/schema/25627491/proto_schema_snapshot.json").read_text())["schema"]
        old = {"EffectId": 20401, "Trigger": [8, 50991, 16, 1]}
        expected = {"EffectId": 20401, "Trigger": [{"TriggerId": 50991, "TriggerLevel": 1}]}
        normalized = normalize_message(old, "TalentEffectConf", schema)
        self.assertEqual(normalized, expected)
        actual = decode_table(encode_table_rows([old], "TalentEffectConf", schema), "TalentEffectConf", schema)
        assert_semantic_equal([old], actual, "TalentEffectConf", schema)

    def test_real_singular_teacher_icon_utf8_body_and_varints_equal_native_object(self):
        schema = json.loads((ROOT / "tools/schema/25627491/proto_schema_snapshot.json").read_text())["schema"]
        icon = {"Atlas": "UI/Atlas/IconNineHud200401/IconNineHud200401", "Sprite": "IconSkill_2004011"}
        body = encode_message(icon, "SkillActivate.Types.AtlasSprite", schema)
        old_text = body.decode("utf-8")
        self.assertTrue(old_text.startswith("\n,UI/Atlas/"))
        self.assertIn("\x12\x11IconSkill_2004011", old_text)
        for old_icon in (old_text, self.legacy_values(body)):
            old = {"TeacherSkillId": 2004011, "Order": 1, "Act": "teacherskill", "Icon": old_icon}
            expected = dict(old, Icon=icon)
            conversions = []
            self.assertEqual(normalize_message(old, "SkillFromTeacher", schema, conversions=conversions), expected)
            self.assertEqual(conversions[0]["messages"], 1)
            actual = decode_table(encode_table_rows([old], "SkillFromTeacher", schema), "SkillFromTeacher", schema)
            self.assertEqual(actual, [expected])
            assert_semantic_equal([old], actual, "SkillFromTeacher", schema)

    def test_singular_legacy_bodies_require_exactly_one_complete_message(self):
        child = {"Text": "中文", "Num": 5}
        body = encode_message(child, "Child", SCHEMA)
        self.assertEqual(legacy_singular_message(body.decode("utf-8"), "Child", SCHEMA), child)
        for value in (body.decode("utf-8") * 2, self.legacy_values(body * 2), "", body.hex(), [10, 1, 120], 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                legacy_singular_message(value, "Child", SCHEMA)

    def test_known_field_null_is_unset_for_scalar_message_map_and_repeated_fields(self):
        # ProtoJSON ordinary-field contract:
        # https://protobuf.dev/programming-guides/json/#null-values
        old = {field[0]: None for field in SCHEMA["Sample"].values()}
        conversions = []
        self.assertEqual(normalize_message(old, "Sample", SCHEMA, conversions=conversions), {})
        self.assertEqual(len(conversions), len(SCHEMA["Sample"]))
        self.assertTrue(all(item["representation"] == "json_null_unset" for item in conversions))
        actual = decode_table(encode_table_rows([old], "Sample", SCHEMA), "Sample", SCHEMA)
        self.assertEqual(actual, [{}])
        assert_semantic_equal([old], actual, "Sample", SCHEMA)
        self.assertEqual(to_fixed_row({"Id": 1, "Value": None, "Child": None}, "SampleFixedPoint", SCHEMA), {"Id": 1})
        with self.assertRaisesRegex(ValidationError, "not in schema"):
            encode_message({"UnknownField": None}, "Sample", SCHEMA)

    def test_null_list_elements_fail_and_literal_null_string_is_preserved(self):
        for row in ({"Ints": [1, None]}, {"Blobs": [None]}, {"Flags": [None]},
                    {"Doubles": [None]}, {"Child": {"Text": None}, "Map": {"x": None}}):
            with self.subTest(row=row), self.assertRaises(ValidationError):
                encode_message(row, "Sample", SCHEMA)
        repeated_child = {"Parent": {"1": ["Items", "RepeatedField<Child>"]}, "Child": SCHEMA["Child"]}
        with self.assertRaisesRegex(ValidationError, "null elements"):
            normalize_message({"Items": [None]}, "Parent", repeated_child)
        native = {"Child": {"Text": "null", "Num": 0}}
        self.assertEqual(decode_message(encode_message(native, "Sample", SCHEMA), "Sample", SCHEMA), native)

    def test_legacy_nested_lists_reject_incomplete_mixed_or_ambiguous_shapes(self):
        schema = {"Child": {"1": ["Name", "string"], "2": ["Count", "uint"]}}
        incomplete = self.legacy_values(b"\x0a\x01x")
        duplicate = self.legacy_values(b"\x0a\x01x\x0a\x01y\x10\x01")
        truncated = self.legacy_values(b"\x0a\x05xy")
        for values in (incomplete, duplicate, truncated, [True, 1], [1, -1], [1, {}]):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                legacy_repeated_messages(values, "Child", schema)
        repeated = {"Child": {"1": ["Values", "RepeatedField<uint>"]}}
        with self.assertRaisesRegex(ValidationError, "ambiguous"):
            legacy_repeated_messages([8, 1], "Child", repeated)

    def test_dump_parser_keeps_full_nested_and_namespace_scopes(self):
        dump = '''// Namespace: game
public sealed class Table : IMessage // TypeDefIndex: 1
{
public const int ChildFieldNumber = 1;
public Table.Types.Child Child { get; set; }
}
// Namespace: game
public sealed class Table.Types.Child : IMessage // TypeDefIndex: 2
{
public const int ValueFieldNumber = 1;
public float Value { get; set; }
}
// Namespace: other
public sealed class Child : IMessage // TypeDefIndex: 3
{
public const int ValueFieldNumber = 1;
public string Value { get; set; }
}
'''
        schema = pipeline.parse_dump_schema(dump)
        self.assertEqual(schema["game.Table"]["1"][1], "game.Table.Types.Child")
        self.assertEqual(schema["game.Table.Types.Child"]["1"][1], "float")
        row = {"Child": {"Value": 0.25}}
        self.assertEqual(decode_message(encode_message(row, "Table", schema), "Table", schema), row)

    def test_dump_global_namespace_and_enum_contract(self):
        dump = '''// Namespace:
public sealed class Global : IMessage // TypeDefIndex: 1
{
public const int ModeFieldNumber = 1;
public EMode Mode { get; set; }
}
// Namespace:
public enum EMode // TypeDefIndex: 2
{
}
'''
        schema = pipeline.parse_dump_schema(dump)
        self.assertEqual(schema, {"Global": {"1": ("Mode", "int")}})
        row = {"Mode": -1}
        self.assertEqual(decode_message(encode_message(row, "Global", schema), "Global", schema), row)

    def test_real_schema_nested_messages_and_fixed_point(self):
        schema = json.loads((ROOT / "tools/schema/25627491/proto_schema_snapshot.json").read_text())["schema"]
        row = {"ActorId": 100001, "Group": 1, "Order": 2, "Action": "run",
               "Icon": [{"Atlas": "Battle", "Sprite": "Icon"}],
               "Mps": [{"Slot": 1, "MpChange": 0.25, "MpChangeLowerbound": -1.5}],
               "Timeout": 0.1, "ReqTriggerId": [-1, 2]}
        raw = encode_table_rows([row], "SkillActivate", schema)
        self.assertEqual(validate_table_payload(raw, [row], "SkillActivate", schema)["rows"], 1)
        actual = decode_table(raw, "SkillActivate", schema)[0]
        self.assertIsInstance(actual["Icon"][0], dict)
        fixed = to_fixed_row(row, "SkillActivateFixedPoint", schema)
        self.assertEqual(fixed["Mps"][0]["MpChangeLowerbound"], -(3 << 31))
        self.assertEqual(decode_table(encode_table_rows([fixed], "SkillActivateFixedPoint", schema), "SkillActivateFixedPoint", schema), [fixed])

    def test_large_integers_float32_and_nested_map(self):
        row = {"Id": 2**32 - 1, "Value": 0.1, "Big": 2**60 + 3,
               "Child": {"Text": "中文", "Num": -3}, "Map": {"x": {"Num": -7}},
               "Ints": [-2**31, -1, 0, 2**31 - 1], "Enabled": True,
               "Flags": [True, False], "Doubles": [0.1, -3.5],
               "Blobs": ["ff00", ""], "BoolMap": {"true": -(2**63), "false": 2**63 - 1}}
        decoded = decode_table(encode_table_rows([row], "Sample", SCHEMA), "Sample", SCHEMA)
        assert_semantic_equal([row], decoded, "Sample", SCHEMA)
        self.assertEqual(decoded[0]["Big"], 2**60 + 3)
        self.assertNotEqual(decoded[0]["Value"], 0.1)

    def test_unknown_wires_are_preserved_without_guessing(self):
        row = {"Id": 1, "f21": {"$wire": 2, "$value": "ff000a"},
               "f22": [{"$wire": 5, "$value": "0000803f"}, {"$wire": 0, "$value": 2**64 - 1}]}
        raw = encode_message(row, "Sample", SCHEMA)
        self.assertEqual(decode_message(raw, "Sample", SCHEMA), row)
        self.assertEqual(encode_message(decode_message(raw, "Sample", SCHEMA), "Sample", SCHEMA), raw)

    def test_unpacked_and_packed_have_same_semantics(self):
        unpacked = b"\x20\x01\x20\x02"
        packed = b"\x22\x02\x01\x02"
        self.assertEqual(decode_message(unpacked, "Sample", SCHEMA), decode_message(packed, "Sample", SCHEMA))

    def test_integer_changes_above_float_precision_fail(self):
        row = {"Big": 2**60 + 1}
        changed = encode_table_rows([{"Big": 2**60 + 2}], "Sample", SCHEMA)
        with self.assertRaisesRegex(ValidationError, "semantic mismatch"):
            validate_table_payload(changed, [row], "Sample", SCHEMA)

    def test_defaults_empty_fields_and_count(self):
        raw = encode_table_rows([{"Id": 0, "Value": 0.0, "Ints": [], "Child": {}}], "Sample", SCHEMA)
        validate_table_payload(raw, [{}], "Sample", SCHEMA)
        with self.assertRaisesRegex(ValidationError, "row count"):
            validate_table_payload(raw, [], "Sample", SCHEMA)

    def test_table_length_bounds_and_trailing_data(self):
        for raw in (b"x", struct.pack("<I", 5) + b"a", struct.pack("<I", 0) + b"x"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                split_table(raw)

    def test_varint_bounds(self):
        for raw in (b"\x80", b"\x80" * 10 + b"\x00", b"\xff" * 9 + b"\x02"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                read_varint(raw)
        for value in (-2**63, 2**64 - 1):
            self.assertEqual(read_varint(write_varint(value))[0], value & (2**64 - 1))

    def test_invalid_wire_utf8_and_packed_lengths_fail(self):
        cases = [b"\x00", b"\x0a\x01a", b"\x12\x03abc", b"\x22\x01\x80",
                 b"\x52\x03abc", b"\x2a\x03\x0a\x01\xff"]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                decode_message(raw, "Sample", SCHEMA)

    def test_invalid_input_types_and_range_fail(self):
        for row in ({"Id": -1}, {"Id": 2**32}, {"Big": 1.2}, {"Enabled": 1},
                    {"Value": float("nan")}, {"Value": 1e100}, {"Child": []}):
            with self.subTest(row=row), self.assertRaises(ValidationError):
                encode_message(row, "Sample", SCHEMA)

    def test_fixed_native_long_never_scales_or_converts_to_float(self):
        row = {"Id": 1, "Value": -0.25, "Big": 2**60 + 3, "Child": {"Num": -3}}
        fixed = to_fixed_row(row, "SampleFixedPoint", SCHEMA)
        self.assertEqual(fixed["Value"], -(1 << 30))
        self.assertEqual(fixed["Big"], 2**60 + 3)
        with self.assertRaisesRegex(ValidationError, "overflow"):
            to_fixed_row({"Value": 2**31}, "SampleFixedPoint", SCHEMA)

    def test_fixed_unchanged_preserves_original_precision_and_deltas(self):
        original = [{"Id": 1, "Value": 0.1}, {"Id": 2, "Value": 0.5}]
        baseline = [{"Id": 1, "Value": 429496730}, {"Id": 2, "Value": 1 << 31}]
        raw = encode_table_rows(baseline, "SampleFixedPoint", SCHEMA)
        current = [original[0], {"Id": 2, "Value": 0.25}, {"Id": 3, "Value": 1.0}]
        expected = expected_fixed_rows(current, original, raw, "Sample", SCHEMA)
        self.assertEqual(expected[0], baseline[0])
        self.assertEqual(expected[1]["Value"], 1 << 30)
        result = validate_table_payload(encode_table_rows(expected, "SampleFixedPoint", SCHEMA), expected, "SampleFixedPoint", SCHEMA, 2)
        self.assertEqual(result["row_delta"], 1)
        with self.assertRaisesRegex(ValidationError, "counts differ"):
            expected_fixed_rows(current, [], raw, "Sample", SCHEMA)

    def test_flattened_nested_schema_collision_is_explicit_preserve_only(self):
        # Outer.Types.Child is absent from a flattened dump; Child.Text is a
        # different definition, so wire5 cannot be interpreted as a string.
        child = b"\x0d" + struct.pack("<f", 1.5)
        rowraw = b"\x2a" + write_varint(len(child)) + child
        row = decode_message(rowraw, "Sample", SCHEMA)
        self.assertEqual(row["Child"]["$opaque_proto"], child.hex())
        self.assertEqual(row["Child"]["$schema"], "Outer.Types.Child")
        self.assertEqual(encode_message(row, "Sample", SCHEMA), rowraw)
        result = validate_table_payload(struct.pack("<I", len(rowraw)) + rowraw, [row], "Sample", SCHEMA)
        self.assertEqual(result["semantic_roundtrip"], "passed_for_interpreted_fields")
        self.assertEqual(result["opaque_policy"], "preserve_only")
        edited = json.loads(json.dumps(row))
        edited["Child"]["$opaque_proto"] = (b"\x0d" + struct.pack("<f", 2.5)).hex()
        with self.assertRaisesRegex(ValidationError, "preserve-only"):
            validate_opaque_preserved([row], [edited])
        validate_opaque_preserved([row], [row, row])

    def test_malformed_nested_bytes_never_become_opaque(self):
        with self.assertRaisesRegex(ValidationError, "length"):
            decode_message(b"\x2a\x03\x0a\x09x", "Sample", SCHEMA)

    def test_alternative_noah_headers_require_syntax_and_unique_key(self):
        source = b'/*\r\n source */\nexport const x = 1;'
        payload = b"NOAH" + pipeline.noah_xor(source, 123456)
        def syntax(args, **kwargs):
            return SimpleNamespace(returncode=0 if "--input-type=module" in args and kwargs["input"] == source else 1)
        with patch.object(pipeline.shutil, "which", return_value="node"), patch.object(pipeline.subprocess, "run", side_effect=syntax):
            plain, key, meta = pipeline.decode_noah_script(payload)
        self.assertEqual((plain, key, meta["syntax_mode"]), (source, 123456, "module"))
        with patch.object(pipeline.shutil, "which", return_value="node"), patch.object(pipeline.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValidationError, "0 validated"):
                pipeline.decode_noah_script(payload)

    def test_strong_noah_header_short_circuits_alternative_key_candidates(self):
        source = b'"use strict"; exports.Example = 1;'
        payload = b"NOAH" + pipeline.noah_xor(source, 998877)
        with patch.object(pipeline.subprocess, "run") as node:
            plain, key, metadata = pipeline.decode_noah_script(payload)
        node.assert_not_called()
        self.assertEqual((plain, key), (source, 998877))
        self.assertEqual(metadata["key_contract"], "unique_from_strong_12_byte_header")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ab = self.root / "game/BlazblueEntropyEffect_Data/StreamingAssets/ab"
        self.ab.mkdir(parents=True)
        (self.ab / "manifest").write_bytes(b"manifest")
        self.assets = {}
        self.add_asset("data/xlsx/sample.ab", "Sample", encode_table_rows([{"Id": 1, "Value": 0.5}], "Sample", SCHEMA))
        self.add_asset("data/xlsxfixed/samplefixedpointwrap.ab", "SampleFixedPointWrap", encode_table_rows([{"Id": 1, "Value": 1 << 31}], "SampleFixedPoint", SCHEMA))
        self.add_asset("data/js/example.ab", "Example", b'NOAH' + pipeline.noah_xor(b'"use strict"; exports.Example=1;', 12345))
        mod = self.root / "mods/test/mod.json"
        mod.parent.mkdir(parents=True)
        mod.write_text(json.dumps({"id": "test", "content": {"tables": {"Sample": []}}}))
        for build in ("1", "2"):
            path = self.root / f"tools/schema/{build}/proto_schema_snapshot.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema": SCHEMA}))
        self.modules = {"UnityPy": SimpleNamespace(load=self.load), "lz4": SimpleNamespace(),
                        "lz4.frame": SimpleNamespace(decompress=lambda raw: raw)}
        self.modules["lz4"].frame = self.modules["lz4.frame"]

    def add_asset(self, logical, name, payload):
        self.assets[logical] = (name, payload)

    def load(self, blob):
        name, payload = self.assets[blob.decode()]
        data = SimpleNamespace(m_Name=name, m_Script=payload)
        return SimpleNamespace(objects=[SimpleNamespace(type=SimpleNamespace(name="TextAsset"), read=lambda: data)])

    def run_pipeline(self, build="1", allow=None):
        entries, blob = [], bytearray()
        for logical in self.assets:
            entries.append({"r": logical, "m": "m_0.m", "s": len(blob)})
            blob += logical.encode()
        (self.ab / "m_0.m").write_bytes(blob)
        (self.ab / "merge.json").write_text(json.dumps(entries))
        args = argparse.Namespace(root=str(self.root), build_id=build, allow_failures=allow)
        with patch.dict(sys.modules, self.modules):
            return pipeline.run(args)

    def test_fresh_setup_replaces_stale_orig_and_is_build_isolated(self):
        old = self.root / "decoded/tables/Sample.json.orig"
        old.parent.mkdir(parents=True)
        old.write_text("stale")
        self.assertEqual(self.run_pipeline(), 0)
        self.assertEqual(json.loads(old.read_text()), [{"Id": 1, "Value": 0.5}])
        self.assertEqual(validate_baseline(self.root, "1")["build_id"], "1")
        self.assertEqual(self.run_pipeline("2"), 0)
        self.assertEqual(validate_baseline(self.root, "2")["build_id"], "2")
        self.assertTrue(list((self.root / ".baseline_history").glob("2_*/decoded/tables/Sample.json.orig")))
        with self.assertRaisesRegex(ValidationError, "installed build"):
            validate_baseline(self.root, "1")

    def test_required_script_failure_preserves_previous_baseline(self):
        self.assertEqual(self.run_pipeline(), 0)
        before = (self.root / "decoded/tables/Sample.json.orig").read_bytes()
        self.assets["data/js/example.ab"] = ("Example", b"NOAHbad")
        self.assertEqual(self.run_pipeline("2"), 1)
        self.assertEqual((self.root / "decoded/tables/Sample.json.orig").read_bytes(), before)
        self.assertEqual(validate_baseline(self.root, "1")["build_id"], "1")
        report = json.loads((self.root / "inspect/decode_report.failed.json").read_text())
        self.assertTrue(any(x["category"] == "required_js_missing" for x in report["failures"]))

    def test_required_truncated_table_never_publishes_partial_json(self):
        self.assets["data/xlsx/sample.ab"] = ("Sample", struct.pack("<I", 20) + b"x")
        self.assertEqual(self.run_pipeline(), 1)
        self.assertFalse((self.root / "decoded/tables/Sample.json").exists())

    def test_baseline_hash_guard_detects_tamper(self):
        self.assertEqual(self.run_pipeline(), 0)
        (self.root / "decoded/tables/Sample.json.orig").write_text("[]")
        with self.assertRaisesRegex(ValidationError, "baseline changed"):
            validate_baseline(self.root, "1")

    def test_nonrequired_unknown_table_is_explicitly_unverified(self):
        self.add_asset("data/xlsx/unknown.ab", "Unknown", b"anything")
        self.assertEqual(self.run_pipeline(), 0)
        report = json.loads((self.root / "inspect/decode_report.json").read_text())
        self.assertEqual(report["skipped"][0]["category"], "unknown_table_schema")
        self.assertFalse((self.root / "decoded/tables/Unknown.json").exists())

    def test_required_waiver_is_rejected(self):
        allow = self.root / "allow.json"
        allow.write_text(json.dumps({"data/xlsx/sample.ab": {"build_id": "1", "reason": "test"}}))
        self.assertEqual(self.run_pipeline(allow=str(allow)), 1)


class VerifyTableIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dec = self.root / "decoded"
        (self.dec / "tables").mkdir(parents=True)
        self.out = self.root / "patch_out"
        import os
        import validation_tables
        namespace = {"ROOT": str(self.root), "DEC": str(self.dec), "OUT": str(self.out),
                     "SCHEMA": SCHEMA, "json": json, "os": os}
        namespace.update(vars(validation_tables))
        namespace["current_build"] = lambda: "fixture"
        tree = ast.parse((ROOT / "make_patch.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "verify_table")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "make_patch.verify_table", "exec"), namespace)
        self.verify = namespace["verify_table"]

    def write_rows(self, original, current):
        (self.dec / "tables/Sample.json").write_text(json.dumps(current))
        (self.dec / "tables/Sample.json.orig").write_text(json.dumps(original))

    def test_make_patch_rejects_semantic_mismatch_and_counts_actual_changes(self):
        self.write_rows([{"Id": 1}], [{"Id": 2}, {"Id": 3}])
        raw = encode_table_rows([{"Id": 2}, {"Id": 3}], "Sample", SCHEMA)
        result = self.verify("Sample", raw)
        self.assertEqual(result["row_delta"], 1)
        self.assertTrue((self.root / "inspect/table_verification/fixture/Sample.json").is_file())
        self.assertFalse((self.out / "_verification").exists())
        with self.assertRaisesRegex(ValidationError, "semantic mismatch"):
            self.verify("Sample", encode_table_rows([{"Id": 2}, {"Id": 4}], "Sample", SCHEMA))

    def test_make_patch_enforces_fixed_original_bytes_and_changed_values(self):
        original = [{"Id": 1, "Value": 0.1}, {"Id": 2, "Value": 0.5}]
        current = [original[0], {"Id": 2, "Value": 0.25}, {"Id": 3, "Value": 1.0}]
        self.write_rows(original, current)
        baseline = [{"Id": 1, "Value": 429496730}, {"Id": 2, "Value": 1 << 31}]
        source = self.root / "extracted_raw/data/xlsxfixed/SampleFixedPointWrap.bin"
        source.parent.mkdir(parents=True)
        source.write_bytes(encode_table_rows(baseline, "SampleFixedPoint", SCHEMA))
        expected = expected_fixed_rows(current, original, source.read_bytes(), "Sample", SCHEMA)
        raw = encode_table_rows(expected, "SampleFixedPoint", SCHEMA)
        self.assertEqual(self.verify("SampleFixedPointWrap", raw)["unchanged_byte_identical_rows"], 1)
        # Different field order is semantically equal, but violates splicing's
        # promise to preserve untouched fixed-point rows byte for byte.
        expected[0] = {"Value": expected[0]["Value"], "Id": 1}
        with self.assertRaisesRegex(ValidationError, "rewritten"):
            self.verify("SampleFixedPointWrap", encode_table_rows(expected, "SampleFixedPoint", SCHEMA))


class FixedTableSpliceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dec = self.root / "decoded"
        self.raw = self.root / "extracted_raw"
        (self.dec / "tables").mkdir(parents=True)
        (self.raw / "data/xlsxfixed").mkdir(parents=True)
        import os
        import validation_tables
        namespace = dict(vars(validation_tables), DEC=str(self.dec), RAW=str(self.raw),
                         SCHEMA=SCHEMA, os=os, json=json, struct=struct)
        namespace["encode"] = lambda row, cls: encode_message(row, cls, SCHEMA)
        namespace["to_fixed_row"] = lambda row, cls: to_fixed_row(row, cls, SCHEMA)
        tree = ast.parse((ROOT / "make_patch.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "encode_fixed_table")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "make_patch.encode_fixed_table", "exec"), namespace)
        self.splice = namespace["encode_fixed_table"]

    def write_fixture(self, original, current, fixed):
        (self.dec / "tables/Sample.json").write_text(json.dumps(current))
        (self.dec / "tables/Sample.json.orig").write_text(json.dumps(original))
        self.baseline = encode_table_rows(fixed, "SampleFixedPoint", SCHEMA)
        (self.raw / "data/xlsxfixed/SampleFixedPointWrap.bin").write_bytes(self.baseline)
        self.original, self.current = original, current

    def assert_valid_splice(self, output):
        expected = expected_fixed_rows(self.current, self.original, self.baseline, "Sample", SCHEMA)
        validate_table_payload(output, expected, "SampleFixedPoint", SCHEMA, len(self.original))

    def test_duplicate_keys_edit_one_semantically_distinct_selector(self):
        original = [{"Id": 7, "Value": 0.1}, {"Id": 7, "Value": 0.2}, {"Id": 9, "Value": 0.3}]
        current = [original[0], {"Id": 7, "Value": 0.25}, original[2]]
        fixed = [{"Id": 7, "Value": 429496730}, {"Id": 7, "Value": 858993460}, {"Id": 9, "Value": 1288490189}]
        self.write_fixture(original, current, fixed)
        output = self.splice("Sample", ["Id"])
        bodies, source = split_table(output), split_table(self.baseline)
        self.assertEqual((bodies[0], bodies[2]), (source[0], source[2]))
        self.assertEqual(decode_message(bodies[1], "SampleFixedPoint", SCHEMA)["Value"], 1 << 30)
        self.assert_valid_splice(output)

    def test_default_field_equivalence_preserves_all_original_bytes(self):
        original = [{"Id": 7}, {"Id": 7}]
        current = [{"Id": 7, "Value": 0.0, "Ints": []}, {"Id": 7, "Enabled": False}]
        self.write_fixture(original, current, [{"Id": 7}, {"Id": 7, "Value": 0}])
        output = self.splice("Sample", ["Id"])
        self.assertEqual(output, self.baseline)
        self.assert_valid_splice(output)

    def test_delete_reorder_and_append_follow_current_json_order(self):
        original = [{"Id": 7, "Value": 0.1}, {"Id": 7, "Value": 0.2}, {"Id": 9, "Value": 0.3}]
        current = [original[2], original[0], {"Id": 10, "Value": -0.25}]
        fixed = [{"Id": 7, "Value": 429496730}, {"Id": 7, "Value": 858993460}, {"Id": 9, "Value": 1288490189}]
        self.write_fixture(original, current, fixed)
        output = self.splice("Sample")
        bodies, source = split_table(output), split_table(self.baseline)
        self.assertEqual(bodies[:2], [source[2], source[0]])
        self.assertEqual(decode_message(bodies[2], "SampleFixedPoint", SCHEMA), {"Id": 10, "Value": -(1 << 30)})
        self.assert_valid_splice(output)

    def test_identical_normal_duplicates_keep_their_original_fixed_precision(self):
        original = [{"Id": 7, "Value": 0.1}, {"Id": 7, "Value": 0.1}]
        fixed = [{"Id": 7, "Value": 429496730}, {"Id": 7, "Value": 429496731}]
        self.write_fixture(original, original, fixed)
        self.assertEqual(self.splice("Sample"), self.baseline)

    def test_baseline_count_mismatch_is_rejected_without_zip_truncation(self):
        self.write_fixture([{"Id": 7}, {"Id": 7}], [{"Id": 7}], [{"Id": 7}])
        with self.assertRaisesRegex(ValidationError, "counts differ"):
            self.splice("Sample")


if __name__ == "__main__":
    unittest.main()
