# -*- coding: utf-8 -*-
"""Bridge pSpace realtime tags into the 8092 blast-furnace dashboard stream.

Run this on the dashboard server (10.30.220.12), not on a developer laptop.
It reads pSpace data from 10.22.181.243:8889 and publishes WebSocket frames
compatible with 高炉前端数据/frontend_dashboard_v3.server.html.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


LOG = logging.getLogger("pspace-8092-bridge")
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PSPACE_SERVER = "10.22.181.243"
DEFAULT_PSPACE_PORT = "8889"
DEFAULT_SIO_GL02_ROOT = r"\冀南钢铁\SIO\GL02"
DEFAULT_MAP_PATH = ROOT_DIR / "高炉前端数据" / "pspace_8092_sensor_map.json"
DEFAULT_CANDIDATE_CSV = ROOT_DIR / "高炉前端数据" / "pspace_8092_candidates.csv"
DEFAULT_QA_DB_PATH = ROOT_DIR / "高炉前端数据" / "data" / "bf_qa.sqlite3"
DEFAULT_CHRONOS_SCRIPT = ROOT_DIR / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.py"
DEFAULT_CHRONOS_MODEL_CANDIDATES = (
    Path(os.getenv("BF_CHRONOS_MODEL_PATH", "")) if os.getenv("BF_CHRONOS_MODEL_PATH") else None,
    ROOT_DIR / "chronos外推预测" / "chronos-v2",
    Path(r"F:\高炉炼铁项目-real-sensor-v2\chronos外推预测\chronos-v2"),
    Path(r"F:\blast_furnace_project3\chronos外推预测\chronos-v2"),
    Path(r"F:\blast_furnace_project\chronos外推预测\chronos-v2"),
)
DEFAULT_CHRONOS_PYTHON_CANDIDATES = (
    Path(os.getenv("BF_CHRONOS_PYTHON", "")) if os.getenv("BF_CHRONOS_PYTHON") else None,
    Path(r"F:\anaconda\envs\torch_cuda128_whm\python.exe"),
    Path(r"C:\Program Files\Python311\python.exe"),
    Path(sys.executable),
)
BASELINE_META_PATH = ROOT_DIR / "炉况规则引擎" / "config" / "baseline_meta.yaml"
DEFAULT_SDK_CANDIDATES = (
    Path(os.getenv("PSPACE_SDK_ROOT", "")) if os.getenv("PSPACE_SDK_ROOT") else None,
    ROOT_DIR / "pythonSDK(1)",
    ROOT_DIR / "PythonAPI",
    Path(r"D:\文件\数据库连接方式\pythonSDK(1)"),
    Path(r"F:\openwebui\pythonSDK(1)"),
    Path(r"F:\pythonSDK(1)"),
)


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    display_name: str
    unit: str
    csv_name: str
    wincc_tag: str
    aliases: tuple[str, ...]
    derived_from: tuple[str, ...] = ()
    derive: str = "avg"


SENSORS: tuple[SensorSpec, ...] = (
    SensorSpec("L", "雷达探尺", "m", "雷达探尺.csv", r"ANALOG\BT_LI423001_AI", ("雷达探尺", "主料线", "料线", "探尺")),
    SensorSpec("L_south", "南尺", "m", "南尺.csv", r"ANALOG\BT_Rod1.Value_M", ("南尺", "南探尺")),
    SensorSpec("L_north", "北尺", "m", "北尺.csv", r"ANALOG\BT_Rod2.Value_M", ("北尺", "北探尺")),
    SensorSpec("Hopper_weight", "罐重", "t", "罐重.csv", r"ANALOG\BT_WI423001_AI", ("罐重", "料罐重量", "称量罐重量")),
    SensorSpec("Hopper_weight_set", "罐重设定", "t", "罐重设定.csv", r"GD_1\罐重设定", ("罐重设定", "料罐重量设定")),
    SensorSpec(
        "P_top",
        "顶压",
        "kPa",
        "选择的炉顶压力.csv",
        r"GD_1\BT_Pre_Sel_M",
        ("炉顶压力", "顶压", "炉顶压力平均", "炉顶煤气压力平均", "PT433001"),
        ("P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"),
    ),
    SensorSpec(
        "T_top",
        "综合顶温",
        "℃",
        "选择的炉顶温度.csv",
        r"GD_1\BT_Temp_Sel_M",
        ("炉顶温度", "综合顶温", "平均顶温", "炉顶煤气温度平均", "TI433001"),
        ("T_top_A", "T_top_B", "T_top_C", "T_top_D"),
    ),
    SensorSpec("T_top_A", "顶温A", "℃", "顶温A.csv", r"ANALOG\TE423001A_AI", ("TI433001A", "炉顶煤气温度1", "炉顶温度A", "顶温A")),
    SensorSpec("T_top_B", "顶温B", "℃", "顶温B.csv", r"ANALOG\TE423001B_AI", ("TI433001B", "炉顶煤气温度2", "炉顶温度B", "顶温B")),
    SensorSpec("T_top_C", "顶温C", "℃", "顶温C.csv", r"ANALOG\TE423001C_AI", ("TI433001C", "炉顶煤气温度3", "炉顶温度C", "顶温C")),
    SensorSpec("T_top_D", "顶温D", "℃", "顶温D.csv", r"ANALOG\TE423001D_AI", ("TI433001D", "炉顶煤气温度4", "炉顶温度D", "顶温D")),
    SensorSpec("P_top_gas_A", "上升管压A", "kPa", "炉顶上升管煤气压力A.csv", r"ANALOG\PT423001A_AI", ("PT433001A", "炉顶煤气压力1", "上升管煤气压力A", "上升管压A")),
    SensorSpec("P_top_gas_B", "上升管压B", "kPa", "炉顶上升管煤气压力B.csv", r"ANALOG\PT423001B_AI", ("PT433001B", "炉顶煤气压力2", "上升管煤气压力B", "上升管压B")),
    SensorSpec("P_top_gas_C", "上升管压C", "kPa", "炉顶上升管煤气压力C.csv", r"ANALOG\PT423001C_AI", ("PT433001C", "炉顶煤气压力3", "上升管煤气压力C", "上升管压C")),
    SensorSpec("P_top_gas_D", "上升管压D", "kPa", "炉顶上升管煤气压力D.csv", r"ANALOG\PT423001D_AI", ("PT433001D", "炉顶煤气压力4", "上升管煤气压力D", "上升管压D")),
    SensorSpec("P_blast_cold", "冷风压力", "kPa", "冷压.csv", r"ANALOG\HS_PT425002.VALUE_OUT", ("冷风压力", "冷压", "冷风总管压力")),
    SensorSpec("P_blast", "热风压力", "kPa", "热压.csv", r"ANALOG\PT415001.VALUE_OUT", ("热风压力", "热压", "热风总管压力")),
    SensorSpec("T_blast", "风温", "℃", "风温.csv", r"ANALOG\TE425001.VALUE_OUT", ("热风温度", "风温")),
    SensorSpec("Q_blast", "风量", "Nm3/min", "风量.csv", r"ANALOG\HS_FE425001.VALUE_OUT", ("风量", "热风流量", "冷风流量")),
    SensorSpec("PCI_rate", "喷煤量", "t/h", "喷煤.csv", r"CI\喷煤速率", ("喷煤速率", "喷煤量", "喷煤")),
    SensorSpec("PCI_set", "喷煤设定", "t/h", "喷煤设定.csv", r"CI\喷煤设定", ("喷煤设定",)),
    SensorSpec("Q_O2", "氧气流量", "Nm3/h", "大流量氧气管流量.csv", r"ANALOG\FT416101_DLLYQG_FT", ("富氧流量", "氧气流量", "氧气管流量", "大流量氧气管流量")),
    SensorSpec("TFT", "理论燃烧温度", "℃", "理论燃烧温度.csv", "", ("理论燃烧温度", "TFT")),
    SensorSpec("PI", "透气性指数", "-", "透指.csv", r"GD_1\透气性指数", ("透气性指数", "透指")),
    SensorSpec("GasUtil", "煤气利用率", "%", "煤气利用率.csv", r"ANALOG\MQLY", ("煤气利用率",)),
    SensorSpec("DP_upper", "上部压差", "kPa", "上部压差.csv", r"GD_1\上部压差", ("上部压差",)),
    SensorSpec("DP_lower", "下部压差", "kPa", "下部压差.csv", r"GD_1\下部压差", ("下部压差",)),
    SensorSpec("DP_total", "压差", "kPa", "全压差.csv", r"GD_1\全炉压差", ("全炉压差", "全压差", "总压差"), ("DP_upper", "DP_lower"), "sum"),
    SensorSpec("T_taphole_1", "1#铁口温度代理", "℃", "1#出铁口温度.csv", r"ANALOG\TE_CTK1.VALUE_OUT", ("1号出铁口温度", "1#出铁口温度", "1号铁口温度", "1#铁口温度")),
    SensorSpec("T_taphole_2", "2#铁口温度代理", "℃", "2#出铁口温度.csv", r"ANALOG\TE_CTK2.VALUE_OUT", ("2号出铁口温度", "2#出铁口温度", "2号铁口温度", "2#铁口温度")),
    SensorSpec("T_taphole_3", "3#铁口温度代理", "℃", "3#出铁口温度.csv", r"ANALOG\TE_CTK3.VALUE_OUT", ("3号出铁口温度", "3#出铁口温度", "3号铁口温度", "3#铁口温度")),
    SensorSpec("O2_rate", "富氧率", "%", "富氧率.csv", "", ("富氧率",)),
    SensorSpec("P_static_lower_mean", "下部静压力参考", "kPa", "静压力_20.35米压力.csv", "", ("静压力_20.35米压力", "20.35米压力")),
    SensorSpec("P_static_middle_mean", "中部静压力参考", "kPa", "静压力_23.49米压力.csv", "", ("静压力_23.49米压力", "23.49米压力")),
    SensorSpec("P_static_upper_mean", "上部静压力参考", "kPa", "静压力_28.98米压力.csv", "", ("静压力_28.98米压力", "28.98米压力")),
) + tuple(
    SensorSpec(
        f"T_body_L{layer}_{sector}",
        f"{layer}层炉体温度{sector}",
        "℃",
        f"T_body_L{layer}_{sector}.csv",
        "",
        (f"{layer}层炉体温度{sector}", f"{layer}层{sector}"),
    )
    for layer in range(7, 17)
    for sector in "ABCDEFGH"
)
SENSOR_BY_ID = {sensor.sensor_id: sensor for sensor in SENSORS}

# REQ-BF3D-BILLBOARD-PSPACE-LIVE-20260726
#
# The dashboard's historical 115-field contract and the furnace-body asset's
# 133 physical-point contract overlap, but they are not identical.  Keep the
# dashboard contract stable for diagnosis and add only the 25 missing
# billboard keys to the WebSocket stream.  The seven dashboard-only keys below
# are intentionally excluded from the physical 133-point count.
BILLBOARD_DASHBOARD_ONLY_SENSOR_IDS = frozenset(
    {
        "Hopper_weight",
        "Hopper_weight_set",
        "T_top",
        "T_taphole_3",
        "P_static_lower_mean",
        "P_static_middle_mean",
        "P_static_upper_mean",
    }
)
BILLBOARD_EXTRA_SENSORS: tuple[SensorSpec, ...] = (
    SensorSpec(
        "P_static_20m35",
        "20.35米静压力",
        "kPa",
        "静压力_20.35米压力.csv",
        "",
        ("20.35米静压力", "20.35米压力"),
    ),
    SensorSpec(
        "P_static_23m49",
        "23.49米静压力",
        "kPa",
        "静压力_23.49米压力.csv",
        "",
        ("23.49米静压力", "23.49米压力"),
    ),
    SensorSpec(
        "P_static_28m98",
        "28.98米静压力",
        "kPa",
        "静压力_28.98米压力.csv",
        "",
        ("28.98米静压力", "28.98米压力"),
    ),
    SensorSpec("T_throat_A", "炉喉温度A", "℃", "T_throat_A.csv", "", ("炉喉A方位温度", "炉喉温度A")),
    SensorSpec("T_throat_B", "炉喉温度B", "℃", "T_throat_B.csv", "", ("炉喉B方位温度", "炉喉温度B")),
    SensorSpec("T_throat_C", "炉喉温度C", "℃", "T_throat_C.csv", "", ("炉喉C方位温度", "炉喉温度C")),
    SensorSpec("T_throat_D", "炉喉温度D", "℃", "T_throat_D.csv", "", ("炉喉D方位温度", "炉喉温度D")),
) + tuple(
    SensorSpec(
        f"P_static_{level}_{sector}",
        f"{display_name}{sector}点静压力",
        "kPa",
        f"P_static_{level}_{sector}.csv",
        "",
        (f"{height_label}{sector}点静压力", f"{display_name}{sector}点静压力"),
    )
    for level, display_name, height_label in (
        ("lower", "炉身下部", "20.35米"),
        ("middle", "炉身中部", "23.49米"),
        ("upper", "炉身上部", "28.98米"),
    )
    for sector in "ABCDEF"
)
STREAM_SENSORS: tuple[SensorSpec, ...] = SENSORS + BILLBOARD_EXTRA_SENSORS
STREAM_SENSOR_BY_ID = {sensor.sensor_id: sensor for sensor in STREAM_SENSORS}
BILLBOARD_SENSOR_IDS: tuple[str, ...] = tuple(
    sensor.sensor_id
    for sensor in SENSORS
    if sensor.sensor_id not in BILLBOARD_DASHBOARD_ONLY_SENSOR_IDS
) + tuple(sensor.sensor_id for sensor in BILLBOARD_EXTRA_SENSORS)
if len(BILLBOARD_SENSOR_IDS) != 133 or len(set(BILLBOARD_SENSOR_IDS)) != 133:
    raise RuntimeError("furnace-body billboard pSpace contract must contain exactly 133 unique points")
BASELINE_SENSOR_IDS = (
    "Q_blast",
    "P_blast",
    "T_blast",
    "GasUtil",
    "PCI_rate",
    "P_top",
    "DP_total",
    "PI",
    "T_top",
    "L",
)
CHRONOS_TARGET_IDS = (
    "PI",
    "DP_total",
    "DP_lower",
    "DP_upper",
    "GasUtil",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
)
CHRONOS_CORE_COVARIATES = (
    "Q_blast",
    "T_blast",
    "P_blast",
    "P_blast_cold",
    "P_top",
    "L",
    "L_south",
    "L_north",
    "PCI_rate",
    "PCI_set",
    "DP_total",
    "DP_lower",
    "DP_upper",
    "GasUtil",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
)
ALIAS_OVERRIDES: dict[str, tuple[str, ...]] = {
    "L_south": ("1#探尺料线", "1号探尺料线", "探尺1料位", "1#探尺", "探尺1"),
    "L_north": ("2#探尺料线", "2号探尺料线", "探尺2料位", "2#探尺", "探尺2"),
    "PCI_set": ("一小时喷煤重量设定执行变量", "喷煤重量设定", "喷煤设定执行变量", "喷吹流量设定"),
}
PREFERRED_TAGS: dict[str, str] = {
    "L": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0046",
    "Hopper_weight": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0059",
    "P_top": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0034",
    "P_top_gas_A": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0067",
    "P_top_gas_B": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0068",
    "P_top_gas_C": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0069",
    "P_top_gas_D": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0070",
    "T_top_A": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0040",
    "T_top_B": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0064",
    "T_top_C": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0072",
    "T_top_D": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0043",
    "P_blast": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0149",
    "P_blast_cold": r"\冀南钢铁\SIO\GL02\RF\SIO_GL02_RF_T0047",
    "T_blast": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0006",
    "Q_blast": r"\冀南钢铁\SIO\GL02\RF\SIO_GL02_RF_T0073",
    "PCI_rate": r"\冀南钢铁\SIO\GL02\PC\SIO_GL02_PC_T0007",
    "PCI_set": r"\冀南钢铁\SIO\GL02\PC\SIO_GL02_PC_T0001",
    "Q_O2": r"\冀南钢铁\SIO\GL02\CX\SIO_GL02_CX_T0288",
    "O2_rate": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0115",
    "TFT": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0104",
    "PI": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0101",
    "L_south": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0075",
    "L_north": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0076",
    "GasUtil": r"\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0115",
    "DP_upper": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0135",
    "DP_lower": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0102",
    "DP_total": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0132",
    "T_taphole_1": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0001",
    "T_taphole_2": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0002",
    "T_taphole_3": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0011",
    "P_static_lower_mean": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0152",
    "P_static_middle_mean": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0153",
    "P_static_upper_mean": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0154",
}
COMMON_MEASUREMENT_EXCLUDE_TERMS = ("设定", "设定值", "目标值", "偏差", "累计")
SENSOR_EXCLUDE_TERMS: dict[str, tuple[str, ...]] = {
    "L": ("冷却水", "氮气", "流量", "摄像装置"),
}


def sio_tag(branch: str, short_name: str) -> str:
    return f"{DEFAULT_SIO_GL02_ROOT}\\{branch}\\{short_name}"


def sio_sensor(
    branch: str,
    short_name: str,
    description: str,
    *,
    unit: str = "",
    status: str = "available",
    confidence: str = "high",
    note: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "tag": sio_tag(branch, short_name),
        "description": description,
        "name": short_name,
        "unit": unit,
        "status": status,
        "confidence": confidence,
        "source_root": DEFAULT_SIO_GL02_ROOT,
        "source": "confirmed_sio_gl02",
    }
    if note:
        item["note"] = note
    return item


def direct_sensor(
    tag: str,
    short_name: str,
    description: str,
    source_root: str,
    *,
    unit: str = "",
    status: str = "available",
    confidence: str = "high",
    source: str = "confirmed_cross_tree",
    note: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "tag": tag,
        "description": description,
        "name": short_name,
        "unit": unit,
        "status": status,
        "confidence": confidence,
        "source_root": source_root,
        "source": source,
    }
    if note:
        item["note"] = note
    return item


def build_confirmed_sio_gl02_sensors() -> dict[str, dict[str, Any]]:
    sensors: dict[str, dict[str, Any]] = {
        "L": sio_sensor("LD", "SIO_GL02_LD_T0046", "2号炉炉顶_高炉炉体料位雷达探尺"),
        "L_south": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0075",
            "2号炉炉顶_下限位24米",
            note="Excel 业务名为南探尺，PLC DB8.DD16；pSpace 描述为下限位24米。",
        ),
        "L_north": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0076",
            "2号炉炉顶_下极限位6米",
            note="Excel 业务名为北探尺，PLC DB8.DD4；pSpace 描述为下极限位6米。",
        ),
        "Hopper_weight": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0059",
            "2号炉炉顶_称量罐实际重量称重",
            status="medium_confidence_available",
            confidence="medium",
            note="优先使用称量罐实际重量；备选点为 LD_T0038 受料斗重量。",
        ),
        "P_top": sio_sensor("LD", "SIO_GL02_LD_T0034", "2号炉炉顶_顶压平均"),
        "P_top_gas_A": sio_sensor("LD", "SIO_GL02_LD_T0067", "2号炉炉顶_上升管煤气压力A"),
        "P_top_gas_B": sio_sensor("LD", "SIO_GL02_LD_T0068", "2号炉炉顶_上升管煤气压力B"),
        "P_top_gas_C": sio_sensor("LD", "SIO_GL02_LD_T0069", "2号炉炉顶_上升管煤气压力C"),
        "P_top_gas_D": sio_sensor("LD", "SIO_GL02_LD_T0070", "2号炉炉顶_上升管煤气压力D"),
        "T_top": {
            "derived_from": ["T_top_A", "T_top_B", "T_top_C", "T_top_D"],
            "derive": "avg",
            "description": "四个上升管煤气温度平均值，作为综合顶温中置信替代量",
            "status": "derived_medium_confidence_substitute",
            "confidence": "medium",
            "source_root": DEFAULT_SIO_GL02_ROOT,
            "source": "confirmed_sio_gl02_derived",
            "note": "GL02 SIO 未找到精确顶温 A-D；该值不能在界面或文档中标成已确认顶温。",
        },
        "T_top_A": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0040",
            "2号炉炉顶_上升管煤气温度",
            status="medium_confidence_substitute",
            confidence="medium",
            note="替代顶温A；不是已确认顶温A。",
        ),
        "T_top_B": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0064",
            "2号炉炉顶_上升管煤气温度",
            note="顶温B/上升管煤气温度B。",
        ),
        "T_top_C": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0072",
            "2号炉炉顶_上升管煤气温度",
            note="顶温C/上升管煤气温度C。",
        ),
        "T_top_D": sio_sensor(
            "LD",
            "SIO_GL02_LD_T0043",
            "2号炉炉顶_上升管煤气温度",
            note="顶温D/上升管煤气温度D。",
        ),
        "P_blast_cold": sio_sensor("RF", "SIO_GL02_RF_T0047", "2号炉热风炉_冷风管道压力"),
        "P_blast": sio_sensor("BT", "SIO_GL02_BT_T0149", "2号炉本体_高炉本体热风压力"),
        "T_blast": sio_sensor("BT", "SIO_GL02_BT_T0006", "2号炉本体_热风温度"),
        "Q_blast": sio_sensor("RF", "SIO_GL02_RF_T0073", "2号炉热风炉_冷风管道流量"),
        "PCI_rate": sio_sensor(
            "PC",
            "SIO_GL02_PC_T0007",
            "2号炉喷吹_喷煤量累积瞬时值",
            status="medium_confidence_available",
            confidence="medium",
            note="喷煤量瞬时口径；备选点为 PC_T0004 上小时喷煤量累计。",
        ),
        "PCI_set": sio_sensor("PC", "SIO_GL02_PC_T0001", "2号炉喷吹_一小时喷煤重量设定执行变量"),
        "Q_O2": sio_sensor("CX", "SIO_GL02_CX_T0288", "2号炉槽下_富氧流量"),
        "O2_rate": sio_sensor("BT", "SIO_GL02_BT_T0115", "2号炉本体_富氧率"),
        "TFT": sio_sensor("BT", "SIO_GL02_BT_T0104", "2号炉本体_理论燃烧温度"),
        "PI": sio_sensor("BT", "SIO_GL02_BT_T0101", "2号炉本体_透气性指数"),
        "GasUtil": direct_sensor(
            r"\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0115",
            "SIO_CC_GF2_T0115",
            "2号炉干法除尘_煤气利用率",
            r"\冀南钢铁\SIO\CC\GF2",
            status="available_cross_tree",
            source="excel_22012_pspace_confirmed",
            note="跨子树确认点，默认随 GL02 诊断桥接读取。",
        ),
        "DP_upper": sio_sensor("BT", "SIO_GL02_BT_T0135", "2号炉本体_上部压差"),
        "DP_lower": sio_sensor("BT", "SIO_GL02_BT_T0102", "2号炉本体_下部压差"),
        "DP_total": sio_sensor("BT", "SIO_GL02_BT_T0132", "2号炉本体_全炉压差"),
        "T_taphole_1": sio_sensor("BT", "SIO_GL02_BT_T0001", "2号炉本体_1号出铁口温度"),
        "T_taphole_2": sio_sensor("BT", "SIO_GL02_BT_T0002", "2号炉本体_2号出铁口温度"),
        "T_taphole_3": sio_sensor("BT", "SIO_GL02_BT_T0011", "2号炉本体_3号出铁口温度"),
        "P_static_lower_mean": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0152",
            "2号炉本体_静压力_20.35米压力",
            status="reference_only",
            confidence="medium",
            note="仅作为趋势参考，不能替代 lower/middle/upper A-F 圆周阵列。",
        ),
        "P_static_middle_mean": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0153",
            "2号炉本体_静压力_23.49米压力",
            status="reference_only",
            confidence="medium",
            note="仅作为趋势参考，不能替代 lower/middle/upper A-F 圆周阵列。",
        ),
        "P_static_upper_mean": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0154",
            "2号炉本体_静压力_28.98米压力",
            status="reference_only",
            confidence="medium",
            note="仅作为趋势参考，不能替代 lower/middle/upper A-F 圆周阵列。",
        ),
    }

    layer_names = {
        7: "7层炉腹下温度",
        8: "8层炉腹上温度",
        9: "9层炉腰下温度",
        10: "10层炉身下温度",
        11: "11层炉身下温度",
        12: "12层炉身下温度",
        13: "13层炉身下温度",
        14: "14层炉身中温度",
        15: "15层炉身上温度",
        16: "16层炉身上温度",
    }
    for layer in range(7, 17):
        for sector_index, sector in enumerate("ABCDEFGH"):
            tag_index = 155 + (layer - 7) * 8 + sector_index
            short_name = f"SIO_GL02_BT_T{tag_index:04d}"
            sensors[f"T_body_L{layer}_{sector}"] = sio_sensor(
                "BT",
                short_name,
                f"2号炉本体_{layer_names[layer]}{sector}",
                status="available_body_temperature",
                confidence="high",
            )
    return sensors


def build_confirmed_billboard_extra_sensors() -> dict[str, dict[str, Any]]:
    sensors: dict[str, dict[str, Any]] = {
        "P_static_20m35": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0152",
            "2号炉本体_20.35米静压力",
            status="available_billboard_physical_point",
            confidence="high",
        ),
        "P_static_23m49": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0153",
            "2号炉本体_23.49米静压力",
            status="available_billboard_physical_point",
            confidence="high",
        ),
        "P_static_28m98": sio_sensor(
            "BT",
            "SIO_GL02_BT_T0154",
            "2号炉本体_28.98米静压力",
            status="available_billboard_physical_point",
            confidence="high",
        ),
    }
    for offset, sector in enumerate("ABCD"):
        sensors[f"T_throat_{sector}"] = sio_sensor(
            "BT",
            f"SIO_GL02_BT_T{235 + offset:04d}",
            f"2号炉本体_炉喉{sector}方位温度",
            status="available_billboard_physical_point",
            confidence="high",
        )

    pressure_tags = {
        "lower": ("20.35米炉腰", (102, 103, 104, 105, 107, 108)),
        "middle": ("23.49米炉身下部", (68, 69, 70, 71, 72, 110)),
        "upper": ("28.98米炉身中部", (75, 76, 77, 78, 79, 80)),
    }
    for level, (description, tag_indexes) in pressure_tags.items():
        for sector, tag_index in zip("ABCDEF", tag_indexes):
            short_name = f"EQ_SIO_GL02_BT_T{tag_index:04d}"
            sensors[f"P_static_{level}_{sector}"] = {
                "tag": rf"\冀南二期\EQ\SI0\GL02\BT\{short_name}",
                "description": f"2#高炉本体-{description}静压力{sector}",
                "name": short_name,
                "unit": "kPa",
                "status": "available_billboard_physical_point",
                "confidence": "high",
                "source": "confirmed_static_pressure_af",
            }
    return sensors


CONFIRMED_SIO_GL02_SENSORS = {
    **build_confirmed_sio_gl02_sensors(),
    **build_confirmed_billboard_extra_sensors(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge pSpace realtime data to the 8092 dashboard WebSocket protocol.")
    parser.add_argument("--sdk-root", default=os.getenv("PSPACE_SDK_ROOT"), help="Path containing PythonAPI.")
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER", DEFAULT_PSPACE_SERVER))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT", DEFAULT_PSPACE_PORT))
    parser.add_argument("--pspace-user", default=os.getenv("PSPACE_USER"))
    parser.add_argument("--pspace-password", default=os.getenv("PSPACE_PASSWORD"))
    parser.add_argument("--scope", default=os.getenv("PSPACE_SCOPE", "GL02"), help="Only discover tags whose long name contains this text.")
    parser.add_argument("--root-path", default=os.getenv("PSPACE_ROOT_PATH", DEFAULT_SIO_GL02_ROOT), help="Root node used to restrict pSpace discovery.")
    parser.add_argument("--map", default=os.getenv("PSPACE_8092_MAP", str(DEFAULT_MAP_PATH)))
    parser.add_argument("--candidate-csv", default=os.getenv("PSPACE_8092_CANDIDATES", str(DEFAULT_CANDIDATE_CSV)))
    parser.add_argument("--discover", action="store_true", help="Discover candidates and write the selected map.")
    parser.add_argument("--once", action="store_true", help="Read one realtime frame and print it as JSON.")
    parser.add_argument("--serve", action="store_true", help="Serve dashboard-compatible WebSocket frames.")
    parser.add_argument("--host", default=os.getenv("BF_WS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BF_WS_PORT", "8767")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("PSPACE_POLL_SECONDS", "1.0")))
    parser.add_argument("--history-limit", type=int, default=int(os.getenv("BF_HISTORY_LIMIT", "1440")))
    parser.add_argument("--history-hours", type=int, default=int(os.getenv("PSPACE_HISTORY_HOURS", "8")))
    parser.add_argument("--history-max-values", type=int, default=int(os.getenv("PSPACE_HISTORY_MAX_VALUES", "20000")))
    parser.add_argument("--history-interval-seconds", type=int, default=int(os.getenv("PSPACE_HISTORY_INTERVAL_SECONDS", "60")))
    parser.add_argument("--history-aggregate", default=os.getenv("PSPACE_HISTORY_AGGREGATE", "PS_HIS_AVERAGE"))
    parser.add_argument("--no-history", action="store_true", help="Do not preload historical values into the init frame.")
    parser.add_argument("--no-diagnosis", action="store_true", help="Disable the optional rule/recommendation engine integration.")
    parser.add_argument("--qa-db", default=os.getenv("BF_QA_DB", str(DEFAULT_QA_DB_PATH)), help="SQLite DB used by the 8092 QA proxy.")
    parser.add_argument("--snapshot-interval-seconds", type=float, default=float(os.getenv("BF_SNAPSHOT_INTERVAL_SECONDS", "300")), help="Persist one furnace QA snapshot at this interval. Use 0 to disable.")
    parser.add_argument("--min-score", type=int, default=int(os.getenv("PSPACE_MIN_SCORE", "4")))
    return parser.parse_args()


def find_sdk_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(path for path in DEFAULT_SDK_CANDIDATES if path is not None)

    for path in candidates:
        if (path / "PythonAPI" / "PsServer.py").exists():
            return path
        if path.name == "PythonAPI" and (path / "PsServer.py").exists():
            return path.parent
    raise FileNotFoundError("Cannot find pSpace PythonAPI SDK. Set PSPACE_SDK_ROOT.")


def load_sdk(sdk_root: Path):
    sys.path.insert(0, str(sdk_root))
    from PythonAPI.PsServer import PsObject
    from PythonAPI import Type as T

    return PsObject, T


def require_credentials(args: argparse.Namespace) -> None:
    if not args.pspace_user or not args.pspace_password:
        raise SystemExit("Missing pSpace credentials. Set PSPACE_USER and PSPACE_PASSWORD.")


def connect_pspace(PsObject, T, args: argparse.Namespace):
    pspace = PsObject()
    result = pspace.Connect(
        {
            "ServerIP": args.pspace_server,
            "ServerPort": str(args.pspace_port),
            "UserName": args.pspace_user,
            "Password": args.pspace_password,
        }
    )
    if result.get(T.Return) != 0:
        raise RuntimeError(f"pSpace Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    return pspace


def numeric_items(mapping: dict[str, Any] | dict[int, Any]):
    def sort_key(item):
        key, _ = item
        try:
            return int(key)
        except (TypeError, ValueError):
            return 10**12

    for key, value in sorted(mapping.items(), key=sort_key):
        try:
            int(key)
        except (TypeError, ValueError):
            continue
        yield key, value


def query_all_tag_names(pspace, T) -> list[str]:
    result = pspace.QueryTag({T.QueryTagLongName: "/"})
    if result.get(T.Return) != 0:
        raise RuntimeError(f"QueryTag('/') failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    count = int(result.get(T.QueryTagPropNum, 0) or 0)
    return [str(result.get(i, {}).get(T.QueryTagPropName, "")) for i in range(count)]


def get_tag_props(pspace, T, tag: str) -> dict[str, str]:
    props: dict[str, str] = {"name": "", "description": "", "unit": ""}
    try:
        result = pspace.GetTagProps(
            {
                T.GetTagPropsTagLongName: tag,
                T.GetTagPropsPropIdsList: [
                    "PS_TAG_PROP_NAME",
                    "PS_TAG_PROP_DESCRIPTION",
                    "PS_TAG_PROP_ENGINEERINGUNIT",
                ],
            }
        )
    except Exception as exc:
        LOG.warning("GetTagProps failed for %s: %s", tag, exc)
        return props

    for _, item in numeric_items(result):
        if not isinstance(item, dict):
            continue
        prop_id = item.get(T.GetTagPropsPropId)
        value = str(item.get(T.GetTagPropsValues, "") or "")
        if prop_id == 2:
            props["name"] = value
        elif prop_id == 5:
            props["description"] = value
        elif prop_id == 85:
            props["unit"] = value
    return props


def normalize_text(value: str) -> str:
    value = value.lower()
    value = value.replace("＃", "#").replace("－", "-")
    return re.sub(r"[\s_（）()：:，,。/\\\-]+", "", value)


def score_sensor(sensor: SensorSpec, tag: str, props: dict[str, str]) -> tuple[int, list[str]]:
    description = props.get("description", "")
    haystack = normalize_text(" ".join([tag, props.get("name", ""), description, props.get("unit", "")]))
    score = 0
    matched: list[str] = []

    for alias in (*sensor.aliases, *ALIAS_OVERRIDES.get(sensor.sensor_id, ())):
        normalized_alias = normalize_text(alias)
        if normalized_alias and normalized_alias in haystack:
            score += max(4, len(normalized_alias))
            matched.append(alias)

    wincc_leaf = sensor.wincc_tag.rsplit("\\", 1)[-1].replace(".VALUE_OUT", "")
    if wincc_leaf and normalize_text(wincc_leaf) in haystack:
        score += 10
        matched.append(wincc_leaf)

    if "高炉" in props.get("description", ""):
        score += 2
    if "\\GL02\\" in tag or tag.endswith("\\GL02"):
        score += 3
    if any(part in tag for part in ("\\LD\\", "\\BT\\", "\\CX\\")):
        score += 1
    if PREFERRED_TAGS.get(sensor.sensor_id) == tag:
        score += 100
        matched.append("preferred_tag")

    if not sensor.sensor_id.endswith("_set"):
        for term in COMMON_MEASUREMENT_EXCLUDE_TERMS:
            if term in description:
                score -= 30
                matched.append(f"exclude:{term}")
    for term in SENSOR_EXCLUDE_TERMS.get(sensor.sensor_id, ()):
        if term in description:
            score -= 30
            matched.append(f"exclude:{term}")
    return score, matched


def discover_mapping(pspace, T, scope: str, root_path: str, min_score: int, candidate_csv: Path | None) -> dict[str, Any]:
    normalized_root = root_path.rstrip("\\")
    names = [
        name
        for name in query_all_tag_names(pspace, T)
        if name.startswith(normalized_root + "\\") and name.count("\\") >= 4
    ]
    LOG.info("discovering tags: scope=%s root=%s count=%s", scope, normalized_root, len(names))
    candidates: list[dict[str, Any]] = []

    for index, tag in enumerate(names, 1):
        props = get_tag_props(pspace, T, tag)
        if index % 500 == 0:
            LOG.info("scanned %s/%s tags", index, len(names))
        for sensor in SENSORS:
            if sensor.derived_from:
                continue
            score, matched = score_sensor(sensor, tag, props)
            if score >= min_score and matched:
                candidates.append(
                    {
                        "sensor_id": sensor.sensor_id,
                        "display_name": sensor.display_name,
                        "unit": sensor.unit,
                        "csv_name": sensor.csv_name,
                        "wincc_tag": sensor.wincc_tag,
                        "pspace_tag": tag,
                        "pspace_name": props.get("name", ""),
                        "pspace_description": props.get("description", ""),
                        "pspace_unit": props.get("unit", ""),
                        "score": score,
                        "matched": "|".join(matched),
                    }
                )

    candidates.sort(key=lambda row: (row["sensor_id"], -int(row["score"]), row["pspace_tag"]))
    if candidate_csv:
        candidate_csv.parent.mkdir(parents=True, exist_ok=True)
        with candidate_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sensor_id",
                    "display_name",
                    "unit",
                    "csv_name",
                    "wincc_tag",
                    "pspace_tag",
                    "pspace_name",
                    "pspace_description",
                    "pspace_unit",
                    "score",
                    "matched",
                ],
            )
            writer.writeheader()
            writer.writerows(candidates)
        LOG.info("wrote candidates: %s", candidate_csv)

    selected: dict[str, dict[str, Any]] = {}
    for row in candidates:
        selected.setdefault(
            row["sensor_id"],
            {
                "tag": row["pspace_tag"],
                "description": row["pspace_description"],
                "name": row["pspace_name"],
                "unit": row["pspace_unit"],
                "score": row["score"],
                "matched": row["matched"],
                "source": "auto_discovered",
            },
        )

    for sensor in SENSORS:
        if sensor.derived_from and sensor.sensor_id not in selected:
            selected[sensor.sensor_id] = {
                "derived_from": list(sensor.derived_from),
                "derive": sensor.derive,
                "source": "derived",
            }

    return {
        "version": 1,
        "scope": scope,
        "root_path": normalized_root,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sensors": selected,
    }


def normalize_confirmed_sio_gl02_mapping(mapping: dict[str, Any], root_path: str) -> dict[str, Any]:
    """Use site-confirmed GL02 points for the realtime bridge.

    Older map files may contain "\\冀南二期\\EQ\\SI0\\GL02" candidates from broad
    discovery.  Broad EQ discovery remains forbidden; the only EQ points kept
    are the 18 explicitly audited A-F static-pressure tags required by the
    furnace-body 133-point billboard contract.
    """
    normalized_root = root_path.rstrip("\\")
    if normalized_root != DEFAULT_SIO_GL02_ROOT:
        return mapping

    return {
        "version": max(int(mapping.get("version", 1) or 1), 2),
        "scope": "GL02",
        "root_path": DEFAULT_SIO_GL02_ROOT,
        "generated_at": mapping.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "normalization": "confirmed_sio_gl02_with_gf2_and_audited_eq_static_pressure_af",
        "sensors": CONFIRMED_SIO_GL02_SENSORS,
    }


def load_or_discover_mapping(pspace, T, args: argparse.Namespace) -> dict[str, Any]:
    map_path = Path(args.map)
    if not args.discover and not map_path.exists() and args.root_path.rstrip("\\") == DEFAULT_SIO_GL02_ROOT:
        mapping = normalize_confirmed_sio_gl02_mapping({}, args.root_path)
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("wrote audited GL02 map without broad discovery: %s", map_path)
        return mapping
    if args.discover or not map_path.exists():
        mapping = discover_mapping(
            pspace,
            T,
            args.scope,
            args.root_path,
            args.min_score,
            Path(args.candidate_csv) if args.candidate_csv else None,
        )
        mapping = normalize_confirmed_sio_gl02_mapping(mapping, args.root_path)
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("wrote selected map: %s", map_path)
        return mapping
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    return normalize_confirmed_sio_gl02_mapping(mapping, args.root_path)


def mapped_tags(mapping: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for sensor_id, item in (mapping.get("sensors") or {}).items():
        tag = item.get("tag") if isinstance(item, dict) else None
        if tag:
            out[sensor_id] = tag
    return out


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_existing_path(candidates: Iterable[Path | None], required_child: str | None = None) -> Path | None:
    for candidate in candidates:
        if candidate is None:
            continue
        path = Path(candidate)
        check = path / required_child if required_child else path
        if check.exists():
            return path
    return None


def chronos_python_path() -> Path:
    found = first_existing_path(DEFAULT_CHRONOS_PYTHON_CANDIDATES)
    if found is None:
        raise FileNotFoundError("Chronos Python executable was not found. Set BF_CHRONOS_PYTHON.")
    return found


def chronos_model_path() -> Path:
    found = first_existing_path(DEFAULT_CHRONOS_MODEL_CANDIDATES, "config.json")
    if found is None:
        raise FileNotFoundError("Chronos-2 model directory was not found. Set BF_CHRONOS_MODEL_PATH.")
    return found


def clean_chronos_series(values: Iterable[float | None], limit: int) -> list[float | None]:
    series = list(values)[-limit:]
    if not series:
        return []
    return [float(value) if is_finite_number(value) else None for value in series]


def future_timestamps_from_cutoff(cutoff: str, horizon: int) -> list[str]:
    parsed = parse_history_timestamp(cutoff)
    if parsed is None:
        parsed = datetime.now()
    return [(parsed + timedelta(minutes=i)).isoformat() for i in range(1, int(horizon) + 1)]


def read_realtime(pspace, T, tag_by_sensor: dict[str, str]) -> tuple[dict[str, float | None], dict[str, Any]]:
    tag_names = list(dict.fromkeys(tag_by_sensor.values()))
    value_by_tag: dict[str, float | None] = {}
    timestamp_by_tag: dict[str, str] = {}
    quality_by_tag: dict[str, Any] = {}
    errors: dict[str, str] = {}
    batch_size = max(1, int(os.getenv("PSPACE_REALREAD_BATCH_SIZE", "100") or 100))

    for start in range(0, len(tag_names), batch_size):
        batch = tag_names[start : start + batch_size]
        result = pspace.RealReadList({T.RealReadListTagNameBuffer: batch})
        return_code = result.get(getattr(T, "Return", "Return"), 0)
        if return_code not in (0, None):
            raise RuntimeError(
                "pSpace RealReadList failed for batch "
                f"{start // batch_size + 1}: return={return_code} "
                f"error={result.get(getattr(T, 'Error', 'Error'), '')}"
            )
        for _, item in numeric_items(result):
            if not isinstance(item, dict):
                continue
            tag = str(item.get(T.TagLongNameDict, "") or "")
            value_by_tag[tag] = to_float(item.get(T.PsRealReadListValueDict))
            timestamp_by_tag[tag] = str(item.get(T.PsRealReadListTimeStamp, "") or "")
            quality_by_tag[tag] = item.get(T.PsRealReadListListQualityDict, "")
            if item.get("ErrorInfo"):
                errors[tag] = str(item.get("ErrorInfo"))

    values = {sensor_id: value_by_tag.get(tag) for sensor_id, tag in tag_by_sensor.items()}
    meta = {"timestamps": timestamp_by_tag, "qualities": quality_by_tag, "errors": errors}
    return values, meta


def read_history_raw(pspace, T, tag_by_sensor: dict[str, str], hours: int, max_values: int):
    tag_names = list(dict.fromkeys(tag_by_sensor.values()))
    if not tag_names or hours <= 0:
        return {}

    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    LOG.info("loading pSpace history: tags=%s range=%s~%s", len(tag_names), start_time, end_time)
    return pspace.HisReadRaw(
        {
            T.HisReadRawTagLongName: tag_names,
            T.HisReadRawstartTime: start_time.strftime("%Y/%m/%d %H:%M:%S.000"),
            T.HisReadRawendTime: end_time.strftime("%Y/%m/%d %H:%M:%S.000"),
            T.HisReadRawMaxValues: max_values,
            T.HisReadRawBounds: 0,
        }
    )


def format_ps_history_time(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S.000")


def read_history_processed(
    pspace,
    T,
    tag_by_sensor: dict[str, str],
    hours: int,
    interval_seconds: int = 60,
    aggregate: str = "PS_HIS_AVERAGE",
):
    tag_names = list(dict.fromkeys(tag_by_sensor.values()))
    if not tag_names or hours <= 0:
        return {}

    interval_seconds = max(1, int(interval_seconds or 60))
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    LOG.info(
        "loading pSpace processed history: tags=%s range=%s~%s interval=%ss aggregate=%s",
        len(tag_names),
        start_time,
        end_time,
        interval_seconds,
        aggregate,
    )
    result = pspace.HisReadProcessed(
        {
            T.HisReadProcessedTagNameBuffer: tag_names,
            T.HisReadProcessedstartTime: format_ps_history_time(start_time),
            T.HisReadProcessedendTime: format_ps_history_time(end_time),
            T.HisReadProcessedInterval: interval_seconds,
            T.HisReadProcessedStatistics: [aggregate] * len(tag_names),
        }
    )
    if isinstance(result, dict) and result.get(T.Return, 0) not in (0, None):
        raise RuntimeError(f"HisReadProcessed failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    return result


def history_record_timestamp(T, record: dict[str, Any], processed: bool) -> datetime | None:
    keys: list[str] = []
    if processed:
        keys.append(getattr(T, "HisReadProcessedTimeStamp", "StampTime"))
    else:
        keys.append(getattr(T, "HisReadRawTimeStamp", "TimeStamp"))
    keys.extend([getattr(T, "TimeStamp", "TimeStamp"), "TimeStamp", "StampTime"])
    for key in dict.fromkeys(keys):
        parsed = parse_history_timestamp(record.get(key, ""))
        if parsed is not None:
            return parsed
    return None


def history_record_value(T, record: dict[str, Any], processed: bool) -> float | None:
    keys: list[str] = []
    if processed:
        keys.append(getattr(T, "HisReadProcessedValueDict", "Value"))
    else:
        keys.append(getattr(T, "HisReadRawValueDict", "Value"))
    keys.extend([getattr(T, "ValueDict", "Value"), "Value"])
    for key in dict.fromkeys(keys):
        value = to_float(record.get(key))
        if value is not None:
            return value
    return None


def parse_history_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in (
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def minute_iso(timestamp: datetime) -> str:
    return timestamp.replace(second=0, microsecond=0).isoformat()


def _derive_numeric(parts: list[float], derive: str) -> float | None:
    if not parts:
        return None
    if derive == "sum":
        return round(sum(parts), 4)
    return round(sum(parts) / len(parts), 4)


def _mapping_derived_specs(mapping: dict[str, Any]) -> list[tuple[str, list[str], str]]:
    sensors = mapping.get("sensors") or {}
    specs: list[tuple[str, list[str], str]] = []

    for sensor_id, item in sensors.items():
        if not isinstance(item, dict):
            continue
        sources = item.get("derived_from")
        if not sources:
            continue
        specs.append((sensor_id, list(sources), str(item.get("derive") or "avg")))

    mapped_sensor_ids = {sensor_id for sensor_id, _, _ in specs}
    for sensor in SENSORS:
        if sensor.sensor_id in mapped_sensor_ids or not sensor.derived_from:
            continue
        specs.append((sensor.sensor_id, list(sensor.derived_from), sensor.derive))

    return specs


def apply_derived_values(values: dict[str, float | None], mapping: dict[str, Any]) -> dict[str, float | None]:
    out = dict(values)
    for sensor_id, sources, derive in _mapping_derived_specs(mapping):
        if out.get(sensor_id) is not None:
            continue
        parts = [out.get(source) for source in sources]
        numeric = [float(value) for value in parts if value is not None]
        derived_value = _derive_numeric(numeric, derive)
        if derived_value is not None:
            out[sensor_id] = derived_value
    return out


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def quantile_sorted(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    q = max(0.0, min(1.0, q))
    pos = (len(values) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return values[lower]
    weight = pos - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def load_baseline_meta(path: Path = BASELINE_META_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        LOG.warning("failed to load baseline meta from %s", path, exc_info=True)
        return {}


def scale_baseline_value(sensor_id: str, current_value: float, value: Any, is_scale: bool = False) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if sensor_id == "GasUtil" and abs(current_value) > 1.5 and abs(out) <= 1.5:
        out *= 100.0
    if is_scale and sensor_id == "GasUtil" and abs(current_value) > 1.5 and abs(out) <= 1.5:
        out *= 100.0
    return out


def quantile_status(value: float, q02: float | None, q10: float | None, q90: float | None, q98: float | None) -> str:
    if q02 is None or q10 is None or q90 is None or q98 is None:
        return ""
    if value < q02:
        return "极低"
    if value < q10:
        return "较低"
    if value <= q90:
        return "正常"
    if value <= q98:
        return "较高"
    return "极高"


def baseline_span_hours(timestamps: list[str], indexes: list[int]) -> float:
    parsed: list[datetime] = []
    for index in indexes:
        if index < 0 or index >= len(timestamps):
            continue
        ts = parse_history_timestamp(timestamps[index])
        if ts is not None:
            parsed.append(ts)
    if len(parsed) < 2:
        return 0.0
    return max(0.0, (max(parsed) - min(parsed)).total_seconds() / 3600.0)


def ensure_snapshot_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS furnace_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_time TEXT NOT NULL,
                created_at TEXT NOT NULL,
                values_json TEXT NOT NULL,
                diagnosis_json TEXT NOT NULL,
                recommendation_json TEXT NOT NULL,
                data_quality_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_furnace_snapshots_created
                ON furnace_snapshots(created_at DESC);
            CREATE TABLE IF NOT EXISTS qa_conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_user_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_qa_conversations_updated
                ON qa_conversations(updated_at DESC);
            CREATE TABLE IF NOT EXISTS qa_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                snapshot_id INTEGER,
                hidden_context_json TEXT,
                FOREIGN KEY(conversation_id) REFERENCES qa_conversations(id)
            );
            CREATE INDEX IF NOT EXISTS idx_qa_messages_conversation
                ON qa_messages(conversation_id, id);
            """
        )


def persist_furnace_snapshot(db_path: Path, payload: dict[str, Any]) -> int:
    ensure_snapshot_db(db_path)
    diagnosis_payload = payload.get("diagnosis") or {}
    recommendation = {}
    if isinstance(diagnosis_payload, dict):
        recommendation = diagnosis_payload.get("recommendation") or {}
    record = {
        "source_time": str(payload.get("timestamp") or now_iso()),
        "created_at": now_utc_iso(),
        "values": payload.get("values") or {},
        "diagnosis": diagnosis_payload,
        "recommendation": recommendation,
        "data_quality": payload.get("data_quality") or {},
    }
    record["payload"] = dict(record)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        cur = conn.execute(
            """
            INSERT INTO furnace_snapshots(
                source_time, created_at, values_json, diagnosis_json,
                recommendation_json, data_quality_json, payload_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["source_time"],
                record["created_at"],
                json.dumps(record["values"], ensure_ascii=False),
                json.dumps(record["diagnosis"], ensure_ascii=False),
                json.dumps(record["recommendation"], ensure_ascii=False),
                json.dumps(record["data_quality"], ensure_ascii=False),
                json.dumps(record["payload"], ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)


def minimal_diagnosis(timestamp: str) -> dict[str, Any]:
    return {
        "diagnosis": {
            "main_label": "normal",
            "secondary_label": None,
            "main_score": 60,
            "main_confidence": 0.76,
            "raw_scores": {"normal": 60, "edge": 0, "hot": 0, "center": 0, "channel": 0, "cold": 0, "lowline": 0, "column": 0},
            "evidence": [{"text": "实时 pSpace 数据已接入，诊断引擎可在后续接入完整 1min 宽表后启用。"}],
            "calculated_at": timestamp,
        },
        "recommendation": {
            "goal": "保持当前制度，先确认实时数据映射质量。",
            "immediate_actions": [],
            "followup_actions": ["核对 8092 曲线与现场 HMI 数值一致性。"],
            "forbidden_actions": ["未完成映射核对前，不依据试接入曲线直接调整生产。"],
            "observe": ["顶压", "风量", "压差", "炉顶温度"],
            "safety_warnings": ["实时桥接仅负责数据接入，不替代现场操作确认。"],
            "recheck_minutes": 10,
            "operator_confirm_required": True,
        },
    }


def data_quality(mapping: dict[str, Any], last_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    sensors = mapping.get("sensors") or {}
    mapped = [sensor.sensor_id for sensor in SENSORS if sensor.sensor_id in sensors and (sensors[sensor.sensor_id].get("tag") or sensors[sensor.sensor_id].get("derived_from"))]
    missing = [sensor.sensor_id for sensor in SENSORS if sensor.sensor_id not in mapped]
    billboard_mapped = [
        sensor_id
        for sensor_id in BILLBOARD_SENSOR_IDS
        if sensor_id in sensors
        and (sensors[sensor_id].get("tag") or sensors[sensor_id].get("derived_from"))
    ]
    billboard_missing = [
        sensor_id for sensor_id in BILLBOARD_SENSOR_IDS if sensor_id not in billboard_mapped
    ]
    medium_confidence = [
        sensor_id
        for sensor_id, item in sensors.items()
        if isinstance(item, dict) and item.get("confidence") == "medium"
    ]
    reference_only = [
        sensor_id
        for sensor_id, item in sensors.items()
        if isinstance(item, dict) and item.get("status") == "reference_only"
    ]
    return {
        "source": "pspace",
        "pspace_server": mapping.get("pspace_server", ""),
        "pspace_port": mapping.get("pspace_port", ""),
        "pspace_source": mapping.get("pspace_source", ""),
        "scope": mapping.get("scope", ""),
        "root_path": mapping.get("root_path", ""),
        "poll_seconds": mapping.get("poll_seconds", ""),
        "billboard_expected": len(BILLBOARD_SENSOR_IDS),
        "billboard_mapped": len(billboard_mapped),
        "billboard_missing": billboard_missing,
        "history_interval_seconds": mapping.get("history_interval_seconds", ""),
        "history_aggregate": mapping.get("history_aggregate", ""),
        "loaded_sensors": len(mapped),
        "expected_sensors": len(SENSORS),
        "missing_files": missing,
        "medium_confidence_sensors": medium_confidence,
        "reference_only_sensors": reference_only,
        "missing_points_before_fill": {},
        "realtime_errors": (last_meta or {}).get("errors", {}),
    }


def load_diagnosis_stack(enabled: bool):
    if not enabled:
        return None
    try:
        import pandas as pd

        engine_dir = ROOT_DIR / "炉况规则引擎"
        rec_dir = ROOT_DIR / "调控结论生成引擎"
        sys.path.insert(0, str(rec_dir))
        sys.path.insert(0, str(engine_dir))

        from features.aggregator import FeatureAggregator
        from features.event_features import update_durations
        from integrated_engine import FullSystemEngine

        baseline_path = engine_dir / "config" / "baseline_meta.yaml"
        return {
            "pd": pd,
            "aggregator": FeatureAggregator(str(baseline_path)),
            "update_durations": update_durations,
            "engine": FullSystemEngine(),
            "state": {"Dur_low": 0, "Dur_stall": 0},
        }
    except Exception as exc:
        LOG.warning("rule/recommendation engine unavailable, using minimal diagnosis: %s", exc)
        return None


class DashboardBridge:
    def __init__(
        self,
        pspace,
        T,
        mapping: dict[str, Any],
        history_limit: int,
        poll_seconds: float,
        diagnosis_enabled: bool = True,
        qa_db_path: str | Path | None = None,
        snapshot_interval_seconds: float = 300,
        source_label: str = "",
    ):
        self.pspace = pspace
        self.T = T
        self.mapping = mapping
        self.tag_by_sensor = mapped_tags(mapping)
        self.history_limit = history_limit
        self.poll_seconds = poll_seconds
        self.clients: set[Any] = set()
        self.timestamps: deque[str] = deque(maxlen=history_limit)
        self.history: dict[str, deque[float | None]] = {
            sensor.sensor_id: deque(maxlen=history_limit) for sensor in STREAM_SENSORS
        }
        self.last_meta: dict[str, Any] = {}
        self.diagnosis_stack = load_diagnosis_stack(diagnosis_enabled)
        self.qa_db_path = Path(qa_db_path) if qa_db_path else DEFAULT_QA_DB_PATH
        self.source_label = source_label or f"{DEFAULT_PSPACE_SERVER}:{DEFAULT_PSPACE_PORT}"
        self.snapshot_interval_seconds = max(0.0, float(snapshot_interval_seconds or 0))
        self.last_diagnosis_monotonic = 0.0
        self.cached_diagnosis: dict[str, Any] | None = None
        self.baseline_meta = load_baseline_meta()
        if self.snapshot_interval_seconds > 0:
            ensure_snapshot_db(self.qa_db_path)

    def append_frame(self, timestamp: str, values: dict[str, float | None]) -> None:
        self.timestamps.append(timestamp)
        for sensor in STREAM_SENSORS:
            self.history[sensor.sensor_id].append(values.get(sensor.sensor_id))

    def build_baseline_compare(self, min_samples: int = 30) -> dict[str, Any]:
        timestamps = list(self.timestamps)
        items: list[dict[str, Any]] = []
        max_coverage_hours = 0.0

        for sensor_id in BASELINE_SENSOR_IDS:
            sensor = SENSOR_BY_ID.get(sensor_id)
            series = list(self.history.get(sensor_id, ()))
            pairs = [(index, float(value)) for index, value in enumerate(series) if is_finite_number(value)]
            if len(pairs) < min_samples:
                continue

            current_index, current_value = pairs[-1]
            reference_pairs = pairs[:-1] if len(pairs) > min_samples else pairs
            if len(reference_pairs) < min_samples:
                continue

            reference_values = sorted(value for _, value in reference_pairs)
            rolling_q02 = quantile_sorted(reference_values, 0.02)
            rolling_q10 = quantile_sorted(reference_values, 0.10)
            q1 = quantile_sorted(reference_values, 0.25)
            median = quantile_sorted(reference_values, 0.5)
            q3 = quantile_sorted(reference_values, 0.75)
            rolling_q90 = quantile_sorted(reference_values, 0.90)
            rolling_q98 = quantile_sorted(reference_values, 0.98)
            if q1 is None or median is None or q3 is None:
                continue

            iqr = q3 - q1
            if abs(iqr) < 1e-9:
                iqr = max(abs(median) * 0.02, 1e-6)

            meta = self.baseline_meta.get(sensor_id, {})
            meta_median = scale_baseline_value(sensor_id, current_value, meta.get("median_ref"))
            meta_iqr = scale_baseline_value(sensor_id, current_value, meta.get("iqr_ref"), is_scale=True)
            q02 = scale_baseline_value(sensor_id, current_value, meta.get("q02_ref"))
            q10 = scale_baseline_value(sensor_id, current_value, meta.get("q10_ref"))
            q25 = scale_baseline_value(sensor_id, current_value, meta.get("q25_ref"))
            q50 = scale_baseline_value(sensor_id, current_value, meta.get("q50_ref"))
            q75 = scale_baseline_value(sensor_id, current_value, meta.get("q75_ref"))
            q90 = scale_baseline_value(sensor_id, current_value, meta.get("q90_ref"))
            q98 = scale_baseline_value(sensor_id, current_value, meta.get("q98_ref"))
            baseline_source = "baseline_meta.yaml" if q02 is not None and q10 is not None and q90 is not None and q98 is not None else "rolling_loaded_history"
            q02 = q02 if q02 is not None else rolling_q02
            q10 = q10 if q10 is not None else rolling_q10
            q90 = q90 if q90 is not None else rolling_q90
            q98 = q98 if q98 is not None else rolling_q98
            ref_median = meta_median if meta_median is not None else median
            ref_iqr = meta_iqr if meta_iqr not in (None, 0) else iqr
            q25_out = q25 if q25 is not None else q1
            q50_out = q50 if q50 is not None else ref_median
            q75_out = q75 if q75 is not None else q3
            normal_low = q10 if q10 is not None else q25_out
            normal_high = q90 if q90 is not None else q75_out
            status = quantile_status(current_value, q02, q10, q90, q98)

            ref_indexes = [index for index, _ in reference_pairs]
            coverage_hours = baseline_span_hours(timestamps, ref_indexes)
            max_coverage_hours = max(max_coverage_hours, coverage_hours)

            first_index = ref_indexes[0] if ref_indexes else current_index
            last_index = ref_indexes[-1] if ref_indexes else current_index
            items.append(
                {
                    "id": sensor_id,
                    "name": sensor.display_name if sensor else sensor_id,
                    "unit": sensor.unit if sensor else "",
                    "current": round(current_value, 6),
                    "mean_ref": round(ref_median, 6),
                    "average_ref": round(sum(reference_values) / len(reference_values), 6),
                    "q02": round(q02, 6) if q02 is not None else None,
                    "q10": round(q10, 6) if q10 is not None else None,
                    "q1": round(q25_out, 6),
                    "q25": round(q25_out, 6),
                    "q50": round(q50_out, 6),
                    "q3": round(q75_out, 6),
                    "q75": round(q75_out, 6),
                    "q90": round(q90, 6) if q90 is not None else None,
                    "q98": round(q98, 6) if q98 is not None else None,
                    "iqr": round(ref_iqr, 6),
                    "normal_low": round(normal_low, 6),
                    "normal_high": round(normal_high, 6),
                    "z": round((current_value - ref_median) / ref_iqr, 6),
                    "status": status,
                    "baseline_source": baseline_source,
                    "sample_count": len(reference_values),
                    "baseline_start": timestamps[first_index] if first_index < len(timestamps) else "",
                    "baseline_end": timestamps[last_index] if last_index < len(timestamps) else "",
                }
            )

        return {
            "mode": "rolling" if max_coverage_hours >= 1.0 else "warmup",
            "coverage_hours": round(max_coverage_hours, 3),
            "updated_at": now_iso(),
            "sample_min": min_samples,
            "source": "pspace_processed_1min",
            "items": items,
        }

    def with_baseline_compare(self, report: dict[str, Any]) -> dict[str, Any]:
        report.setdefault("diagnosis", {})
        if isinstance(report["diagnosis"], dict):
            report["diagnosis"]["baseline_compare"] = self.build_baseline_compare()
        return report

    def bootstrap_history(
        self,
        hours: int,
        max_values: int,
        interval_seconds: int = 60,
        aggregate: str = "PS_HIS_AVERAGE",
    ) -> None:
        if hours <= 0:
            return
        processed = True
        try:
            result = read_history_processed(
                self.pspace,
                self.T,
                self.tag_by_sensor,
                hours,
                interval_seconds=interval_seconds,
                aggregate=aggregate,
            )
        except Exception:
            LOG.warning("failed to preload pSpace processed history; falling back to raw history", exc_info=True)
            processed = False
            try:
                result = read_history_raw(self.pspace, self.T, self.tag_by_sensor, hours, max_values)
            except Exception:
                LOG.exception("failed to preload pSpace history; realtime bridge will continue")
                return

        sensor_by_tag: dict[str, list[str]] = {}
        for sensor_id, tag in self.tag_by_sensor.items():
            sensor_by_tag.setdefault(tag, []).append(sensor_id)

        value_keys = {sensor.sensor_id for sensor in SENSORS} | set(self.tag_by_sensor)
        values_by_sensor_minute: dict[str, dict[str, float | None]] = {sensor_id: {} for sensor_id in value_keys}
        total_records = 0
        for tag, sensor_ids in sensor_by_tag.items():
            records = result.get(tag, {})
            if not isinstance(records, dict):
                continue
            if "ErrorInfo" in records or "Error" in records:
                LOG.warning("history read error for %s: %s", tag, records.get("ErrorInfo", records.get("Error", "")))
                continue
            for _, record in numeric_items(records):
                if not isinstance(record, dict):
                    continue
                parsed = history_record_timestamp(self.T, record, processed)
                if parsed is None:
                    continue
                value = history_record_value(self.T, record, processed)
                key = minute_iso(parsed)
                for sensor_id in sensor_ids:
                    values_by_sensor_minute[sensor_id][key] = value
                total_records += 1

        timeline = sorted({key for values in values_by_sensor_minute.values() for key in values})
        if not timeline:
            LOG.warning("pSpace history preload returned no usable records")
            return
        if len(timeline) > self.history_limit:
            timeline = timeline[-self.history_limit :]

        last_values: dict[str, float | None] = {sensor_id: None for sensor_id in value_keys}
        for timestamp in timeline:
            raw_values: dict[str, float | None] = {}
            for sensor_id in value_keys:
                minute_values = values_by_sensor_minute.get(sensor_id, {})
                if timestamp in minute_values:
                    last_values[sensor_id] = minute_values[timestamp]
                raw_values[sensor_id] = last_values.get(sensor_id)
            self.append_frame(timestamp, apply_derived_values(raw_values, self.mapping))

        LOG.info(
            "preloaded pSpace history: mode=%s minutes=%s records=%s",
            "processed_1min" if processed else "raw_minute_floor",
            len(timeline),
            total_records,
        )

    def build_diagnosis_payload(self, timestamp: str) -> dict[str, Any]:
        stack = self.diagnosis_stack
        if not stack or len(self.timestamps) == 0:
            return self.with_baseline_compare(minimal_diagnosis(timestamp))
        try:
            pd = stack["pd"]
            frame = pd.DataFrame(
                {sensor.sensor_id: list(self.history[sensor.sensor_id]) for sensor in SENSORS},
                index=pd.to_datetime(list(self.timestamps), errors="coerce"),
            ).dropna(how="all")
            if frame.empty:
                return self.with_baseline_compare(minimal_diagnosis(timestamp))
            window = frame.tail(60).reset_index().rename(columns={"index": "timestamp"})
            features = stack["aggregator"].aggregate(window)
            stack["state"] = stack["update_durations"](stack["state"], features)
            features.update(stack["state"])

            current = frame.tail(1).iloc[0]
            try:
                features["high_pressure_flag"] = 1 if float(current.get("P_top", 0) or 0) > 200 else 0
            except Exception:
                features["high_pressure_flag"] = 0
            features.setdefault("TRT_running_flag", 0)

            report = stack["engine"].run_full_pipeline(features, timestamp=timestamp)
            report["features"] = {
                "T_body_lower": features.get("T_body_lower"),
                "T_body_middle": features.get("T_body_middle"),
                "T_body_upper": features.get("T_body_upper"),
                "HotSector": features.get("HotSector"),
                "HotSectorScore": features.get("HotSectorScore"),
                "HotSpotJump": features.get("HotSpotJump"),
                "DP_total_z": features.get("z60_DP_total"),
                "realtime_source": "pspace",
            }
            return self.with_baseline_compare(report)
        except Exception:
            LOG.exception("failed to build rule/recommendation diagnosis from realtime history")
            return self.with_baseline_compare(minimal_diagnosis(timestamp))

    def build_init_payload(self) -> dict[str, Any]:
        history = {"timestamps": list(self.timestamps)}
        for sensor in STREAM_SENSORS:
            history[sensor.sensor_id] = list(self.history[sensor.sensor_id])
        ts = history["timestamps"][-1] if history["timestamps"] else now_iso()
        diagnosis = self.cached_diagnosis or self.build_diagnosis_payload(ts)
        return {
            "type": "init",
            "timestamp": ts,
            "history": history,
            "forecast": {"timestamps": []},
            "data_quality": data_quality(self.mapping, self.last_meta),
            "diagnosis": diagnosis,
            "replay": {"mode": "pspace_realtime", "source": self.source_label},
        }

    def diagnosis_for_frame(self, timestamp: str) -> tuple[dict[str, Any], bool]:
        if self.snapshot_interval_seconds <= 0:
            return self.build_diagnosis_payload(timestamp), False
        now = time.monotonic()
        if self.cached_diagnosis is not None and now - self.last_diagnosis_monotonic < self.snapshot_interval_seconds:
            return self.cached_diagnosis, False
        self.cached_diagnosis = self.build_diagnosis_payload(timestamp)
        self.last_diagnosis_monotonic = now
        return self.cached_diagnosis, True

    def read_frame(self) -> dict[str, Any]:
        raw_values, meta = read_realtime(self.pspace, self.T, self.tag_by_sensor)
        values = apply_derived_values(raw_values, self.mapping)
        timestamp = next((ts for ts in meta.get("timestamps", {}).values() if ts), "") or now_iso()
        self.last_meta = meta
        self.append_frame(timestamp, values)
        diagnosis, diagnosis_refreshed = self.diagnosis_for_frame(timestamp)
        payload = {
            "type": "tick",
            "timestamp": timestamp,
            "values": {
                sensor.sensor_id: values.get(sensor.sensor_id) for sensor in STREAM_SENSORS
            },
            "point_meta": self.billboard_point_meta(meta),
            "forecast": {"timestamps": []},
            "data_quality": data_quality(self.mapping, meta),
            "diagnosis": diagnosis,
            "replay": {"mode": "pspace_realtime", "source": self.source_label},
        }
        if diagnosis_refreshed:
            self.persist_snapshot(payload)
        return payload

    def billboard_point_meta(self, meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
        timestamps = meta.get("timestamps") or {}
        qualities = meta.get("qualities") or {}
        errors = meta.get("errors") or {}
        output: dict[str, dict[str, Any]] = {}
        for sensor_id in BILLBOARD_SENSOR_IDS:
            tag = self.tag_by_sensor.get(sensor_id)
            if not tag:
                continue
            item = {
                "timestamp": timestamps.get(tag, ""),
                "quality": qualities.get(tag, ""),
            }
            if errors.get(tag):
                item["error"] = errors[tag]
            output[sensor_id] = item
        return output

    def persist_snapshot(self, payload: dict[str, Any]) -> None:
        if self.snapshot_interval_seconds <= 0:
            return
        try:
            snapshot_id = persist_furnace_snapshot(self.qa_db_path, payload)
            LOG.info("persisted QA furnace snapshot id=%s db=%s", snapshot_id, self.qa_db_path)
        except Exception:
            LOG.exception("failed to persist QA furnace snapshot")

    def chronos_covariates_for(self, target_id: str, context_mins: int) -> list[dict[str, Any]]:
        covariates: list[dict[str, Any]] = []
        for sensor_id in CHRONOS_CORE_COVARIATES:
            if sensor_id == target_id:
                continue
            values = clean_chronos_series(self.history.get(sensor_id, ()), context_mins)
            if len(values) < 30 or not any(value is not None for value in values):
                continue
            sensor = SENSOR_BY_ID.get(sensor_id)
            covariates.append(
                {
                    "id": sensor_id,
                    "name": sensor.display_name if sensor else sensor_id,
                    "values": values,
                }
            )
        return covariates

    def build_chronos_job(self, target_id: str, horizon: int, context_mins: int) -> dict[str, Any]:
        target_id = str(target_id or "").strip()
        sensor = SENSOR_BY_ID.get(target_id)
        if sensor is None:
            raise ValueError(f"unknown Chronos target: {target_id}")
        target_values = clean_chronos_series(self.history.get(target_id, ()), context_mins)
        if len(target_values) < 30 or not any(value is not None for value in target_values):
            raise ValueError(f"not enough Chronos context for {target_id}: {len(target_values)}")
        cutoff = self.timestamps[-1] if self.timestamps else now_iso()
        return {
            "job_id": target_id,
            "target": {
                "id": target_id,
                "name": sensor.display_name,
                "values": target_values,
            },
            "covariates": self.chronos_covariates_for(target_id, len(target_values)),
            "context_minutes": len(target_values),
            "prediction_minutes": int(horizon),
            "cutoff_time": cutoff,
            "future_timestamps": future_timestamps_from_cutoff(cutoff, int(horizon)),
        }

    def build_chronos_batch_payload(self, target_ids: Iterable[str], horizon: int, context_mins: int) -> dict[str, Any]:
        requested = [str(item).strip() for item in target_ids if str(item).strip()]
        if not requested:
            requested = list(CHRONOS_TARGET_IDS)
        jobs: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for target_id in requested:
            try:
                jobs.append(self.build_chronos_job(target_id, horizon, context_mins))
            except Exception as exc:  # noqa: BLE001
                skipped.append({"target_id": target_id, "reason": str(exc)})
        if not jobs:
            raise ValueError(f"no Chronos targets have enough context: {skipped}")
        return {"jobs": jobs, "skipped": skipped}

    def run_chronos_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not DEFAULT_CHRONOS_SCRIPT.exists():
            raise FileNotFoundError(f"Chronos script not found: {DEFAULT_CHRONOS_SCRIPT}")
        python_path = chronos_python_path()
        model_path = chronos_model_path()
        tmp_path = ""
        out_path = ""
        err_path = ""
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as handle:
                json.dump({key: value for key, value in payload.items() if key != "skipped"}, handle, ensure_ascii=False)
                tmp_path = handle.name
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".out", encoding="utf-8") as out_handle:
                out_path = out_handle.name
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".err", encoding="utf-8") as err_handle:
                err_path = err_handle.name
            with open(out_path, "w", encoding="utf-8", errors="replace") as stdout_handle, open(
                err_path, "w", encoding="utf-8", errors="replace"
            ) as stderr_handle:
                proc = subprocess.run(
                    [
                        str(python_path),
                        str(DEFAULT_CHRONOS_SCRIPT),
                        "--input",
                        tmp_path,
                        "--model-path",
                        str(model_path),
                    ],
                    cwd=str(ROOT_DIR),
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    timeout=float(os.getenv("BF_CHRONOS_TIMEOUT_SECONDS", "900")),
                )
            stdout_text = Path(out_path).read_text(encoding="utf-8", errors="replace") if out_path else ""
            stderr_text = Path(err_path).read_text(encoding="utf-8", errors="replace") if err_path else ""
            if proc.returncode != 0:
                raise RuntimeError(stderr_text.strip() or stdout_text.strip() or "Chronos prediction failed")
            lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
            json_line = next((line for line in reversed(lines) if line.startswith("{")), "")
            if not json_line:
                raise RuntimeError(stdout_text.strip() or stderr_text.strip() or "Chronos did not return JSON")
            result = json.loads(json_line)
            result["type"] = "chronos_prediction_batch" if "jobs" in payload else "chronos_prediction"
            result["engine"] = "chronos_2_live"
            result["model_path"] = str(model_path)
            result["skipped"] = payload.get("skipped", [])
            return result
        finally:
            for path in (tmp_path, out_path, err_path):
                if not path:
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def handle_chronos_request(self, websocket, request: dict[str, Any]) -> None:
        horizon = max(1, min(240, int(request.get("prediction_minutes") or 120)))
        context_mins = max(30, min(self.history_limit, int(request.get("context_minutes") or 480)))
        request_type = request.get("type")
        if request_type == "chronos_predict_recommended_batch":
            target_ids = request.get("target_ids") or CHRONOS_TARGET_IDS
            payload = self.build_chronos_batch_payload(target_ids, horizon, context_mins)
            await websocket.send(
                json.dumps(
                    {
                        "type": "chronos_prediction_status",
                        "status": "running_batch",
                        "target_id": "recommended_batch",
                        "target_count": len(payload.get("jobs", [])),
                        "engine": "chronos_2_live",
                    },
                    ensure_ascii=False,
                )
            )
        else:
            target_id = str(request.get("target_id") or "PI")
            payload = self.build_chronos_job(target_id, horizon, context_mins)
            await websocket.send(
                json.dumps(
                    {
                        "type": "chronos_prediction_status",
                        "status": "running",
                        "target_id": target_id,
                        "engine": "chronos_2_live",
                    },
                    ensure_ascii=False,
                )
            )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: self.run_chronos_payload(payload))
        await websocket.send(json.dumps(result, ensure_ascii=False))

    async def register(self, websocket) -> None:
        self.clients.add(websocket)
        await websocket.send(json.dumps(self.build_init_payload(), ensure_ascii=False))
        LOG.info("client connected: total=%s", len(self.clients))

    async def unregister(self, websocket) -> None:
        self.clients.discard(websocket)
        LOG.info("client disconnected: total=%s", len(self.clients))

    async def handler(self, websocket) -> None:
        await self.register(websocket)
        try:
            async for message in websocket:
                try:
                    request = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if request.get("type") not in {"chronos_predict", "chronos_predict_recommended_batch"}:
                    continue
                try:
                    await self.handle_chronos_request(websocket, request)
                except Exception as exc:  # noqa: BLE001
                    LOG.exception("Chronos prediction failed")
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "chronos_prediction_batch"
                                if request.get("type") == "chronos_predict_recommended_batch"
                                else "chronos_prediction",
                                "status": "error",
                                "message": str(exc),
                            },
                            ensure_ascii=False,
                        )
                    )
        finally:
            await self.unregister(websocket)

    async def broadcast_loop(self) -> None:
        while True:
            try:
                payload = self.read_frame()
                text = json.dumps(payload, ensure_ascii=False)
                if self.clients:
                    dead = set()
                    for websocket in list(self.clients):
                        try:
                            await websocket.send(text)
                        except Exception:
                            dead.add(websocket)
                    for websocket in dead:
                        await self.unregister(websocket)
                LOG.info("tick %s mapped=%s clients=%s", payload["timestamp"], len(self.tag_by_sensor), len(self.clients))
            except Exception:
                LOG.exception("failed to read/broadcast realtime frame")
            await asyncio.sleep(self.poll_seconds)


def print_mapping_summary(mapping: dict[str, Any]) -> None:
    sensors = mapping.get("sensors") or {}
    for sensor in STREAM_SENSORS:
        item = sensors.get(sensor.sensor_id, {})
        if item.get("tag"):
            print(f"{sensor.sensor_id}\t{sensor.display_name}\t{item.get('tag')}\t{item.get('description', '')}")
        elif item.get("derived_from"):
            print(f"{sensor.sensor_id}\t{sensor.display_name}\tDERIVED({','.join(item.get('derived_from', []))})")
        else:
            print(f"{sensor.sensor_id}\t{sensor.display_name}\tMISSING")


async def serve_websocket(bridge: DashboardBridge, host: str, port: int) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Missing dependency: websockets. Install it in the server Python environment.") from exc

    LOG.info("serving WebSocket ws://%s:%s", host, port)
    async with websockets.serve(bridge.handler, host, port):
        await bridge.broadcast_loop()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    require_credentials(args)
    sdk_root = find_sdk_root(args.sdk_root)
    LOG.info("using SDK root: %s", sdk_root)
    PsObject, T = load_sdk(sdk_root)
    pspace = connect_pspace(PsObject, T, args)

    try:
        mapping = load_or_discover_mapping(pspace, T, args)
        mapping["pspace_server"] = args.pspace_server
        mapping["pspace_port"] = args.pspace_port
        mapping["pspace_source"] = f"{args.pspace_server}:{args.pspace_port}"
        mapping["poll_seconds"] = args.poll_seconds
        mapping["history_interval_seconds"] = args.history_interval_seconds
        mapping["history_aggregate"] = args.history_aggregate
        print_mapping_summary(mapping)
        bridge = DashboardBridge(
            pspace,
            T,
            mapping,
            args.history_limit,
            args.poll_seconds,
            diagnosis_enabled=not args.no_diagnosis,
            qa_db_path=args.qa_db,
            snapshot_interval_seconds=args.snapshot_interval_seconds,
            source_label=f"{args.pspace_server}:{args.pspace_port}",
        )
        if not args.no_history:
            bridge.bootstrap_history(
                args.history_hours,
                args.history_max_values,
                interval_seconds=args.history_interval_seconds,
                aggregate=args.history_aggregate,
            )

        if args.once:
            payload = bridge.read_frame()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.serve:
            asyncio.run(serve_websocket(bridge, args.host, args.port))
            return 0

        LOG.info("no action requested; use --discover, --once, or --serve")
        return 0
    finally:
        try:
            pspace.CloseConnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
