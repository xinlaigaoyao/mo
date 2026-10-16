"""Prepared for unified verification: real node parsing, hash/version/cache gates.

These tests use temporary payloads and directories. They do not run the real
game probe, regenerate mods or launch a build.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verified_typetrees
from verified_typetrees import CachedTypeTrees, flattened
from typetree_probe import layout_differences

try:
    import UnityPy
except ImportError:
    UnityPy = None

INPUTS = {"unity_version": "2022.3.62f2", "globalgamemanagers_sha256": "a" * 64,
          "gameassembly_sha256": "b" * 64, "metadata_sha256": "c" * 64}


def fixture_node():
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode
    definitions = [(0, "MonoBehaviour", "Base", -1), (1, "PPtr<MonoScript>", "m_Script", 12),
                   (2, "int", "m_FileID", 4), (2, "SInt64", "m_PathID", 8),
                   (1, "string", "m_Name", -1), (1, "int", "Value", 4)]
    return TypeTreeNode.from_list([
        {"m_Level": level, "m_Type": typ, "m_Name": name, "m_ByteSize": size,
         "m_Version": 1, "m_TypeFlags": 0, "m_Index": index, "m_MetaFlag": 0}
        for index, (level, typ, name, size) in enumerate(definitions)])


class FixtureObject:
    """Uses UnityPy's actual TypeTree reader, with a local MonoScript identity."""
    def __init__(self):
        self.serialized_type = types.SimpleNamespace(node=fixture_node())
        self.path_id = 1
        self.type = types.SimpleNamespace(name="MonoBehaviour")
        name = b"Fixture"
        text = struct.pack("<I", len(name)) + name
        text += b"\0" * (-len(text) % 4)
        self.raw = struct.pack("<iq", 0, 2) + text + struct.pack("<i", 17)
        script = types.SimpleNamespace(m_AssemblyName="Assembly-CSharp.dll", m_Namespace="Fixture", m_ClassName="Type")
        script_object = types.SimpleNamespace(parse_as_object=lambda: script)
        self.assets_file = types.SimpleNamespace(objects={2: script_object}, ref_types=[])

    def read_typetree(self, nodes=None, check_read=True):
        from UnityPy.helpers.TypeTreeHelper import read_typetree
        from UnityPy.streams import EndianBinaryReader
        return read_typetree(nodes or self.serialized_type.node, EndianBinaryReader(self.raw, endian="<"),
                             byte_size=len(self.raw), check_read=check_read, assetsfile=self.assets_file)

    def get_raw_data(self):
        return self.raw


@unittest.skipIf(UnityPy is None, "Use bundled Python for actual TypeTree node fixtures")
class VerifiedCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.obj = FixtureObject()

    def cache(self, **kwargs):
        return CachedTypeTrees(self.root, "123", inputs=deepcopy(INPUTS), **kwargs)

    def seed(self):
        cache = self.cache()
        info = cache.cache_embedded_object(self.obj, logical_bundle="actor/fixture.ab", bundle_sha256="d" * 64,
                                          expected_type=("Assembly-CSharp", "Fixture.Type"))
        return cache, info

    def native_dump(self):
        dump = self.root / "dump"
        (dump / "DummyDll").mkdir(parents=True)
        (dump / "game_build.txt").write_text("123", encoding="utf-8")
        (dump / "provenance.json").write_text(json.dumps({"build_id": "123",
            "gameassembly_sha256": INPUTS["gameassembly_sha256"], "metadata_sha256": INPUTS["metadata_sha256"]}), encoding="utf-8")
        (dump / "DummyDll/Assembly-CSharp.dll").write_bytes(b"temporary generated metadata DLL")
        return dump

    def test_verified_embedded_cache_works_without_dump_or_native_factory(self):
        _, info = self.seed()
        self.assertEqual(info["source"], "embedded-verified")
        self.assertTrue(info["check_read"])
        def prohibited(version):
            self.fail("verified cache initialized the native generator")
        offline = self.cache(factory=prohibited)
        node = offline.get_nodes_up("Assembly-CSharp.dll", "Fixture.Type")
        self.assertEqual(self.obj.read_typetree(node, check_read=True)["Value"], 17)
        self.assertEqual(offline.candidate_requests, [])

    def test_cache_hash_drift_is_rejected(self):
        cache, _ = self.seed()
        path = cache.dir / "Assembly-CSharp__Fixture.Type.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.cache().get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_actual_version_or_game_input_change_rejects_cache(self):
        self.seed()
        for field, value in (("unity_version", "2022.3.62f3"), ("metadata_sha256", "e" * 64),
                             ("gameassembly_sha256", "f" * 64), ("globalgamemanagers_sha256", "0" * 64)):
            with self.subTest(field=field):
                altered = dict(INPUTS)
                altered[field] = value
                with self.assertRaisesRegex(ValueError, "different game input/version"):
                    CachedTypeTrees(self.root, "123", inputs=altered)

    def test_missing_verified_cache_and_dump_fails(self):
        with self.assertRaisesRegex(ValueError, "No verified TypeTree cache"):
            self.cache().get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_unindexed_cache_is_not_trusted(self):
        cache = self.cache()
        cache.dir.mkdir(parents=True)
        (cache.dir / "Assembly-CSharp__Fixture.Type.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unindexed"):
            cache.get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_cache_file_missing_is_not_regenerated_silently(self):
        cache, _ = self.seed()
        (cache.dir / "Assembly-CSharp__Fixture.Type.json").unlink()
        with self.assertRaisesRegex(ValueError, "hash mismatch/missing"):
            self.cache().get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_verified_index_identity_mismatch_is_rejected(self):
        cache, _ = self.seed()
        index = cache.dir / "index.json"
        data = json.loads(index.read_text(encoding="utf-8"))
        data["layouts"]["Assembly-CSharp__Fixture.Type.json"]["fullname"] = "Different.Type"
        index.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.cache().get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_wrong_monoscript_identity_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError, "MonoScript identity"):
            self.cache().cache_embedded_object(self.obj, logical_bundle="actor/fixture.ab", bundle_sha256="d" * 64,
                                               expected_type=("Assembly-CSharp", "Different.Type"))
        self.assertFalse((self.root / "tools").exists())

    def test_truncated_object_does_not_produce_verified_cache(self):
        self.obj.raw = self.obj.raw[:-1]
        with self.assertRaises(Exception):
            self.cache().cache_embedded_object(self.obj, logical_bundle="actor/fixture.ab", bundle_sha256="d" * 64)
        self.assertFalse((self.root / "tools").exists())

    def test_conflicting_embedded_layout_is_not_silently_replaced(self):
        cache, _ = self.seed()
        nodes = flattened(self.obj.serialized_type.node)
        nodes[-1]["m_Name"] = "OtherValue"
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode
        self.obj.serialized_type.node = TypeTreeNode.from_list(nodes)
        with self.assertRaisesRegex(ValueError, "Conflicting embedded layouts"):
            cache.cache_embedded_object(self.obj, logical_bundle="actor/other.ab", bundle_sha256="d" * 64)

    def test_generated_candidate_uses_f2_and_is_explicitly_unverified(self):
        self.native_dump()
        versions, folders = [], []
        class Native:
            def __init__(native, version):
                versions.append(version)
            def load_local_dll_folder(native, folder):
                folders.append(folder)
            def get_nodes_up(native, assembly, fullname):
                return fixture_node()
        cache = self.cache(factory=Native)
        cache.get_nodes_up("Assembly-CSharp", "Fixture.Type")
        self.assertEqual(versions, ["2022.3.62f2"])
        self.assertEqual(len(folders), 1)
        self.assertEqual(cache.index["layouts"]["Assembly-CSharp__Fixture.Type.json"]["source"], "generated-unverified")
        self.assertFalse(cache.index["layouts"]["Assembly-CSharp__Fixture.Type.json"]["check_read"])
        self.assertEqual(len(cache.candidate_requests), 1)

    def test_generated_cache_does_not_become_verified_offline_fallback(self):
        dump = self.native_dump()
        native = types.SimpleNamespace(load_local_dll_folder=lambda folder: None,
                                       get_nodes_up=lambda assembly, fullname: fixture_node())
        self.cache(factory=lambda version: native).get_nodes_up("Assembly-CSharp", "Fixture.Type")
        (dump / "provenance.json").unlink()
        with self.assertRaisesRegex(ValueError, "No verified TypeTree cache"):
            self.cache().get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_dummy_dll_hash_change_is_rejected_for_candidate_route(self):
        dump = self.native_dump()
        native = types.SimpleNamespace(load_local_dll_folder=lambda folder: None,
                                       get_nodes_up=lambda assembly, fullname: fixture_node())
        self.cache(factory=lambda version: native).get_nodes_up("Assembly-CSharp", "Fixture.Type")
        (dump / "DummyDll/Assembly-CSharp.dll").write_bytes(b"changed DLL")
        with self.assertRaisesRegex(ValueError, "DummyDll files differ"):
            self.cache(factory=lambda version: native).get_nodes_up("Assembly-CSharp", "Fixture.Type")

    def test_layout_diff_reports_real_alignment_and_array_type_changes(self):
        original = fixture_node()
        values = flattened(original)
        values[1]["m_MetaFlag"] = 0x4000
        values[-1]["m_Type"] = "float"
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode
        differences = layout_differences(original, TypeTreeNode.from_list(values))
        changes = {value["path"]: value for value in differences["type_or_alignment_differences"]}
        self.assertTrue(changes["Base/m_Script"]["generated_align4"])
        self.assertEqual(changes["Base/Value"]["generated_type"], "float")

    def test_actual_globalgamemanagers_version_is_used(self):
        data = self.root / "game/BlazblueEntropyEffect_Data"
        metadata = data / "il2cpp_data/Metadata"
        metadata.mkdir(parents=True)
        (data / "globalgamemanagers").write_bytes(b"temporary manager bytes")
        (data.parent / "GameAssembly.dll").write_bytes(b"temporary assembly bytes")
        (metadata / "global-metadata.dat").write_bytes(b"temporary metadata bytes")
        environment = types.SimpleNamespace(files={"main": types.SimpleNamespace(unity_version="2022.3.62f2")})
        with patch.object(UnityPy, "load", return_value=environment):
            inputs = verified_typetrees.game_inputs(self.root)
        self.assertEqual(inputs["unity_version"], "2022.3.62f2")
        self.assertEqual(inputs["metadata_sha256"], hashlib.sha256(b"temporary metadata bytes").hexdigest())


if __name__ == "__main__":
    unittest.main()
