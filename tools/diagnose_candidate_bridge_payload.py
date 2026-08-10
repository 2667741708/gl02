from __future__ import annotations

import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def main() -> int:
    root = Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW")
    service_dir = root / "自动诊断服务"
    sys.path.insert(0, str(service_dir))
    candidate = service_dir / "local_pg_ws_bridge.candidate.py"
    spec = importlib.util.spec_from_file_location("abc_candidate_bridge", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with psycopg.connect(**module.pg_params(), row_factory=dict_row) as connection:
        timestamp, values = module.latest_values(connection)
        context = module.build_foreman_recommendation_context(connection, values, timestamp)
        payload = module.latest_diagnosis(connection, context)
        row = connection.execute(
            """SELECT id,diagnosis_ts,diagnosis_json FROM bf_sensor.diagnosis_snapshots
               ORDER BY diagnosis_ts DESC,updated_at DESC NULLS LAST,created_at DESC NULLS LAST,id DESC LIMIT 1"""
        ).fetchone()
        anchor = row["diagnosis_ts"].replace(tzinfo=None)
        history = module.fetch_abc_history(connection, anchor - timedelta(minutes=89), anchor)
        baseline = module.fetch_abc_baselines(connection, anchor)
        combined = dict(context)
        combined.update((row.get("diagnosis_json") or {}).get("feature_snapshot") or {})
        if history:
            for variable in module.ABC_HISTORY_VARIABLES:
                combined.pop(variable, None)
            combined.update(module.abc_aligned_current(history))
        config = module.load_abc_config()
        features, quality = module.build_abc_feature_snapshot(
            combined,
            baseline=baseline,
            history=history,
            data_age_seconds=(row.get("diagnosis_json") or {}).get("source_lag_seconds"),
            coverage_ratio=((row.get("diagnosis_json") or {}).get("data_coverage") or {}).get("coverage_ratio", 0.0),
            thresholds=config.get("feature_thresholds") or {},
        )
        internal = module.evaluate_abc(features, quality=quality, timestamp=row["diagnosis_ts"], config=config)

    bundle = payload.get("abc_rule_bundle") or {}
    rules = bundle.get("rules") or []
    result = {
        "timestamp": str(timestamp),
        "payload_keys": sorted(payload.keys()),
        "abc_schema": bundle.get("schema_version"),
        "abc_state": bundle.get("state"),
        "abc_error_type": bundle.get("error_type"),
        "rule_count": len(rules),
        "rule_statuses": {
            status: sum((rule.get("status") or rule.get("state")) == status for rule in rules)
            for status in ("eligible", "blocked", "needs_data", "manual_confirm", "normal", "watch", "warning", "critical")
        },
        "recommendation_state": (payload.get("recommendation_status") or {}).get("state"),
        "recommendation_error_type": (payload.get("recommendation_status") or {}).get("error_type"),
        "foreman_guidance_state": (payload.get("foreman_guidance") or {}).get("state"),
        "incomplete_rules": [
            {
                "rule_id": item.get("rule_id"),
                "confidence": item.get("confidence"),
                "missing_features": item.get("missing_features"),
            }
            for item in internal.get("evaluations", [])
            if not item.get("data_complete")
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
