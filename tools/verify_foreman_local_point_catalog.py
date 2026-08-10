"""Read-only verification for the local GL02 point catalog extension."""

from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path

from apply_foreman_points_and_coal_storage import MARKER_BEGIN, POINT_ROWS, SYNC_MARKER_BEGIN


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog = root / "config" / "点位清单.tsv"
    schema = root / "schema" / "postgresql_required_points.sql"
    sync = root / "src" / "sync_from_243_pg.py"
    module = root / "src" / "coal_hourly.py"
    with catalog.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    by_name = {row["变量名"]: row for row in rows}
    expected = {row[0]: row for row in POINT_ROWS}
    mismatches = {}
    for name, values in expected.items():
        actual = by_name.get(name)
        if actual is None:
            mismatches[name] = "missing"
            continue
        if actual["短名"] != values[3] or actual["点ID/长名"] != values[4]:
            mismatches[name] = {"short_name": actual["短名"], "tag": actual["点ID/长名"]}
    result = {
        "passed": not mismatches and MARKER_BEGIN in schema.read_text(encoding="utf-8") and SYNC_MARKER_BEGIN in sync.read_text(encoding="utf-8") and module.is_file(),
        "catalog_rows": len(rows),
        "physical_rows": sum(1 for row in rows if row["短名"] != "派生" and row["点ID/长名"].startswith("\\")),
        "derived_rows": sum(1 for row in rows if row["短名"] == "派生" or not row["点ID/长名"].startswith("\\")),
        "confirmed_rows": len(expected) - len(mismatches),
        "mismatches": mismatches,
        "schema_installed": MARKER_BEGIN in schema.read_text(encoding="utf-8"),
        "sync_hook_installed": SYNC_MARKER_BEGIN in sync.read_text(encoding="utf-8"),
        "coal_module_installed": module.is_file(),
    }
    try:
        ast.parse(sync.read_text(encoding="utf-8"), filename=str(sync))
        ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        result["python_syntax"] = "ok"
    except SyntaxError as exc:
        result["python_syntax"] = str(exc)
        result["passed"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
