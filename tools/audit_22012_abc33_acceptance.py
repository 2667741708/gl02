from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _obj(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _close(left, right, tolerance=1e-6):
    try:
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def main() -> int:
    service = Path(os.getenv("ABC33_SERVICE_ROOT") or (Path(__file__).resolve().parents[1] / "自动诊断服务"))
    sys.path.insert(0, str(service))
    from abc_rule_catalog import RULE_BY_ID

    dsn = " ".join(
        f"{key}={value}"
        for key, value in {
            "host": os.getenv("GL02_PGHOST", "127.0.0.1"),
            "port": os.getenv("GL02_PGPORT", "5432"),
            "dbname": os.getenv("GL02_PGDATABASE", "bf_trend"),
            "user": os.getenv("GL02_PGUSER"),
            "password": os.getenv("GL02_PGPASSWORD"),
        }.items()
        if value
    )
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        batch = conn.execute(
            """SELECT * FROM bf_sensor.abc_rule_evaluation_batches
               ORDER BY evaluation_ts DESC,id DESC LIMIT 1"""
        ).fetchone()
        if not batch:
            raise RuntimeError("no ABC33 evaluation batch")
        rows = conn.execute(
            """SELECT * FROM bf_sensor.abc_rule_evaluation_items
               WHERE batch_id=%s ORDER BY category,rule_id""",
            (batch["id"],),
        ).fetchall()

        formula_errors = []
        provenance_errors = []
        threshold_errors = []
        sensor_pairs = {}
        baseline_pairs = {}
        full_rules = []
        zero_terms = 0
        zero_rules = 0
        for row in rows:
            item = dict(row)
            item["weights"] = _obj(item.get("weights"), {})
            item["thresholds"] = _obj(item.get("thresholds"), {})
            item["contributions"] = _obj(item.get("contributions"), [])
            item["formula_terms"] = _obj(item.get("formula_terms"), [])
            item["missing_features"] = _obj(item.get("missing_features"), [])
            item["public_detail"] = _obj(item.get("public_detail"), {})
            weights = item["weights"]
            contributions = item["contributions"]
            if set(item["thresholds"]) != set(weights):
                threshold_errors.append({"rule_id": item["rule_id"], "expected": sorted(weights), "actual": sorted(item["thresholds"])})
            available_weight = sum(float(part["weight"]) for part in contributions)
            weighted_sum = 0.0
            for part in contributions:
                term = part.get("feature_key")
                actual = float(part.get("raw_value"))
                normalized = float(part.get("normalized_value"))
                weight = float(part.get("weight"))
                contribution = float(part.get("contribution"))
                weighted_sum += contribution
                if actual == 0:
                    zero_terms += 1
                if not _close(contribution, normalized * weight):
                    formula_errors.append({"rule_id": item["rule_id"], "term": term, "kind": "term_product"})
                required = ("formula", "effective_thresholds", "source_features", "source_values", "baseline_snapshot")
                if any(key not in part for key in required):
                    provenance_errors.append({"rule_id": item["rule_id"], "term": term, "missing": [key for key in required if key not in part]})
                for variable, value in (part.get("source_values") or {}).items():
                    if isinstance(value, (int, float)):
                        sensor_pairs.setdefault(variable, value)
                for variable, snapshot in (part.get("baseline_snapshot") or {}).items():
                    if isinstance(snapshot, dict) and snapshot.get("baseline_day"):
                        baseline_pairs[(variable, str(snapshot["baseline_day"])[:10])] = snapshot
            risk = 100.0 * weighted_sum / available_weight if available_weight else 0.0
            expected_score = 100.0 - risk if RULE_BY_ID[item["rule_id"]].direction == "maintenance" else risk
            if not _close(round(expected_score, 4), item["score"]):
                formula_errors.append({"rule_id": item["rule_id"], "kind": "rule_score", "expected": round(expected_score, 4), "actual": item["score"]})
            if _close(item["score"], 0):
                zero_rules += 1
            full_rules.append(item)

        db_sensor = {}
        if sensor_pairs:
            variables = sorted(sensor_pairs)
            db_rows = conn.execute(
                """SELECT DISTINCT ON (r.variable_name) r.variable_name,v.ts,v.value,v.aggregate,r.tag_long_name
                   FROM bf_sensor.one_minute_values v
                   JOIN bf_sensor.sensor_registry r USING(tag_long_name)
                   WHERE r.variable_name=ANY(%s) AND v.ts<=%s
                   ORDER BY r.variable_name,v.ts DESC""",
                (variables, batch["evaluation_ts"]),
            ).fetchall()
            db_sensor = {row["variable_name"]: dict(row) for row in db_rows}

        sensor_checks = []
        for variable, expected in sorted(sensor_pairs.items()):
            row = db_sensor.get(variable)
            sensor_checks.append({
                "variable": variable,
                "snapshot_value": expected,
                "db_value": row.get("value") if row else None,
                "db_ts": row.get("ts") if row else None,
                "tag_long_name": row.get("tag_long_name") if row else None,
                "matched": bool(row) and _close(expected, row.get("value")),
            })

        baseline_checks = []
        for (variable, baseline_day), expected in sorted(baseline_pairs.items()):
            row = conn.execute(
                """SELECT variable_name,baseline_day,median_ref,iqr_ref,p25,p75,sample_count,coverage_ratio
                   FROM bf_sensor.daily_baselines WHERE variable_name=%s AND baseline_day=%s""",
                (variable, baseline_day),
            ).fetchone()
            matched = bool(row)
            if row:
                for key in ("median_ref", "iqr_ref", "p25", "p75", "coverage_ratio"):
                    if expected.get(key) is not None and not _close(expected.get(key), row.get(key)):
                        matched = False
            baseline_checks.append({"variable": variable, "baseline_day": baseline_day, "matched": matched, "db": dict(row) if row else None, "snapshot": expected})

    service_status = {
        "rule_count": len(rows),
        "category_counts": {category: sum(row["category"] == category for row in rows) for category in "ABC"},
        "needs_data": sum(row["status"] == "needs_data" for row in rows),
        "confidence_nonzero": sum(float(row["confidence"] or 0) > 0 for row in rows),
        "zero_rule_scores": zero_rules,
        "zero_formula_terms": zero_terms,
        "formula_errors": formula_errors,
        "threshold_errors": threshold_errors,
        "provenance_errors": provenance_errors,
        "sensor_match_count": sum(item["matched"] for item in sensor_checks),
        "sensor_check_count": len(sensor_checks),
        "sensor_mismatches": [item for item in sensor_checks if not item["matched"]],
        "baseline_match_count": sum(item["matched"] for item in baseline_checks),
        "baseline_check_count": len(baseline_checks),
        "baseline_mismatches": [item for item in baseline_checks if not item["matched"]],
    }
    output = {
        "schema": "abc33.acceptance.audit.v1",
        "batch": dict(batch),
        "summary": service_status,
        "rules": full_rules,
        "sensor_checks": sensor_checks,
        "baseline_checks": baseline_checks,
    }
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2))
    hard_ok = (
        len(rows) == 33
        and service_status["category_counts"] == {"A": 9, "B": 13, "C": 11}
        and service_status["needs_data"] < 33
        and not formula_errors
        and not threshold_errors
        and not provenance_errors
    )
    return 0 if hard_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
