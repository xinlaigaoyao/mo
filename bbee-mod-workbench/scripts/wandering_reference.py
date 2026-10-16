"""Read-only, source-bound Wandering Sword PAK v11 reference inventory.

This exports selected *raw Unreal package members*, not decoded pictures/audio.
No executable, DLL, UE4SS plugin or game configuration is loaded or executed.
PAK layout references: trumank/repak footer.rs, pak.rs, entry.rs and data.rs.
The CLI intentionally has no alternate source, AES key, bulk-extract or overwrite.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import sys
from typing import BinaryIO
import uuid
import zlib

SOURCE_ROOT = Path(r"E:\SteamLibrary\steamapps\common\Wandering Sword")
PAK_PATH = SOURCE_ROOT / "Wandering_Sword/Content/Paks/Wandering_Sword-WindowsNoEditor.pak"
EXPECTED_PAK_SHA256 = "5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff"
WORKBENCH = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = WORKBENCH / "references/wandering-sword"
MAX_INDEX_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 500_000
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 64
REPARSE_POINT = 0x400


class ReferenceError(ValueError):
    """An unsupported, changed or unsafe input must stop the operation."""


def checked_read(reader: BinaryIO, count: int) -> bytes:
    if count < 0:
        raise ReferenceError("Negative read length")
    data = reader.read(count)
    if len(data) != count:
        raise ReferenceError("Truncated PAK metadata or payload")
    return data


def unpack(reader: BinaryIO, fmt: str) -> tuple:
    return struct.unpack(fmt, checked_read(reader, struct.calcsize(fmt)))


def fstring(reader: BinaryIO) -> str:
    (length,) = unpack(reader, "<i")
    if abs(length) > 65_536:
        raise ReferenceError("PAK string exceeds metadata limit")
    if length == 0:
        return ""
    raw = checked_read(reader, length if length > 0 else -length * 2)
    text = raw.decode("utf-8" if length > 0 else "utf-16le", errors="strict")
    if not text.endswith("\0") or "\0" in text[:-1]:
        raise ReferenceError("Invalid PAK FString terminator")
    return text[:-1]


def plain_path(path: Path, *, stop_at: Path) -> None:
    """Refuse existing junctions/symlinks from path up through the trusted root."""
    absolute, boundary = Path(os.path.abspath(path)), Path(os.path.abspath(stop_at))
    try:
        absolute.relative_to(boundary)
    except ValueError as exc:
        raise ReferenceError("Path escapes its allowed root") from exc
    current = absolute
    while True:
        if os.path.lexists(current):
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
                raise ReferenceError(f"Links/reparse points are forbidden: {current.name}")
        if current == boundary:
            break
        current = current.parent


def member_path(name: str) -> str:
    if not name or "\\" in name or "\0" in name or name.startswith("/"):
        raise ReferenceError("Member must be a relative PAK path using forward slashes")
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
                *(f"COM{i}" for i in "¹²³"), *(f"LPT{i}" for i in "¹²³")}
    for part in parts:
        if part in ("", ".", "..") or part[-1:] in (".", " "):
            raise ReferenceError("Unsafe member component")
        if any(ord(char) < 32 or char in '<>:"|?*' for char in part):
            raise ReferenceError("Unsafe member character")
        if part.split(".", 1)[0].upper() in reserved:
            raise ReferenceError("Reserved Windows device member name")
    if PurePosixPath(name).as_posix() != name:
        raise ReferenceError("Noncanonical member path")
    return name


def sha256_stream(reader: BinaryIO) -> str:
    reader.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: reader.read(4 * 1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def identity(reader: BinaryIO) -> tuple[int, int, int, int]:
    info = os.fstat(reader.fileno())
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    compressed_bytes: int
    uncompressed_bytes: int
    compression_method: int
    block_count: int
    block_size: int
    block_lengths: tuple[int, ...]

    def summary(self) -> dict:
        return {"member": self.name, "offset": self.offset,
                "stored_bytes": self.compressed_bytes,
                "uncompressed_bytes": self.uncompressed_bytes,
                "compression": "none" if self.compression_method == 0 else "Zlib"}


class PakV11:
    """Limited traditional PAK reader; unsupported format features fail closed."""

    def __init__(self, reader: BinaryIO, expected_sha256: str):
        self.reader = reader
        self.source_identity = identity(reader)
        self.size = self.source_identity[2]
        self.source_sha256 = sha256_stream(reader)
        if self.source_sha256 != expected_sha256:
            raise ReferenceError("Source PAK SHA256 differs from the reviewed reference snapshot")
        if self.size < 221:
            raise ReferenceError("Missing PAK v11 footer")
        reader.seek(self.size - 221)
        footer = checked_read(reader, 221)
        magic, version, self.index_offset, index_size = struct.unpack_from("<IIQQ", footer, 17)
        if magic != 0x5A6F12E1 or version != 11:
            raise ReferenceError("Only the reviewed PAK v11 format is supported")
        if footer[:16] != bytes(16) or footer[16] != 0:
            raise ReferenceError("Encrypted/index-keyed PAKs are unsupported")
        slots = []
        for pos in range(61, 221, 32):
            field = footer[pos:pos + 32]
            name, _, padding = field.partition(b"\0")
            if any(padding):
                raise ReferenceError("Noncanonical compression slot")
            slots.append(name.decode("ascii", errors="strict"))
        if slots != ["Zlib", "", "", "", ""]:
            raise ReferenceError("Unknown or changed compression slots")
        self.index_sha1 = footer[41:61].hex()
        index = self._index_blob(self.index_offset, index_size, self.index_sha1)
        index_reader = io.BytesIO(index)
        self.mount_point = fstring(index_reader)
        if self.mount_point != "../../../":
            raise ReferenceError("Unexpected base PAK mount point")
        (self.declared_entries,) = unpack(index_reader, "<I")
        if self.declared_entries > MAX_ENTRIES:
            raise ReferenceError("PAK member count exceeds inventory limit")
        (self.path_hash_seed,) = unpack(index_reader, "<Q")
        self.secondary_indices = {}
        blobs = {}
        for label in ("path_hash", "full_directory"):
            (present,) = unpack(index_reader, "<I")
            if present != 1:
                raise ReferenceError("Both reviewed PAK secondary indices are required")
            offset, length = unpack(index_reader, "<QQ")
            digest = checked_read(index_reader, 20).hex()
            blobs[label] = self._index_blob(offset, length, digest)
            self.secondary_indices[label] = {"offset": offset, "bytes": length, "sha1": digest}
        (encoded_size,) = unpack(index_reader, "<I")
        if encoded_size > MAX_INDEX_BYTES:
            raise ReferenceError("Encoded entries exceed metadata limit")
        encoded = checked_read(index_reader, encoded_size)
        (non_encoded_count,) = unpack(index_reader, "<I")
        if non_encoded_count or index_reader.tell() != len(index):
            raise ReferenceError("Non-encoded or trailing index metadata is unsupported")
        directory_reader = io.BytesIO(blobs["full_directory"])
        (self.directory_count,) = unpack(directory_reader, "<I")
        if self.directory_count > MAX_ENTRIES:
            raise ReferenceError("Directory count exceeds metadata limit")
        self.entries = {}
        casefold_names = set()
        for _ in range(self.directory_count):
            directory = fstring(directory_reader)
            if directory.startswith("//") or directory and not directory.endswith("/"):
                raise ReferenceError("Invalid PAK directory name")
            directory = directory.removeprefix("/")
            (count,) = unpack(directory_reader, "<I")
            if count > MAX_ENTRIES or len(self.entries) + count > self.declared_entries:
                raise ReferenceError("Directory member count exceeds declared inventory")
            for _ in range(count):
                filename = fstring(directory_reader)
                if "/" in filename:
                    raise ReferenceError("Directory entry filename includes a separator")
                name = member_path(directory + filename)
                (encoded_offset,) = unpack(directory_reader, "<i")
                if encoded_offset < 0 or encoded_offset >= len(encoded):
                    raise ReferenceError("Deleted/pruned/non-encoded entries are unsupported")
                folded = name.casefold()
                if folded in casefold_names:
                    raise ReferenceError("Duplicate/case-colliding member path")
                casefold_names.add(folded)
                self.entries[name] = self._entry(name, encoded, encoded_offset)
        if len(self.entries) != self.declared_entries or directory_reader.tell() != len(blobs["full_directory"]):
            raise ReferenceError("PAK directory inventory is incomplete")
        self.assert_source_unchanged()

    def _index_blob(self, offset: int, count: int, digest: str) -> bytes:
        if count > MAX_INDEX_BYTES or offset < 0 or offset + count > self.size - 221:
            raise ReferenceError("Index range exceeds bounded PAK metadata")
        self.reader.seek(offset)
        data = checked_read(self.reader, count)
        if hashlib.sha1(data).hexdigest() != digest:
            raise ReferenceError("PAK index SHA1 mismatch")
        return data

    def _entry(self, name: str, encoded: bytes, offset: int) -> Entry:
        stream = io.BytesIO(encoded)
        stream.seek(offset)
        (bits,) = unpack(stream, "<I")
        method = (bits >> 23) & 0x3F
        if bits & (1 << 22):
            raise ReferenceError("Encrypted payload member is unsupported")
        if method not in (0, 1):
            raise ReferenceError("Unknown payload compression method")
        blocks = (bits >> 6) & 0xFFFF
        block_size = bits & 0x3F
        block_size = unpack(stream, "<I")[0] if block_size == 0x3F else block_size << 11
        def number(bit: int) -> int:
            return unpack(stream, "<I" if bits & (1 << bit) else "<Q")[0]
        position, uncompressed = number(31), number(30)
        compressed = number(29) if method else uncompressed
        lengths = tuple(unpack(stream, "<I")[0] for _ in range(blocks)) if blocks > 1 else ()
        header_size = 53 + (4 + blocks * 16 if method else 0)
        if method == 0 and blocks or method != 0 and (not blocks or not uncompressed):
            raise ReferenceError("Invalid compression/block layout")
        if position + header_size + compressed > self.index_offset:
            raise ReferenceError("Member payload overlaps the primary index")
        if lengths and sum(lengths) != compressed:
            raise ReferenceError("Encoded block sizes differ from stored payload length")
        return Entry(name, position, compressed, uncompressed, method, blocks, block_size, lengths)

    def assert_source_unchanged(self) -> None:
        if identity(self.reader) != self.source_identity:
            raise ReferenceError("Source PAK changed while being read")

    def summary(self) -> dict:
        return {"source_pak": str(PAK_PATH), "source_pak_sha256": self.source_sha256,
                "pak_bytes": self.size, "pak_version": 11, "mount_point": self.mount_point,
                "primary_index_sha1": self.index_sha1, "secondary_indices": self.secondary_indices,
                "member_count": len(self.entries), "directory_count": self.directory_count,
                "encrypted_index": False, "encrypted_members": 0,
                "extensions": dict(Counter(PurePosixPath(name).suffix for name in self.entries)),
                "compression_counts": dict(Counter(entry.summary()["compression"] for entry in self.entries.values()))}

    def read_selected(self, name: str, byte_cap: int) -> tuple[bytes, dict]:
        entry = self.entries.get(member_path(name))
        if entry is None:
            raise ReferenceError(f"Exact member is absent from the reviewed base PAK: {name}")
        if max(entry.uncompressed_bytes, entry.compressed_bytes) > byte_cap:
            raise ReferenceError(f"Member exceeds configured byte cap: {name}")
        self.reader.seek(entry.offset)
        disk_offset, stored, unpacked, method = unpack(self.reader, "<QQQI")
        payload_hash = checked_read(self.reader, 20).hex()
        if disk_offset not in (0, entry.offset):
            raise ReferenceError("On-disk member offset disagrees with its index")
        blocks = []
        if method:
            (block_count,) = unpack(self.reader, "<I")
            if block_count != entry.block_count:
                raise ReferenceError("On-disk compression block count mismatch")
            blocks = [unpack(self.reader, "<QQ") for _ in range(block_count)]
        flags, block_size = unpack(self.reader, "<BI")
        if flags or (stored, unpacked, method) != (entry.compressed_bytes, entry.uncompressed_bytes, entry.compression_method):
            raise ReferenceError("Member header/index mismatch or encrypted/deleted member")
        header_size = self.reader.tell() - entry.offset
        if method and entry.block_count > 1 and block_size != entry.block_size:
            raise ReferenceError("Member compression block size mismatch")
        if method:
            cursor = header_size
            for start, end in blocks:
                if start != cursor or end < start:
                    raise ReferenceError("Gapped/overlapping compressed blocks are unsupported")
                cursor = end
            if cursor != header_size + stored:
                raise ReferenceError("Compressed block range/length mismatch")
            lengths = tuple(end - start for start, end in blocks)
            if entry.block_lengths and entry.block_lengths != lengths:
                raise ReferenceError("On-disk and encoded block lengths differ")
            if entry.block_count > 1 and (not block_size or math.ceil(unpacked / block_size) != entry.block_count):
                raise ReferenceError("Compression block geometry is invalid")
        packed = checked_read(self.reader, stored)
        if hashlib.sha1(packed).hexdigest() != payload_hash:
            raise ReferenceError("Stored member payload SHA1 mismatch")
        if not method:
            raw = packed
        else:
            decoded = bytearray()
            for start, end in blocks:
                remaining = unpacked - len(decoded)
                expected = min(block_size, remaining) if len(blocks) > 1 else remaining
                decoder = zlib.decompressobj()
                block = decoder.decompress(packed[start - header_size:end - header_size], expected + 1)
                if len(block) != expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    raise ReferenceError("Zlib block is truncated, oversized or has trailing data")
                decoded.extend(block)
            raw = bytes(decoded)
        if len(raw) != unpacked:
            raise ReferenceError("Decoded member length mismatch")
        self.assert_source_unchanged()
        return raw, {**entry.summary(), "stored_sha1": payload_hash,
                     "decoded_sha256": hashlib.sha256(raw).hexdigest(),
                     "output_kind": "raw Unreal PAK member; not converted image/audio"}


def output_directory() -> Path:
    plain_path(OUTPUT_ROOT, stop_at=Path(WORKBENCH.anchor))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    plain_path(OUTPUT_ROOT, stop_at=WORKBENCH)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    target = OUTPUT_ROOT / name
    target.mkdir(exist_ok=False)
    return target


def write_json_exclusive(path: Path, data: dict) -> None:
    plain_path(path, stop_at=OUTPUT_ROOT)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def remove_owned_output(target: Path) -> None:
    if target.parent != OUTPUT_ROOT or not target.name:
        raise ReferenceError("Refusing cleanup outside owned output directory")
    plain_path(target, stop_at=WORKBENCH)
    target.resolve().relative_to(OUTPUT_ROOT.resolve())
    for path in target.rglob("*"):
        plain_path(path, stop_at=OUTPUT_ROOT)
    shutil.rmtree(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("inventory", help="Read verified base PAK inventory and print metadata; no output files")
    find = actions.add_parser("find", help="Find member paths by literal substrings; no regex or output files")
    find.add_argument("query", nargs="+", help="Case-insensitive literal substrings; every query must match")
    find.add_argument("--limit", type=int, default=100)
    extract = actions.add_parser("extract", help="Export explicitly listed raw members to a fresh reference folder")
    extract.add_argument("--member", action="append", required=True, help="Exact full member path; repeat to select more")
    extract.add_argument("--max-member-mib", type=int, default=16)
    extract.add_argument("--max-total-mib", type=int, default=64)
    args = parser.parse_args(argv)
    if args.action == "find" and not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    if args.action == "extract":
        if len(args.member) > MAX_MEMBERS or len(set(args.member)) != len(args.member):
            parser.error("Choose at most 64 distinct explicit members")
        if not 1 <= args.max_member_mib <= MAX_MEMBER_BYTES // (1024 * 1024):
            parser.error("--max-member-mib must be between 1 and 256")
        if not 1 <= args.max_total_mib <= MAX_TOTAL_BYTES // (1024 * 1024):
            parser.error("--max-total-mib must be between 1 and 512")
        for name in args.member:
            member_path(name)
    plain_path(PAK_PATH, stop_at=Path(SOURCE_ROOT.anchor))
    with PAK_PATH.open("rb") as reader:
        pak = PakV11(reader, EXPECTED_PAK_SHA256)
        if args.action == "inventory":
            result = pak.summary()
        elif args.action == "find":
            queries = [query.casefold() for query in args.query]
            found = [entry for name, entry in sorted(pak.entries.items()) if all(query in name.casefold() for query in queries)]
            result = {"source_pak_sha256": pak.source_sha256, "queries": args.query,
                      "matches": len(found), "returned": min(len(found), args.limit),
                      "members": [entry.summary() for entry in found[:args.limit]]}
        else:
            total = 0
            stored_total = 0
            staged = []
            total_cap = args.max_total_mib * 1024 * 1024
            member_cap = args.max_member_mib * 1024 * 1024
            for name in args.member:
                entry = pak.entries.get(name)
                if entry is None:
                    raise ReferenceError(f"Exact member is absent: {name}")
                total += entry.uncompressed_bytes
                stored_total += entry.compressed_bytes
                if max(total, stored_total) > total_cap:
                    raise ReferenceError("Selected stored/decoded total exceeds configured byte cap")
                data, receipt = pak.read_selected(name, member_cap)
                staged.append((name, data, receipt))
            pak.assert_source_unchanged()
            target = output_directory()
            try:
                receipts = []
                for name, data, receipt in staged:
                    destination = target / "raw" / Path(*PurePosixPath(name).parts)
                    plain_path(destination, stop_at=OUTPUT_ROOT)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    plain_path(destination, stop_at=OUTPUT_ROOT)
                    with destination.open("xb") as stream:
                        stream.write(data)
                    with destination.open("rb") as stream:
                        if destination.stat().st_size != len(data) or sha256_stream(stream) != receipt["decoded_sha256"]:
                            raise ReferenceError("Exported member readback SHA256/length mismatch")
                    receipts.append({**receipt, "output_relative": destination.relative_to(target).as_posix()})
                manifest = {"captured_utc": datetime.now(timezone.utc).isoformat(),
                            "source": pak.summary(), "selection_mode": "explicit members only",
                            "decoder_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            "selected_count": len(receipts), "decoded_total_bytes": total,
                            "stored_total_bytes": stored_total,
                            "companions_auto_selected": False, "members": receipts}
                write_json_exclusive(target / "manifest.json", manifest)
                pak.assert_source_unchanged()
                result = {"status": "exported_raw_members", "output": str(target),
                          "manifest": str(target / "manifest.json"), "selected_count": len(receipts),
                          "decoded_total_bytes": total, "source_pak_sha256": pak.source_sha256}
            except BaseException:
                remove_owned_output(target)
                raise
        pak.assert_source_unchanged()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReferenceError, OSError, UnicodeError, struct.error, zlib.error) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
