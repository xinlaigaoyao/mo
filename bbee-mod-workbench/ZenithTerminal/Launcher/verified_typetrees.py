"""Input-bound cache prioritizing layouts verified on complete real objects.

Native DummyDll generation remains an explicitly unverified candidate route.
Embedded layouts are promoted only after forced JSON-roundtripped rereads;
no read-length check is disabled here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def flattened(node):
    return [{key: value for key, value in item.items() if key != "m_Children"}
            for item in node.to_dict_list()]


def _semantic_hash(tree):
    def binary(value):
        if isinstance(value, (bytes, bytearray)):
            return {"$bytes": bytes(value).hex()}
        raise TypeError(f"Unsupported TypeTree value {type(value).__name__}")
    # Unity animation curves may contain infinities or NaNs. Stable serialized
    # values compare repeat reads without misclassifying NaN != NaN as a change.
    raw = json.dumps(tree, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=binary)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _name(assembly, fullname):
    if not assembly or not fullname or any(character in assembly + fullname for character in ("/", "\\", ":", "\0")):
        raise ValueError("Unsafe type cache name")
    assembly = assembly.removesuffix(".dll")
    return assembly, fullname, assembly + "__" + fullname + ".json"


def object_identity(obj, tree=None):
    """Bind the layout to the actual referenced MonoScript, not a caller label."""
    from UnityPy.classes import PPtr
    tree = obj.read_typetree(check_read=True) if tree is None else tree
    pointer = tree.get("m_Script")
    if not isinstance(pointer, dict) or not {"m_FileID", "m_PathID"} <= set(pointer):
        raise ValueError("Embedded MonoBehaviour has no resolvable MonoScript identity")
    script = PPtr(m_FileID=pointer["m_FileID"], m_PathID=pointer["m_PathID"],
                  assetsfile=obj.assets_file).deref_parse_as_object()
    fullname = (script.m_Namespace + "." if script.m_Namespace else "") + script.m_ClassName
    return script.m_AssemblyName.removesuffix(".dll"), fullname


def game_inputs(root):
    import UnityPy
    data = Path(root) / "game" / "BlazblueEntropyEffect_Data"
    managers = data / "globalgamemanagers"
    versions = {str(asset.unity_version) for asset in UnityPy.load(str(managers)).files.values()
                if hasattr(asset, "unity_version")}
    if len(versions) != 1:
        raise ValueError("Cannot establish one Unity version from the actual game header")
    return {"unity_version": versions.pop(), "globalgamemanagers_sha256": _sha(managers),
            "gameassembly_sha256": _sha(data.parent / "GameAssembly.dll"),
            "metadata_sha256": _sha(data / "il2cpp_data" / "Metadata" / "global-metadata.dat")}


class CachedTypeTrees:
    def __init__(self, root, build_id, *, inputs=None, factory=None):
        self.root, self.build = Path(root).resolve(), str(build_id)
        if not self.build.isdigit():
            raise ValueError("TypeTree cache requires an explicit numeric game build")
        self.dir = self.root / "tools" / "typetrees" / self.build
        self.inputs = game_inputs(self.root) if inputs is None else dict(inputs)
        if not isinstance(self.inputs.get("unity_version"), str) or not self.inputs["unity_version"]:
            raise ValueError("TypeTree inputs have no actual Unity version")
        self.factory = factory
        self.real = None
        self.nodes = {}
        self.candidate_requests = []
        index = self.dir / "index.json"
        self.index = json.loads(index.read_text("utf-8")) if index.exists() else {
            "format": 2, "build_id": self.build, "inputs": self.inputs, "files": {}, "layouts": {}}
        if self.index.get("format") not in (1, 2) or self.index.get("build_id") != self.build or self.index.get("inputs") != self.inputs:
            raise ValueError("TypeTree cache is from a different game input/version")
        if not isinstance(self.index.get("files"), dict) or not isinstance(self.index.get("layouts", {}), dict):
            raise ValueError("Invalid TypeTree cache index")
        self.index.setdefault("layouts", {})  # v1 generated entries were never verified on real objects.

    def _real(self):
        if self.real is None:
            dump = self.root / "dump"
            if not (dump / "provenance.json").is_file() or not (dump / "game_build.txt").is_file():
                raise ValueError("No verified TypeTree cache and no provenance-bound DummyDll fallback; seed an embedded layout first")
            provenance = json.loads((dump / "provenance.json").read_text("utf-8"))
            if (dump / "game_build.txt").read_text("utf-8").strip() != self.build or provenance.get("build_id") != self.build:
                raise ValueError("DummyDll metadata dump belongs to a different build")
            for name in ("gameassembly_sha256", "metadata_sha256"):
                if provenance.get(name) != self.inputs[name]:
                    raise ValueError("DummyDll provenance differs from game input")
            dll = dump / "DummyDll"
            if any(path.is_symlink() for path in dll.glob("*.dll")):
                raise ValueError("DummyDll input must not be a symlink")
            # Bind every generated assembly. A stamped dump alone cannot detect a stale or edited DLL.
            dll_hashes = {path.name: _sha(path) for path in sorted(dll.glob("*.dll"))}
            if not dll_hashes:
                raise ValueError("No generated DummyDll assemblies are available")
            known = self.index.get("dummy_dll_hashes")
            if known is not None and known != dll_hashes:
                raise ValueError("Generated DummyDll files differ from the cache's source")
            if self.factory is None:
                from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
                self.real = TypeTreeGenerator(self.inputs["unity_version"])
            else:
                self.real = self.factory(self.inputs["unity_version"])
            self.real.load_local_dll_folder(str(dll))
            self.index["dummy_dll_hashes"] = dll_hashes
        return self.real

    def _load(self, name):
        path = self.dir / name
        expected = self.index["files"].get(name)
        if expected is None or not path.is_file() or path.is_symlink() or _sha(path) != expected:
            raise ValueError("TypeTree cache hash mismatch/missing: " + name)
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode
        return TypeTreeNode.from_list(json.loads(path.read_text("utf-8")))

    def _store(self, name, node, information):
        path = self.dir / name
        _write(path, flattened(node))
        self.index["format"] = 2
        self.index["files"][name] = _sha(path)
        self.index["layouts"][name] = information
        _write(self.dir / "index.json", self.index)

    def generate_candidate(self, assembly, fullname):
        """Generate without claiming or caching full-object compatibility."""
        assembly, fullname, _ = _name(assembly, fullname)
        return self._real().get_nodes_up(assembly, fullname)

    def cache_embedded_object(self, obj, *, logical_bundle, bundle_sha256, expected_type=None):
        node = getattr(getattr(obj, "serialized_type", None), "node", None)
        if node is None:
            raise ValueError("Object has no embedded layout to verify")
        embedded = obj.read_typetree(nodes=node, check_read=True)
        assembly, fullname = object_identity(obj, embedded)
        assembly, fullname, name = _name(assembly, fullname)
        if expected_type is not None and (assembly, fullname) != (expected_type[0].removesuffix(".dll"), expected_type[1]):
            raise ValueError("Embedded MonoScript identity differs from the requested cached type")
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode
        encoded = json.loads(json.dumps(flattened(node)))
        cloned = TypeTreeNode.from_list(encoded)
        forced = obj.read_typetree(nodes=cloned, check_read=True)
        if _semantic_hash(embedded) != _semantic_hash(forced):
            raise ValueError("JSON-roundtripped embedded layout changes the actual object")
        if not isinstance(bundle_sha256, str) or len(bundle_sha256) != 64 or any(character not in "0123456789abcdefABCDEF" for character in bundle_sha256):
            raise ValueError("Embedded layout needs a bound source-bundle SHA-256")
        information = {"source": "embedded-verified", "check_read": True,
                       "assembly": assembly, "fullname": fullname, "logical_bundle": logical_bundle,
                       "bundle_sha256": bundle_sha256.lower(), "path_id": obj.path_id,
                       "object_sha256": hashlib.sha256(obj.get_raw_data()).hexdigest(),
                       "semantic_sha256": _semantic_hash(forced), "nodes": len(encoded)}
        previous = self.index["layouts"].get(name, {})
        if previous.get("source") == "embedded-verified" and name in self.index["files"]:
            if flattened(self._load(name)) != encoded:
                raise ValueError("Conflicting embedded layouts for the same build/type")
        self._store(name, cloned, information)
        self.nodes[(assembly, fullname)] = cloned
        return information

    def get_nodes_up(self, assembly, fullname):
        assembly, fullname, name = _name(assembly, fullname)
        key = (assembly, fullname)
        if key in self.nodes:
            return self.nodes[key]
        expected = self.index["files"].get(name)
        information = self.index["layouts"].get(name, {})
        if expected is not None:
            node = self._load(name)
            if information.get("source") == "embedded-verified" and (information.get("assembly"), information.get("fullname")) != key:
                raise ValueError("Verified TypeTree cache identity mismatch")
            if information.get("source") != "embedded-verified" or information.get("check_read") is not True:
                self._real()
                self.candidate_requests.append({"assembly": assembly, "fullname": fullname,
                                                "status": "generated-unverified-cache"})
        else:
            if (self.dir / name).exists():
                raise ValueError("Unindexed TypeTree cache file: " + name)
            node = self.generate_candidate(assembly, fullname)
            self._store(name, node, {"source": "generated-unverified", "check_read": False,
                                    "assembly": assembly, "fullname": fullname})
            self.candidate_requests.append({"assembly": assembly, "fullname": fullname,
                                            "status": "generated-unverified"})
        self.nodes[key] = node
        return node
