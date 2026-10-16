"""Strict, dependency-free codec and baseline validation for the game's tables.

Only the outer little-endian uint32 record framing is game specific. Message
fields use the dumped protobuf schema; unknown fields retain their wire type and
bytes in an explicit JSON representation instead of being guessed as text.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections import defaultdict, deque
from fractions import Fraction
from pathlib import Path


class ValidationError(ValueError):
    pass


class SchemaMismatch(ValidationError):
    """A well-framed field disagrees with a flattened nested schema."""


SIGNED32 = {"int", "int32", "sbyte", "short"}
SIGNED64 = {"long", "int64"}
UNSIGNED32 = {"uint", "uint32", "byte", "ushort"}
UNSIGNED64 = {"ulong", "uint64"}


def resolve_type(name, schema):
    name = name.strip()
    if name in schema:
        return name
    # Il2CppDumper uses X.Types.Y in properties but emits Y's own declaration.
    if ".Types." in name and name.rsplit(".", 1)[-1] in schema:
        return name.rsplit(".", 1)[-1]
    return name


def classify(pt, schema):
    pt = pt.strip()
    mp = re.fullmatch(r"MapField<(.+),\s*(.+)>", pt)
    if mp:
        return "map", tuple(resolve_type(x, schema) for x in mp.groups())
    mm = re.fullmatch(r"RepeatedField<(.+)>", pt)
    declared = (mm.group(1) if mm else pt).strip()
    base = resolve_type(declared, schema)
    kind = {"float": "float", "double": "double", "string": "string",
            "ByteString": "bytes", "byte[]": "bytes", "?": "unknown"}.get(base)
    kind = kind or ("msg" if base in schema else "varint")
    return ("rep_" if mm else "") + kind, declared if kind == "msg" else base


def read_varint(raw, pos=0):
    start = pos
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(raw):
            raise ValidationError(f"truncated varint at {start}")
        byte = raw[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise ValidationError(f"varint exceeds uint64 at {start}")
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
    raise ValidationError(f"unterminated varint at {start}")


def write_varint(value):
    if isinstance(value, bool):
        value = int(value)
    if not isinstance(value, int) or not -(1 << 63) <= value < (1 << 64):
        raise ValidationError(f"not a representable protobuf integer: {value!r}")
    value &= (1 << 64) - 1
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _tag(number, wire):
    if not 1 <= number < (1 << 29):
        raise ValidationError(f"invalid field number {number}")
    return write_varint((number << 3) | wire)


def _take(raw, pos, size):
    if size < 0 or pos + size > len(raw):
        raise ValidationError(f"length {size} at {pos} exceeds remaining {len(raw) - pos}")
    return raw[pos:pos + size], pos + size


def _wire_value(raw, pos, wire):
    if wire == 0:
        return read_varint(raw, pos)
    if wire in (1, 5):
        return _take(raw, pos, 8 if wire == 1 else 4)
    if wire == 2:
        length, pos = read_varint(raw, pos)
        return _take(raw, pos, length)
    raise ValidationError(f"unsupported protobuf wire type {wire}")


def _integer(value, base):
    if base == "bool":
        return bool(value)
    if base in SIGNED32:
        value &= (1 << 32) - 1
        return value - (1 << 32) if value >= (1 << 31) else value
    if base in SIGNED64:
        return value - (1 << 64) if value >= (1 << 63) else value
    if base in UNSIGNED32 and value >= 1 << 32:
        raise SchemaMismatch(f"{base} wire value out of range: {value}")
    return value


def _default(kind, base):
    return {} if kind == "msg" else "" if kind in ("string", "bytes") else False if base == "bool" else 0


def _decode_scalar(value, wire, kind, base, schema, path=""):
    expected_wire = {"float": 5, "double": 1, "string": 2, "bytes": 2, "msg": 2, "varint": 0}[kind]
    if wire != expected_wire:
        raise SchemaMismatch(f"{path} {base} expects wire {expected_wire}, found {wire}")
    if kind == "varint":
        return _integer(value, base)
    if kind in ("float", "double"):
        result = struct.unpack("<f" if kind == "float" else "<d", value)[0]
        if not math.isfinite(result):
            raise ValidationError(f"non-finite {base} cannot be safely edited as JSON")
        return result
    if kind == "string":
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as ex:
            raise ValidationError(f"invalid UTF-8 string: {ex}") from ex
    return value.hex() if kind == "bytes" else decode_message(value, base, schema)


def _decode_map(value, bases, schema):
    kt, vt = bases
    kk, kb = classify(kt, schema)
    vk, vb = classify(vt, schema)
    key, val = _default(kk, kb), _default(vk, vb)
    pos = 0
    while pos < len(value):
        tag, pos = read_varint(value, pos)
        field, wire = tag >> 3, tag & 7
        item, pos = _wire_value(value, pos, wire)
        if field not in (1, 2):
            raise ValidationError("unknown map-entry field cannot be preserved in a JSON map")
        if field == 1:
            key = _decode_scalar(item, wire, kk, kb, schema)
        else:
            val = _decode_scalar(item, wire, vk, vb, schema)
    return ("true" if key else "false") if kb == "bool" else str(key), val


def decode_message(raw, cls, schema):
    try:
        return _decode_message_strict(raw, cls, schema)
    except SchemaMismatch as ex:
        if ".Types." not in cls or cls in schema:
            raise
        # Build snapshots flatten nested declarations. A leaf-name collision
        # must not cause guessed types or lost fields: keep the whole scoped
        # message opaque, with an explicit coverage gap in the audit report.
        return {"$opaque_proto": raw.hex(), "$schema": cls, "$reason": str(ex)}


def _decode_message_strict(raw, cls, schema):
    cls = resolve_type(cls, schema)
    if cls not in schema:
        raise ValidationError(f"missing schema for {cls}")
    fields = {int(number): field for number, field in schema[cls].items()}
    result = {}
    pos = 0
    while pos < len(raw):
        tag, pos = read_varint(raw, pos)
        number, wire = tag >> 3, tag & 7
        if not 1 <= number < (1 << 29):
            raise ValidationError(f"invalid field tag {tag}")
        value, pos = _wire_value(raw, pos, wire)
        name, pt = fields.get(number, (f"f{number}", "?"))
        kind, base = classify(pt, schema)
        if kind == "unknown":
            item = {"$wire": wire, "$value": value if wire == 0 else value.hex()}
            if name in result:
                prior = result[name]
                result[name] = (prior if isinstance(prior, list) else [prior]) + [item]
            else:
                result[name] = item
        elif kind == "map":
            if wire != 2:
                raise ValidationError(f"map {name} expects wire 2, found {wire}")
            key, val = _decode_map(value, base, schema)
            result.setdefault(name, {})[key] = val
        elif kind.startswith("rep_"):
            sk = kind[4:]
            values = result.setdefault(name, [])
            if wire == 2 and sk in ("varint", "float", "double"):
                idx = 0
                packed_wire = {"varint": 0, "float": 5, "double": 1}[sk]
                while idx < len(value):
                    item, idx = _wire_value(value, idx, packed_wire)
                    values.append(_decode_scalar(item, packed_wire, sk, base, schema, f"{cls}.{name} (field {number})"))
            else:
                values.append(_decode_scalar(value, wire, sk, base, schema, f"{cls}.{name} (field {number})"))
        else:
            result[name] = _decode_scalar(value, wire, kind, base, schema, f"{cls}.{name} (field {number})")
    return result


def encode_scalar(kind, base, value, schema):
    if kind in ("float", "double"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValidationError(f"{base} must be a finite number: {value!r}")
        try:
            return (5, struct.pack("<f", value)) if kind == "float" else (1, struct.pack("<d", value))
        except (OverflowError, struct.error) as ex:
            raise ValidationError(f"{base} out of range: {value}") from ex
    if kind == "string":
        if not isinstance(value, str):
            raise ValidationError(f"string field received {value!r}")
        raw = value.encode("utf-8")
    elif kind == "bytes":
        if not isinstance(value, str):
            raise ValidationError("bytes field must contain hexadecimal text")
        try:
            raw = bytes.fromhex(value)
        except ValueError as ex:
            raise ValidationError(f"invalid bytes field: {ex}") from ex
    elif kind == "msg":
        raw = encode_message(value, base, schema)
    elif kind == "varint":
        if base == "bool":
            if not isinstance(value, bool):
                raise ValidationError(f"bool field received {value!r}")
        elif not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"integer field received {value!r}")
        bits = 32 if base in SIGNED32 | UNSIGNED32 else 64
        signed = base in SIGNED32 | SIGNED64 or base not in UNSIGNED32 | UNSIGNED64 | {"bool"}
        low, high = (-(1 << (bits - 1)), 1 << (bits - 1)) if signed else (0, 1 << bits)
        if not low <= value < high:
            raise ValidationError(f"{base} out of range: {value}")
        return 0, write_varint(value)
    else:
        raise ValidationError(f"unsupported scalar kind {kind}")
    return 2, write_varint(len(raw)) + raw


def _unknown_bytes(number, value):
    result = bytearray()
    for item in value if isinstance(value, list) else [value]:
        if not isinstance(item, dict) or set(item) != {"$wire", "$value"}:
            raise ValidationError(f"unknown f{number} needs explicit $wire/$value")
        wire, data = item["$wire"], item["$value"]
        if wire == 0:
            body = write_varint(data)
        elif wire in (1, 2, 5):
            body = bytes.fromhex(data)
            if wire in (1, 5) and len(body) != (8 if wire == 1 else 4):
                raise ValidationError("unknown fixed-width field has wrong length")
            if wire == 2:
                body = write_varint(len(body)) + body
        else:
            raise ValidationError(f"unsupported unknown wire type {wire}")
        result += _tag(number, wire) + body
    return result


def legacy_repeated_messages(values, cls, schema):
    """Recover the old flattened packed-varint form under a narrow contract.

    The legacy decoder erased repeated-message boundaries. Recovery is safe
    only when every message contains *all* known singular scalar fields once,
    in increasing field-number order. That full schema-sized sequence gives
    explicit boundaries; incomplete, nested, repeated or unknown fields fail
    instead of using the old `field <= previous` boundary guess.
    """
    if not isinstance(values, list) or not values:
        raise ValidationError(f"{cls}: invalid legacy repeated-message representation")
    if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < (1 << 64) for v in values):
        raise ValidationError(f"{cls}: legacy repeated-message values must be uint64 integers")
    raw = b"".join(write_varint(value) for value in values)
    return _legacy_message_bodies(raw, cls, schema)


def _legacy_message_bodies(raw, cls, schema):
    """Parse exact complete scalar-schema bodies without guessing boundaries."""
    resolved = resolve_type(cls, schema)
    if resolved not in schema or not raw:
        raise ValidationError(f"{cls}: invalid or empty legacy protobuf body")
    fields = sorted((int(number), field) for number, field in schema[resolved].items())
    if not fields:
        raise ValidationError(f"{cls}: an empty nested schema cannot delimit legacy messages")
    for _, (_, pt) in fields:
        kind, _ = classify(pt, schema)
        if kind not in {"varint", "float", "double", "string", "bytes"}:
            raise ValidationError(f"{cls}: legacy nested/repeated/unknown fields are ambiguous; use object records")
    messages = []
    pos = 0
    while pos < len(raw):
        start = pos
        for number, (name, pt) in fields:
            tag, pos = read_varint(raw, pos)
            if tag >> 3 != number:
                raise ValidationError(f"{cls}: legacy message is incomplete or ambiguous at field {name}; use object records")
            value, pos = _wire_value(raw, pos, tag & 7)
            kind, base = classify(pt, schema)
            _decode_scalar(value, tag & 7, kind, base, schema, f"{cls}.{name}")
        body = raw[start:pos]
        message = decode_message(body, cls, schema)
        if "$opaque_proto" in message or encode_message(message, cls, schema) != body:
            raise ValidationError(f"{cls}: legacy message is not a fully known canonical protobuf object")
        messages.append(message)
    return messages


def legacy_singular_message(value, cls, schema):
    """Recover exactly one body from old varint lists or raw UTF-8 strings.

    The old decoder emitted a UTF-8 string for an unresolved singular message
    when its complete wire body happened to be valid UTF-8. No hex/base64 or
    scalar-to-message guessing is performed. Multiple bodies are never merged.
    """
    if isinstance(value, list):
        messages = legacy_repeated_messages(value, cls, schema)
    elif isinstance(value, str):
        try:
            raw = value.encode("utf-8")
        except UnicodeEncodeError as ex:
            raise ValidationError(f"{cls}: legacy protobuf body is not valid UTF-8") from ex
        messages = _legacy_message_bodies(raw, cls, schema)
    else:
        raise ValidationError(f"{cls}: singular message requires an object or supported legacy body")
    if len(messages) != 1:
        raise ValidationError(f"{cls}: singular legacy message contains {len(messages)} bodies; exactly one is required")
    return messages[0]


def normalize_message(obj, cls, schema, *, conversions=None, path=""):
    """Normalize legacy bodies and ordinary ProtoJSON nulls without file edits.

    https://protobuf.dev/programming-guides/json/#null-values specifies null as
    unset for known ordinary fields (including whole repeated/map fields), with
    key validation retained and null list elements forbidden. This table codec
    does not implement specialized google.protobuf well-known-type JSON forms.
    """
    resolved = resolve_type(cls, schema)
    if resolved not in schema or not isinstance(obj, dict):
        raise ValidationError(f"{path or cls}: requires a known schema and a JSON object")
    if "$opaque_proto" in obj:
        return dict(obj)
    fields = {field[0]: field[1] for field in schema[resolved].values()}
    result = {}
    for name, value in obj.items():
        location = path + "." + name if path else cls + "." + name
        if name not in fields:
            result[name] = value
            continue
        kind, base = classify(fields[name], schema)
        if value is None:
            if base in {"google.protobuf.NullValue", "Google.Protobuf.WellKnownTypes.NullValue"}:
                raise ValidationError(f"{location}: specialized NullValue JSON sentinel handling is unsupported")
            if conversions is not None:
                conversions.append({"path": location, "schema": fields[name], "representation": "json_null_unset",
                                    "contract": "protobuf_protojson_known_field_null_is_unset",
                                    "source": "https://protobuf.dev/programming-guides/json/#null-values"})
            continue
        if kind.startswith("rep_") and isinstance(value, list) and any(item is None for item in value):
            raise ValidationError(f"{location}: null elements are forbidden inside repeated fields")
        if kind == "rep_msg":
            if not isinstance(value, list):
                raise ValidationError(f"{location}: repeated message requires a JSON array")
            if value and any(not isinstance(item, dict) for item in value):
                native = legacy_repeated_messages(value, base, schema)
                if conversions is not None:
                    raw = b"".join(write_varint(item) for item in value)
                    conversions.append({"path": location, "schema": base, "representation": "legacy_flattened_varints",
                                        "legacy_values": len(value), "messages": len(native), "raw_bytes": len(raw),
                                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                        "contract": "complete_singular_scalar_fields_in_schema_order_exact_byte_roundtrip"})
                value = native
            result[name] = [normalize_message(item, base, schema, conversions=conversions, path=location + f"[{i}]")
                            for i, item in enumerate(value)]
        elif kind == "msg":
            if not isinstance(value, dict):
                representation = "legacy_singular_varints" if isinstance(value, list) else "legacy_singular_utf8_body"
                value = legacy_singular_message(value, base, schema)
                if conversions is not None:
                    raw = encode_message(value, base, schema)
                    conversions.append({"path": location, "schema": base, "representation": representation,
                                        "messages": 1, "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                        "contract": "exactly_one_complete_scalar_schema_body_exact_byte_roundtrip"})
            result[name] = normalize_message(value, base, schema, conversions=conversions, path=location)
        elif kind == "map" and classify(base[1], schema)[0] == "msg":
            if not isinstance(value, dict):
                raise ValidationError(f"{location}: message map requires a JSON object")
            result[name] = {key: normalize_message(item, base[1], schema, conversions=conversions, path=location + f"[{key!r}]")
                            for key, item in value.items()}
        else:
            result[name] = value
    return result


def encode_message(obj, cls, schema):
    if isinstance(obj, dict) and "$opaque_proto" in obj:
        if set(obj) != {"$opaque_proto", "$schema", "$reason"} or obj["$schema"] != cls:
            raise ValidationError("invalid opaque scoped message")
        raw = bytes.fromhex(obj["$opaque_proto"])
        if decode_message(raw, cls, schema) != obj:
            raise ValidationError("opaque bytes/provenance no longer match the decoded schema gap")
        return raw
    obj = normalize_message(obj, cls, schema)
    cls = resolve_type(cls, schema)
    if cls not in schema or not isinstance(obj, dict):
        raise ValidationError(f"{cls} requires a known schema and a JSON object")
    byname = {field[0]: (int(number), field[1]) for number, field in schema[cls].items()}
    result = bytearray()
    for name, value in obj.items():
        if name in byname:
            number, pt = byname[name]
        else:
            match = re.fullmatch(r"f(\d+)", name)
            if not match or int(match.group(1)) in {int(n) for n in schema[cls]}:
                raise ValidationError(f"{cls}.{name} is not in schema")
            number, pt = int(match.group(1)), "?"
        kind, base = classify(pt, schema)
        if kind == "unknown":
            result += _unknown_bytes(number, value)
        elif kind == "map":
            if not isinstance(value, dict):
                raise ValidationError(f"{cls}.{name} requires a map")
            kk, kb = classify(base[0], schema)
            vk, vb = classify(base[1], schema)
            for key, val in value.items():
                if kk == "varint":
                    if kb == "bool":
                        if key not in ("true", "false"):
                            raise ValidationError("bool map key must be true or false")
                        key = key == "true"
                    else:
                        key = int(key)
                kw, kr = encode_scalar(kk, kb, key, schema)
                vw, vr = encode_scalar(vk, vb, val, schema)
                body = _tag(1, kw) + kr + _tag(2, vw) + vr
                result += _tag(number, 2) + write_varint(len(body)) + body
        elif kind.startswith("rep_"):
            if not isinstance(value, list):
                raise ValidationError(f"{cls}.{name} requires a list")
            sk = kind[4:]
            if sk in ("varint", "float", "double"):
                if value:
                    body = b"".join(encode_scalar(sk, base, item, schema)[1] for item in value)
                    result += _tag(number, 2) + write_varint(len(body)) + body
            else:
                for item in value:
                    wire, body = encode_scalar(sk, base, item, schema)
                    result += _tag(number, wire) + body
        else:
            wire, body = encode_scalar(kind, base, value, schema)
            result += _tag(number, wire) + body
    return bytes(result)


def split_table(raw):
    rows = []
    pos = 0
    while pos < len(raw):
        if len(raw) - pos < 4:
            raise ValidationError(f"trailing {len(raw) - pos} byte(s) at table offset {pos}")
        size = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        row, pos = _take(raw, pos, size)
        rows.append(row)
    return rows


def decode_table(raw, cls, schema):
    result = []
    for index, row in enumerate(split_table(raw)):
        try:
            result.append(decode_message(row, cls, schema))
        except (ValidationError, ValueError, struct.error) as ex:
            raise ValidationError(f"{cls} row {index}: {ex}") from ex
    return result


def encode_table_rows(rows, cls, schema):
    if not isinstance(rows, list):
        raise ValidationError("table JSON must be an array")
    result = bytearray()
    for index, row in enumerate(rows):
        try:
            body = encode_message(row, cls, schema)
        except (ValidationError, ValueError, TypeError, struct.error) as ex:
            raise ValidationError(f"{cls} row {index}: {ex}") from ex
        result += struct.pack("<I", len(body)) + body
    return bytes(result)


def _canonical_scalar(value, kind, base, schema):
    if kind == "msg":
        return canonical_message(value, base, schema)
    if kind in ("float", "double"):
        # Quantize binary32 only; integer comparisons never convert to float.
        return struct.unpack("<f", struct.pack("<f", value))[0] if kind == "float" else value
    return value


def canonical_message(obj, cls, schema):
    if "$opaque_proto" in obj:
        return obj
    obj = normalize_message(obj, cls, schema)
    fields = {field[0]: field[1] for field in schema[resolve_type(cls, schema)].values()}
    result = {}
    for name, value in obj.items():
        if name not in fields:
            result[name] = value
            continue
        kind, base = classify(fields[name], schema)
        if kind == "map":
            vk, vb = classify(base[1], schema)
            if value:
                result[name] = {str(k): _canonical_scalar(v, vk, vb, schema) for k, v in value.items()}
        elif kind.startswith("rep_"):
            if value:
                result[name] = [_canonical_scalar(v, kind[4:], base, schema) for v in value]
        elif value != _default(kind, base):
            result[name] = _canonical_scalar(value, kind, base, schema)
    return result


def assert_semantic_equal(expected, actual, cls, schema):
    if len(expected) != len(actual):
        raise ValidationError(f"{cls}: row count changed: expected {len(expected)}, decoded {len(actual)}")
    for index, (left, right) in enumerate(zip(expected, actual)):
        a, b = canonical_message(left, cls, schema), canonical_message(right, cls, schema)
        if a != b:
            names = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            raise ValidationError(f"{cls} row {index}: semantic mismatch in {names[:8]}")


def validate_table_payload(raw, expected, cls, schema, baseline_count=None):
    actual = decode_table(raw, cls, schema)
    assert_semantic_equal(expected, actual, cls, schema)
    # A second roundtrip also catches encoder-only mismatches and unknown wires.
    second = decode_table(encode_table_rows(actual, cls, schema), cls, schema)
    assert_semantic_equal(actual, second, cls, schema)
    opaque = opaque_segments(actual)
    return {"schema": cls, "rows": len(actual), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "baseline_rows": baseline_count, "row_delta": None if baseline_count is None else len(actual) - baseline_count,
            "framing": "complete", "semantic_roundtrip": "passed_for_interpreted_fields" if opaque else "passed",
            "opaque_segments": opaque, "opaque_policy": "preserve_only" if opaque else None}


def opaque_segments(value, path=""):
    result = []
    if isinstance(value, dict):
        if "$opaque_proto" in value:
            result.append({"path": path, "schema": value["$schema"], "reason": value["$reason"],
                           "bytes": len(bytes.fromhex(value["$opaque_proto"])),
                           "sha256": hashlib.sha256(bytes.fromhex(value["$opaque_proto"])).hexdigest()})
        else:
            for name, child in value.items():
                result.extend(opaque_segments(child, path + "." + name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(opaque_segments(child, path + f"[{index}]"))
    return result


def validate_opaque_preserved(original, current):
    allowed = {(x["schema"], x["sha256"]) for x in opaque_segments(original)}
    for item in opaque_segments(current):
        if (item["schema"], item["sha256"]) not in allowed:
            raise ValidationError(f"opaque schema gap is preserve-only; cannot edit {item['path']} ({item['schema']})")


def to_fixed_row(row, cls, schema, normal_cls=None):
    """Scale only float -> fixed int64 fields, keeping native integers exact."""
    normal_cls = normal_cls or cls.removesuffix("FixedPoint")
    row = normalize_message(row, normal_cls, schema)
    if "$opaque_proto" in row:
        raise ValidationError("opaque scoped message cannot be converted to a different fixed-point schema")
    source = {f[0]: f[1] for f in schema[resolve_type(normal_cls, schema)].values()}
    target = {f[0]: f[1] for f in schema[resolve_type(cls, schema)].values()}
    result = {}
    for name, value in row.items():
        if name not in target or name not in source:
            # Unknown fields can have different layouts between normal/fixed.
            if name not in target:
                raise ValidationError(f"cannot map {normal_cls}.{name} into fixed-point schema")
            result[name] = value
            continue
        sk, sb = classify(source[name], schema)
        tk, tb = classify(target[name], schema)
        repeated = sk.startswith("rep_")
        sv, tv = sk.removeprefix("rep_"), tk.removeprefix("rep_")
        def convert(item):
            if sv in ("float", "double") and tv == "varint" and tb in SIGNED64:
                if isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item):
                    raise ValidationError("fixed-point source must be finite")
                result = round(Fraction(item) * (1 << 32))
                if not -(1 << 63) <= result < 1 << 63:
                    raise ValidationError(f"fixed-point overflow: {item}")
                return result
            if sv == tv == "msg":
                return to_fixed_row(item, tb, schema, sb)
            if source[name] != target[name]:
                raise ValidationError(f"unhandled fixed-point schema conversion {source[name]} -> {target[name]}")
            return item
        if sk == tk == "map":
            # Current dumped tables do not use fixed-valued maps. Refuse unknown conversions.
            if sb != tb:
                raise ValidationError(f"unhandled fixed-point map conversion for {name}")
            result[name] = value
        else:
            result[name] = [convert(x) for x in value] if repeated else convert(value)
    return result


def expected_fixed_rows(current, original, fixed_raw, name, schema):
    fixed = decode_table(fixed_raw, name + "FixedPoint", schema)
    if len(original) != len(fixed):
        raise ValidationError(f"{name}: normal/fixed baseline counts differ ({len(original)}/{len(fixed)})")
    unchanged = defaultdict(deque)
    def key(row):
        return json.dumps(canonical_message(row, name, schema), sort_keys=True, ensure_ascii=False)
    for normal, encoded in zip(original, fixed):
        unchanged[key(normal)].append(encoded)
    result = []
    for row in current:
        queue = unchanged[key(row)]
        result.append(queue.popleft() if queue else to_fixed_row(row, name + "FixedPoint", schema, name))
    return result


def encode_fixed_table_rows(current, original, fixed_raw, name, schema):
    """Build fixed bytes with semantic queues, shared by build and preflight."""
    bodies = split_table(fixed_raw)
    if len(original) != len(bodies):
        raise ValidationError(f"{name}: normal/fixed baseline counts differ ({len(original)}/{len(bodies)})")
    validate_opaque_preserved(original, current)
    unchanged = defaultdict(deque)
    def fingerprint(row):
        return json.dumps(canonical_message(row, name, schema), sort_keys=True, ensure_ascii=False)
    for row, body in zip(original, bodies):
        unchanged[fingerprint(row)].append(body)
    output = bytearray()
    preserved = encoded = 0
    for row in current:
        candidates = unchanged[fingerprint(row)]
        if candidates:
            body = candidates.popleft()
            preserved += 1
        else:
            body = encode_message(to_fixed_row(row, name + "FixedPoint", schema), name + "FixedPoint", schema)
            encoded += 1
        output += struct.pack("<I", len(body)) + body
    return bytes(output), {"unchanged_byte_identical_rows": preserved, "edited_or_new_rows": encoded,
                           "unused_original_bodies": len(original) - preserved, "row_delta": len(current) - len(original)}


def validate_baseline(root, build_id=None):
    """Verify immutable .orig/raw/schema/key hashes before a composer may build."""
    root = Path(root)
    path = root / "inspect" / "baseline_manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        report = json.loads((root / "inspect" / "decode_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise ValidationError(f"no usable fresh baseline; rerun setup: {ex}") from ex
    if manifest.get("format") != 1 or report.get("status") != "passed":
        raise ValidationError("baseline decode was not successful")
    if build_id and manifest.get("build_id") != str(build_id):
        raise ValidationError(f"baseline build {manifest.get('build_id')} != installed build {build_id}")
    if report.get("build_id") != manifest.get("build_id"):
        raise ValidationError("baseline and decode report build ids differ")
    files = manifest.get("files", {})
    if not files:
        raise ValidationError("baseline manifest has no immutable files")
    actual_files = {p.relative_to(root).as_posix() for p in (root / "extracted_raw").rglob("*") if p.is_file()}
    actual_files.update(p.relative_to(root).as_posix() for p in (root / "decoded").rglob("*.orig") if p.is_file())
    actual_files.update(("inspect/proto_schema.json", "inspect/js_keys.json"))
    if actual_files != set(files):
        raise ValidationError("baseline immutable file set changed; rerun fresh setup")
    for relative, digest in files.items():
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValidationError(f"baseline path escapes root: {relative}")
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
            raise ValidationError(f"baseline changed or missing: {relative}; rerun fresh setup")
    return manifest
