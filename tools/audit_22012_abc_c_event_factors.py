from __future__ import annotations

import json
import math
import os
import sys
from datetime import timedelta
from pathlib import Path


def clip(value):
    return max(0.0, min(1.0, float(value)))


def high(value, a, b):
    return None if value is None else clip((float(value) - a) / (b - a))


def low(value, a, b):
    return None if value is None else clip((a - float(value)) / (a - b))


def absolute(value, a, b):
    return None if value is None else clip((abs(float(value)) - a) / (b - a))


def main():
    service = Path(os.environ["ABC33_SERVICE_ROOT"])
    sys.path.insert(0, str(service))
    patch_root = os.environ.get("ABC33_PATCH_ROOT")
    if patch_root:
        sys.path.insert(0, patch_root)
    from diagnosis_scheduler import AutoDiagnosisScheduler, build_abc_runtime_inputs
    from abc_feature_builder import BODY_POINT_NAMES, build_feature_snapshot
    from abc_rule_engine import evaluate, load_config
    from abc_public_review import build_public_review

    scheduler = AutoDiagnosisScheduler()
    target, _ = scheduler.latest_complete_target(wait=False)
    rows = scheduler.store.query_daily_baselines(target, baseline_days=30)
    baseline = {
        row["variable_name"]: {
            "baseline_day": row["baseline_day"],
            "window_start": row["baseline_window_start"],
            "window_end": row["baseline_window_end"],
            "median_ref": float(row["median_ref"]),
            "iqr_ref": float(row["iqr_ref"]),
            "p25": float(row["p25"]) if row.get("p25") is not None else None,
            "p75": float(row["p75"]) if row.get("p75") is not None else None,
            "coverage_ratio": float(row["coverage_ratio"]),
            "sample_count": int(row["sample_count"]),
        }
        for row in rows
    }
    frame = scheduler.store.fetch_wide_frame(target - timedelta(minutes=89), target, None)
    current, history = build_abc_runtime_inputs(frame, target)
    config = load_config(service / "config" / "abc_furnace_rules.v1.json")
    features, quality = build_feature_snapshot(
        current,
        baseline=baseline,
        history=history,
        data_age_seconds=0,
        coverage_ratio=1.0,
        thresholds=config["feature_thresholds"],
    )
    body = []
    for name in BODY_POINT_NAMES:
        z = features.get(f"z60_{name}")
        slope = features.get(f"slope30_{name}")
        z_risk = high(z, .8, 1.5) if z is not None else None
        slope_risk = high(slope, .5, 1.2) if slope is not None else None
        if z_risk is None or slope_risk is None:
            continue
        body.append({
            "variable": name,
            "current": current.get(name),
            "z60": z,
            "slope30": slope,
            "z_risk": z_risk,
            "slope_risk": slope_risk,
            "combined": max(z_risk, slope_risk),
            "baseline": baseline.get(name),
        })
    body.sort(key=lambda item: item["combined"], reverse=True)
    cooling = []
    for name in ("Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water"):
        z = features.get(f"z60_{name}")
        cooling.append({"variable": name, "current": current.get(name), "z60": z, "risk": low(z, -.8, -1.5) if z is not None else None, "baseline": baseline.get(name)})
    name = "ExpansionTankLevel"
    z = features.get(f"z60_{name}")
    cooling.append({"variable": name, "current": current.get(name), "z60": z, "risk": absolute(z, .6, 1.2) if z is not None else None, "baseline": baseline.get(name)})
    cooling.sort(key=lambda item: item["risk"] if item["risk"] is not None else -1, reverse=True)
    factors = {key: features.get(key) for key in ("CoolingRisk", "CoolingConcurrence", "BodyHotRisk", "BodyHotConcurrence", "BodyHotEscalation", "BodyTempRange", "slopeBodyMax", "TopTempRange", "TopPressRange", "DrainProxy")}
    bundle = evaluate(features, quality=quality, timestamp=target, config=config)
    c_events = {
        item["rule_id"]: {
            "operator_score": item["score"],
            "raw_formula_score": item.get("raw_formula_score"),
            "status": item["status"],
            "event_confirmation": item.get("event_confirmation"),
            "event_confirmation_state": item.get("event_confirmation_state"),
        }
        for item in bundle["evaluations"] if item["rule_id"] in {"C4", "C5", "C7"}
    }
    with scheduler.store.connection_scope() as conn:
        public_review = build_public_review(conn, "C7", target)
    output = {
        "evaluation_ts": target,
        "factors": factors,
        "body_count": len(body),
        "body_top20": body[:20],
        "body_risk_counts": {str(level): sum(item["combined"] >= level for item in body) for level in (.25, .5, .75, 1.0)},
        "body_top3_mean": sum(item["combined"] for item in body[:3]) / 3 if len(body) >= 3 else None,
        "body_top5_mean": sum(item["combined"] for item in body[:5]) / 5 if len(body) >= 5 else None,
        "cooling": cooling,
        "cooling_top2_mean": sum(item["risk"] for item in cooling[:2]) / 2 if len(cooling) >= 2 and all(item["risk"] is not None for item in cooling[:2]) else None,
        "c_events": c_events,
        "public_review": {
            "schema_version": public_review["schema_version"],
            "metric_count": public_review["metric_count"],
            "available_count": public_review["available_count"],
            "missing_count": public_review["missing_count"],
            "body_count": len(public_review["body_metrics"]),
            "cooling_count": len(public_review["cooling_metrics"]),
            "main_metrics": public_review["main_metrics"],
            "body_first": public_review["body_metrics"][0] if public_review["body_metrics"] else None,
            "body_last": public_review["body_metrics"][-1] if public_review["body_metrics"] else None,
        },
    }
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
