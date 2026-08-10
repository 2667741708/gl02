from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
V4_ROOT = WORKSPACE.parent / "服务器实际运行版V4"
SYNC_ROOT = V4_ROOT / "数据库同步和存取"
MODULE_PATH = SYNC_ROOT / "src" / "raw_minute_pipeline.py"


def load_module():
    spec = importlib.util.spec_from_file_location("raw_minute_pipeline_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeT:
    Return = "Return"
    HisReadRawTimeStamp = "timestamp"
    HisReadRawValueDict = "value"
    HisReadRawQualityDict = "quality"


class FakePspaceHistory:
    @staticmethod
    def numeric_items(tag_result):
        return [(str(index), value) for index, value in enumerate(tag_result["rows"])]

    @staticmethod
    def parse_timestamp(value):
        return datetime.fromisoformat(value)

    @staticmethod
    def coerce_number(value):
        return None if value is None else float(value)

    @staticmethod
    def floor_timestamp(value, interval_seconds):
        start = value.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds = int((value - start).total_seconds())
        return start + timedelta(seconds=(seconds // interval_seconds) * interval_seconds)

    @staticmethod
    def timestamp_text(value):
        return value.strftime("%Y-%m-%d %H:%M:%S")


class MinuteAverageSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_quality_contract(self):
        self.assertTrue(self.module.quality_is_good(""))
        self.assertTrue(self.module.quality_is_good("Good"))
        self.assertTrue(self.module.quality_is_good("Good(CALCULATED)"))
        self.assertTrue(self.module.quality_is_good("192"))
        self.assertFalse(self.module.quality_is_good("Bad"))

    def test_good_raw_samples_are_averaged_and_audited(self):
        result = {
            "tag-a": {
                "rows": [
                    {"timestamp": "2026-08-05 12:00:00", "value": 10, "quality": "Good"},
                    {"timestamp": "2026-08-05 12:00:05", "value": 100, "quality": "Bad"},
                    {"timestamp": "2026-08-05 12:00:10", "value": 20, "quality": "Good"},
                    {"timestamp": "2026-08-05 12:00:15", "value": None, "quality": "Good"},
                ]
            }
        }
        series, audits, raw_rows, errors = self.module.parse_raw_result_details(
            result,
            FakeT,
            ["tag-a"],
            FakePspaceHistory,
            target_interval_seconds=60,
            source_interval_seconds=5,
            observed_at=datetime.fromisoformat("2026-08-05 12:02:00"),
        )
        self.assertEqual(errors, {})
        self.assertEqual(series["tag-a"]["2026-08-05 12:00:00"], 15.0)
        audit = audits["tag-a"]["2026-08-05 12:00:00"]
        self.assertEqual(audit["sample_count"], 4)
        self.assertEqual(audit["numeric_sample_count"], 3)
        self.assertEqual(audit["good_sample_count"], 2)
        self.assertEqual(audit["expected_sample_count"], 12)
        self.assertAlmostEqual(audit["coverage_ratio"], 2 / 12)
        self.assertEqual(audit["min_value"], 10.0)
        self.assertEqual(audit["max_value"], 20.0)
        self.assertEqual(audit["last_value"], 20.0)
        self.assertEqual(audit["semantic_version"], "valid_raw_mean_v1")
        self.assertTrue(audit["window_complete"])
        self.assertEqual(len(raw_rows["tag-a"]), 4)

    def test_open_minute_is_not_marked_complete_and_bad_rows_are_retained(self):
        result = {
            "tag-a": {
                "rows": [
                    {"timestamp": "2026-08-05 12:01:05", "value": 10, "quality": "Bad"},
                ]
            }
        }
        series, audits, raw_rows, errors = self.module.parse_raw_result_details(
            result,
            FakeT,
            ["tag-a"],
            FakePspaceHistory,
            target_interval_seconds=60,
            source_interval_seconds=5,
            minute_completion_lag_seconds=60,
            observed_at=datetime.fromisoformat("2026-08-05 12:02:30"),
        )
        self.assertEqual(series, {})
        self.assertEqual(errors["tag-a"], "no good raw rows returned")
        self.assertEqual(len(raw_rows["tag-a"]), 1)
        self.assertFalse(audits["tag-a"]["2026-08-05 12:01:00"]["window_complete"])

    def test_configuration_and_schema_use_canonical_average(self):
        config = json.loads((SYNC_ROOT / "config" / "sync_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["source"]["source_aggregate"], "average")
        self.assertEqual(config["source"]["target_aggregate"], "PS_RAW_AVERAGE")
        self.assertTrue(config["source"]["persist_raw_5s"])
        self.assertEqual(config["source"]["raw_retention_days"], 30)
        self.assertEqual(config["source"]["minute_completion_lag_seconds"], 60)

        schema = (SYNC_ROOT / "schema" / "postgresql_required_points.sql").read_text(encoding="utf-8")
        for column in (
            "sample_count",
            "numeric_sample_count",
            "good_sample_count",
            "expected_sample_count",
            "coverage_ratio",
            "min_value",
            "max_value",
            "last_value",
            "window_complete",
            "semantic_version",
        ):
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", schema)

    def test_runtime_wrapper_has_single_writer_lock_and_average_flags(self):
        wrapper = (SYNC_ROOT / "run_realtime_sync_pg_bg.ps1").read_text(encoding="utf-8")
        self.assertIn("[System.IO.FileShare]::None", wrapper)
        self.assertIn("$SharedLockDir = Join-Path $ProjectRoot 'logs'", wrapper)
        self.assertIn('$ConfigPath = Join-Path $ScriptRoot "config\\sync_config.json"', wrapper)
        self.assertIn("--config $ConfigPath", wrapper)
        self.assertIn("--target-aggregate PS_RAW_AVERAGE", wrapper)
        self.assertIn("--source-aggregate $SourceAggregate", wrapper)
        self.assertIn("--persist-raw-5s", wrapper)
        self.assertIn("--raw-retention-days 30", wrapper)

    def test_processed_backfill_does_not_inherit_raw_target_label(self):
        source = (SYNC_ROOT / "src" / "sync_from_243_pg.py").read_text(encoding="utf-8")
        self.assertIn('elif source_mode == "raw":', source)
        self.assertIn('source_cfg.get("aggregate") or "PS_HIS_AVERAGE"', source)


if __name__ == "__main__":
    unittest.main()
