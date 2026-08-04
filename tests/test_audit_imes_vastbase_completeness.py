from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "audit_imes_vastbase_completeness.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("imes_completeness_audit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CompletenessAuditTests(unittest.TestCase):
    def test_two_furnace_condition_uses_center_and_heat_number(self):
        item = MODULE.DbObject("public", "demo", "BASE TABLE", "测试", ("prodcentercode", "meltno", "workdate"), "workdate", True)
        condition = MODULE.two_furnace_condition(item)
        self.assertIn("2D012", condition)
        self.assertIn("2#%%", condition)

    def test_daily_query_is_bounded_and_grouped(self):
        item = MODULE.DbObject("public", "demo", "BASE TABLE", "测试", ("prodcentercode", "workdate"), "workdate", True)
        query, params = MODULE.build_daily_query(item, "2026-05-01", "2026-05-31")
        self.assertIn("GROUP BY", query)
        self.assertIn("SUBSTR", query)
        self.assertEqual(params, ("2026-05-01", "2026-06-01"))

    def test_no_two_furnace_identifier_reports_null(self):
        item = MODULE.DbObject("public", "demo", "BASE TABLE", "测试", ("workdate",), "workdate", True)
        query, _ = MODULE.build_summary_query(item, "2026-05-01", "2026-05-31")
        self.assertIn("NULL::bigint", query)


if __name__ == "__main__":
    unittest.main()
