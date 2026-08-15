"""Generate the versioned spoken-language catalog beside the authoritative point TSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "数据库同步和存取" / "config" / "点位清单.tsv"
DEFAULT_OUTPUT = ROOT / "数据库同步和存取" / "config" / "点位语义目录.json"


MANUAL_ALIASES: dict[str, list[str]] = {
    "O2_rate": ["富氧率", "氧气富化率", "鼓风富氧比例", "富氧百分比"],
    "TFT": ["理论燃烧温度", "理论燃烧温度值", "风口理论燃烧温度"],
    "GasUtil": ["煤气利用率", "煤气利用", "炉顶煤气利用率"],
    "CO2_top": ["炉顶二氧化碳", "顶煤气二氧化碳", "煤气二氧化碳含量"],
    "CO_top": ["炉顶一氧化碳", "顶煤气一氧化碳", "煤气一氧化碳含量"],
    "H2_top": ["炉顶氢气", "顶煤气氢气", "煤气氢气含量"],
    "P_top": ["顶压", "炉顶压力", "炉顶压", "平均顶压", "综合顶压"],
    "L": ["主料线", "雷达料线", "雷达探尺", "炉顶料位"],
    "L_south": ["南探尺", "南尺", "南边料线", "南侧探尺"],
    "L_north": ["北探尺", "北尺", "北边料线", "北侧探尺"],
    "T_top": ["综合顶温", "平均顶温", "四点平均顶温", "炉顶平均温度"],
    "PI": ["透气性指数", "透气指数", "炉况透气性"],
    "DP_total": ["全炉压差", "总压差", "炉内总压差", "总体压差"],
    "DP_lower": ["下部压差", "炉下部压差", "下段压差"],
    "DP_upper": ["上部压差", "炉上部压差", "上段压差"],
    "T_blast": ["热风温度", "风温", "热风炉风温"],
    "P_blast": ["热风压力", "热风压", "热风风压"],
    "P_blast_cold": ["冷风压力", "冷风压", "冷风风压"],
    "Q_blast": ["冷风流量", "冷风管道流量", "风量", "鼓风流量"],
    "PCI_rate": ["喷煤量", "喷煤强度", "实时喷煤量", "喷煤速率"],
    "PCI_set": ["喷煤设定", "喷煤设定值", "设定喷煤量"],
    "Q_O2": ["富氧流量", "氧气流量", "富氧气量"],
    "PCI_previous_hour": ["上小时喷煤量", "上一小时喷煤量", "前一小时喷煤量"],
    "PCI_current_hour": ["本小时喷煤量", "当前小时喷煤量", "这小时喷煤量"],
    "BlastEnergy": ["鼓风动能", "风能", "鼓风能量"],
    "BlastSpeedStd": ["标准风速", "标况风速", "标准状态风速"],
    "BlastSpeedActual": ["实际风速", "实况风速", "当前风速"],
    "Q_soft_water": ["软水流量", "软水回水流量", "软化水流量"],
    "P_soft_water": ["软水压力", "软水给水压力", "软化水压力"],
    "Q_high_pressure_water": ["高压水流量", "高压供水流量", "高压水量"],
    "P_high_pressure_water": ["高压水压力", "高压供水压力", "高压水压"],
    "P_medium_pressure_water": ["中压水压力", "中压供水压力", "中压水压"],
    "ExpansionTankLevel": ["膨胀罐液位", "膨胀罐水位", "膨胀罐料位"],
    "Hopper_weight": ["罐重", "称量罐重量", "炉顶称量罐重量"],
    "Q_N2": ["氮气流量", "氮气量", "炉顶氮气流量"],
    "P_N2": ["氮气压力", "氮气总管压力", "炉顶氮气压力"],
    "P_O2_valve_in": ["阀前富氧压力", "富氧阀前压力", "氧气阀前压力"],
    "P_O2_valve_out": ["阀后富氧压力", "富氧阀后压力", "氧气阀后压力"],
}


def normalized(value: Any) -> str:
    return re.sub(r"[\s,，。；;：:、/\\_\-—（）()#号]+", "", str(value or "").lower())


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = re.sub(r"\s+", "", str(raw or "").strip())
        key = normalized(value)
        if not value or len(key) < 2 or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def display_parts(row: dict[str, str]) -> list[str]:
    display = str(row.get("中文名/标高") or "").strip()
    parts = re.split(r"[/，,]", display)
    return [re.sub(r"[，,]\s*\d+(?:\.\d+)?m$", "", part).strip() for part in parts if part.strip()]


def family_aliases(variable: str, row: dict[str, str]) -> list[str]:
    body = re.fullmatch(r"T_body_L(\d+)_([A-H])", variable)
    if body:
        layer, position = body.groups()
        return [
            f"{layer}层{position}点炉体温度",
            f"{layer}层{position}点温度",
            f"炉身{layer}层{position}点温度",
            f"{layer}层{position}方位温度",
            f"{position}点{layer}层炉身温度",
        ]
    top = re.fullmatch(r"([PT])_top_([A-D])", variable)
    if top:
        kind, position = top.groups()
        noun = "顶温" if kind == "T" else "顶压"
        physical = "上升管煤气温度" if kind == "T" else "上升管煤气压力"
        aliases = [f"{noun}{position}", f"{position}点{noun}", f"{noun}{position}点", f"{position}{physical}", f"{physical}{position}"]
        if kind == "P":
            aliases.append(f"P_top_gas_{position}")
        return aliases
    throat = re.fullmatch(r"T_throat_([A-D])", variable)
    if throat:
        position = throat.group(1)
        return [f"炉喉温度{position}", f"{position}点炉喉温度", f"炉喉{position}点温度", f"37.2米{position}点温度"]
    static = re.fullmatch(r"P_static_(lower|middle|upper)_([A-F])", variable)
    if static:
        level, position = static.groups()
        height, area = {
            "lower": ("20.35米", "炉腰"),
            "middle": ("23.49米", "炉身下部"),
            "upper": ("28.98米", "炉身中部"),
        }[level]
        return [f"{height}{position}点静压", f"{height}{position}点静压力", f"{area}{position}点静压", f"{position}点{area}静压力"]
    static_avg = re.fullmatch(r"P_static_(20m35|23m49|28m98)", variable)
    if static_avg:
        height = {"20m35": "20.35米", "23m49": "23.49米", "28m98": "28.98米"}[static_avg.group(1)]
        return [f"{height}静压", f"{height}静压力", f"{height}平均静压"]
    tap = re.fullmatch(r"T_taphole_([12])", variable)
    if tap:
        number = tap.group(1)
        return [f"{number}号出铁口温度", f"{number}号铁口温度", f"{number}铁口温度"]
    return []


def build_aliases(row: dict[str, str]) -> list[str]:
    variable = str(row["变量名"]).strip()
    parts = display_parts(row)
    aliases = [*MANUAL_ALIASES.get(variable, []), *family_aliases(variable, row), *parts]
    description = re.sub(r"^2[#号]?高炉|^2号炉", "", str(row.get("描述") or ""))
    description = re.sub(r"^(?:本体|炉顶|热风炉|槽下|喷吹|干法除尘)[_-]?", "", description).strip("_- ")
    if description and not re.fullmatch(r"上升管煤气温度", description):
        aliases.append(description)
    primary = aliases[0] if aliases else variable
    aliases.extend([f"2号炉{primary}", f"当前{primary}"])
    return unique([value for value in aliases if normalized(value) != normalized(variable)])


def expressions(primary: str) -> list[str]:
    return [
        f"现在的{primary}是多少",
        f"帮我查一下{primary}当前值",
        f"看一下{primary}最近一小时怎么变化",
        f"把{primary}和上一小时比较一下",
    ]


def generate(input_path: Path) -> dict[str, Any]:
    raw = input_path.read_bytes()
    with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    objects: list[dict[str, Any]] = []
    ids: set[str] = set()
    for row in rows:
        variable = str(row.get("变量名") or "").strip()
        if not variable:
            continue
        if variable in ids:
            raise ValueError(f"duplicate variable: {variable}")
        ids.add(variable)
        aliases = build_aliases(row)
        if not aliases:
            raise ValueError(f"no spoken alias generated: {variable}")
        object_kind = "derived_metric" if str(row.get("短名") or "").strip() == "派生" else "physical_sensor"
        objects.append({
            "object_id": variable,
            "object_kind": object_kind,
            "display_name": str(row.get("中文名/标高") or "").strip(),
            "semantic_aliases": aliases,
            "spoken_expressions": expressions(aliases[0]),
            "source": {
                "branch": str(row.get("节点分支") or "").strip(),
                "short_name": str(row.get("短名") or "").strip(),
                "point_id": str(row.get("点ID/长名") or "").strip(),
                "description": str(row.get("描述") or "").strip(),
                "status_usage": str(row.get("状态/用途") or "").strip(),
            },
        })

    alias_owners: dict[str, set[str]] = defaultdict(set)
    for item in objects:
        for alias in item["semantic_aliases"]:
            alias_owners[normalized(alias)].add(item["object_id"])
    collisions = [
        {"normalized_alias": alias, "object_ids": sorted(owners)}
        for alias, owners in sorted(alias_owners.items())
        if len(owners) > 1
    ]
    if collisions:
        collision_keys = {item["normalized_alias"] for item in collisions}
        for item in objects:
            item["semantic_aliases"] = [alias for alias in item["semantic_aliases"] if normalized(alias) not in collision_keys]
            if not item["semantic_aliases"]:
                raise ValueError(f"all aliases collide: {item['object_id']}")
            item["spoken_expressions"] = expressions(item["semantic_aliases"][0])

    payload: dict[str, Any] = {
        "schema_version": "semantic_point_catalog.v1",
        "catalog_version": "2026-08-13.1",
        "source_path": "数据库同步和存取/config/点位清单.tsv",
        "source_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "object_count": len(objects),
        "physical_sensor_count": sum(1 for item in objects if item["object_kind"] == "physical_sensor"),
        "derived_metric_count": sum(1 for item in objects if item["object_kind"] == "derived_metric"),
        "alias_collision_policy": "remove_ambiguous_aliases_and_require_disambiguation",
        "removed_alias_collisions": collisions,
        "objects": objects,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["catalog_hash"] = hashlib.sha256(canonical).hexdigest().upper()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = generate(args.input.resolve())
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("semantic point catalog is stale; regenerate it")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(json.dumps({
        "ok": True,
        "object_count": payload["object_count"],
        "catalog_hash": payload["catalog_hash"],
        "removed_collision_count": len(payload["removed_alias_collisions"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
