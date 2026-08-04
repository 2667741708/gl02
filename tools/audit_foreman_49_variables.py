#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Audit whether the foreman trend-screen variables exist in bf_sensor.sensor_registry.

Requirement: REQ-20260515-FOREMAN-49
Docs: docs/requirements_traceability.md#req-20260515-foreman-49
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ForemanVariable:
    name: str
    variable_name: str | None = None
    aliases: tuple[str, ...] = ()
    note: str = ""


FOREMAN_VARIABLES: tuple[ForemanVariable, ...] = (
    ForemanVariable("东南顶压", "P_top_gas_A", ("顶压A", "上升管煤气压力A"), "数据库以 A-D 命名，暂未保存东南/东北方位映射"),
    ForemanVariable("东北顶压", "P_top_gas_B", ("顶压B", "上升管煤气压力B"), "数据库以 A-D 命名，暂未保存东南/东北方位映射"),
    ForemanVariable("西北顶压", "P_top_gas_C", ("顶压C", "上升管煤气压力C"), "数据库以 A-D 命名，暂未保存西北/西南方位映射"),
    ForemanVariable("西南顶压", "P_top_gas_D", ("顶压D", "上升管煤气压力D"), "数据库以 A-D 命名，暂未保存西北/西南方位映射"),
    ForemanVariable("雷达探尺", "L", ("雷达探尺", "主料线")),
    ForemanVariable("北尺", "L_north", ("北探尺", "北尺")),
    ForemanVariable("南尺", "L_south", ("南探尺", "南尺")),
    ForemanVariable("东北顶温", "T_top_A", ("顶温A", "上升管煤气温度A"), "数据库以 A-D 命名，暂未保存东北/东南方位映射"),
    ForemanVariable("东南顶温", "T_top_B", ("顶温B", "上升管煤气温度B"), "数据库以 A-D 命名，暂未保存东北/东南方位映射"),
    ForemanVariable("西北顶温", "T_top_C", ("顶温C", "上升管煤气温度C"), "数据库以 A-D 命名，暂未保存西北/西南方位映射"),
    ForemanVariable("西南顶温", "T_top_D", ("顶温D", "上升管煤气温度D"), "数据库以 A-D 命名，暂未保存西北/西南方位映射"),
    ForemanVariable("上小时喷煤量", "PCI_set", ("一小时喷煤重量设定", "喷煤设定")),
    ForemanVariable("本小时喷煤量", None, ("本小时喷煤",)),
    ForemanVariable("喷煤实际速率", "PCI_rate", ("喷煤量", "喷煤强度")),
    ForemanVariable("冷风流量", "Q_blast", ("冷风管道流量", "风量")),
    ForemanVariable("冷风压力", "P_blast_cold", ("冷风管道压力",)),
    ForemanVariable("热风压力", "P_blast", ("热风压力",)),
    ForemanVariable("热风温度", "T_blast", ("热风温度",)),
    ForemanVariable("透气性指数", "PI", ("透气性指数",)),
    ForemanVariable("炉腹煤气指数", None, ("炉腹煤气指数",)),
    ForemanVariable("炉腹煤气量", None, ("炉腹煤气量",)),
    ForemanVariable("全炉压差", "DP_total", ("全炉压差", "全压差")),
    ForemanVariable("上部压差", "DP_upper", ("上部压差",)),
    ForemanVariable("下部压差", "DP_lower", ("下部压差",)),
    ForemanVariable("下部压差占比", None, ("下部压差占比",), "可由 DP_lower/DP_total 派生，当前数据库未单独登记"),
    ForemanVariable("荒煤气压力", "P_top", ("顶压平均", "荒煤气压力")),
    ForemanVariable("荒煤气温度", "T_top", ("综合顶温", "荒煤气温度"), "当前为顶温 A-D 派生均值"),
    ForemanVariable("外网煤气压力", None, ("外网煤气压力",)),
    ForemanVariable("煤气利用率", "GasUtil", ("煤气利用率",)),
    ForemanVariable("二氧化碳", None, ("二氧化碳", "CO2")),
    ForemanVariable("一氧化碳", None, ("一氧化碳", "CO")),
    ForemanVariable("氢气", None, ("氢气", "H2")),
    ForemanVariable("鼓风动能", None, ("鼓风动能",)),
    ForemanVariable("标准风速", None, ("标准风速",)),
    ForemanVariable("实际风速", None, ("实际风速",)),
    ForemanVariable("软水流量", None, ("软水流量",)),
    ForemanVariable("软水压力", None, ("软水压力",)),
    ForemanVariable("高压水流量", None, ("高压水流量",)),
    ForemanVariable("高压水压力", None, ("高压水压力",)),
    ForemanVariable("中压水压力", None, ("中压水压力",)),
    ForemanVariable("膨胀罐液位", None, ("膨胀罐液位",)),
    ForemanVariable("罐重", None, ("罐重", "料罐重量")),
    ForemanVariable("氮气流量", None, ("氮气流量",)),
    ForemanVariable("氧气压力", None, ("氧气压力",)),
    ForemanVariable("阀前富氧压力", None, ("阀前富氧压力",)),
    ForemanVariable("阀后富氧压力", None, ("阀后富氧压力",)),
    ForemanVariable("富氧流量", "Q_O2", ("富氧流量", "大流量氧流量")),
    ForemanVariable("富氧率", "O2_rate", ("富氧率",)),
    ForemanVariable("理论燃烧温度", "TFT", ("理论燃烧温度",)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit foreman 49 variables against PostgreSQL sensor_registry.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="gl02_sync")
    parser.add_argument("--password", default="gl02_local_sync")
    parser.add_argument("--out-prefix", default="logs/foreman_49_variable_audit")
    return parser.parse_args()


def load_registry(conn) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT variable_name, chinese_name, short_name, tag_long_name, description,
               status_usage, is_enabled, is_derived
        FROM bf_sensor.sensor_registry
        ORDER BY variable_name
        """
    ).fetchall()
    return {str(row["variable_name"]): dict(row) for row in rows}, [dict(row) for row in rows]


def fuzzy_match(item: ForemanVariable, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    terms = [item.name, *item.aliases]
    for row in rows:
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("variable_name", "chinese_name", "description", "short_name", "tag_long_name")
        )
        if any(term and term in haystack for term in terms):
            return row
    return None


def audit(registry: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in FOREMAN_VARIABLES:
        row = registry.get(item.variable_name or "") if item.variable_name else None
        match_type = "exact_variable_name" if row else ""
        if not row:
            row = fuzzy_match(item, rows)
            match_type = "fuzzy_text" if row else "missing"
        result.append(
            {
                "foreman_name": item.name,
                "status": "exists" if row else "missing",
                "match_type": match_type,
                "variable_name": row.get("variable_name") if row else item.variable_name,
                "chinese_name": row.get("chinese_name") if row else "",
                "short_name": row.get("short_name") if row else "",
                "tag_long_name": row.get("tag_long_name") if row else "",
                "description": row.get("description") if row else "",
                "is_enabled": row.get("is_enabled") if row else "",
                "is_derived": row.get("is_derived") if row else "",
                "note": item.note,
            }
        )
    return result


def write_outputs(items: list[dict[str, Any]], out_prefix: str) -> None:
    prefix = Path(out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    exists = [item for item in items if item["status"] == "exists"]
    missing = [item for item in items if item["status"] == "missing"]
    lines = [
        "# 工长关注49项变量数据库审计",
        "",
        f"- 存在：{len(exists)}",
        f"- 缺失：{len(missing)}",
        "",
        "## 缺失项",
        "",
        "| 变量 | 说明 |",
        "|---|---|",
    ]
    lines.extend(f"| {item['foreman_name']} | {item['note'] or 'sensor_registry 未匹配到变量'} |" for item in missing)
    lines.extend(["", "## 已存在项", "", "| 工长图变量 | 数据库变量 | 点名 | 描述 | 备注 |", "|---|---|---|---|---|"])
    lines.extend(
        f"| {item['foreman_name']} | `{item['variable_name']}` | `{item['short_name']}` | {item['description']} | {item['note']} |"
        for item in exists
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"exists": len(exists), "missing": len(missing), "json": str(json_path), "csv": str(csv_path), "md": str(md_path)}, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    params = {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": args.user,
        "password": args.password,
        "connect_timeout": 8,
    }
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        registry, rows = load_registry(conn)
        items = audit(registry, rows)
    write_outputs(items, args.out_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
