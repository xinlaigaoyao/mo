"""Real small UnityFS/serialized fixtures plus corruptions; no game installation."""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_verification import (BuildVerificationError, verify_build, unityfs_directory,
    validate_managed_references, validate_manifest_additions, _noah_xor)
from validation_tables import encode_table_rows

try:
    import UnityPy
except ImportError:
    UnityPy = None


def aligned_text(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    data = struct.pack("<I", len(raw)) + raw
    return data + b"\0" * (-len(data) % 4)


def make_serialized(objects, cab="CAB-fixture", externals=(), pointer_type=False):
    """Generate Unity's real v17 metadata and object data, not a mocked loader."""
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode
    from UnityPy.streams import EndianBinaryWriter
    node = None
    if pointer_type:
        node = TypeTreeNode.from_list([
            {"m_Level": level, "m_Type": typ, "m_Name": name, "m_ByteSize": size, "m_Version": 1,
             "m_TypeFlags": 0, "m_Index": index, "m_MetaFlag": 0}
            for index, (level, typ, name, size) in enumerate([
                (0, "Fixture", "Base", -1), (1, "string", "m_Name", -1),
                (1, "PPtr<Object>", "m_Target", 12), (2, "int", "m_FileID", 4),
                (2, "SInt64", "m_PathID", 8)])])
    metadata = EndianBinaryWriter(endian="<")
    metadata.write_string_to_null("2022.3.62f2")
    metadata.write_int(5)
    metadata.write_boolean(pointer_type)
    metadata.write_int(1)
    metadata.write_int(114 if pointer_type else 49)
    metadata.write_boolean(False)
    metadata.write_short(-1)
    if pointer_type:
        metadata.write_bytes(b"\0" * 16)  # MonoBehaviour script hash
    metadata.write_bytes(b"\0" * 16)
    if pointer_type:
        node.dump_blob(metadata, 17)
    metadata.write_int(len(objects))
    data = bytearray()
    for object_id, name, payload in objects:
        body = aligned_text(name) + (struct.pack("<iq", *payload) if pointer_type else aligned_text(payload))
        metadata.align_stream(4)
        metadata.write_long(object_id)
        metadata.write_u_int(len(data))
        metadata.write_u_int(len(body))
        metadata.write_int(0)
        data += body
        data += b"\0" * (-len(data) % 8)
    metadata.write_int(0)  # scripts
    metadata.write_int(len(externals))
    for external in externals:
        metadata.write_string_to_null("")
        metadata.write_bytes(b"\0" * 16)
        metadata.write_int(0)
        metadata.write_string_to_null("archive:/" + external + "/" + external)
    metadata.write_string_to_null("")
    meta = metadata.bytes
    data_offset = (20 + len(meta) + 15) // 16 * 16
    header = struct.pack(">IIII", len(meta), data_offset + len(data), 17, data_offset) + b"\0" * 4
    return header + meta + b"\0" * (data_offset - 20 - len(meta)) + data


def make_bundle(serialized, cab="CAB-fixture", compression=False, end_info=False):
    info = b"\0" * 16 + struct.pack(">iIIHiqqI", 1, len(serialized), len(serialized), 0,
                                        1, 0, len(serialized), 4) + cab.encode() + b"\0"
    if compression:
        import lz4.block
        packed = lz4.block.compress(info, store_size=False)
    else:
        packed = info
    prefix = b"UnityFS\0" + struct.pack(">I", 6) + b"5.x.x\0" + b"2022.3.62f2\0"
    flags = 64 | (2 if compression else 0) | (128 if end_info else 0)
    header = prefix + struct.pack(">QIII", len(prefix) + 20 + len(packed) + len(serialized), len(packed), len(info), flags)
    return header + (serialized + packed if end_info else packed + serialized)


class ManagedAndManifestTests(unittest.TestCase):
    def test_managed_references_resolve_and_missing_or_duplicate_fail(self):
        tree = {"uses": [{"rid": 4}, {"rid": -2}], "references": {"RefIds": [
            {"rid": 4, "type": {"class": "Fixture"}, "data": {"next": {"rid": 4}}}]}}
        self.assertEqual(validate_managed_references(tree, "fixture")["definitions"], 1)
        tree["uses"][0]["rid"] = 5
        with self.assertRaisesRegex(BuildVerificationError, "unresolved"):
            validate_managed_references(tree, "fixture")
        tree["uses"][0]["rid"] = 4
        tree["references"]["RefIds"] *= 2
        with self.assertRaisesRegex(BuildVerificationError, "duplicate"):
            validate_managed_references(tree, "fixture")

    def test_manifest_names_require_real_output_and_dependency_entries(self):
        adds = {"names": ["actor/new"], "entries": [["actor/new", ["actor/original"]]],
                "guids": [["actor/new", "1234" * 8]]}
        self.assertEqual(validate_manifest_additions(adds, {"actor/new.ab"})["names"], ["actor/new"])
        with self.assertRaisesRegex(BuildVerificationError, "no staged"):
            validate_manifest_additions(adds, set())
        adds["entries"] = []
        with self.assertRaisesRegex(BuildVerificationError, "dependency entries"):
            validate_manifest_additions(adds, {"actor/new.ab"})


@unittest.skipIf(UnityPy is None, "Run with bundled Interpreter Python for real UnityPy fixtures")
class RealBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "patch_out"
        self.output.mkdir()
        self.schema = {"FixtureTable": {"1": ["Id", "uint"], "2": ["Value", "float"]},
                       "FixtureTableFixedPoint": {"1": ["Id", "uint"], "2": ["Value", "long"]}}
        for folder in ("inspect", "decoded/tables", "decoded/data/js/core", "extracted_raw/data/xlsxfixed"):
            (self.root / folder).mkdir(parents=True)
        self.current = [{"Id": 1, "Value": 1.25}]
        (self.root / "inspect/proto_schema.json").write_text(json.dumps(self.schema), encoding="utf-8")
        (self.root / "inspect/js_keys.json").write_text("{}", encoding="utf-8")
        (self.root / "decoded/tables/FixtureTable.json").write_text(json.dumps(self.current), encoding="utf-8")
        (self.root / "decoded/tables/FixtureTable.json.orig").write_text(json.dumps(self.current), encoding="utf-8")
        (self.root / "inspect/decode_report.json").write_text('{"status":"passed","build_id":"123"}', encoding="utf-8")
        self.immutable = ["inspect/proto_schema.json", "inspect/js_keys.json", "decoded/tables/FixtureTable.json.orig"]
        self.baseline()
        (self.output / "_build.json").write_text('{"gameBuild":"123","mods":{}}', encoding="utf-8")

    def baseline(self):
        files = {relative: hashlib.sha256((self.root / relative).read_bytes()).hexdigest() for relative in self.immutable}
        (self.root / "inspect/baseline_manifest.json").write_text(json.dumps({"format": 1, "build_id": "123", "files": files}), encoding="utf-8")

    def stage(self, relative, objects, cab="CAB-fixture", **options):
        data = make_bundle(make_serialized(objects, cab, **options), cab)
        path = self.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def verify(self):
        return verify_build(self.root, self.output, "123")

    def test_real_table_bundle_readback_matches_composed_rows(self):
        raw = encode_table_rows(self.current, "FixtureTable", self.schema)
        self.stage("data/xlsx/fixturetable.ab", [(1, "FixtureTable", raw)])
        report = self.verify()
        self.assertEqual(report["status"], "passed")
        table = next(file for file in report["files"] if file["kind"] == "bundle")
        self.assertEqual(table["payload"]["rows"], 1)
        self.assertEqual(table["payload"]["semantic_roundtrip"], "passed")
        self.assertIn("_build.json", report["metadata_hashes"])

    def test_real_table_payload_mismatch_blocks_verification(self):
        raw = encode_table_rows([{"Id": 1, "Value": 9}], "FixtureTable", self.schema)
        self.stage("data/xlsx/fixturetable.ab", [(1, "FixtureTable", raw)])
        with self.assertRaisesRegex(Exception, "semantic mismatch"):
            self.verify()

    def test_real_fixed_table_payload_matches_exact_fixed_semantics(self):
        original = encode_table_rows([{"Id": 1, "Value": 5368709120}], "FixtureTableFixedPoint", self.schema)
        baseline = self.root / "extracted_raw/data/xlsxfixed/FixtureTableFixedPointWrap.bin"
        baseline.write_bytes(original)
        self.immutable.append(baseline.relative_to(self.root).as_posix())
        self.baseline()
        self.stage("data/xlsxfixed/fixturetablefixedpointwrap.ab", [(1, "FixtureTableFixedPointWrap", original)])
        self.assertEqual(next(file for file in self.verify()["files"] if file["kind"] == "bundle")["payload"]["kind"], "fixed_table")

    def test_real_noah_js_payload_roundtrip_and_mismatch(self):
        path = self.root / "decoded/data/js/core/Fixture.js"
        path.write_bytes(b"exports.value = 1;\n")
        (self.root / "inspect/js_keys.json").write_text('{"data/js/core/Fixture":"12345678"}', encoding="utf-8")
        self.baseline()
        self.stage("data/js/core/fixture.ab", [(1, "Fixture", b"NOAH" + _noah_xor(path.read_bytes(), 0x12345678))])
        report = self.verify()
        self.assertTrue(next(file for file in report["files"] if file["kind"] == "bundle")["payload"]["noah"])
        path.write_bytes(b"exports.value = 2;\n")
        with self.assertRaisesRegex(BuildVerificationError, "does not equal"):
            self.verify()

    def test_actual_unitypy_repack_lz4_and_end_directory(self):
        serialized = make_serialized([(1, "Fixture", b"data")])
        for compressed in (False, True):
            for at_end in (False, True):
                raw = make_bundle(serialized, compression=compressed, end_info=at_end)
                self.assertEqual(unityfs_directory(io.BytesIO(raw), length=len(raw))["blocks"], 1)
                env = UnityPy.load(raw)
                rewritten = env.file.save(packer="lz4")
                self.assertEqual(unityfs_directory(io.BytesIO(rewritten), length=len(rewritten))["nodes"][0]["path"], "CAB-fixture")

    def test_declared_length_corruption_is_rejected(self):
        path = self.stage("actor/test.ab", [(1, "Fixture", b"data")])
        path.write_bytes(path.read_bytes() + b"extra")
        with self.assertRaisesRegex(BuildVerificationError, "declared length"):
            self.verify()

    def test_duplicate_object_ids_cannot_hide_in_unitypy_dictionary(self):
        self.stage("actor/test.ab", [(1, "Fixture", b"one"), (1, "Second", b"two")])
        with self.assertRaisesRegex(BuildVerificationError, "duplicate/null object ID"):
            self.verify()

    def test_real_local_pptr_is_checked_and_dangling_pointer_fails(self):
        path = self.stage("actor/test.ab", [(1, "One", (0, 2)), (2, "Two", (0, 0))], pointer_type=True)
        report = self.verify()
        bundle = next(file for file in report["files"] if file["kind"] == "bundle")
        self.assertEqual(bundle["pointers"]["local"], 1)
        path.unlink()
        self.stage("actor/test.ab", [(1, "One", (0, 99))], pointer_type=True)
        with self.assertRaisesRegex(BuildVerificationError, "dangling local PPtr"):
            self.verify()

    def test_real_external_pptr_resolves_staged_cab_and_rejects_missing_object(self):
        self.stage("actor/target.ab", [(2, "Target", b"data")], cab="CAB-target")
        source = self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-target"])
        self.assertEqual(self.verify()["external_pointers"]["checked"], 1)
        source.unlink()
        self.stage("actor/source.ab", [(1, "Source", (1, 99))], cab="CAB-source", pointer_type=True, externals=["CAB-target"])
        with self.assertRaisesRegex(BuildVerificationError, "dangling external PPtr"):
            self.verify()

    def test_real_external_file_index_out_of_bounds_fails(self):
        self.stage("actor/source.ab", [(1, "Source", (2, 99))], cab="CAB-source", pointer_type=True, externals=["CAB-target"])
        with self.assertRaisesRegex(BuildVerificationError, "file index 2 is out of range"):
            self.verify()

    def test_builtin_external_boundary_is_explicit_in_passed_report(self):
        self.stage("actor/source.ab", [(1, "Source", (1, 99))], cab="CAB-source", pointer_type=True, externals=["unity_builtin_extra"])
        report = self.verify()
        self.assertEqual(report["external_pointers"]["checked"], 0)
        self.assertEqual(report["external_pointers"]["builtin_targets_not_object_checked"], ["unity_builtin_extra"])

    def test_header_only_baseline_cab_index_and_lazy_object_load(self):
        ab = self.root / "game/BlazblueEntropyEffect_Data/StreamingAssets/ab"
        ab.mkdir(parents=True)
        target = make_bundle(make_serialized([(2, "Target", b"data")]), "CAB-baseline")
        (ab / "m_a.m").write_bytes(target)
        (ab / "merge.json").write_text('[{"r":"actor/target.ab","m":"m_a.m","s":0}]', encoding="utf-8")
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-baseline"])
        report = self.verify()
        self.assertEqual(report["external_pointers"]["checked"], 1)
        self.assertEqual(report["external_pointers"]["lazy_loaded_cabs"], 1)
        self.assertEqual(report["external_pointers"]["header_indexed_bundles"], 1)

    def merged_baseline(self, segments):
        ab = self.root / "game/BlazblueEntropyEffect_Data/StreamingAssets/ab"
        ab.mkdir(parents=True, exist_ok=True)
        rows, blob = [], bytearray()
        for logical, raw in segments:
            rows.append({"r": logical, "m": "m_fixture.m", "s": len(blob)})
            blob += raw
        (ab / "m_fixture.m").write_bytes(blob)
        (ab / "merge.json").write_text(json.dumps(rows), encoding="utf-8")

    def test_source_index_classifies_three_exact_non_bundle_metadata_formats(self):
        import lz4.frame
        target = make_bundle(make_serialized([(2, "Target", b"data")]), "CAB-baseline")
        self.merged_baseline([
            ("manifest", lz4.frame.compress(b"FastManifest V3\r\nN:0\r\nN:0\r\nN:0\r\n----\r\n")),
            ("shadervariantinfos", b"s:consolecontents/effect/shader\n"),
            ("buildlogtep.json", b'{"Date":"fixture"}\r\n'),
            ("actor/target.ab", target)])
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-baseline"])
        report = self.verify()
        self.assertEqual(report["external_pointers"]["checked"], 1)
        self.assertEqual(report["external_pointers"]["header_indexed_bundles"], 1)
        metadata = report["external_pointers"]["non_bundle_source_segments"]
        self.assertEqual({entry["logical_names"][0] for entry in metadata}, {"manifest", "shadervariantinfos", "buildlogtep.json"})

    def test_source_index_rejects_unknown_non_bundle_instead_of_skipping(self):
        self.merged_baseline([("actor/broken.ab", b"not a bundle")])
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-baseline"])
        with self.assertRaisesRegex(BuildVerificationError, "unrecognized non-UnityFS baseline segment"):
            self.verify()

    def test_source_index_rejects_known_metadata_name_with_wrong_signature(self):
        self.merged_baseline([("manifest", b'{"wrong":"format"}')])
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-baseline"])
        with self.assertRaisesRegex(BuildVerificationError, "unrecognized non-UnityFS baseline segment"):
            self.verify()

    def test_source_index_still_rejects_malformed_unityfs(self):
        self.merged_baseline([("actor/broken.ab", b"UnityFS\0truncated")])
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-baseline"])
        with self.assertRaisesRegex(BuildVerificationError, "truncated resource"):
            self.verify()

    def test_non_bundle_source_classification_cannot_satisfy_missing_external_target(self):
        self.merged_baseline([("buildlogtep.json", b'{"cab":"CAB-missing"}')])
        self.stage("actor/source.ab", [(1, "Source", (1, 2))], cab="CAB-source", pointer_type=True, externals=["CAB-missing"])
        with self.assertRaisesRegex(BuildVerificationError, "0 baseline targets"):
            self.verify()

    def test_staged_raw_metadata_has_no_unityfs_exception(self):
        destination = self.output / "actor/invalid.ab"
        destination.parent.mkdir()
        destination.write_bytes(b'{"not":"a staged UnityFS resource"}')
        with self.assertRaises(BuildVerificationError):
            self.verify()

    def test_immutable_baseline_change_blocks_output_gate(self):
        self.stage("actor/test.ab", [(1, "Fixture", b"data")])
        (self.root / self.immutable[0]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "baseline changed"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
