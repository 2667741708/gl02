"""REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808 contract tests."""

from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import os
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SPEC = importlib.util.spec_from_file_location("si_v20_shadow", BACKEND / "si_v20_shadow.py")
assert SPEC and SPEC.loader
si_v20_shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(si_v20_shadow)


class FakeStore:
    def __init__(self) -> None:
        self.inserted = []
        self.target = {
            "meltno": "2#20260807-095",
            "furnace_no": "2",
            "open_ts": datetime(2026, 8, 7, 7, 40),
            "si_avg": 0.31,
            "source_updated_at": datetime(2026, 8, 7, 10, 0),
        }
        self.heats = [
            {
                "meltno": f"2#20260807-{seq:03d}",
                "open_ts": datetime(2026, 8, 7, hour, 0),
                "source_updated_at": datetime(2026, 8, 7, hour + 1, 0),
                "si_avg": value,
            }
            for seq, hour, value in (
                (90, 0, 0.25),
                (91, 1, 0.30),
                (92, 2, 0.35),
                (93, 3, 0.32),
                (94, 4, 0.28),
            )
        ] + [self.target]

    def get_target(self, meltno):
        return dict(self.target) if meltno == self.target["meltno"] else None

    def all_heats_until(self, furnace_no, target_open_ts):
        return [dict(item) for item in self.heats]

    def insert_prediction(self, row):
        self.inserted.append(dict(row))
        return {
            "prediction_id": 1,
            "requested_at": "2026-08-07 06:40:01+08:00",
            "created_at": "2026-08-07 06:40:01+08:00",
        }

    def get_hourly_prediction(self, _furnace_no, _cutoff_ts):
        return None

    def list_history(self, **_kwargs):
        return [
            {
                "target_meltno": "2#20260807-094",
                "target_open_ts": "2026-08-07 04:00:00",
                "prediction_si_mean": None,
                "actual_si_mean": 0.28,
                "has_prediction": False,
                "actual_ready": True,
                "absolute_error": None,
                "hit_abs_le_005": None,
                "history_status": "actual_only",
            }
        ]

    def get_prediction_detail(self, prediction_id):
        return {
            "prediction_id": prediction_id,
            "target_meltno": "2#20260807-095",
            "prediction_si_mean": 0.31,
            "feature_snapshot": {"history_mean__Si_lag_1": 0.28},
            "model_contract": {"target": "mean_si"},
            "actual_si_mean": 0.32,
        }

    def list_hourly_outcomes(self, **_kwargs):
        return [
            {
                "prediction_id": 8,
                "predicted_target_meltno": "2#20260808-113",
                "matched_actual_meltno": "2#20260808-114",
                "matched_actual_open_ts": "2026-08-08 18:01:00",
                "prediction_si_mean": 0.33,
                "actual_si_mean": 0.37,
                "signed_error": -0.04,
                "absolute_error": 0.04,
                "hit_abs_le_005": True,
            }
        ]


class SiV20ShadowWorkbenchTests(unittest.TestCase):
    def test_prediction_access_does_not_require_login_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BF_SI_V20_REQUIRE_LOGIN", None)
            self.assertFalse(si_v20_shadow.require_login())

    def test_portable_model_export_is_verified(self):
        model = si_v20_shadow.load_model()
        self.assertEqual(model.schema, "bf.si.v20.portable_extra_trees.v1")
        self.assertEqual(model.model_name, "ablation_history")
        self.assertEqual(len(model.feature_columns), 14)
        audit_path = si_v20_shadow.DEFAULT_MODEL_PATH.with_suffix(
            si_v20_shadow.DEFAULT_MODEL_PATH.suffix + ".audit.json"
        )
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "verified_equivalent")
        self.assertLessEqual(audit["max_abs_prediction_delta"], 1e-12)
        self.assertEqual(audit["sha256"], model.sha256)

    def test_history_features_exclude_current_and_unpublished_labels(self):
        heats = [
            {"meltno": "2#20260801-001", "open_ts": "2026-08-01 00:00:00", "source_updated_at": "2026-08-01 02:00:00", "si_avg": 0.20},
            {"meltno": "2#20260801-002", "open_ts": "2026-08-01 02:00:00", "source_updated_at": "2026-08-01 05:00:00", "si_avg": 0.30},
            {"meltno": "2#20260801-003", "open_ts": "2026-08-01 04:00:00", "source_updated_at": "2026-08-01 07:00:00", "si_avg": 0.40},
            {"meltno": "2#20260801-004", "open_ts": "2026-08-01 06:00:00", "source_updated_at": "2026-08-01 05:10:00", "si_avg": 0.99},
        ]
        features = si_v20_shadow.build_history_features(
            target_meltno="2#20260801-004",
            target_open_ts=datetime(2026, 8, 1, 6, 0),
            cutoff_ts=datetime(2026, 8, 1, 5, 30),
            heats=heats,
        )
        self.assertEqual(features["history_mean__Si_lag_1"], 0.30)
        self.assertEqual(features["history_mean__Si_lag_2"], 0.20)
        self.assertIsNone(features["history_mean__Si_lag_3"])
        self.assertEqual(features["v20_history__visible_label_count"], 2.0)
        self.assertEqual(features["v20_history__latest_label_meltno_distance"], 2.0)
        self.assertEqual(features["v20_history__unlabeled_heat_gap"], 1.0)
        self.assertEqual(features["v20_history__recent5_unpublished_count"], 1.0)
        self.assertNotIn(0.99, [features[f"history_mean__Si_lag_{i}"] for i in range(1, 6)])

    def test_prediction_is_persisted_and_returns_later_actual_comparison(self):
        store = FakeStore()
        service = si_v20_shadow.SiV20ShadowService(store=store)
        result = service.predict(
            {
                "target_meltno": "2#20260807-095",
                "cutoff_mode": "explicit",
                "cutoff_ts": "2026-08-07 06:40:00",
            },
            username="furnace_chief",
            role="高炉长",
        )
        prediction = result["prediction"]
        self.assertTrue(prediction["persisted"])
        self.assertEqual(prediction["actual_si_mean"], 0.31)
        self.assertTrue(prediction["actual_ready"])
        self.assertAlmostEqual(prediction["lead_minutes"], 60.0)
        self.assertTrue(0.0 < prediction["si_mean"] < 1.0)
        self.assertEqual(len(store.inserted), 1)
        self.assertEqual(store.inserted[0]["requested_by"], "furnace_chief")
        self.assertEqual(store.inserted[0]["prediction_status"], "experimental_shadow")

    def test_history_keeps_actual_only_heat_visible_without_counting_it_as_evaluated(self):
        service = si_v20_shadow.SiV20ShadowService(store=FakeStore())
        result = service.history(
            date_from=None, date_to=None, meltno=None, limit=100, latest_per_heat=True,
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["metrics"]["actual_count"], 1)
        self.assertEqual(result["metrics"]["prediction_count"], 0)
        self.assertEqual(result["metrics"]["evaluated_count"], 0)
        self.assertEqual(result["items"][0]["actual_si_mean"], 0.28)

    def test_readiness_and_prediction_detail_contracts_are_available(self):
        service = si_v20_shadow.SiV20ShadowService(store=FakeStore())
        readiness = service.data_readiness({
            "target_meltno": "2#20260807-095",
            "target_open_ts": "2026-08-07 07:40:00",
            "cutoff_mode": "explicit",
            "cutoff_ts": "2026-08-07 06:40:00",
        })
        self.assertEqual(readiness["schema"], "bf.si.v20.data_readiness.v1")
        self.assertTrue(readiness["leakage_contract"]["current_target_si_excluded"])
        detail = service.prediction_detail(7)
        self.assertEqual(detail["schema"], "bf.si.v20.prediction_detail.v1")
        self.assertEqual(detail["prediction"]["target_meltno"], "2#20260807-095")

    def test_historical_replay_uses_open_minus_60_minutes_and_skips_missing_open(self):
        store = FakeStore()
        store.targets_for_range = lambda *_args, **_kwargs: [
            {"meltno": "2#20260807-095", "open_ts": datetime(2026, 8, 7, 7, 40)},
            {"meltno": "2#20260807-096", "open_ts": None},
        ]
        service = si_v20_shadow.SiV20ShadowService(store=store)
        calls = []

        def fake_predict_row(**kwargs):
            calls.append(kwargs)
            return {"prediction": {"target_meltno": kwargs["target_meltno"], "lead_minutes": 60.0}}

        with mock.patch.object(service, "_predict_row", side_effect=fake_predict_row):
            result = service.replay(
                {"date_from": "2026-08-07", "date_to": "2026-08-07", "limit": 20},
                username="local_operator",
                role="operator",
            )

        self.assertEqual(result["requested_count"], 2)
        self.assertEqual(result["predicted_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(calls[0]["target_meltno"], "2#20260807-095")
        self.assertEqual(calls[0]["cutoff_ts"], datetime(2026, 8, 7, 6, 40))
        self.assertEqual(calls[0]["request_mode"], "historical_range_replay")

    def test_hourly_prediction_rounds_cutoff_to_hour_and_tags_schedule_mode(self):
        service = si_v20_shadow.SiV20ShadowService(store=FakeStore())
        captured = []

        def fake_predict_row(**kwargs):
            captured.append(kwargs)
            return {"prediction": {"target_meltno": kwargs["target_meltno"], "request_mode": kwargs["request_mode"]}}

        with mock.patch.object(service, "_predict_row", side_effect=fake_predict_row):
            result = service.hourly_predict(
                {
                    "target_meltno": "2#20260807-095",
                    "target_open_ts": "2026-08-07 07:40:00",
                    "cutoff_ts": "2026-08-07 06:00:00",
                },
                username="local_operator",
                role="operator",
            )

        self.assertEqual(result["prediction"]["request_mode"], "hourly_schedule")
        self.assertEqual(captured[0]["cutoff_ts"], datetime(2026, 8, 7, 6, 0))
        self.assertEqual(captured[0]["request_mode"], "hourly_schedule")
        self.assertEqual(
            captured[0]["audit_context"]["hourly_actual_match_rule"],
            "first_real_heat_open_after_requested_at",
        )

    def test_hourly_target_advances_past_stale_candidate(self):
        status = {
            "candidate_targets": [
                {
                    "meltno": "2#20260809-126",
                    "open_ts": "2026-08-09 19:00:00",
                    "recent_median_interval_minutes": 97,
                    "source_type": "22012_local_imes_mirror",
                }
            ],
            "targets": [
                {"meltno": "2#20260809-125", "open_ts": "2026-08-09 17:23:00"},
            ],
        }
        target = si_v20_shadow.resolve_hourly_target(status, datetime(2026, 8, 9, 20, 0))
        self.assertEqual(target["meltno"], "2#20260809-127")
        self.assertEqual(target["open_ts"], "2026-08-09 20:37:00")
        self.assertEqual(target["candidate_status"], "hourly_inferred_next_after_cutoff")

    def test_hourly_duplicate_returns_original_audit_row(self):
        store = FakeStore()
        store.get_hourly_prediction = lambda *_args: {
            "prediction_id": 9,
            "request_id": "existing-hour",
            "target_meltno": "2#20260807-095",
            "target_open_ts": "2026-08-07 07:40:00",
            "prediction_cutoff_ts": "2026-08-07 06:00:00",
            "requested_at": "2026-08-07 06:00:05+08:00",
            "lead_minutes": 100.0,
            "prediction_si_mean": 0.31,
            "prediction_p10": 0.25,
            "prediction_p50": 0.31,
            "prediction_p90": 0.37,
            "feature_snapshot": {"history_mean__Si_lag_1": 0.28},
        }
        service = si_v20_shadow.SiV20ShadowService(store=store)
        result = service.hourly_predict(
            {
                "target_meltno": "2#20260807-095",
                "target_open_ts": "2026-08-07 07:40:00",
                "cutoff_ts": "2026-08-07 06:00:00",
            },
            username="scheduler",
            role="system",
        )
        self.assertTrue(result["prediction"]["deduplicated"])
        self.assertEqual(result["prediction"]["prediction_id"], 9)
        self.assertEqual(len(store.inserted), 0)

    def test_hourly_history_uses_next_real_heat_metrics(self):
        service = si_v20_shadow.SiV20ShadowService(store=FakeStore())
        result = service.hourly_history(
            date_from=None,
            date_to=None,
            limit=100,
        )
        self.assertEqual(result["match_rule"], "first_real_heat_open_after_requested_at")
        self.assertEqual(result["metrics"]["matched_heat_count"], 1)
        self.assertEqual(result["metrics"]["evaluated_count"], 1)
        self.assertAlmostEqual(result["metrics"]["hit_rate_abs_le_005"], 1.0)

    def test_real_mirror_candidates_are_marked_and_not_replaced_by_latest_completed_heat(self):
        historical = [
            {"meltno": "2#20260808-109", "open_ts": "2026-08-08 06:50:00", "close_ts": "2026-08-08 08:30:00", "si_avg": 0.40},
            {"meltno": "2#20260808-110", "open_ts": "2026-08-08 10:03:00", "close_ts": "2026-08-08 12:15:00", "si_avg": 0.41},
        ]
        candidates = si_v20_shadow.build_candidate_targets(historical, [
            {"meltno": "2#20260808-111", "work_date": "2026-08-08", "official_open_ts": None, "official_close_ts": None, "mirrored_at": "2026-08-08 13:55:00"},
            {"meltno": "2#20260808-112", "work_date": "2026-08-08", "official_open_ts": None, "official_close_ts": None, "mirrored_at": "2026-08-08 13:55:00"},
        ])
        self.assertEqual([item["meltno"] for item in candidates], ["2#20260808-111", "2#20260808-112"])
        self.assertTrue(all(item["candidate_time_is_estimated"] for item in candidates))
        self.assertTrue(all(item["source_type"] == "22012_local_imes_mirror" for item in candidates))
        self.assertEqual(candidates[0]["candidate_status"], "planned_not_opened")
        self.assertNotEqual(candidates[0]["meltno"], "2#20260808-110")

    def test_stale_no_time_placeholder_is_not_recommended_after_newer_completed_heat(self):
        historical = [
            {"meltno": "2#20260809-125", "open_ts": "2026-08-09 17:23:00", "close_ts": "2026-08-09 19:00:00", "si_avg": 0.23},
        ]
        candidates = si_v20_shadow.build_candidate_targets(historical, [
            {"meltno": "2#20260808-114", "work_date": "2026-08-08", "official_open_ts": None, "official_close_ts": None},
            {"meltno": "2#20260809-126", "work_date": "2026-08-09", "official_open_ts": None, "official_close_ts": None},
        ])
        self.assertEqual([item["meltno"] for item in candidates], ["2#20260809-126"])

    def test_standalone_page_busts_immutable_workbench_asset_cache(self):
        page = (ROOT / "高炉前端数据" / "si_v20_workbench.html").read_text(encoding="utf-8")
        asset = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-workbench.js").read_text(encoding="utf-8")
        self.assertIn("bf-si-v20-workbench.js?v=20260810-hourly-table-r2", page)
        self.assertNotIn("hourlyAuto", page)
        self.assertIn("严格整点预测（独立常开）", page)
        self.assertIn("state.autoDateTo", asset)
        self.assertIn("最新实际", asset)
        self.assertIn("downloadPredictionBtn", page)
        self.assertIn("downloadActualBtn", page)
        self.assertIn("meltWithinRange", asset)
        self.assertIn("\\ufeff", asset)

    def test_server_and_frontend_contracts_are_mounted_for_both_ports(self):
        server = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
        frontend = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-shadow-workbench.js").read_text(encoding="utf-8")
        main_html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(encoding="utf-8")
        front2_html = (ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html").read_text(encoding="utf-8")
        for route in ("/api/si-v20/status", "/api/si-v20/history", "/api/si-v20/hourly-history", "/api/si-v20/schedule", "/api/si-v20/scheduled-history", "/api/si-v20/data-readiness", "/api/si-v20/prediction-detail", "/api/si-v20/predict", "/api/si-v20/hourly-predict", "/api/si-v20/schedule/configure", "/api/si-v20/schedule/dispatch", "/api/si-v20/scheduled-replay", "/api/si-v20/replay"):
            self.assertIn(route, server)
        self.assertIn("['8093', '8094'].includes(location.port)", frontend)
        self.assertIn("随后获得的实际平均Si", frontend)
        self.assertIn("候选炉次（点击选择）", frontend)
        self.assertIn("查询实际与预测曲线", frontend)
        self.assertIn("bf-si-v20-shadow-workbench.js", main_html)
        self.assertIn("bf-si-v20-shadow-workbench.js", front2_html)
        standalone = (ROOT / "高炉前端数据" / "si_v20_workbench.html").read_text(encoding="utf-8")
        standalone_js = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-workbench.js").read_text(encoding="utf-8")
        self.assertIn("严格整点预测汇总", standalone)
        self.assertIn("20260810-hourly-table-r2", standalone)
        self.assertIn("/api/si-v20/hourly-history", standalone_js)
        self.assertIn("匹配实际", standalone_js)


if __name__ == "__main__":
    unittest.main()
