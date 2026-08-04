# -*- coding: utf-8 -*-
"""事件型特征与持续时间变量。"""

from __future__ import annotations

import pandas as pd


HIGH_PRESSURE_THRESHOLD_KPA = 200.0


def update_durations(state, features):
    """更新持续时间特征。"""
    if features.get("DeltaL", 0) > 0.5:
        state["Dur_low"] = state.get("Dur_low", 0) + 1
    else:
        state["Dur_low"] = 0

    l_series = features.get("L_effective_series")
    if l_series is None:
        l_series = features.get("L_series")
    if l_series is not None and len(l_series.dropna()) >= 5:
        std_l = l_series.tail(5).std()
        if std_l < 0.01:
            state["Dur_stall"] = state.get("Dur_stall", 0) + 1
        else:
            state["Dur_stall"] = 0
    else:
        state["Dur_stall"] = state.get("Dur_stall", 0)

    return state


def extract_event_flags(df, features=None, state=None):
    """从实时窗口和派生特征中提取事件标志。"""
    flags = {}
    features = features or {}

    if "charge_fault_flag" in df.columns:
        flags["charge_fault_flag"] = bool(df["charge_fault_flag"].iloc[-1])
    elif "Hopper_weight_set" in df.columns and "Hopper_weight" in df.columns:
        target = float(df["Hopper_weight_set"].iloc[-1] or 0)
        actual = float(df["Hopper_weight"].iloc[-1] or 0)
        flags["charge_fault_flag"] = bool(target > 1 and abs(target - actual) > max(5.0, target * 0.5))
    else:
        flags["charge_fault_flag"] = False

    if "probe_stall_flag" in df.columns:
        flags["probe_stall_flag"] = bool(df["probe_stall_flag"].iloc[-1])
    elif "probe_stall_flag" in features:
        flags["probe_stall_flag"] = bool(features.get("probe_stall_flag"))
    elif "L_slope_20" in features:
        flags["probe_stall_flag"] = bool(abs(float(features.get("L_slope_20", 0) or 0)) <= 0.01)
    else:
        flags["probe_stall_flag"] = bool(features.get("Dur_stall", 0) >= 5)

    if "tuyere_abnormal_flag" in df.columns:
        flags["tuyere_abnormal_flag"] = bool(df["tuyere_abnormal_flag"].iloc[-1])
    else:
        flags["tuyere_abnormal_flag"] = False

    if "high_pressure_flag" in df.columns:
        raw = df["high_pressure_flag"].iloc[-1]
        flags["high_pressure_flag"] = bool(raw if pd.notna(raw) else 0)
    elif "P_top" in df.columns:
        flags["high_pressure_flag"] = bool(float(df["P_top"].iloc[-1] or 0) > HIGH_PRESSURE_THRESHOLD_KPA)
    else:
        flags["high_pressure_flag"] = False

    if "TRT_running_flag" in df.columns:
        raw = df["TRT_running_flag"].iloc[-1]
        try:
            flags["TRT_running_flag"] = bool(float(raw) > 0)
        except Exception:
            flags["TRT_running_flag"] = bool(raw)
    else:
        flags["TRT_running_flag"] = False

    return flags
