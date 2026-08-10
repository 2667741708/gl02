"""验证8093完整建议引擎、8767负载和前端绑定契约。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from recommendation_adapter import ENGINE_VERSION, generate_recommendation  # noqa: E402
import local_pg_ws_bridge as bridge  # noqa: E402


LABELS = ["normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"]


class RecommendationEngineContractTests(unittest.TestCase):
    def diagnosis(self, label: str, secondary: str | None = None) -> dict:
        return {
            "timestamp": "2026-07-15 00:20:00",
            "main_label": label,
            "main_score": 80.0,
            "main_confidence": 1.0,
            "secondary_label": secondary,
            "raw_scores": {label: 80.0, "column": 80.0 if label == "column" else 0.0},
            "feature_snapshot": {},
        }

    def test_all_eight_conditions_generate_structured_actions(self) -> None:
        for label in LABELS:
            with self.subTest(label=label):
                result = generate_recommendation(
                    self.diagnosis(label),
                    {"P_top": 180.0, "T_top": 125.0, "L": 2.0},
                )
                self.assertEqual(result["main_label"], label)
                self.assertTrue(result["goal"])
                self.assertTrue(result["immediate_actions"])
                self.assertIn("forbidden_actions", result)
                self.assertEqual(result["engine_meta"]["version"], ENGINE_VERSION)
                self.assertTrue(result["engine_meta"]["read_only"])

    def test_combined_condition_and_safety_gate(self) -> None:
        combined = generate_recommendation(
            self.diagnosis("cold", "lowline"),
            {"P_top": 180.0, "T_top": 125.0, "L": 2.0},
        )
        self.assertEqual(combined["combined_mode"], "lowline_plus_cold")

        high_pressure = generate_recommendation(
            self.diagnosis("column"),
            {"P_top": 253.8, "T_top": 360.0, "L": 2.0},
        )
        self.assertFalse(high_pressure["safety_gate_passed"])
        self.assertTrue(high_pressure["safety_warnings"])
        self.assertEqual(high_pressure["immediate_actions"][0]["source"], "safety_gate")

    def test_8767_payload_contains_ready_recommendation(self) -> None:
        row = {
            "diagnosis_ts": datetime(2026, 7, 15, 0, 20),
            "main_label": "normal",
            "main_score": 61.0,
            "main_confidence": 1.0,
            "secondary_label": None,
            "secondary_score": 0.0,
            "secondary_confidence": 0.0,
            "evidence": [],
            "raw_scores": {"normal": 61.0},
            "diagnosis_json": {"feature_snapshot": {"probe_stall_flag": 0}},
        }
        payload = bridge.diagnosis_snapshot_payload(
            row,
            current_values={"P_top": 253.8, "T_top": 125.6, "L": 2.0},
        )
        self.assertEqual(payload["recommendation_status"]["state"], "ready")
        self.assertEqual(payload["recommendation"]["engine_meta"]["version"], ENGINE_VERSION)
        self.assertEqual(payload["recommendation"]["main_label"], "normal")

    def test_frontend_binds_engine_component_and_normalizes_confidence(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-OPT-FULL-ENGINE-20260715", html)
        self.assertIn("OptimizationTab = OptimizationMultiConditionCockpitLayout;", html)
        self.assertIn("function bfRecommendationConfidence", html)
        self.assertIn("诊断：{fmtTime(d.diagnosis_ts || d.timestamp, 'hms')} ｜ 数据：", html)
        component = html.split("function OptimizationEngineCockpitLayout", 1)[1].split(
            "REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805", 1
        )[0]
        self.assertNotIn("a.score", component)
        self.assertNotIn("风险贡献", component)
        self.assertIn("执行阶段", component)
        self.assertIn("现场边界", component)
        self.assertNotIn("版本：{engine.meta.version", component)
        self.assertIn("evidenceMetricIdsByLabel", component)
        self.assertNotIn("规则判据：", component)
        self.assertNotIn("处置逻辑：", component)
        self.assertIn("{basisEvidence.join", component)
        self.assertIn("<br />{basisLogic}", component)
        self.assertNotIn("active.reason||rec.explanation", component)

    def test_overview_reuses_standardized_engine_and_keeps_three_summaries(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-8093-OVERVIEW-SHARED-RECOMMENDATION-20260715", html)
        component = html.split(
            "OverviewRight = function BFOverviewRightThreeColumnV12", 1
        )[1].split("OverviewTab = function BFOverviewTabThreeColumnV12", 1)[0]
        self.assertIn("bfRecommendationEngineView(diagnosis)", component)
        self.assertIn("engine.actions.slice(0, 3)", component)
        self.assertIn("完整 · 前三条摘要", component)
        self.assertIn("action.name", component)
        self.assertIn("action.reason", component)
        self.assertIn("等待完整建议返回", component)
        self.assertIn("建议暂不可用", component)
        self.assertNotIn("titles=['优化送风制度','调整布料策略']", component)

    def test_overview_trend_jump_is_rendered_in_panel_header(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-8093-OVERVIEW-TREND-JUMP-NO-OVERLAP-20260715", html)
        panel = html.split("function Panel(", 1)[1].split("function Spark", 1)[0]
        self.assertIn("headerAction", panel)
        self.assertIn("panel-head-action", panel)
        trend = html.split("function OverviewLargeTrendV8", 1)[1].split(
            "OverviewRight=function BFOverviewRightV8", 1
        )[0]
        self.assertIn("headerAction={jump}", trend)
        self.assertIn("overview-trend-jump-v14", trend)
        self.assertNotIn("overview-trend-jump-v13", trend)
        style = html.split(".overview-trend-jump-v14", 1)[1].split(
            "OPS-8093-AUTO-MONITOR-DOCK-MD-V9", 1
        )[0]
        self.assertIn("position:static", style)
        self.assertNotIn("position:absolute", style)

    def test_optimization_uses_nonduplicated_risk_insights(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-8093-OPT-RISK-INSIGHTS-20260715", html)
        self.assertIn("function bfPrimarySecondaryScoreTrendOption", html)
        self.assertIn("function bfBaselineDeviationOption", html)
        component = html.split("function OptimizationEngineCockpitLayout", 1)[1].split(
            "REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805", 1
        )[0]
        self.assertIn("bf-decision-evidence-grid", component)
        self.assertIn("baselineText", component)
        self.assertIn("bf-risk-insight-grid", component)
        self.assertIn("主炉况 / 次炉况得分演化", component)
        self.assertIn("关键变量相对历史基线偏离", component)
        self.assertNotIn(
            'metrics.slice(0,4).map(m=><div className="cockpit-trend-card"', component
        )

    def test_optimization_bottom_replaces_duplicate_sparks_with_risk_insights(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-8093-OPT-RISK-INSIGHTS-20260715", html)
        self.assertIn("function bfPrimarySecondaryScoreTrendOption", html)
        self.assertIn("function bfBaselineDeviationOption", html)
        component = html.split("function OptimizationEngineCockpitLayout", 1)[1].split(
            "REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805", 1
        )[0]
        self.assertIn("炉况演化 / 建议", component)
        self.assertIn("bfPrimarySecondaryScoreTrendOption(d, buf.diagnosisHistory || [])", component)
        self.assertIn("bfBaselineDeviationOption(d, evidenceMetricIds)", component)
        self.assertIn("bf-risk-insight-grid", component)
        self.assertNotIn("metrics.slice(0,4).map(m=>", component)


if __name__ == "__main__":
    unittest.main(verbosity=2)
