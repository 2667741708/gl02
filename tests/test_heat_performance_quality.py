from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from heat_performance_quality import (  # noqa: E402
    AGGREGATION_VERSION,
    SCHEMA_UPGRADE_DDL,
    TABLE_DDL,
    HeatPerformanceQualityStore,
    _json_safe,
    build_gap_audit,
    build_summary_row,
    chemistry_statistics,
)


def test_json_safe_serializes_date_and_datetime_with_their_supported_contracts() -> None:
    assert _json_safe(date(2026, 8, 6)) == "2026-08-06"
    assert _json_safe(datetime(2026, 8, 6, 14, 30, 5)) == "2026-08-06 14:30:05"
    assert _json_safe(Decimal("0.230000")) == 0.23


def sample(seq: int, si: float, *, c: float = 4.9, mn: float = 0.25) -> dict:
    return {
        "sample_no": f"22608-065-{seq:03d}",
        "sample_ts": datetime(2026, 8, 5, 4 + seq, 30),
        "C": c,
        "Si": si,
        "Mn": mn,
        "P": 0.16,
        "S": 0.04,
    }


def test_chemistry_statistics_keeps_average_median_range_and_count() -> None:
    stats = chemistry_statistics([sample(1, 0.20), sample(2, 0.25), sample(3, 0.24)])

    assert stats["Si"]["valid_count"] == 3
    assert round(stats["Si"]["avg"], 6) == 0.23
    assert stats["Si"]["median"] == 0.24
    assert stats["Si"]["min"] == 0.20
    assert stats["Si"]["max"] == 0.25
    assert round(stats["Si"]["spread"], 6) == 0.05


def test_build_summary_row_is_one_official_heat_and_preserves_samples() -> None:
    row = build_summary_row({
        "meltno": "2#20260805-065",
        "workdate": "2026-08-05",
        "open_ts": datetime(2026, 8, 5, 4, 20),
        "close_ts": datetime(2026, 8, 5, 6, 45),
        "duration_minutes": 145,
        "theory_iron_qty": 610,
        "actual_iron_qty": 606.5,
        "slag_rate": 0.32,
        "output_count": 2,
        "batch_start": "B100",
        "batch_end": "B112",
        "batch_count": 13,
        "hot_metal_samples": [sample(1, 0.20), sample(2, 0.25), sample(3, 0.24)],
        "alignment_status": "partial",
        "outputs": [
            {"gross_weight": 330.0, "tare_weight": 25.0},
            {"gross_weight": 326.5, "tare_weight": 24.0},
        ],
    })

    assert row["meltno"] == "2#20260805-065"
    assert row["furnace_no"] == "2"
    assert row["hot_metal_sample_count"] == 3
    assert round(row["si_avg"], 6) == 0.23
    assert row["si_median"] == 0.24
    assert row["si_band"] == "target"
    assert row["quality_status"] == "complete"
    assert len(row["sample_details"]) == 3
    assert row["batch_count"] == 13
    assert row["gross_weight_total"] == 656.5
    assert row["tare_weight_total"] == 49.0
    assert row["net_weight_total"] == 607.5
    assert len(row["output_details"]) == 2
    assert row["aggregation_version"] == AGGREGATION_VERSION
    assert "不替代" not in row["quality_summary"]


def test_build_summary_row_marks_partial_and_missing_without_zero_fill() -> None:
    row = build_summary_row({
        "meltno": "2#20260805-066",
        "open_ts": datetime(2026, 8, 5, 7, 0),
        "hot_metal_samples": [{"sample_no": "x", "Si": 0.45}],
    })

    assert row["quality_status"] == "partial"
    assert row["si_band"] == "above_target"
    assert row["c_avg"] is None
    assert row["missing_elements"] == ["C", "Mn", "P", "S"]


def test_schema_contract_has_primary_key_json_lineage_and_no_raw_overwrite() -> None:
    assert "meltno text PRIMARY KEY" in TABLE_DDL
    assert "chemistry_stats jsonb" in TABLE_DDL
    assert "sample_details jsonb" in TABLE_DDL
    assert "output_details jsonb" in TABLE_DDL
    assert "aggregation_version text NOT NULL" in TABLE_DDL
    assert "time_anomaly_reasons jsonb" in TABLE_DDL
    assert "repair_checked_at timestamp with time zone" in TABLE_DDL
    assert "future_pending boolean" in TABLE_DDL
    assert "ADD COLUMN IF NOT EXISTS time_anomaly_reasons" in SCHEMA_UPGRADE_DDL
    assert "DROP TABLE" not in TABLE_DDL.upper()


def test_summary_preserves_structured_time_repair_lineage() -> None:
    checked_at = datetime(2026, 8, 7, 10, 15)
    row = build_summary_row({
        "meltno": "2#20260806-090",
        "open_ts": datetime(2026, 8, 6, 23, 33),
        "close_ts": datetime(2026, 8, 7, 0, 30),
        "raw_open_ts": datetime(2026, 8, 7, 23, 33),
        "raw_close_ts": datetime(2026, 8, 7, 0, 30),
        "repaired_open_ts": datetime(2026, 8, 6, 23, 33),
        "repaired_close_ts": datetime(2026, 8, 7, 0, 30),
        "alignment_status": "time_anomaly_repaired",
        "time_anomaly_reasons": ["opentime_date_rebased_to_workdate", "closetime_rollover_next_day"],
        "repair_checked_at": checked_at,
        "future_pending": False,
        "hot_metal_samples": [],
    })

    assert row["source_status"] == "time_anomaly_repaired"
    assert row["time_anomaly_reasons"] == [
        "opentime_date_rebased_to_workdate",
        "closetime_rollover_next_day",
    ]
    assert row["repair_checked_at"] == checked_at
    assert row["future_pending"] is False


def test_gap_audit_reports_missing_summary_fields_and_sample_changes() -> None:
    rows = [
        {"meltno": "2#20260807-095", "open_ts": datetime(2026, 8, 7, 7, 40), "close_ts": None,
         "output_count": 1, "hot_metal_sample_count": 2},
        {"meltno": "2#20260807-096", "open_ts": datetime(2026, 8, 7, 9, 26), "close_ts": None,
         "output_count": 2, "hot_metal_sample_count": 2},
    ]
    existing = {
        "2#20260807-096": {
            "meltno": "2#20260807-096", "open_ts": None, "close_ts": None,
            "output_count": 0, "hot_metal_sample_count": 1,
        },
    }

    mirror = {
        "2#20260807-096": {
            "meltno": "2#20260807-096", "mirror_row_count": 1,
            "open_ts_present": False, "close_ts_present": False,
            "output_present": False, "si_present": True,
        },
    }
    audit = build_gap_audit(rows, existing, mirror=mirror)

    assert audit["source_present_mirror_missing"] == ["2#20260807-095"]
    assert audit["summary_missing"] == ["2#20260807-095"]
    assert audit["source_field_mirror_empty"] == [{
        "meltno": "2#20260807-096",
        "fields": ["open_ts", "output_count"],
    }]
    assert audit["mirror_audit_available"] is True
    assert audit["sample_count_changes"][0]["delta"] == 1


def test_upsert_sql_protects_repaired_lineage_but_allows_matured_future_row() -> None:
    executed: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):
            executed.append(str(sql))

    class Store(HeatPerformanceQualityStore):
        def connect(self, *, read_only=True):
            return Connection()

    Store().upsert_rows([{"meltno": "2#20260806-090"}])
    sql = executed[0]

    assert "existing.source_status = 'time_anomaly_repaired'" in sql
    assert "existing.source_status = 'future_pending'" in sql
    assert "existing.open_ts > now() + interval '5 minutes'" in sql
    assert "existing.time_anomaly_reasons ? 'meltno_workdate_date_mismatch'" in sql
    assert "raw_open_ts=CASE" in sql
    assert "time_anomaly_reasons=CASE" in sql
    assert "WHEN EXCLUDED.si_avg IS NOT NULL" in sql
    assert "COALESCE(EXCLUDED.si_available_at, existing.aggregated_at, now())" in sql


def test_schema_upgrade_recovers_missing_si_availability_from_aggregation_time() -> None:
    assert "COALESCE(si_available_at, aggregated_at, now())" in SCHEMA_UPGRADE_DDL
    assert "'recovered_aggregation_timestamp'" in SCHEMA_UPGRADE_DDL


def test_list_api_hides_future_pending_by_default_and_allows_explicit_audit_view() -> None:
    source = (BACKEND / "heat_performance_quality.py").read_text(encoding="utf-8")
    proxy = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")

    assert 'clauses.append("future_pending IS NOT TRUE")' in source
    assert "include_future: bool = False" in source
    assert 'params.get("include_future", ["0"])' in proxy
    assert "include_future=include_future" in proxy


def test_8093_frontend_exposes_real_loading_empty_error_and_sample_states() -> None:
    html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(encoding="utf-8")
    asset = (ROOT / "高炉前端数据" / "assets" / "bf-heat-performance-quality-8093-query-v2.js").read_text(encoding="utf-8")

    assert "bf-heat-performance-quality-8093-query-v2.js?v=20260807-query-v2" in html
    assert "/api/heat-performance-quality?" in asset
    assert "正在读取最近炉次" in asset
    assert "暂时没有已聚合的炉次数据" in asset
    assert "读取失败" in asset
    assert "原始试样" in asset
    assert "实绩铁量" in asset


def test_proxy_registers_read_only_heat_performance_endpoint() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")

    assert 'parsed.path == "/api/heat-performance-quality"' in source
    assert "HeatPerformanceQualityStore().list_rows" in source
    assert '"read_only": True' in source


def test_table_readiness_probe_uses_dict_row_key_not_numeric_index() -> None:
    source = (BACKEND / "heat_performance_quality.py").read_text(encoding="utf-8")

    assert "AS relation_name" in source
    assert 'exists_row["relation_name"]' in source
    assert 'fetchone()[0]' not in source
