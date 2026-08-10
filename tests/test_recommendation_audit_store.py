"""Contract tests for full-fidelity append-only recommendation persistence."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from recommendation_adapter import generate_recommendation_bundle  # noqa: E402
from recommendation_audit_store import (  # noqa: E402
    ACTION_STATUSES,
    RecommendationAuditValidationError,
    build_audit_identity,
    persist_recommendation_bundle,
    canonical_json,
    validate_recommendation_bundle,
)


def diagnosis_payload() -> dict:
    return {
        "diagnosis_ts": "2026-08-06 11:05:00",
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
        "data_coverage": {"available": 28, "total": 28, "ratio": 1.0},
        "missing_variables": [],
        "feature_snapshot": {},
    }


def current_values() -> dict:
    return {
        "P_top": 180,
        "T_top": 108,
        "T_blast": 1120,
        "GasUtil": 42,
        "L": 2.0,
        "P_blast_cold": 450,
        "PCI_set": 40,
        "PCI_rate": 40,
        "current_values_timestamp": "2026-08-06 11:05:00",
        "P_blast_cold_timestamp": "2026-08-06 11:05:00",
        "pressure_baseline_p25": 438,
        "pressure_baseline_p75": 475,
        "pressure_baseline_day": "2026-08-06",
        "pressure_baseline_sample_count": 40000,
        "pressure_baseline_coverage_ratio": 0.95,
        "pressure_baseline_updated_at": "2026-08-06 00:05:00",
        "coal_ash_pct": 12.5,
        "anthracite_200mesh_pct": 78,
        "coal_moisture_pct": 0.8,
        "coal_analysis_current_flag": 1,
        "serious_abnormal_flag": 0,
        "serious_cold_flag": 0,
        "blast_reduced_flag": 0,
        "pressure_mode": "high_pressure",
        "blast_stable_flag": 1,
        "hot_state_sufficient_flag": 1,
        "slag_iron_drained_flag": 1,
        "DP_total": 2.1,
        "approved_dp_limit": 3.0,
        "unsmooth_condition_flag": 1,
    }


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeAuditConnection:
    def __init__(self):
        self.next_batch_id = 1
        self.batches: dict[str, dict] = {}
        self.actions: dict[int, list[tuple]] = {}

    def transaction(self):
        return nullcontext()

    def execute(self, sql: str, params=()):
        normalized = " ".join(sql.split())
        if "INSERT INTO bf_assistant.recommendation_audit_batches" in normalized:
            key = params[1]
            if key in self.batches:
                return FakeCursor(None)
            row = {
                "id": self.next_batch_id,
                "recommendation_bundle": json.loads(params[22]),
                "action_count": params[20],
                "status_counts": json.loads(params[21]),
                "created_at": "2026-08-06T11:05:01+08:00",
            }
            self.next_batch_id += 1
            self.batches[key] = row
            self.actions[row["id"]] = []
            return FakeCursor(row)
        if "INSERT INTO bf_assistant.recommendation_audit_actions" in normalized:
            self.actions[int(params[0])].append(tuple(params))
            return FakeCursor(None)
        if "FROM bf_assistant.recommendation_audit_batches" in normalized:
            return FakeCursor(self.batches.get(params[0]))
        if "FROM bf_assistant.recommendation_audit_actions WHERE batch_id" in normalized:
            return FakeCursor({"count": len(self.actions.get(int(params[0]), []))})
        raise AssertionError(f"unexpected SQL: {normalized[:160]}")


class RecommendationAuditContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diagnosis = diagnosis_payload()
        self.values = current_values()
        self.bundle = generate_recommendation_bundle(self.diagnosis, self.values)

    def test_full_bundle_contains_eight_conditions_and_all_audit_fields(self) -> None:
        rows = validate_recommendation_bundle(self.bundle)
        self.assertEqual(len(self.bundle["conditions"]), 8)
        self.assertEqual(len(rows), 16)
        statuses = {item["action"]["status"] for item in rows}
        self.assertTrue(statuses.issubset(ACTION_STATUSES))
        action = next(item["action"] for item in rows if item["action"]["id"] == "LOW-PCI-UP-02")
        for field in (
            "source_refs",
            "trigger_evidence",
            "preconditions",
            "blocking_reasons",
            "delta",
            "sequence",
            "missing_inputs",
            "observation_window",
            "approval",
            "control_variable",
            "control_label",
            "current_value",
            "recommended_change",
            "recommended_target",
            "unit",
            "step_tier",
            "effective_at",
            "limit_snapshot",
        ):
            with self.subTest(field=field):
                self.assertIn(field, action)

    def test_missing_sequence_is_rejected_before_database_write(self) -> None:
        broken = copy.deepcopy(self.bundle)
        del broken["conditions"][0]["recommendation"]["actions"][0]["sequence"]
        with self.assertRaises(RecommendationAuditValidationError):
            validate_recommendation_bundle(broken)

    def test_non_finite_sensor_values_are_stored_as_json_null(self) -> None:
        encoded = canonical_json({"T_blast": float("nan"), "P_top": float("inf")})
        self.assertEqual(json.loads(encoded), {"P_top": None, "T_blast": None})

    def test_identity_is_stable_for_same_diagnosis_engine_and_policy(self) -> None:
        first, identity = build_audit_identity(
            self.diagnosis,
            self.bundle,
            diagnosis_snapshot_id=124,
            furnace_id="GL02",
        )
        changed_bundle = copy.deepcopy(self.bundle)
        changed_bundle["conditions"][0]["recommendation"]["goal"] = "different transient rendering"
        second, _ = build_audit_identity(
            self.diagnosis,
            changed_bundle,
            diagnosis_snapshot_id=124,
            furnace_id="GL02",
        )
        self.assertEqual(first, second)
        self.assertEqual(identity["policy_sha256"], self.bundle["engine_meta"]["policy_sha256"])

    def test_first_bundle_is_immutable_and_duplicate_returns_persisted_bundle(self) -> None:
        conn = FakeAuditConnection()
        first = persist_recommendation_bundle(
            conn,
            self.diagnosis,
            self.values,
            self.bundle,
            diagnosis_snapshot_id=124,
        )
        changed = copy.deepcopy(self.bundle)
        changed["conditions"][0]["recommendation"]["goal"] = "must not replace audit payload"
        second = persist_recommendation_bundle(
            conn,
            self.diagnosis,
            {**self.values, "T_blast": 1130},
            changed,
            diagnosis_snapshot_id=124,
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertEqual(first["bundle"], second["bundle"])
        self.assertEqual(len(conn.actions[first["batch_id"]]), first["action_count"])

    def test_schema_is_append_only_and_enumerates_all_statuses(self) -> None:
        ddl = (SERVICE_DIR / "recommendation_audit_schema.sql").read_text(encoding="utf-8")
        self.assertIn("recommendation_audit_batches", ddl)
        self.assertIn("recommendation_audit_actions", ddl)
        self.assertIn("recommendation_bundle jsonb NOT NULL", ddl)
        self.assertIn("action_payload jsonb NOT NULL", ddl)
        self.assertIn("control_variable text", ddl)
        self.assertIn("recommended_target double precision", ddl)
        self.assertIn("recommendation_audit.v2", ddl)
        self.assertIn("'eligible','blocked','needs_data','manual_confirm'", ddl)
        self.assertIn("ON DELETE RESTRICT", ddl)
        self.assertIn("reject_recommendation_audit_mutation", ddl)
        self.assertIn("BEFORE UPDATE OR DELETE OR TRUNCATE", ddl)

    def test_ws_bridge_fails_closed_when_audit_persistence_fails(self) -> None:
        source = (SERVICE_DIR / "local_pg_ws_bridge.py").read_text(encoding="utf-8")
        self.assertIn("persist_recommendation_bundle", source)
        self.assertIn('"reason": "full_audit_persistence_required"', source)
        self.assertIn('payload.pop("recommendation_bundle", None)', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
