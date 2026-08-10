#!/usr/bin/env python3
"""Read-only database verification for the V20 strict whole-hour channel."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
sys.path.insert(0, str(BACKEND))

from si_v20_shadow import SiV20ShadowStore  # noqa: E402


def main() -> int:
    store = SiV20ShadowStore()
    with store.connect(read_only=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    to_regclass('bf_assistant.si_v20_strict_hourly_slot')::text AS slot_table,
                    to_regclass('bf_assistant.si_v20_prediction_audit')::text AS audit_table,
                    to_regclass('bf_assistant.heat_performance_quality_summary')::text AS actual_table
                """
            )
            tables = dict(cursor.fetchone())
            cursor.execute(
                """
                SELECT COUNT(*) AS slot_count,
                       COUNT(*) FILTER (WHERE slot_status = 'success') AS succeeded_count,
                       COUNT(*) FILTER (WHERE slot_status IN ('pending','failed_retryable')) AS retryable_count,
                       COUNT(*) FILTER (WHERE slot_status = 'running') AS running_count,
                       COUNT(*) FILTER (
                           WHERE slot_status = 'running'
                             AND requested_at < now() - interval '10 minutes'
                       ) AS stale_running_count,
                       COUNT(*) FILTER (
                           WHERE schedule_slot_ts < date_trunc('hour', now())
                             AND slot_status <> 'success'
                       ) AS overdue_incomplete_count,
                       MIN(schedule_slot_ts) AS first_slot,
                       MAX(schedule_slot_ts) AS last_slot,
                       COUNT(*) - COUNT(DISTINCT (furnace_no, schedule_slot_ts)) AS duplicate_slots,
                       COUNT(*) FILTER (
                           WHERE date_part('minute', schedule_slot_ts) <> 0
                              OR date_part('second', schedule_slot_ts) <> 0
                       ) AS non_hour_slots
                FROM bf_assistant.si_v20_strict_hourly_slot
                """
            )
            slots = dict(cursor.fetchone())
            cursor.execute(
                """
                SELECT schedule_slot_ts, slot_status, attempt_count,
                       requested_at, completed_at, prediction_id, last_error
                  FROM bf_assistant.si_v20_strict_hourly_slot
                 ORDER BY schedule_slot_ts DESC
                 LIMIT 24
                """
            )
            recent_slots = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT COUNT(*) AS prediction_count,
                       COUNT(*) FILTER (WHERE matched_actual_meltno IS NOT NULL) AS frozen_match_count,
                       COUNT(*) FILTER (
                           WHERE prediction_cutoff_ts <> schedule_slot_ts
                              OR date_part('minute', prediction_cutoff_ts) <> 0
                              OR date_part('second', prediction_cutoff_ts) <> 0
                       ) AS cutoff_contract_violations,
                       MAX(schedule_slot_ts) AS latest_prediction_slot,
                       MAX(execution_completed_at) AS latest_completed_at
                FROM bf_assistant.si_v20_prediction_audit
                WHERE request_mode = 'strict_hourly'
                """
            )
            predictions = dict(cursor.fetchone())
            cursor.execute(
                """
                SELECT COUNT(*) FILTER (WHERE si_avg IS NOT NULL) AS si_rows,
                       COUNT(*) FILTER (
                           WHERE si_avg IS NOT NULL
                             AND si_availability_confidence = 'legacy_availability_unknown'
                       ) AS legacy_availability_unknown,
                       COUNT(*) FILTER (
                           WHERE si_avg IS NOT NULL AND si_available_at IS NULL
                       ) AS missing_availability
                FROM bf_assistant.heat_performance_quality_summary
                """
            )
            availability = dict(cursor.fetchone())
            cursor.execute(
                """
                SELECT meltno, open_ts, close_ts, si_avg,
                       si_available_at, si_availability_confidence,
                       source_updated_at, source_status, aggregated_at
                  FROM bf_assistant.heat_performance_quality_summary
                 WHERE si_avg IS NOT NULL
                   AND si_available_at IS NULL
                 ORDER BY COALESCE(source_updated_at, aggregated_at) DESC
                 LIMIT 20
                """
            )
            missing_availability_rows = [dict(row) for row in cursor.fetchall()]
    ok = bool(
        all(tables.values())
        and slots["duplicate_slots"] == 0
        and slots["non_hour_slots"] == 0
        and slots["stale_running_count"] == 0
        and slots["overdue_incomplete_count"] == 0
        and predictions["cutoff_contract_violations"] == 0
        and availability["missing_availability"] == 0
    )
    payload = {
        "ok": ok,
        "schema": "ops.si-v20.strict-hourly-production-db-verification.v1",
        "tables": tables,
        "slots": slots,
        "recent_slots": recent_slots,
        "predictions": predictions,
        "si_availability": availability,
        "missing_availability_rows": missing_availability_rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
