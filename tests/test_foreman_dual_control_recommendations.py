"""Contract tests for read-only P_blast_cold/PCI_set foreman advice."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from recommendation_adapter import generate_recommendation_bundle  # noqa: E402


ALLOWED = {"P_blast_cold", "PCI_set"}
AUDIT_FIELDS = {
    "source_document",
    "source_refs",
    "trigger_evidence",
    "preconditions",
    "blocking_reasons",
    "delta",
    "sequence",
    "missing_inputs",
    "observation_window",
    "approval",
    "status",
    "control_variable",
    "control_label",
    "current_value",
    "recommended_change",
    "recommended_target",
    "unit",
    "step_tier",
    "effective_at",
    "limit_snapshot",
}


def diagnosis(label: str, score: float = 80.0) -> dict:
    return {
        "timestamp": "2026-08-06 17:00:00",
        "main_label": label,
        "main_score": score,
        "secondary_label": None,
        "raw_scores": {label: score},
        "feature_snapshot": {},
    }


def values(**overrides: object) -> dict:
    payload = {
        "P_blast_cold": 450.0,
        "PCI_set": 40.0,
        "PCI_rate": 40.0,
        "current_values_timestamp": "2026-08-06 17:00:00",
        "P_blast_cold_timestamp": "2026-08-06 17:00:00",
        "pressure_baseline_p25": 438.0,
        "pressure_baseline_p75": 475.0,
        "pressure_baseline_day": "2026-08-06",
        "pressure_baseline_sample_count": 40000,
        "pressure_baseline_coverage_ratio": 0.95,
        "pressure_baseline_updated_at": "2026-08-06 00:05:00",
        "blast_stable_flag": 1,
        "hot_state_sufficient_flag": 1,
        "slag_iron_drained_flag": 1,
        "DP_total": 2.1,
        "approved_dp_limit": 3.0,
        "tuyere_abnormal_flag": 0,
        "high_pressure_flag": 0,
        "coal_ash_pct": 12.5,
        "anthracite_200mesh_pct": 78.0,
        "coal_moisture_pct": 0.8,
        "coal_analysis_current_flag": 1,
        "serious_abnormal_flag": 0,
        "serious_cold_flag": 0,
        "blast_reduced_flag": 0,
        "pressure_mode": "high_pressure",
        "L": 3.2,
        "unsmooth_condition_flag": 1,
    }
    payload.update(overrides)
    return payload


def active_plan(label: str, score: float = 80.0, **overrides: object) -> dict:
    return generate_recommendation_bundle(diagnosis(label, score), values(**overrides))["active_plan"]


def find_action(plan: dict, variable: str, direction: str | None = None) -> dict:
    matches = [
        action
        for action in plan["actions"]
        if action.get("control_variable") == variable
        and (direction is None or action.get("adjustment_direction") == direction)
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {variable}/{direction} action, got {matches!r}")
    return matches[0]


class ForemanDualControlRecommendationTests(unittest.TestCase):
    def test_pressure_step_boundaries(self) -> None:
        cases = ((59.9, 3.0, "low"), (60, 5.0, "medium"), (74.9, 5.0, "medium"),
                 (75, 10.0, "high"), (85, 10.0, "critical"))
        for score, expected_step, expected_tier in cases:
            with self.subTest(score=score):
                action = find_action(active_plan("hot", score), "P_blast_cold", "increase")
                self.assertEqual(action["status"], "eligible")
                self.assertEqual(action["step_tier"]["standard_step"], expected_step)
                self.assertEqual(action["step_tier"]["severity"], expected_tier)
                self.assertEqual(action["recommended_target"], 450.0 + expected_step)

    def test_pressure_q3_cap_returns_actual_4_7_kpa(self) -> None:
        action = find_action(
            active_plan("hot", 65, P_blast_cold=453.3, pressure_baseline_p75=458.0),
            "P_blast_cold",
            "increase",
        )
        self.assertEqual(action["status"], "eligible")
        self.assertEqual(action["recommended_target"], 458.0)
        self.assertEqual(action["recommended_change"], 4.7)
        self.assertTrue(action["step_tier"]["clamped"])
        self.assertEqual(action["limit_snapshot"]["normal_q3"], 458.0)

    def test_pressure_400_floor_caps_high_severity_reduction(self) -> None:
        action = find_action(
            active_plan("lowline", 75, P_blast_cold=405.0),
            "P_blast_cold",
            "decrease",
        )
        self.assertEqual(action["status"], "eligible")
        self.assertEqual(action["recommended_target"], 400.0)
        self.assertEqual(action["recommended_change"], -5.0)
        self.assertTrue(action["step_tier"]["clamped"])

    def test_pressure_limit_blocks_and_missing_baseline_needs_data(self) -> None:
        floor = find_action(active_plan("lowline", 65, P_blast_cold=400), "P_blast_cold")
        self.assertEqual(floor["status"], "blocked")
        self.assertTrue(any("400kPa" in reason for reason in floor["blocking_reasons"]))

        cap = find_action(
            active_plan("hot", 65, P_blast_cold=458, pressure_baseline_p75=458),
            "P_blast_cold",
        )
        self.assertEqual(cap["status"], "blocked")

        missing = find_action(
            active_plan("hot", 65, pressure_baseline_p25=None, pressure_baseline_p75=None),
            "P_blast_cold",
        )
        self.assertEqual(missing["status"], "needs_data")
        self.assertIn("pressure_baseline_p25", missing["missing_inputs"])
        self.assertIn("pressure_baseline_p75", missing["missing_inputs"])
        self.assertIsNone(missing["recommended_target"])

    def test_invalid_or_stale_pressure_baseline_needs_data(self) -> None:
        cases = (
            {"pressure_baseline_p25": 458, "pressure_baseline_p75": 458},
            {"pressure_baseline_coverage_ratio": 0.749},
            {"pressure_baseline_day": "2026-08-03"},
            {"pressure_baseline_updated_at": None},
            {"current_values_timestamp": "2026-08-06 16:54:00", "P_blast_cold_timestamp": None},
        )
        for override in cases:
            with self.subTest(override=override):
                action = find_action(active_plan("hot", 65, **override), "P_blast_cold")
                self.assertEqual(action["status"], "needs_data")

    def test_missing_pressure_data_wins_over_nonsevere_policy_block(self) -> None:
        action = find_action(
            active_plan("cold", 59.9, pressure_baseline_p25=None),
            "P_blast_cold",
            "decrease",
        )
        self.assertEqual(action["status"], "needs_data")
        self.assertIn("pressure_baseline_p25", action["missing_inputs"])
        self.assertTrue(action["deferred_blocking_reasons"])

    def test_coal_increase_next_hour_and_upper_cap(self) -> None:
        increase = find_action(active_plan("cold", 65), "PCI_set", "increase")
        self.assertEqual(increase["status"], "eligible")
        self.assertEqual(increase["recommended_target"], 42.0)
        self.assertEqual(increase["recommended_change"], 2.0)
        self.assertEqual(increase["effective_at"], "2026-08-06 18:00:00")

        capped = find_action(
            active_plan(
                "cold",
                75,
                P_blast_cold=400,
                PCI_set=44,
                serious_cold_flag=1,
            ),
            "PCI_set",
            "increase",
        )
        self.assertEqual(capped["status"], "eligible")
        self.assertEqual(capped["recommended_target"], 45.0)
        self.assertEqual(capped["recommended_change"], 1.0)
        self.assertTrue(capped["step_tier"]["clamped"])

    def test_coal_normal_limits_and_transition_state(self) -> None:
        upper = find_action(active_plan("cold", 65, PCI_set=45), "PCI_set", "increase")
        self.assertEqual(upper["status"], "blocked")

        lower = find_action(active_plan("hot", 65, PCI_set=10), "PCI_set", "decrease")
        self.assertEqual(lower["status"], "blocked")

        transition = find_action(active_plan("hot", 65, PCI_set=7), "PCI_set", "decrease")
        self.assertEqual(transition["status"], "manual_confirm")
        self.assertIsNone(transition["recommended_target"])
        self.assertTrue(transition["approval"]["required"])

    def test_severe_column_stops_coal_at_zero_for_immediate_confirmation(self) -> None:
        action = find_action(active_plan("column", 90, PCI_set=37), "PCI_set", "stop")
        self.assertEqual(action["status"], "manual_confirm")
        self.assertEqual(action["recommended_target"], 0.0)
        self.assertEqual(action["recommended_change"], -37.0)
        self.assertEqual(action["step_tier"]["mode"], "emergency_stop")
        self.assertEqual(action["effective_at"], "2026-08-06 17:00:00")

    def test_pressure_reduction_blocks_simultaneous_coal_increase(self) -> None:
        plan = active_plan("cold", 80, serious_cold_flag=1)
        pressure = find_action(plan, "P_blast_cold", "decrease")
        coal = find_action(plan, "PCI_set", "increase")
        self.assertEqual(pressure["status"], "eligible")
        self.assertEqual(coal["status"], "blocked")
        self.assertIn("当前处于减风降压阶段，不具备增加喷煤资格", coal["blocking_reasons"])

    def test_all_actions_have_full_audit_contract_and_required_approval(self) -> None:
        scenarios = (
            active_plan("hot", 65),
            active_plan("lowline", 75, P_blast_cold=405),
            active_plan("cold", 80, serious_cold_flag=1),
            active_plan("column", 90, PCI_set=37),
            active_plan("hot", 65, pressure_baseline_p25=None),
        )
        seen_statuses: set[str] = set()
        for plan in scenarios:
            for action in plan["actions"]:
                self.assertTrue(AUDIT_FIELDS.issubset(action), action)
                self.assertIn(action["control_variable"], ALLOWED)
                self.assertTrue(action["approval"]["required"])
                self.assertTrue(action["read_only"])
                seen_statuses.add(action["status"])
        self.assertEqual(seen_statuses, {"eligible", "blocked", "needs_data", "manual_confirm"})

    def test_all_eight_condition_plans_expose_only_allowed_controls(self) -> None:
        bundle = generate_recommendation_bundle(diagnosis("cold", 65), values())
        self.assertEqual(len(bundle["conditions"]), 8)
        for condition in bundle["conditions"]:
            recommendation = condition["recommendation"]
            actions = recommendation["actions"]
            self.assertEqual(condition["action_count"], len(actions))
            self.assertTrue(all(action.get("control_variable") in ALLOWED for action in actions))
            self.assertEqual({action.get("control_variable") for action in actions}, ALLOWED)
            self.assertTrue(recommendation["control_scope"]["read_only"])
            self.assertEqual(recommendation["control_scope"]["evidence_only_variables"], ["Q_blast"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
