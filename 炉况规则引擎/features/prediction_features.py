"""
Derived feature set for online blast-furnace model prediction.

The rule engine and the frontend use raw 1-minute sensor columns such as PI,
DP_total, T_top_A, and T_body_L14_A.  Chronos prediction benefits from a more
compact process feature table, so this module adds the derived variables used
by the recommended 10-target prediction group:

  - radar sounding smooth/change features
  - hopper weight change/cycle proxies
  - top-temperature mean/range
  - body layer mean/max/span summaries
  - static-pressure and uptake-pressure mean/range summaries

Targets remain the real sensor columns.  The target's own history is passed to
Chronos as `target`; these derived columns are only used as past covariates.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd


PREDICTION_TARGETS: List[Dict[str, object]] = [
    {"id": "PI", "name": "透气指数", "priority": 1},
    {"id": "DP_total", "name": "全压差", "priority": 2},
    {"id": "DP_lower", "name": "下部压差", "priority": 2},
    {"id": "DP_upper", "name": "上部压差", "priority": 2},
    {"id": "GasUtil", "name": "煤气利用率", "priority": 3},
    {"id": "T_top", "name": "综合顶温", "priority": 4},
    {"id": "T_top_A", "name": "顶温A", "priority": 4},
    {"id": "T_top_B", "name": "顶温B", "priority": 4},
    {"id": "T_top_C", "name": "顶温C", "priority": 4},
    {"id": "T_top_D", "name": "顶温D", "priority": 4},
]


CORE_OPERATION = [
    "Q_blast",
    "T_blast",
    "P_blast_cold",
    "P_blast",
    "DP_total",
    "DP_lower",
    "DP_upper",
    "P_top",
    "PCI_rate",
    "PCI_set",
]
TOP_DERIVED = ["T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "T_top_mean_ad", "T_top_range_ad"]
RADAR_DERIVED = ["L_radar_smooth", "L_radar_delta_5m", "L_radar_range_5m"]
HOPPER_DERIVED = ["Hopper_weight", "Hopper_weight_delta_1m", "Hopper_weight_rate_5m", "Hopper_weight_is_zero", "Hopper_discharge_event"]
RULER_DERIVED = ["L_SN_diff", "L_south_is_valid", "L_north_is_valid", "L_south_is_negative", "L_north_is_negative"]
UPTAKE_PRESSURE = ["P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D", "P_top_gas_mean", "P_top_gas_range"]
STATIC_PRESSURE = [
    *(f"P_static_upper_{s}" for s in "ABCDEF"),
    *(f"P_static_middle_{s}" for s in "ABCDEF"),
    *(f"P_static_lower_{s}" for s in "ABCDEF"),
    "P_static_upper_mean", "P_static_upper_range",
    "P_static_middle_mean", "P_static_middle_range",
    "P_static_lower_mean", "P_static_lower_range",
]
BODY_LAYER_SUMMARY = [
    *(f"T_body_L{layer}_mean" for layer in range(7, 17)),
    *(f"T_body_L{layer}_max" for layer in range(7, 17)),
    *(f"T_body_L{layer}_span" for layer in range(7, 17)),
    "T_body_lower_mean", "T_body_middle_mean", "T_body_upper_mean", "T_body_lower_upper_gradient",
]
BODY_UPPER_RAW = [f"T_body_L{layer}_{sector}" for layer in (14, 15, 16) for sector in "ABCDEFGH"]


RECOMMENDED_COVARIATES: Dict[str, List[str]] = {
    "PI": [
        *CORE_OPERATION,
        *RADAR_DERIVED,
        *HOPPER_DERIVED,
        *TOP_DERIVED,
        "GasUtil",
        *STATIC_PRESSURE,
    ],
    "DP_total": [
        "P_blast_cold", "P_blast", "Q_blast", "T_blast", "P_top", "PI", "PCI_rate", "PCI_set",
        "DP_lower", "DP_upper", *TOP_DERIVED, *BODY_LAYER_SUMMARY,
    ],
    "DP_lower": [
        "P_blast_cold", "P_blast", "Q_blast", "T_blast", "P_top", "PI", "PCI_rate", "PCI_set",
        "DP_total", "DP_upper", *TOP_DERIVED, *BODY_LAYER_SUMMARY,
    ],
    "DP_upper": [
        "P_blast_cold", "P_blast", "Q_blast", "T_blast", "P_top", "PI", "PCI_rate", "PCI_set",
        "DP_total", "DP_lower", *TOP_DERIVED, *BODY_LAYER_SUMMARY,
    ],
    "GasUtil": [
        "Q_blast", "T_blast", "PCI_rate", "PCI_set", "P_top", "T_top", *TOP_DERIVED,
        "DP_total", "DP_upper", "DP_lower", "PI", *HOPPER_DERIVED, *UPTAKE_PRESSURE, *STATIC_PRESSURE,
    ],
    "T_top": [
        "T_top_A", "T_top_B", "T_top_C", "T_top_D", "P_top", "Q_blast", "T_blast",
        "PCI_rate", "PCI_set", "DP_total", "DP_upper", "DP_lower", "PI", "L", *BODY_UPPER_RAW,
    ],
    "T_top_A": [
        "T_top", "T_top_B", "T_top_C", "T_top_D", "P_top", "Q_blast", "T_blast",
        "PCI_rate", "PCI_set", "DP_total", "PI", "L", *BODY_UPPER_RAW,
    ],
    "T_top_B": [
        "T_top", "T_top_A", "T_top_C", "T_top_D", "P_top", "Q_blast", "T_blast",
        "PCI_rate", "PCI_set", "DP_total", "PI", "L", *BODY_UPPER_RAW,
    ],
    "T_top_C": [
        "T_top", "T_top_A", "T_top_B", "T_top_D", "P_top", "Q_blast", "T_blast",
        "PCI_rate", "PCI_set", "DP_total", "PI", "L", *BODY_UPPER_RAW,
    ],
    "T_top_D": [
        "T_top", "T_top_A", "T_top_B", "T_top_C", "P_top", "Q_blast", "T_blast",
        "PCI_rate", "PCI_set", "DP_total", "PI", "L", *BODY_UPPER_RAW,
    ],
}


DERIVED_FEATURE_NAMES = {
    "L_radar_smooth": "雷达探尺_平滑值",
    "L_radar_delta_5m": "雷达探尺_5分钟变化量",
    "L_radar_range_5m": "雷达探尺_5分钟极差",
    "L_SN_diff": "南北尺差",
    "L_south_is_valid": "南尺有效状态",
    "L_north_is_valid": "北尺有效状态",
    "L_south_is_negative": "南尺是否负值",
    "L_north_is_negative": "北尺是否负值",
    "Hopper_weight_delta_1m": "罐重_1分钟变化量",
    "Hopper_weight_rate_5m": "罐重_5分钟变化率",
    "Hopper_weight_is_zero": "罐重是否回零",
    "Hopper_discharge_event": "罐重卸料事件",
    "T_top_mean_ad": "顶温A-D均值",
    "T_top_range_ad": "顶温A-D极差",
    "T_top_std_ad": "顶温A-D标准差",
    "P_top_gas_mean": "上升管压力A-D均值",
    "P_top_gas_range": "上升管压力A-D极差",
}


def _existing(columns, frame):
    return [col for col in columns if col in frame.columns]


def _add_mean_range(frame: pd.DataFrame, cols: List[str], mean_col: str, range_col: str) -> None:
    cols = _existing(cols, frame)
    if not cols:
        return
    frame[mean_col] = frame[cols].mean(axis=1)
    frame[range_col] = frame[cols].max(axis=1) - frame[cols].min(axis=1)


def build_prediction_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Return raw + derived prediction features aligned on the same minute index."""
    frame = data.copy()

    if "L" in frame:
        frame["L_radar_smooth"] = frame["L"].rolling(5, min_periods=1).median()
        frame["L_radar_delta_5m"] = frame["L_radar_smooth"].diff(5)
        frame["L_radar_range_5m"] = frame["L"].rolling(5, min_periods=1).max() - frame["L"].rolling(5, min_periods=1).min()

    if "L_south" in frame and "L_north" in frame:
        frame["L_SN_diff"] = (frame["L_south"] - frame["L_north"]).abs()
        frame["L_south_is_valid"] = frame["L_south"].notna().astype(float)
        frame["L_north_is_valid"] = frame["L_north"].notna().astype(float)
        frame["L_south_is_negative"] = (frame["L_south"] < 0).astype(float)
        frame["L_north_is_negative"] = (frame["L_north"] < 0).astype(float)

    if "Hopper_weight" in frame:
        frame["Hopper_weight_delta_1m"] = frame["Hopper_weight"].diff()
        frame["Hopper_weight_rate_5m"] = frame["Hopper_weight"].diff(5) / 5.0
        frame["Hopper_weight_is_zero"] = (frame["Hopper_weight"].abs() < 1e-6).astype(float)
        frame["Hopper_discharge_event"] = (frame["Hopper_weight_delta_1m"] < -5).astype(float)

    top_cols = _existing(["T_top_A", "T_top_B", "T_top_C", "T_top_D"], frame)
    if top_cols:
        frame["T_top_mean_ad"] = frame[top_cols].mean(axis=1)
        frame["T_top_range_ad"] = frame[top_cols].max(axis=1) - frame[top_cols].min(axis=1)
        frame["T_top_std_ad"] = frame[top_cols].std(axis=1)

    for layer in range(7, 17):
        cols = _existing([f"T_body_L{layer}_{sector}" for sector in "ABCDEFGH"], frame)
        if cols:
            frame[f"T_body_L{layer}_mean"] = frame[cols].mean(axis=1)
            frame[f"T_body_L{layer}_max"] = frame[cols].max(axis=1)
            frame[f"T_body_L{layer}_span"] = frame[cols].max(axis=1) - frame[cols].min(axis=1)

    lower = _existing([f"T_body_L{x}_mean" for x in (7, 8, 9)], frame)
    middle = _existing([f"T_body_L{x}_mean" for x in (10, 11, 12, 13)], frame)
    upper = _existing([f"T_body_L{x}_mean" for x in (14, 15, 16)], frame)
    if lower:
        frame["T_body_lower_mean"] = frame[lower].mean(axis=1)
    if middle:
        frame["T_body_middle_mean"] = frame[middle].mean(axis=1)
    if upper:
        frame["T_body_upper_mean"] = frame[upper].mean(axis=1)
    if lower and upper:
        frame["T_body_lower_upper_gradient"] = frame["T_body_lower_mean"] - frame["T_body_upper_mean"]

    for zone in ("upper", "middle", "lower"):
        _add_mean_range(
            frame,
            [f"P_static_{zone}_{sector}" for sector in "ABCDEF"],
            f"P_static_{zone}_mean",
            f"P_static_{zone}_range",
        )

    _add_mean_range(
        frame,
        ["P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"],
        "P_top_gas_mean",
        "P_top_gas_range",
    )

    return frame.replace([float("inf"), float("-inf")], pd.NA).ffill().bfill()


def recommended_covariates_for(target_id: str, available_columns) -> List[str]:
    available = set(available_columns)
    return [
        col for col in dict.fromkeys(RECOMMENDED_COVARIATES.get(target_id, []))
        if col != target_id and col in available
    ]
