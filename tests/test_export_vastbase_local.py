from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).parents[1] / "tools" / "export_vastbase_local.py"
SPEC = importlib.util.spec_from_file_location("export_vastbase_local", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeExportCursor:
    def __init__(self) -> None:
        self.description = [("workdate",), ("meltno",), ("value_02",)]
        self.executed = None
        self._batches = [
            [("2026-07-15", "2#20260715-1", 0.25)],
            [],
        ]

    def execute(self, query, params=()):
        self.executed = (query, params)

    def fetchmany(self, _size):
        return self._batches.pop(0)


class VastbaseDiscoveryTests(unittest.TestCase):
    def test_confirmed_objects_are_classified(self):
        self.assertEqual(
            MODULE.classify_object("public", "t_ipes_out_put", ("workdate",)),
            "生产实绩",
        )
        self.assertEqual(
            MODULE.classify_object("public", "batch_input", ("workdate",)),
            "批次投料",
        )

    def test_column_fallback_classifies_material_input(self):
        category = MODULE.classify_object(
            "public",
            "unknown_feed_rows",
            ("materialCode", "materialName", "dryQuan"),
        )
        self.assertEqual(category, "原料投入候选")

    def test_group_catalog_preserves_ordinal_order(self):
        rows = [
            ("public", "demo", "BASE TABLE", "b", 2),
            ("public", "demo", "BASE TABLE", "a", 1),
            ("pg_catalog", "hidden", "BASE TABLE", "x", 1),
        ]
        self.assertEqual(
            MODULE.group_catalog_rows(rows),
            [("public", "demo", "BASE TABLE", ("a", "b"))],
        )

    def test_build_query_uses_inclusive_business_date_range_and_limit(self):
        item = MODULE.DbObject(
            "public",
            "t_ipes_out_put",
            "BASE TABLE",
            "生产实绩",
            ("workdate", "meltno"),
            "workdate",
            True,
        )
        query, params = MODULE.build_export_query(
            item, "2026-07-14", "2026-07-15", 1000
        )
        self.assertIn('"workdate" >= %s', query)
        self.assertIn("LIMIT %s", query)
        self.assertEqual(params, ("2026-07-14", "2026-07-16", 1000))

    def test_unlimited_export_requires_explicit_approval(self):
        args = SimpleNamespace(
            start_date="2026-07-14",
            end_date="2026-07-15",
            max_rows_per_object=0,
            allow_unlimited=False,
            export=True,
            include_other=False,
            object=[],
        )
        with self.assertRaisesRegex(ValueError, "requires --allow-unlimited"):
            MODULE.validate_args(args)

    def test_filter_defaults_to_mes_candidates_only(self):
        candidates = [
            MODULE.DbObject("public", "batch_input", "VIEW", "批次投料", (), None, True),
            MODULE.DbObject("public", "audit_log", "BASE TABLE", "其他", (), None, True),
        ]
        selected = MODULE.filter_objects(candidates, [], [], False)
        self.assertEqual([item.name for item in selected], ["batch_input"])

    def test_export_object_writes_bounded_csv(self):
        item = MODULE.DbObject(
            "public",
            "heat_lab",
            "VIEW",
            "炉次化验",
            ("workdate", "meltno", "value_02"),
            "workdate",
            True,
        )
        cursor = FakeExportCursor()
        with tempfile.TemporaryDirectory() as tmp:
            result = MODULE.export_object(
                cursor,
                item,
                Path(tmp),
                "2026-07-15",
                "2026-07-15",
                50,
            )
            self.assertEqual(result["rows"], 1)
            content = (Path(tmp) / result["file"]).read_text(encoding="utf-8-sig")
            self.assertIn("2#20260715-1", content)
            self.assertEqual(cursor.executed[1], ("2026-07-15", "2026-07-16", 50))


if __name__ == "__main__":
    unittest.main()
