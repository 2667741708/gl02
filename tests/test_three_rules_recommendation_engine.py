"""三规二制四类调剂建议引擎 v5 合同测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from recommendation_adapter import (  # noqa: E402
    ENGINE_VERSION,
    build_features_snapshot,
    generate_recommendation,
)


LABELS = ["normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"]
REQUIRED_ACTION_FIELDS = {
    "id",
    "scheme",
    "status",
    "name",
    "user_facing_text",
    "source_refs",
    "trigger_evidence",
    "preconditions",
    "blocking_reasons",
    "delta",
    "sequence",
    "missing_inputs",
    "observation_window",
    "approval",
    "read_only",
}


def diagnosis(label: str, *, score: float = 70.0, secondary: str | None = None) -> dict:
    return {
        "timestamp": "2026-08-04 16:00:00",
        "main_label": label,
        "main_score": score,
        "secondary_label": secondary,
        "raw_scores": {label: score},
        "feature_snapshot": {},
    }


def by_id(result: dict) -> dict[str, dict]:
    return {action["id"]: action for action in result["actions"]}


class ThreeRulesRecommendationEngineTests(unittest.TestCase):
    def test_every_action_has_stable_audit_contract(self) -> None:
        for label in LABELS:
            with self.subTest(label=label):
                result = generate_recommendation(
                    diagnosis(label, score=80),
                    {"P_top": 180, "T_top": 125, "L": 2.0},
                )
                self.assertEqual(result["schema_version"], "three_rules_two_systems.v1")
                self.assertEqual(result["engine_meta"]["version"], ENGINE_VERSION)
                self.assertTrue(result["actions"])
                for action in result["actions"]:
                    self.assertTrue(REQUIRED_ACTION_FIELDS.issubset(action))
                    self.assertIn(
                        action["status"],
                        {"eligible", "blocked", "needs_data", "manual_confirm"},
                    )
                    self.assertTrue(action["source_refs"])
                    self.assertTrue(action["trigger_evidence"])
                    self.assertIsInstance(action["preconditions"], list)
                    self.assertIn("rank", action["sequence"])
                    self.assertIn("required", action["approval"])
                    self.assertTrue(action["read_only"])
                    if action["status"] == "blocked":
                        self.assertTrue(action["blocking_reasons"])
                    if action["status"] == "needs_data":
                        self.assertTrue(action["missing_inputs"])

    def test_cold_chain_uses_document_order_and_allows_coal_when_safe(self) -> None:
        result = generate_recommendation(
            diagnosis("cold", score=65),
            {
                "T_blast": 1120,
                "PCI_rate": 130,
                "coal_ash_pct": 12.5,
                "anthracite_200mesh_pct": 78,
                "coal_moisture_pct": 0.8,
                "coal_analysis_current_flag": 1,
                "O2_rate": 4.2,
                "Q_blast": 3900,
                "serious_abnormal_flag": 0,
                "blast_reduced_flag": 0,
            },
        )
        actions = by_id(result)
        self.assertEqual(actions["LOW-TBLAST-UP-06"]["status"], "eligible")
        self.assertEqual(actions["LOW-PCI-UP-02"]["status"], "eligible")
        self.assertEqual(actions["LOW-PCI-UP-02"]["sequence"]["rank"], 20)
        self.assertLess(
            actions["LOW-TBLAST-UP-06"]["sequence"]["position"],
            actions["LOW-PCI-UP-02"]["sequence"]["position"],
        )
        self.assertEqual(
            actions["LOW-TBLAST-UP-06"]["delta"],
            {
                "min": 10,
                "max": 20,
                "unit": "℃",
                "hourly_limit": {"max": 50, "unit": "℃/h"},
            },
        )

    def test_cold_serious_abnormal_blocks_coal_increase_and_returns_stop_rule(self) -> None:
        result = generate_recommendation(
            diagnosis("cold", score=82),
            {
                "T_blast": 1120,
                "PCI_rate": 130,
                "O2_rate": 4.2,
                "Q_blast": 3900,
                "serious_abnormal_flag": 1,
            },
        )
        actions = by_id(result)
        self.assertEqual(actions["LOW-PCI-UP-02"]["status"], "blocked")
        self.assertIn("严重失常", "；".join(actions["LOW-PCI-UP-02"]["blocking_reasons"]))
        self.assertEqual(actions["LOW-PCI-DOWN-05"]["status"], "manual_confirm")

    def test_coal_increase_requires_quality_data_and_blocks_out_of_spec_coal(self) -> None:
        missing_quality = generate_recommendation(
            diagnosis("cold", score=65),
            {"T_blast": 1120, "PCI_rate": 130, "O2_rate": 4.2, "Q_blast": 3900},
        )
        missing_action = by_id(missing_quality)["LOW-PCI-UP-02"]
        self.assertEqual(missing_action["status"], "needs_data")
        self.assertIn("coal_ash_pct", missing_action["missing_inputs"])

        out_of_spec = generate_recommendation(
            diagnosis("cold", score=65),
            {
                "T_blast": 1120,
                "PCI_rate": 130,
                "O2_rate": 4.2,
                "Q_blast": 3900,
                "coal_ash_pct": 13.5,
                "anthracite_200mesh_pct": 78,
                "coal_moisture_pct": 0.8,
                "coal_analysis_current_flag": 1,
            },
        )
        blocked_action = by_id(out_of_spec)["LOW-PCI-UP-02"]
        self.assertEqual(blocked_action["status"], "blocked")
        self.assertIn("灰分超过13.0%", "；".join(blocked_action["blocking_reasons"]))

    def test_hot_chain_keeps_all_five_steps_in_document_order(self) -> None:
        result = generate_recommendation(
            diagnosis("hot", score=72),
            {
                "Q_blast": 3600,
                "approved_best_blast": 4000,
                "blast_stable_flag": 1,
                "hot_state_sufficient_flag": 1,
                "slag_iron_drained_flag": 1,
                "DP_total": 2.1,
                "approved_dp_limit": 3.0,
                "O2_rate": 4.0,
                "oxygen_coal_coordinated_flag": 1,
                "TFT": 2200,
                "approved_tft_limit": 2300,
                "coke_load_current": 4.0,
                "coke_load_target": 4.05,
                "PCI_rate": 130,
                "T_blast": 1150,
            },
        )
        expected = [
            "LOW-BLAST-UP-GATE",
            "LOW-O2-UP-GATE",
            "LOAD-UP-01",
            "LOW-PCI-DOWN-02",
            "LOW-TBLAST-DOWN-08",
        ]
        self.assertEqual([a["id"] for a in result["actions"]], expected)
        self.assertEqual(by_id(result)["LOAD-UP-01"]["status"], "manual_confirm")
        self.assertEqual(by_id(result)["LOAD-UP-01"]["delta"]["min"], 1.0)

    def test_hot_with_high_dp_and_edge_blocks_blast_and_oxygen_but_keeps_later_steps(self) -> None:
        result = generate_recommendation(
            diagnosis("hot", score=75, secondary="edge"),
            {
                "Q_blast": 3600,
                "approved_best_blast": 4000,
                "blast_stable_flag": 1,
                "hot_state_sufficient_flag": 1,
                "slag_iron_drained_flag": 1,
                "DP_total": 3.5,
                "approved_dp_limit": 3.0,
                "O2_rate": 4.0,
                "oxygen_coal_coordinated_flag": 1,
                "TFT": 2200,
                "approved_tft_limit": 2300,
                "PCI_rate": 130,
                "T_blast": 1150,
            },
        )
        actions = by_id(result)
        self.assertEqual(result["combined_mode"], "edge_plus_hot")
        self.assertEqual(actions["LOW-BLAST-UP-GATE"]["status"], "blocked")
        self.assertEqual(actions["LOW-O2-UP-GATE"]["status"], "blocked")
        self.assertEqual(actions["LOW-PCI-DOWN-02"]["status"], "eligible")

    def test_lowline_net_coke_never_invents_amount(self) -> None:
        result = generate_recommendation(
            diagnosis("lowline", score=80),
            {"Q_blast": 3800, "L": 3.2},
        )
        net_coke = by_id(result)["NET-COKE-05"]
        self.assertEqual(net_coke["status"], "needs_data")
        self.assertEqual(net_coke["delta"], None)
        self.assertIn("lowline_duration_minutes", net_coke["missing_inputs"])
        self.assertIn("lowline_depth", net_coke["missing_inputs"])
        self.assertIn("net_coke_target", net_coke["missing_inputs"])

    def test_high_pressure_channel_blocks_sit_burden_and_returns_unique_safety_action(self) -> None:
        result = generate_recommendation(
            diagnosis("channel", score=85),
            {
                "P_top": 250,
                "Q_blast": 3600,
                "O2_rate": 3.5,
                "hot_state_sufficient_flag": 1,
                "serious_channel_or_bias_flag": 1,
                "top_water_stopped_flag": 1,
            },
        )
        actions = by_id(result)
        self.assertEqual(actions["UP-12"]["status"], "blocked")
        self.assertIn("高压", "；".join(actions["UP-12"]["blocking_reasons"]))
        self.assertEqual(actions["SAFETY-PRESSURE-NORMAL"]["status"], "manual_confirm")
        self.assertEqual(result["immediate_actions"][0]["source"], "safety_gate")

    def test_basicity_trigger_needs_batch_aligned_calculation_data(self) -> None:
        result = generate_recommendation(
            diagnosis("normal"),
            {"slag_r2_actual": 1.30},
        )
        action = by_id(result)["BASICITY-07"]
        self.assertEqual(action["status"], "needs_data")
        self.assertIn("burden_r2_theoretical", action["missing_inputs"])
        self.assertIsNone(action["delta"].get("direction"))

    def test_generic_combination_preserves_old_identifier_without_pair_if(self) -> None:
        result = generate_recommendation(
            diagnosis("cold", score=75, secondary="lowline"),
            {"P_top": 180, "T_top": 125, "L": 3.0},
        )
        self.assertEqual(result["combined_mode"], "lowline_plus_cold")
        self.assertIn("同时伴随低料线", result["explanation"])

    def test_string_zero_flags_are_not_treated_as_true(self) -> None:
        features = build_features_snapshot(
            {"feature_snapshot": {"TRT_running_flag": "0", "probe_stall_flag": "0"}},
            {"P_top": 180},
        )
        self.assertEqual(features["TRT_running_flag"], 0)
        self.assertEqual(features["probe_stall_flag"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
