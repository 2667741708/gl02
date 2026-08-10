"""Evaluate all 33 ABC furnace rules against a downloaded input snapshot."""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "自动诊断服务"
sys.path.insert(0, str(SERVICE))
from abc_feature_builder import build_feature_snapshot  # noqa: E402
from abc_rule_catalog import RULE_BY_ID  # noqa: E402
from abc_rule_engine import evaluate, load_config  # noqa: E402
from abc_term_semantics import term_semantics  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default=str(SERVICE / "config" / "abc_furnace_rules.v1.json"))
    return parser.parse_args()


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def timestamp(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def load_rows(path: Path) -> dict[str, list[tuple[datetime, float]]]:
    buckets: dict[str, dict[datetime, list[float]]] = defaultdict(lambda: defaultdict(list))
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            value = number(row.get("value"))
            if value is None:
                continue
            minute = timestamp(row["ts"]).replace(second=0, microsecond=0)
            buckets[str(row["variable_name"])][minute].append(value)
    return {
        name: sorted((minute, sum(values) / len(values)) for minute, values in minutes.items())
        for name, minutes in buckets.items()
    }


def build_window(rows: dict[str, list[tuple[datetime, float]]], anchor: datetime):
    grid = [anchor.replace(second=0, microsecond=0) - timedelta(minutes=89-index) for index in range(90)]
    history: dict[str, Any] = {
        "timestamps": [item.isoformat(sep=" ") for item in grid],
        "evaluation_ts": anchor.isoformat(),
    }
    current: dict[str, float] = {}
    current_ts: dict[str, str] = {}
    ages: list[float] = []
    for name, samples in rows.items():
        times = [item[0] for item in samples]
        left = bisect.bisect_left(times, grid[0])
        right = bisect.bisect_right(times, anchor)
        selected = samples[left:right]
        by_minute = dict(selected)
        history[name] = [by_minute.get(item) for item in grid]
        if selected:
            stamp, value = selected[-1]
            age = max(0.0, (anchor - stamp).total_seconds())
            if age <= 300:
                current[name] = value
                current_ts[name] = stamp.isoformat()
                ages.append(age)
    return current, current_ts, history, max(ages) if ages else None


def sensor_snapshot(spec, current, current_ts, baseline):
    result = []
    for name in spec.primary_sensors:
        row = baseline.get(name, {})
        result.append({
            "variable_name": name,
            "current_value": current.get(name),
            "timestamp": current_ts.get(name),
            "baseline_median": row.get("median_ref"),
            "baseline_iqr": row.get("iqr_ref"),
            "baseline_p25": row.get("p25"),
            "baseline_p75": row.get("p75"),
            "coverage_ratio": row.get("coverage_ratio"),
        })
    return result


def main() -> int:
    options = arguments()
    snapshot = Path(options.snapshot)
    output = Path(options.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    baseline_rows = json.loads((snapshot / "baselines_30d.json").read_text(encoding="utf-8-sig"))
    baseline = {str(row["variable_name"]): row for row in baseline_rows}
    rows = load_rows(snapshot / "realtime_day.jsonl.gz")
    anchor = max(stamp for samples in rows.values() for stamp, _ in samples)
    current, current_ts, history, age = build_window(rows, anchor)
    config = load_config(options.config)
    features, quality = build_feature_snapshot(
        current,
        baseline=baseline,
        history=history,
        data_age_seconds=age,
        coverage_ratio=1.0,
        thresholds=config.get("feature_thresholds") or {},
        current_timestamps=current_ts,
    )
    bundle = evaluate(features, quality=quality, timestamp=anchor, config=config)
    report_rules = []
    csv_rows = []
    for item in bundle["evaluations"]:
        spec = RULE_BY_ID[item["rule_id"]]
        available_weight = sum(float(term["weight"]) for term in item["contributions"])
        by_term = {term["feature_key"]: term for term in item["contributions"]}
        term_rows = []
        for term, weight in item["weights"].items():
            contribution = by_term.get(term)
            semantic = term_semantics(term)
            raw_value = contribution.get("raw_value") if contribution else None
            normalized = contribution.get("normalized_value") if contribution else None
            weighted = contribution.get("contribution") if contribution else None
            effective = weighted * 100.0 / available_weight if weighted is not None and available_weight else None
            term_row = {
                "feature_key": term,
                "physical_label": semantic["label"],
                "physical_meaning": semantic["meaning"],
                "available": contribution is not None,
                "raw_value": raw_value,
                "term_score_0_100": normalized * 100.0 if normalized is not None else None,
                "weight_percent": float(weight),
                "score_weight_product": weighted,
                "effective_contribution_points": effective,
                "missing_reason": None if contribution else "本次快照缺少该因子所需数据、基线或现场批准阈值",
            }
            term_rows.append(term_row)
            csv_rows.append({"rule_id": spec.rule_id, "rule_name": spec.display_name, **term_row})
        report_rules.append({
            "rule_id": spec.rule_id,
            "category": spec.category,
            "display_name": spec.display_name,
            "direction": spec.direction,
            "total_score": item["score"],
            "risk_score": item["risk_score"],
            "confidence": item["confidence"],
            "status": item["status"],
            "data_complete": item["data_complete"],
            "available_weight": available_weight,
            "total_weight": sum(float(value) for value in item["weights"].values()),
            "missing_features": item["missing_features"],
            "sensor_values": sensor_snapshot(spec, current, current_ts, baseline),
            "terms": term_rows,
        })
    report = {
        "schema_version": "abc33.local-rule-audit.v1",
        "snapshot_path": str(snapshot.resolve()),
        "evaluation_ts": anchor.isoformat(),
        "config_version": bundle["config_version"],
        "catalog_version": bundle["catalog_version"],
        "release_state": config.get("release_control"),
        "feature_count": len(features),
        "internal_features": features,
        "internal_feature_quality": quality,
        "current_variable_count": len(current),
        "summary": {
            "rule_count": len(report_rules),
            "complete_rules": sum(1 for item in report_rules if item["data_complete"]),
            "incomplete_rules": sum(1 for item in report_rules if not item["data_complete"]),
            "confidence_at_least_75pct": sum(1 for item in report_rules if item["confidence"] >= .75),
        },
        "rules": report_rules,
    }
    (output / "abc33_rule_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "abc33_rule_terms.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    lines = [
        "# ABC33本机实数审计", "", f"- 计算时刻：`{anchor.isoformat()}`",
        f"- 完整规则：{report['summary']['complete_rules']}/33",
        f"- 置信度达到75%：{report['summary']['confidence_at_least_75pct']}/33", "",
        "|规则|总分|风险分|置信度|可用权重|缺失因子|", "|---|---:|---:|---:|---:|---|",
    ]
    for item in report_rules:
        missing = "、".join(item["missing_features"]) or "无"
        lines.append(f"|{item['rule_id']} {item['display_name']}|{item['total_score']:.4f}|{item['risk_score']:.4f}|{item['confidence']:.1%}|{item['available_weight']:.0f}/100|{missing}|")
    for item in report_rules:
        lines.extend([
            "", f"## {item['rule_id']} {item['display_name']}", "",
            f"- 规则总分：`{item['total_score']:.4f}`；风险分：`{item['risk_score']:.4f}`。",
            f"- 置信度：`{item['confidence']:.1%}`；可用权重：`{item['available_weight']:.0f}/100`。",
            f"- 缺失因子：{'、'.join(item['missing_features']) or '无'}。", "",
            "|因子|实际物理含义|因子值|小项分数|权重|分数×权重|最终贡献点|状态|",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ])
        for term in item["terms"]:
            def show(value):
                return "—" if value is None else f"{float(value):.6f}"
            state = "可计算" if term["available"] else "缺数据/基线/阈值"
            lines.append(
                f"|{term['physical_label']} (`{term['feature_key']}`)|{term['physical_meaning']}|"
                f"{show(term['raw_value'])}|{show(term['term_score_0_100'])}|{term['weight_percent']:.0f}%|"
                f"{show(term['score_weight_product'])}|{show(term['effective_contribution_points'])}|{state}|"
            )
    (output / "abc33_rule_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), **report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
