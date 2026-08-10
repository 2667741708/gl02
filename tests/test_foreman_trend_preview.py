"""Static contracts for the standalone foreman trend preview.

Requirement: REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "foreman_trend_preview.html"
STYLE = ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.css"
SCRIPT = ROOT / "高炉前端数据" / "assets" / "foreman-trend-preview.js"
ORIGINAL_PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


class ForemanTrendPreviewContract(unittest.TestCase):
    """Keep the comparison page isolated from the current production trend tab."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.css = STYLE.read_text(encoding="utf-8")
        cls.js = SCRIPT.read_text(encoding="utf-8")
        cls.original = ORIGINAL_PAGE.read_text(encoding="utf-8")

    def test_preview_is_standalone_and_original_trend_remains(self) -> None:
        self.assertIn('data-page="foreman-trend-preview"', self.html)
        self.assertIn("function TrendTab", self.original)
        self.assertIn('className="screen trend-grid vertical-analysis"', self.original)
        self.assertNotIn("foreman-trend-preview.css", self.original)
        self.assertNotIn("foreman-trend-preview.js", self.original)

    def test_local_assets_and_real_stream_boundary_are_present(self) -> None:
        self.assertIn('src="libs/echarts.min.js"', self.html)
        self.assertIn('href="assets/foreman-trend-preview.css"', self.html)
        self.assertIn('src="assets/foreman-trend-preview.js', self.html)
        self.assertIn("new WebSocket(url)", self.js)
        self.assertIn("message.type === 'init'", self.js)
        self.assertIn("message.type === 'tick'", self.js)
        self.assertIn("布局校验数据 · 非生产", self.js)

    def test_pspace_realtime_overlay_selector_ratio_and_color_contracts(self) -> None:
        self.assertIn("pspace_ws_port", self.js)
        self.assertIn("connectPspaceWebSocket", self.js)
        self.assertTrue("pspace_realtime" in self.js or "pSpace 秒级" in self.js)
        self.assertIn("lower-pressure-ratio", self.js)
        self.assertIn("DP_lower_ratio", self.js)
        self.assertIn('id="series-picker"', self.html)
        self.assertIn("data-action=\"series-picker\"", self.html)
        self.assertIn("seriesColor", self.js)
        self.assertIn("--metric-series-color", self.js)

    def test_49_metric_matrix_and_two_linked_charts_are_declared(self) -> None:
        matrix = self.js.split("const FOREMAN_METRIC_COLUMNS =", 1)[1].split("const MAIN_SERIES", 1)[0]
        self.assertEqual(len(re.findall(r"\bm\('", matrix)), 49)
        self.assertIn("grid-template-columns: repeat(7", self.css)
        self.assertIn('id="main-trend-chart"', self.html)
        self.assertIn('id="lower-trend-chart"', self.html)
        self.assertIn("window.echarts.connect(TREND_GROUP)", self.js)

    def test_controls_are_actions_not_decorative_icons(self) -> None:
        for action in ("cursor", "zoom-in", "zoom-out", "pan-left", "pan-right", "reset", "latest", "export"):
            self.assertIn(f'data-action="{action}"', self.html)
        self.assertIn("handleToolbarAction", self.js)
        self.assertIn("exportChart", self.js)


if __name__ == "__main__":
    unittest.main()
