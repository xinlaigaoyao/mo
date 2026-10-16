"""Read-only composed-table preflight, before expensive Unity resource imports.

Call preflight_tables(ROOT, touched_names, schema=SCHEMA, build_id=build_id,
                      report_path=Path(ROOT)/"inspect"/"table_preflight.json")
after successful table/JS composition. It never imports UnityPy, rewrites input
JSON, generates bundles, or touches game/save data. The caller validates the
immutable baseline once before composing; the standalone CLI does that itself.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re

from validation_tables import (ValidationError, encode_fixed_table_rows, encode_table_rows,
    expected_fixed_rows, normalize_message, validate_baseline, validate_opaque_preserved,
    validate_table_payload)


class TablePreflightError(ValidationError):
    def __init__(self, report):
        self.report = report
        details = "; ".join(f"{item['table']}: {item['error']}" for item in report["failures"])
        super().__init__("Table preflight failed before resource generation: " + details)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def preflight_tables(root, table_names, *, schema=None, build_id=None, report_path=None):
    """Encode and fully verify normal/fixed payloads in memory; raise on failure.

    All touched tables are checked even if an earlier one fails. On failure,
    TablePreflightError.report carries the complete structured result. Supported
    legacy nested-list conversions are counted and audited; source files remain
    unchanged. Explicit report_path is the only file this function may write.
    """
    root = Path(root).resolve()
    marker = (root / "inspect/game_build.txt").read_text(encoding="utf-8").strip()
    bound_build = str(build_id if build_id is not None else marker)
    if marker != bound_build:
        raise ValidationError(f"table preflight baseline build {marker} != requested {bound_build}")
    schema_path = root / "inspect/proto_schema.json"
    schema_bytes = schema_path.read_bytes()
    if schema is None:
        schema = json.loads(schema_bytes)
    elif json.dumps(schema, sort_keys=True) != json.dumps(json.loads(schema_bytes), sort_keys=True):
        raise ValidationError("table preflight schema differs from the current baseline schema")
    names = list(table_names)
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name) for name in names):
        raise ValidationError("table preflight received an invalid table name")
    names = sorted(set(names))
    report = {"format": 1, "status": "failed", "build_id": bound_build,
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "normal_and_fixed_table_payloads_before_resource_generation",
              "source_files": {"inspect/proto_schema.json": _sha(schema_bytes),
                               "inspect/game_build.txt": _sha((root / "inspect/game_build.txt").read_bytes())},
              "tables": [], "failures": [], "legacy_conversions": []}
    def read(relative):
        content = (root / relative).read_bytes()
        report["source_files"][relative] = _sha(content)
        return content
    for name in names:
        try:
            if name not in schema:
                raise ValidationError(f"missing schema for {name}")
            current = json.loads(read(f"decoded/tables/{name}.json"))
            original = json.loads(read(f"decoded/tables/{name}.json.orig"))
            if not isinstance(current, list) or not isinstance(original, list):
                raise ValidationError("normal/current table JSON must both be arrays")
            conversions = []
            normalized = [normalize_message(row, name, schema, conversions=conversions,
                                            path=f"{name}[{index}]") for index, row in enumerate(current)]
            validate_opaque_preserved(original, normalized)
            normal_payload = encode_table_rows(normalized, name, schema)
            normal = validate_table_payload(normal_payload, normalized, name, schema, len(original))
            result = {"table": name, "normal": normal, "legacy_conversions": len(conversions)}
            report["legacy_conversions"].extend(conversions)
            fixed_name = name + "FixedPoint"
            if fixed_name in schema:
                fixed_baseline = read(f"extracted_raw/data/xlsxfixed/{fixed_name}Wrap.bin")
                fixed_payload, preservation = encode_fixed_table_rows(normalized, original, fixed_baseline, name, schema)
                fixed_expected = expected_fixed_rows(normalized, original, fixed_baseline, name, schema)
                result["fixed"] = {**validate_table_payload(fixed_payload, fixed_expected, fixed_name, schema, len(original)),
                                   **preservation}
            report["tables"].append(result)
        except (ValidationError, OSError, ValueError, TypeError, KeyError) as ex:
            report["failures"].append({"table": name, "error": str(ex)})
    report["table_count"] = len(report["tables"])
    report["fixed_table_count"] = sum("fixed" in item for item in report["tables"])
    if not report["failures"]:
        report["status"] = "passed"
    if report_path is not None:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["failures"]:
        raise TablePreflightError(report)
    return report


def assert_preflight_unchanged(root, report):
    """Optional guard immediately before encoding after long resource imports."""
    root = Path(root).resolve()
    if report.get("status") != "passed":
        raise ValidationError("cannot use a failed table preflight")
    for relative, digest in report["source_files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or _sha(path.read_bytes()) != digest:
            raise ValidationError(f"table preflight input changed during resource generation: {relative}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", nargs="*")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--all", action="store_true", help="check every decoded normal table")
    parser.add_argument("--build-id", default=os.environ.get("BBMOD_BUILD_ID"))
    parser.add_argument("--report")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    tables = sorted(path.stem for path in (root / "decoded/tables").glob("*.json")) if args.all else args.tables
    if not tables:
        parser.error("provide table names or --all")
    validate_baseline(root, args.build_id)
    result = preflight_tables(root, tables, build_id=args.build_id, report_path=args.report)
    print(f"Table preflight passed: {result['table_count']} normal, {result['fixed_table_count']} fixed, "
          f"{len(result['legacy_conversions'])} audited legacy conversions")


if __name__ == "__main__":
    main()
