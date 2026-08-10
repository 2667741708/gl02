"""Contract tests for multi-condition recommendations and structured model review."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
ASSISTANT_BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
for source_dir in (SERVICE_DIR, ASSISTANT_BACKEND):
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

from recommendation_adapter import (  # noqa: E402
    DIAGNOSIS_LABELS,
    ENGINE_VERSION,
    generate_recommendation_bundle,
)
import diagnosis_model_review  # noqa: E402


def diagnosis_payload() -> dict:
    return {
        "diagnosis_ts": "2026-08-05 10:25:00",
        "main_label": "cold",
        "main_score": 76.0,
        "secondary_label": "edge",
        "raw_scores": {
            "normal": 22,
            "lowline": 31,
            "edge": 48,
            "center": 18,
            "channel": 12,
            "cold": 76,
            "hot": 9,
            "column": 14,
        },
        "evidence": ["顶温连续下降", "煤气利用率下降"],
        "baseline_compare": {
            "T_top": {"z": -1.4, "current": 108, "mean": 128},
            "GasUtil": {"z": -1.1, "current": 42, "mean": 47},
        },
        "data_coverage": {"available": 27, "total": 28, "ratio": 0.96},
        "feature_snapshot": {},
    }


class MultiConditionRecommendationTests(unittest.TestCase):
    def test_bundle_contains_active_plan_and_all_eight_condition_plans(self) -> None:
        bundle = generate_recommendation_bundle(
            diagnosis_payload(),
            {"P_top": 180, "T_top": 108, "T_blast": 1120, "GasUtil": 42, "L": 2.0},
        )
        self.assertEqual(bundle["schema_version"], "multi_condition_recommendation.v1")
        self.assertEqual(bundle["engine_meta"]["version"], ENGINE_VERSION)
        self.assertEqual(bundle["conditions"][0]["label"], "cold")
        self.assertEqual(bundle["conditions"][0]["scope"], "active")
        self.assertEqual(bundle["conditions"][1]["label"], "edge")
        self.assertEqual(bundle["conditions"][1]["scope"], "supporting")
        self.assertEqual({item["label"] for item in bundle["conditions"]}, set(DIAGNOSIS_LABELS))
        self.assertEqual(len(bundle["conditions"]), 8)
        for item in bundle["conditions"]:
            with self.subTest(label=item["label"]):
                self.assertTrue(item["read_only"])
                self.assertTrue(item["recommendation"]["actions"])
                self.assertEqual(item["action_count"], len(item["recommendation"]["actions"]))
                self.assertEqual(
                    item["recommendation"]["engine_meta"]["version"], ENGINE_VERSION
                )

    def test_hypothetical_plan_does_not_inherit_current_secondary_condition(self) -> None:
        bundle = generate_recommendation_bundle(diagnosis_payload(), {"P_top": 180, "L": 2.0})
        lowline = next(item for item in bundle["conditions"] if item["label"] == "lowline")
        self.assertEqual(lowline["scope"], "hypothetical")
        self.assertIsNone(lowline["recommendation"]["secondary_label"])
        self.assertEqual(
            lowline["recommendation"]["engine_meta"]["source"], "condition_hypothesis"
        )


class DiagnosisModelReviewContractTests(unittest.TestCase):
    def request_payload(self, reviewed_label: str = "cold") -> dict:
        return {
            "reviewed_label": reviewed_label,
            "diagnosis": diagnosis_payload(),
            "diagnosis_history": [
                {
                    "timestamp": "2026-08-05 10:20:00",
                    "label": "cold",
                    "raw": diagnosis_payload()["raw_scores"],
                }
            ],
            "recommendation": {
                "goal": "先稳顺行，再补热",
                "safety_gate_passed": True,
                "actions": [
                    {
                        "id": "LOW-TBLAST-UP-06",
                        "name": "提高热风温度",
                        "status": "eligible",
                        "trigger_evidence": [{"field": "main_label", "actual": "cold"}],
                        "blocking_reasons": [],
                        "missing_inputs": [],
                    }
                ],
            },
        }

    def test_context_is_whitelisted_and_contains_eight_scores(self) -> None:
        context = diagnosis_model_review.normalize_review_context(self.request_payload())
        self.assertEqual(context["reviewed_label"], "cold")
        self.assertEqual(context["reviewed_display_name"], "热制度下行")
        self.assertEqual(context["reviewed_score"], 76.0)
        self.assertEqual(set(context["scores"]), set(DIAGNOSIS_LABELS))
        self.assertEqual(len(context["diagnosis_history"]), 1)
        self.assertEqual(context["data_coverage"], 0.96)
        self.assertEqual(context["baseline_items"][0]["id"], "T_top")
        self.assertEqual(context["recommendation"]["actions"][0]["status"], "eligible")

    def test_prompt_forbids_score_and_action_rewrite(self) -> None:
        context = diagnosis_model_review.normalize_review_context(self.request_payload())
        messages = diagnosis_model_review.build_review_messages(context)
        self.assertIn("不能修改分数", messages[0]["content"])
        self.assertIn("不能新增调剂动作", messages[0]["content"])
        self.assertIn("只返回一个JSON对象", messages[0]["content"])

    def test_model_json_is_validated_and_normalized(self) -> None:
        parsed = diagnosis_model_review.parse_model_payload(
            """```json
            {
              "verdict": "partial_agree",
              "model_support_score": 72.4,
              "summary": "热制度下行基本成立，但边缘发展分数同步升高。",
              "supporting_evidence": ["顶温下降"],
              "contradicting_evidence": ["总压差暂未升高"],
              "missing_data": ["最近炉次铁水硅含量"],
              "attention_items": ["继续观察煤气利用率"],
              "risk_change": "rising",
              "manual_review_recommended": true
            }
            ```"""
        )
        self.assertEqual(parsed["verdict"], "partial_agree")
        self.assertEqual(parsed["model_support_score"], 72)
        self.assertTrue(parsed["manual_review_recommended"])

    def test_invalid_free_text_is_rejected(self) -> None:
        with self.assertRaises(diagnosis_model_review.ModelReviewValidationError):
            diagnosis_model_review.parse_model_payload("我认为诊断基本正确。")

    def test_cache_is_isolated_by_reviewed_condition_and_returns_defensive_copy(self) -> None:
        cold = diagnosis_model_review.normalize_review_context(self.request_payload("cold"))
        edge = diagnosis_model_review.normalize_review_context(self.request_payload("edge"))
        cold_key = diagnosis_model_review.review_cache_key(cold, "internal-model")
        edge_key = diagnosis_model_review.review_cache_key(edge, "internal-model")
        self.assertNotEqual(cold_key, edge_key)
        cache = diagnosis_model_review.DiagnosisModelReviewCache(ttl_seconds=30)
        cache.put(cold_key, {"state": "completed", "model_meta": {"cache_hit": False}})
        first = cache.get(cold_key)
        self.assertTrue(first["model_meta"]["cache_hit"])
        first["state"] = "changed"
        self.assertEqual(cache.get(cold_key)["state"], "completed")

    def test_frontend_and_proxy_expose_new_contract_markers(self) -> None:
        html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(
            encoding="utf-8"
        )
        proxy = (
            ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
        ).read_text(encoding="utf-8")
        bridge = (ROOT / "自动诊断服务" / "local_pg_ws_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805", html)
        self.assertIn("REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806", html)
        self.assertIn("OptimizationTab = OptimizationVisualWorkbenchLayout", html)
        self.assertIn("8类炉况建议矩阵", html)
        self.assertIn("完整动作详情", html)
        self.assertIn("/api/diagnosis/model-review", html)
        self.assertIn('parsed.path == "/api/diagnosis/model-review"', proxy)
        self.assertIn('payload["recommendation_bundle"] = bundle', bridge)


if __name__ == "__main__":
    unittest.main(verbosity=2)
