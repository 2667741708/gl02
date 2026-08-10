"""Read-only PostgreSQL privilege probe for the 220.12 diagnosis review store."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg


def main() -> int:
    host = os.getenv("GL02_PGHOST") or "127.0.0.1"
    port = int(os.getenv("GL02_PGPORT") or "5432")
    database = os.getenv("GL02_PGDATABASE") or "bf_trend"
    user = os.getenv("GL02_PGUSER") or ""
    password = os.getenv("GL02_PGPASSWORD") or ""
    if not user or not password:
        raise RuntimeError("GL02 PostgreSQL machine credentials are not configured")
    with psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=5,
    ) as connection:
        result = connection.execute(
            """
            SELECT json_build_object(
              'database', current_database(),
              'user', current_user,
              'server_version', current_setting('server_version'),
              'database_create', has_database_privilege(current_user, current_database(), 'CREATE'),
              'bf_sensor_usage', has_schema_privilege(current_user, 'bf_sensor', 'USAGE'),
              'bf_sensor_create', has_schema_privilege(current_user, 'bf_sensor', 'CREATE'),
              'bf_assistant_exists', to_regnamespace('bf_assistant') IS NOT NULL,
              'bf_assistant_usage', CASE WHEN to_regnamespace('bf_assistant') IS NULL THEN NULL ELSE has_schema_privilege(current_user, 'bf_assistant', 'USAGE') END,
              'bf_assistant_create', CASE WHEN to_regnamespace('bf_assistant') IS NULL THEN NULL ELSE has_schema_privilege(current_user, 'bf_assistant', 'CREATE') END,
              'review_table_exists', to_regclass('bf_assistant.diagnosis_review_events') IS NOT NULL,
              'manual_score_table_exists', to_regclass('bf_assistant.diagnosis_manual_score_events') IS NOT NULL,
              'ai_analysis_table_exists', to_regclass('bf_assistant.diagnosis_ai_analysis_snapshots') IS NOT NULL,
              'diagnosis_snapshots_select', has_table_privilege(current_user, 'bf_sensor.diagnosis_snapshots', 'SELECT')
            )
            """
        ).fetchone()[0]
        if result["review_table_exists"]:
            result["review_row_count"] = connection.execute(
                "SELECT count(*) FROM bf_assistant.diagnosis_review_events"
            ).fetchone()[0]
        if result["manual_score_table_exists"]:
            result["manual_score_row_count"] = connection.execute(
                "SELECT count(*) FROM bf_assistant.diagnosis_manual_score_events"
            ).fetchone()[0]
        if result["ai_analysis_table_exists"]:
            result["ai_analysis_row_count"] = connection.execute(
                "SELECT count(*) FROM bf_assistant.diagnosis_ai_analysis_snapshots"
            ).fetchone()[0]
        if result["diagnosis_snapshots_select"]:
            latest = connection.execute(
                """
                SELECT id, diagnosis_ts, main_label
                FROM bf_sensor.diagnosis_snapshots
                ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            result["latest_diagnosis"] = {
                "id": latest[0] if latest else None,
                "diagnosis_ts": latest[1].isoformat() if latest else None,
                "main_label": latest[2] if latest else None,
            }
    os.environ["BF_DIAG_REVIEW_PGHOST"] = host
    os.environ["BF_DIAG_REVIEW_PGPORT"] = str(port)
    os.environ["BF_DIAG_REVIEW_PGDATABASE"] = database
    os.environ["BF_DIAG_REVIEW_PGUSER"] = user
    os.environ["BF_DIAG_REVIEW_PGPASSWORD"] = password
    os.environ["BF_DIAG_REVIEW_PGSCHEMA"] = "bf_assistant"
    temp_dir = Path(os.environ.get("TEMP") or r"C:\Users\Administrator\AppData\Local\Temp")
    sys.path.insert(0, str(temp_dir))
    import diagnosis_review  # type: ignore

    store = diagnosis_review.DiagnosisReviewStore()
    rows = store.read_latest_diagnosis_rows(limit=32)
    context = diagnosis_review.derive_current_episode(rows, furnace_id="BF")
    result["derived_context"] = {
        "available": bool(context.get("available")),
        "diagnosis_ts": context.get("diagnosis_ts"),
        "main_label": context.get("main_label"),
        "candidate_count": len(context.get("candidates") or []),
    }
    print(json.dumps({
        "schema": "ops.8093.diagnosis-review.pg-privilege-probe.v1",
        "endpoint": f"{host}:{port}/{database}",
        "result": result,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
