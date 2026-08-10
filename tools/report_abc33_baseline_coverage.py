"""Create an auditable list of ABC33 30-day baselines below quality gates."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def group(name: str) -> str:
    if name.startswith("T_body_"):
        return "炉体温度"
    if name.startswith("P_static_"):
        return "炉体静压"
    if name in {"T_taphole_mean", "T_top"}:
        return "派生特征"
    if name in {"Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel"}:
        return "冷却系统"
    if name in {"BlastEnergy", "Hopper_weight", "Q_N2", "P_N2"}:
        return "新增工长点位"
    if name in {"L", "L_south", "L_north"}:
        return "料线"
    if name.startswith("T_top_"):
        return "四点顶温"
    return "其他核心变量"


def reason(row: dict) -> str:
    name = str(row["variable_name"])
    coverage = float(row.get("coverage_ratio") or 0)
    source = row.get("source") or {}
    if name == "ExpansionTankLevel" and source.get("type") == "hourly_then_daily_mean":
        return "已采用小时均值→日均值策略，本项按30个日样本门禁，不属于不足"
    if name in {"BlastEnergy", "Hopper_weight", "Q_N2", "P_N2"} and coverage < .2:
        return "目标库仅约2–3天历史，需从pSpace补回完整30日后重算"
    if name == "T_top":
        return "四点顶温要求同分钟全部齐全，异步上报造成派生对齐损失"
    if name.startswith("T_body_"):
        return "炉体温度为变化触发/非逐分钟满报，逐分钟75%分母不适配，需受控保持值或分层聚合策略"
    if name in {"L_south", "L_north"} or name.startswith("T_top_"):
        return "点位存在分钟缺口；需核对pSpace源数据并评估短时有界保持后再重算"
    if coverage >= .70:
        return "接近75%门禁但仍不足；不得直接四舍五入通过"
    return "30日有效分钟覆盖不足，需核对源库回填或点位采集语义"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baselines", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gate", type=float, default=.75)
    args = parser.parse_args()
    rows = json.loads(Path(args.baselines).read_text(encoding="utf-8-sig"))
    low = []
    for row in rows:
        if float(row.get("coverage_ratio") or 0) >= args.gate:
            continue
        item = {
            "group": group(str(row["variable_name"])),
            "variable_name": row["variable_name"],
            "baseline_day": row.get("baseline_day"),
            "sample_count": row.get("sample_count"),
            "expected_samples": row.get("expected_minutes"),
            "coverage_ratio": row.get("coverage_ratio"),
            "source_type": (row.get("source") or {}).get("type"),
            "reason": reason(row),
        }
        low.append(item)
    low.sort(key=lambda item: (item["group"], item["variable_name"]))
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "group",
        "variable_name",
        "baseline_day",
        "sample_count",
        "expected_samples",
        "coverage_ratio",
        "source_type",
        "reason",
    ]
    with (out / "abc33_baselines_below_75.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(low)
    lines = ["# ABC33低于75%的30日基线", "", f"共 `{len(low)}` 项。", "", "|分类|变量|样本数/期望|覆盖率|原因|", "|---|---|---:|---:|---|"]
    for item in low:
        lines.append(f"|{item['group']}|`{item['variable_name']}`|{item['sample_count']}/{item['expected_samples']}|{float(item['coverage_ratio']):.2%}|{item['reason']}|")
    (out / "abc33_baselines_below_75.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({"ok": True, "below_gate": len(low), "output_dir": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
