from __future__ import annotations

import importlib.util
import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


MCP_PATH = Path(__file__).resolve().parents[1] / "mcp" / "bf_data_mcp_server.py"
IMPORT_CONFIG_DIR = tempfile.TemporaryDirectory()
IMPORT_CONFIG_ROOT = Path(IMPORT_CONFIG_DIR.name)
IMPORT_MAPPING = IMPORT_CONFIG_ROOT / "mapping.json"
IMPORT_STORAGE = IMPORT_CONFIG_ROOT / "storage.json"
IMPORT_MAPPING.write_text('{"variables": []}', encoding="utf-8")
IMPORT_STORAGE.write_text('{}', encoding="utf-8")
os.environ.setdefault("BF_GL02_MAPPING_PATH", str(IMPORT_MAPPING))
os.environ.setdefault("BF_GL02_STORAGE_CONFIG", str(IMPORT_STORAGE))
SPEC = importlib.util.spec_from_file_location("bf_data_mcp_server_chart_tests", MCP_PATH)
assert SPEC and SPEC.loader
mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mcp)


UNITS = {
    "T_top": "℃",
    "P_top": "kPa",
    "Q_blast": "m³/min",
    "L_south": "m",
    "L_north": "m",
}


def fake_history(variable, start_time, end_time, limit=500, source_preference="auto"):
    start = datetime.fromisoformat(start_time.replace("T", " "))
    rows = []
    if variable.startswith("T_body_L"):
        match = __import__("re").fullmatch(r"T_body_L(\d+)_([A-H])", variable)
        assert match
        layer = int(match.group(1))
        position_index = ord(match.group(2)) - ord("A")
        offset = layer * 4 + position_index
        unit = "℃"
    else:
        offset = list(UNITS).index(variable) + 1
        unit = UNITS[variable]
    for index in range(30):
        rows.append(
            {
                "ts": (start + timedelta(minutes=index)).isoformat(sep=" ", timespec="seconds"),
                "value": offset * 10 + index * (0.4 + offset * 0.05),
                "quality": "Good",
            }
        )
    return {
        "ok": True,
        "variable": {
            "variable_name": variable,
            "description": f"测试变量 {variable}",
            "unit": unit,
        },
        "start_time": start_time,
        "end_time": end_time,
        "count": len(rows),
        "data": rows[:limit],
        "source": {"type": "test", "preference": source_preference},
    }


class McpChartExpansionTests(unittest.TestCase):
    def test_static_pressure_extension_registers_three_heights_by_six_positions(self):
        names = {item.get("variable_name") for item in mcp.VARIABLES}
        expected = {
            f"P_static_{level}_{position}"
            for level in ("lower", "middle", "upper")
            for position in "ABCDEF"
        }
        self.assertTrue(expected.issubset(names))
        self.assertEqual(mcp.resolve_variable("20.35米A点静压力")["variable_name"], "P_static_lower_A")
        self.assertEqual(mcp.resolve_variable("EQ_SIO_GL02_BT_T0110")["variable_name"], "P_static_middle_F")
        self.assertEqual(mcp.resolve_variable("28.98米F点静压力")["variable_name"], "P_static_upper_F")
        lower_a = mcp.public_variable(mcp.resolve_variable("P_static_lower_A"))
        self.assertEqual(mcp.extension_source_preference(lower_a, "auto"), "auto")
        self.assertEqual(mcp.extension_source_preference(lower_a, "database"), "database")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_charts_dir = mcp.CHARTS_DIR
        mcp.CHARTS_DIR = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"BF_MCP_PLOT_SUBPROCESS": "0"})
        self.env.start()
        self.history = patch.object(mcp, "query_gl02_history", side_effect=fake_history)
        self.history.start()
        self.start = "2026-07-15 10:00:00"
        self.end = "2026-07-15 10:29:00"

    def tearDown(self):
        self.history.stop()
        self.env.stop()
        mcp.CHARTS_DIR = self.original_charts_dir
        self.temp.cleanup()

    def assert_chart(self, result):
        self.assertTrue(result["ok"], result)
        self.assertTrue(Path(result["image_path"]).is_file())
        self.assertTrue(result["image_url"].startswith("/data/mcp_charts/"))
        self.assertTrue(Path(result["data_path"]).is_file())

    def test_mcp_schema_exposes_chart_tools_and_new_options(self):
        tools = asyncio.run(mcp.mcp.list_tools())
        by_name = {tool.name: tool for tool in tools}
        self.assertIn("plot_gl02_trends", by_name)
        self.assertIn("plot_gl02_analysis", by_name)
        self.assertIn("plot_gl02_body_temperature_matrix", by_name)
        self.assertIn("query_gl02_sensors", by_name)
        trend_properties = by_name["plot_gl02_trends"].inputSchema["properties"]
        analysis_properties = by_name["plot_gl02_analysis"].inputSchema["properties"]
        matrix_properties = by_name["plot_gl02_body_temperature_matrix"].inputSchema["properties"]
        self.assertIn("chart_type", trend_properties)
        self.assertIn("moving_average_points", trend_properties)
        self.assertIn("reference_values", trend_properties)
        self.assertIn("analysis_type", analysis_properties)
        self.assertIn("start_layer", matrix_properties)
        self.assertIn("positions", matrix_properties)

    def test_batch_sensor_tool_supports_multiple_history_series(self):
        result = mcp.query_gl02_sensors(
            ["T_top", "P_top", "Q_blast"],
            query_type="history",
            start_time=self.start,
            end_time=self.end,
            max_points_per_variable=20,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["tool"], "query_gl02_sensors")
        self.assertEqual(result["query_type"], "history")
        self.assertEqual(result["variable_count"], 3)
        self.assertEqual(result["success_count"], 3)
        self.assertEqual(result["failure_count"], 0)
        self.assertTrue(all(len(item["data"]) == 20 for item in result["items"]))

    def test_batch_sensor_tool_keeps_partial_latest_failures(self):
        def fake_latest(variable, source_preference="auto"):
            if variable == "missing_sensor":
                raise ValueError("未找到变量")
            return {
                "ok": True,
                "variable": {"variable_name": variable, "description": variable, "unit": "℃"},
                "latest": {"ts": self.end, "value": 42.5, "quality": "Good"},
                "source": {"type": "test"},
            }

        with patch.object(mcp, "get_latest_gl02_value", side_effect=fake_latest):
            result = mcp.query_gl02_sensors(["T_top", "missing_sensor"], query_type="latest")
        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertFalse(result["items"][1]["ok"])

    def test_body_temperature_matrix_renders_heat_cells_sparklines_and_values(self):
        result = mcp.plot_gl02_body_temperature_matrix(
            self.start,
            self.end,
            start_layer=7,
            end_layer=8,
            positions=["A", "B"],
            title="炉体温度矩阵测试",
        )
        self.assert_chart(result)
        self.assertEqual(result["tool"], "plot_gl02_body_temperature_matrix")
        self.assertEqual(result["cell_count"], 4)
        self.assertEqual(result["available_cell_count"], 4)
        self.assertEqual(result["missing_cell_count"], 0)
        self.assertEqual(result["layers"], [7, 8])
        self.assertEqual(result["positions"], ["A", "B"])
        self.assertTrue(all(cell["current_value"] is not None for cell in result["cells"]))

    def test_body_temperature_matrix_marks_missing_cell_without_interpolation(self):
        normal_history = fake_history

        def history_with_missing(variable, start_time, end_time, limit=500, source_preference="auto"):
            if variable == "T_body_L8_B":
                return {
                    "ok": True,
                    "variable": {"variable_name": variable, "description": "缺测点", "unit": "℃"},
                    "data": [],
                    "source": {"type": "test"},
                }
            return normal_history(variable, start_time, end_time, limit, source_preference)

        self.history.stop()
        with patch.object(mcp, "query_gl02_history", side_effect=history_with_missing):
            result = mcp.plot_gl02_body_temperature_matrix(
                self.start,
                self.end,
                start_layer=7,
                end_layer=8,
                positions="A-B",
            )
        self.history.start()
        self.assert_chart(result)
        self.assertEqual(result["available_cell_count"], 3)
        self.assertEqual(result["missing_cell_count"], 1)
        missing = next(cell for cell in result["cells"] if cell["variable"] == "T_body_L8_B")
        self.assertIsNone(missing["current_value"])

    def test_auto_trend_uses_dual_axis_for_two_different_units(self):
        result = mcp.plot_gl02_trends(
            ["T_top", "P_top"],
            self.start,
            self.end,
            chart_type="auto",
            show_extrema=True,
            moving_average_points=5,
        )
        self.assert_chart(result)
        self.assertEqual(result["chart_type_used"], "dual_axis")
        self.assertEqual(result["options"]["moving_average_points"], 5)

    def test_auto_trend_uses_small_multiples_for_many_mixed_units(self):
        result = mcp.plot_gl02_trends(
            ["T_top", "P_top", "Q_blast"],
            self.start,
            self.end,
            chart_type="auto",
            theme="dark",
        )
        self.assert_chart(result)
        self.assertEqual(result["chart_type_used"], "small_multiples")
        self.assertEqual(result["theme"], "dark")

    def test_auto_trend_uses_small_multiples_for_large_scale_gap_even_without_units(self):
        items = []
        for variable, base in (("sensor_a", 47.0), ("sensor_b", 250.0), ("sensor_c", 14500.0)):
            items.append(
                {
                    "requested_variable": variable,
                    "variable": {"variable_name": variable, "unit": ""},
                    "rows": [{"ts": self.start, "value": base}, {"ts": self.end, "value": base * 1.01}],
                }
            )
        self.assertEqual(mcp.choose_trend_chart_type("auto", items), "small_multiples")

    def test_trend_supports_area_and_reference_line_options(self):
        result = mcp.plot_gl02_trends(
            ["P_top"],
            self.start,
            self.end,
            chart_type="area",
            reference_values={"P_top": 25.0},
            show_latest=False,
        )
        self.assert_chart(result)
        self.assertEqual(result["chart_type_used"], "area")
        self.assertEqual(result["options"]["reference_values"], {"P_top": 25.0})

    def test_analysis_auto_uses_scatter_and_returns_correlation(self):
        result = mcp.plot_gl02_analysis(
            ["L_south", "L_north"],
            self.start,
            self.end,
            analysis_type="auto",
        )
        self.assert_chart(result)
        self.assertEqual(result["analysis_type_used"], "correlation_scatter")
        self.assertEqual(result["derived"]["correlation"]["aligned_count"], 30)
        self.assertAlmostEqual(result["derived"]["correlation"]["pearson_r"], 1.0, places=6)

    def test_analysis_supports_heatmap_distribution_and_boxplot(self):
        for analysis_type in ("correlation_heatmap", "distribution", "boxplot"):
            with self.subTest(analysis_type=analysis_type):
                result = mcp.plot_gl02_analysis(
                    ["T_top", "P_top", "Q_blast"],
                    self.start,
                    self.end,
                    analysis_type=analysis_type,
                    scale="zscore" if analysis_type == "boxplot" else "raw",
                )
                self.assert_chart(result)
                self.assertEqual(result["analysis_type_used"], analysis_type)


if __name__ == "__main__":
    unittest.main()
