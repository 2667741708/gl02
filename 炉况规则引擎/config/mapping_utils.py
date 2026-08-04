# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Dict, List

import yaml


ENGINE_DIR = Path(__file__).resolve().parent.parent
VARIABLE_MAP_PATH = ENGINE_DIR / "config" / "variable_map.yaml"
SECTORS = tuple("ABCDEFGH")
BODY_LAYER_TAGS = {
    7: "7层炉腹下标高16860{sector}.csv",
    8: "8层炉腹上标高18335{sector}.csv",
    9: "9层炉腰下标高20125{sector}.csv",
    10: "10层炉身下标高21860{sector}.csv",
    11: "11层路身下标高23711{sector}.csv",
    12: "12层路身下标高25441{sector}.csv",
    13: "13层路身下标高27171{sector}.csv",
    14: "14层炉身中标高28901{sector}.csv",
    15: "15层炉身上标高30631{sector}.csv",
    16: "16层炉身下标高32361{sector}.csv",
}


def _generated_real_sensor_mappings() -> Dict[str, Dict[str, str]]:
    mappings: Dict[str, Dict[str, str]] = {}
    for layer, pattern in BODY_LAYER_TAGS.items():
        for sector in SECTORS:
            tag_sector = "" if layer in (8, 9) and sector == "A" else sector
            mappings[f"T_body_L{layer}_{sector}"] = {
                "tag": pattern.format(sector=tag_sector),
                "unit": "℃",
                "type": "high_freq",
                "source": "csv",
                "description": f"{layer}层炉体温度{sector}点，炉体不同高度与圆周方位温度阵列",
            }

    extra = {
        "L_radar": ("雷达探尺.csv", "m", "雷达探尺，作为主料线 L_main 的优先来源"),
        "P_hot": ("热压.csv", "kPa", "热风压力"),
        "P_cold": ("冷压.csv", "kPa", "冷风压力"),
        "DP_upper": ("上部压差.csv", "kPa", "上部压差"),
        "DP_lower": ("下部压差.csv", "kPa", "下部压差"),
        "DP_total": ("全压差.csv", "kPa", "全压差"),
        "GasUtil": ("煤气利用率.csv", "%", "煤气利用率"),
        "PCI_actual": ("喷煤.csv", "t/h", "喷煤实际值"),
        "PCI_set": ("喷煤设定.csv", "t/h", "喷煤设定值"),
        "O2_big_flow": ("大流量氧气管流量.csv", "m3/h", "大流量氧气管流量"),
        "O2_small_flow": ("小流量氧气管流量.csv", "m3/h", "小流量氧气管流量"),
        "cooling_wall_supply_pressure": ("冷却壁供水环管压力.csv", "kPa", "冷却壁供水环管压力"),
        "cooling_wall_return_pressure": ("冷却壁回水环管压力.csv", "kPa", "冷却壁回水环管压力"),
        "cooling_wall_supply_flow_1": ("冷却壁供水环管流量1.csv", "m3/h", "冷却壁供水环管流量1"),
        "cooling_wall_supply_flow_2": ("冷却壁供水环管流量2.csv", "m3/h", "冷却壁供水环管流量2"),
    }
    for name, (tag, unit, description) in extra.items():
        mappings[name] = {
            "tag": tag,
            "unit": unit,
            "type": "high_freq",
            "source": "csv",
            "description": description,
        }

    for level in ("upper", "middle", "lower"):
        cn = {"upper": "上部", "middle": "中部", "lower": "下部"}[level]
        for sector in "ABCDEF":
            mappings[f"P_static_{level}_{sector}"] = {
                "tag": f"{cn}静压力{sector}.csv",
                "unit": "kPa",
                "type": "high_freq",
                "source": "csv",
                "description": f"{cn}静压力{sector}点",
            }
    return mappings


def load_variable_map() -> Dict[str, Dict[str, str]]:
    raw = yaml.safe_load(VARIABLE_MAP_PATH.read_text(encoding="utf-8")) or {}
    mappings = raw.get("mappings", {}) or {}
    generated = _generated_real_sensor_mappings()
    generated.update(mappings)
    if "L" in generated and "L_radar" in generated:
        generated["L_radar"] = generated["L"]
    if "P_blast" in generated:
        generated["P_hot"] = generated["P_blast"]
    if "P_blast_cold" in generated:
        generated["P_cold"] = generated["P_blast_cold"]
    if "PCI_rate" in generated:
        generated["PCI_actual"] = generated["PCI_rate"]
    if "Q_O2" in generated:
        generated["O2_big_flow"] = generated["Q_O2"]
    return generated


def build_csv_tag_map() -> "OrderedDict[str, str]":
    mappings = load_variable_map()
    tag_map: "OrderedDict[str, str]" = OrderedDict()
    for internal_name, meta in mappings.items():
        tag = meta.get("tag")
        if tag and str(tag).endswith(".csv"):
            tag_map[str(tag)] = internal_name
    return tag_map


def get_signal_definitions() -> List[Dict[str, str]]:
    mappings = load_variable_map()
    signals: List[Dict[str, str]] = []
    for internal_name, meta in mappings.items():
        signals.append(
            {
                "name": internal_name,
                "tag": "" if meta.get("tag") is None else str(meta.get("tag")),
                "unit": str(meta.get("unit", "")),
                "type": str(meta.get("type", "")),
                "source": str(meta.get("source", "csv" if meta.get("tag") else "")),
                "description": str(meta.get("description", "")),
            }
        )
    return signals
