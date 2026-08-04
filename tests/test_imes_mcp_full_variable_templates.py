from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "update_imes_mcp_full_variable_templates.py"
SOURCE_PATH = (
    ROOT
    / "logs"
    / "imes_complete_row_samples_20260727"
    / "imes_complete_row_samples.json"
)
TARGET_PATH = ROOT / "PT" / "IMES_Vastbase_MCP指令模板全集.md"
SPEC = importlib.util.spec_from_file_location(
    "imes_full_variable_template_generator_tests", GENERATOR_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ImesMcpFullVariableTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
        cls.target = TARGET_PATH.read_text(encoding="utf-8")
        cls.generated, cls.manifest, cls.catalog = MODULE.build_appendix(
            cls.source
        )

    def test_actual_catalog_is_11_objects_and_315_object_fields(self):
        self.assertEqual(self.manifest["actual_objects"], 11)
        self.assertEqual(self.manifest["actual_object_fields"], 315)
        self.assertEqual(self.catalog["object_count"], 11)
        self.assertEqual(self.catalog["entry_count"], 315)

    def test_every_actual_field_has_semantics_and_colloquial_template(self):
        self.assertTrue(self.manifest["complete"])
        self.assertEqual(self.manifest["documented_object_fields"], 315)
        self.assertEqual(self.manifest["undocumented_fields"], [])
        for account in self.source["accounts"]:
            for relation in account["relations"]:
                object_name = (
                    f"{relation['table_schema']}.{relation['table_name']}"
                )
                self.assertIn(f"`{object_name}`", self.generated)
                for column in relation["columns"]:
                    field = column["column_name"]
                    with self.subTest(object=object_name, field=field):
                        self.assertIn(
                            f'`variables=["{field}"]`',
                            self.generated,
                        )
                        self.assertIn(
                            f"返回实际字段{field}",
                            self.generated,
                        )

    def test_generated_section_in_document_is_up_to_date(self):
        expected = MODULE.replace_generated_section(
            self.target, self.generated
        )
        self.assertEqual(self.target, expected)
        catalog_path = (
            ROOT
            / "高炉前端数据"
            / "智能助手"
            / "mcp"
            / "imes_full_variable_catalog.json"
        )
        self.assertEqual(
            json.loads(catalog_path.read_text(encoding="utf-8")),
            self.catalog,
        )

    def test_critical_boundaries_are_explicit(self):
        self.assertIn(
            "缺少旧表编号到化学成分映射，禁止猜测",
            self.generated,
        )
        self.assertIn(
            "炼钢试样、钢种、工序和合金/残余元素；不是高炉铁水",
            self.generated,
        )
        self.assertIn(
            "是投料量，不是化学元素；物料需关联料仓历史",
            self.generated,
        )
        self.assertIn(
            "当前核查样本全空",
            self.generated,
        )

    def test_each_object_has_profile_time_field_and_copyable_json(self):
        for item in self.manifest["per_object"]:
            with self.subTest(object=item["object"]):
                self.assertEqual(
                    item["actual_fields"], item["documented_fields"]
                )
                self.assertIn(
                    f'"account_profile": "{item["profile"]}"',
                    self.generated,
                )
                self.assertIn(
                    f'"object_name": "{item["object"]}"',
                    self.generated,
                )
                self.assertIn(
                    f'"time_column": "{item["time_field"]}"',
                    self.generated,
                )


if __name__ == "__main__":
    unittest.main()
