#!/usr/bin/env python3
"""Read-only verification of the V20 schedule tables on the active server database."""

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
                    to_regclass('bf_assistant.si_v20_prediction_schedule')::text AS schedule_table,
                    to_regclass('bf_assistant.si_v20_prediction_run')::text AS run_table,
                    to_regclass('bf_assistant.si_v20_prediction_audit')::text AS audit_table
                """
            )
            tables = cursor.fetchone()
            cursor.execute(
                """
                SELECT schedule_id, schedule_key, furnace_no, enabled,
                       cadence_minutes, next_slot_ts, last_slot_ts, last_run_status
                FROM bf_assistant.si_v20_prediction_schedule
                ORDER BY schedule_id
                """
            )
            schedules = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT COUNT(*) AS scheduled_point_count,
                       MAX(schedule_slot_ts) AS latest_schedule_slot
                FROM bf_assistant.si_v20_prediction_audit
                WHERE schedule_id IS NOT NULL
                """
            )
            audit = dict(cursor.fetchone())
    payload = {
        "ok": all(tables.values()),
        "schema": "ops.si-v20.schedule-production-db-verification.v1",
        "tables": {
            "schedule": tables["schedule_table"],
            "run": tables["run_table"],
            "audit": tables["audit_table"],
        },
        "schedules": schedules,
        "audit": audit,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
