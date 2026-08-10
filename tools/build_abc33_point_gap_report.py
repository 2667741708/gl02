from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--billboards",
        default=str(ROOT / "高炉前端数据" / "models" / "gl02_furnace_body_billboards.v1.json"),
    )
    parser.add_argument("--coverage-threshold", type=float, default=0.75)
    parser.add_argument("--stale-seconds", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    options = arguments()
    snapshot = Path(options.snapshot)
    output = Path(options.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    metadata = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8-sig"))
    registry_rows = json.loads((snapshot / "registry.json").read_text(encoding="utf-8-sig"))
    latest = json.loads((snapshot / "latest_values.json").read_text(encoding="utf-8-sig"))
    billboards = json.loads(Path(options.billboards).read_text(encoding="utf-8-sig"))
    billboard_rows = billboards.get("points") or billboards.get("items") or billboards.get("billboards") or billboards
    position_by_variable = {
        str(item.get("canonical_id") or item.get("data_binding_key")): item
        for item in billboard_rows
        if isinstance(item, dict) and (item.get("canonical_id") or item.get("data_binding_key"))
    }

    exported_at = parse_time(metadata.get("exported_at"))
    day_start = parse_time(metadata.get("day_start"))
    if exported_at is None or day_start is None:
        raise RuntimeError("snapshot metadata timestamps are unavailable")
    if exported_at.tzinfo is not None and day_start.tzinfo is None:
        day_start = day_start.replace(tzinfo=exported_at.tzinfo)
    expected_minutes = max(1, int((exported_at - day_start).total_seconds() // 60) + 1)
    counts = {str(key): int(value) for key, value in (metadata.get("observation_counts") or {}).items()}

    registry: dict[str, dict[str, Any]] = {}
    for item in registry_rows:
        name = str(item.get("variable_name") or "")
        if name and not bool(item.get("is_derived")) and name not in registry:
            registry[name] = item

    required_variables = set(registry)
    # Hopper_weight_set is a documented ABC review point even when the source
    # registry cannot yet resolve a physical tag.
    required_variables.add("Hopper_weight_set")

    rows: list[dict[str, Any]] = []
    for variable in sorted(required_variables):
        item = registry.get(variable) or {}
        observation_count = counts.get(variable, 0)
        coverage = observation_count / expected_minutes
        latest_row = latest.get(variable) or {}
        latest_ts = parse_time(latest_row.get("ts"))
        age_seconds = None
        if latest_ts is not None:
            if exported_at.tzinfo is not None and latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=exported_at.tzinfo)
            age_seconds = max(0.0, (exported_at - latest_ts).total_seconds())
        model = position_by_variable.get(variable) or {}
        position = model.get("position") if isinstance(model.get("position"), list) else []
        if not item:
            state = "registry_missing"
            reason = "传感器注册表没有确认的实际点位ID"
        elif observation_count == 0:
            state = "no_observation"
            reason = "当日截至导出时刻没有分钟数据"
        elif age_seconds is None or age_seconds > options.stale_seconds:
            state = "stale"
            reason = f"最后数据年龄超过{int(options.stale_seconds)}秒"
        elif coverage < options.coverage_threshold:
            state = "sparse"
            reason = f"当日分钟覆盖率低于{options.coverage_threshold:.0%}"
        else:
            state = "available"
            reason = "当前可用"
        if state == "available":
            continue
        tag = str(item.get("tag_long_name") or "")
        rows.append(
            {
                "variable_name": variable,
                "state": state,
                "reason": reason,
                "actual_point_id": tag,
                "point_short_id": tag.rsplit("\\", 1)[-1] if tag else "",
                "latest_value": latest_row.get("value"),
                "latest_timestamp": latest_row.get("ts"),
                "data_age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                "observed_minutes": observation_count,
                "expected_minutes": expected_minutes,
                "coverage_ratio": round(coverage, 6),
                "model_node_id": model.get("id"),
                "coordinate_x": position[0] if len(position) > 0 else None,
                "coordinate_y": position[1] if len(position) > 1 else None,
                "coordinate_z": position[2] if len(position) > 2 else None,
                "coordinate_authority": model.get("coordinate_authority"),
                "display_name": model.get("display_name") or model.get("semantic_name_cn"),
            }
        )

    report = {
        "schema_version": "abc33.point-gap-audit.v1",
        "exported_at": metadata.get("exported_at"),
        "snapshot_day": metadata.get("snapshot_day"),
        "expected_minutes": expected_minutes,
        "coverage_threshold": options.coverage_threshold,
        "stale_seconds": options.stale_seconds,
        "summary": {
            "reported_points": len(rows),
            "registry_missing": sum(row["state"] == "registry_missing" for row in rows),
            "no_observation": sum(row["state"] == "no_observation" for row in rows),
            "stale": sum(row["state"] == "stale" for row in rows),
            "sparse": sum(row["state"] == "sparse" for row in rows),
        },
        "points": rows,
        "zero_value_policy": "数值0不是缺失；只有无注册、无观测、超时或覆盖不足才进入本报告",
    }
    (output / "abc33_point_gap_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fieldnames = list(rows[0]) if rows else ["variable_name", "state", "reason"]
    with (output / "abc33_point_gap_report.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# ABC33采集缺口与低实时性点位",
        "",
        f"- 数据导出时刻：`{metadata.get('exported_at')}`",
        f"- 截至当时理论分钟数：`{expected_minutes}`",
        "- 判断口径：0值是合法物理值，不按缺失处理。",
        "",
        "|变量|状态|实际点位ID|最新值/时间|分钟覆盖|模型坐标(x,y,z)|原因|",
        "|---|---|---|---|---:|---|---|",
    ]
    for row in rows:
        coordinate = ", ".join(
            "—" if row[key] is None else str(row[key])
            for key in ("coordinate_x", "coordinate_y", "coordinate_z")
        )
        lines.append(
            f"|`{row['variable_name']}`|{row['state']}|`{row['actual_point_id'] or '未确认'}`|"
            f"{row['latest_value'] if row['latest_value'] is not None else '—'} / {row['latest_timestamp'] or '—'}|"
            f"{row['observed_minutes']}/{row['expected_minutes']} ({row['coverage_ratio']:.1%})|{coordinate}|{row['reason']}|"
        )
    (output / "abc33_point_gap_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **report["summary"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
