"""高压、悬料、顶温、风口和TRT安全门禁。"""

from __future__ import annotations

from typing import Any


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return float(value) == 1.0
    except (TypeError, ValueError):
        return False


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_safety_gate(diagnosis_result: dict[str, Any]) -> dict[str, Any]:
    """返回安全门禁状态、警示、强制动作和禁用动作。"""
    features = diagnosis_result.get("features_snapshot", {}) or {}
    main_label = str(diagnosis_result.get("main_label") or "")
    main_score = _as_float(diagnosis_result.get("main_score"))
    raw_scores = diagnosis_result.get("raw_scores", {}) or {}
    column_score = _as_float(
        raw_scores.get("column"), main_score if main_label == "column" else 0.0
    )
    probe_stall = _as_bool(features.get("probe_stall_flag"))
    confirmed_column = main_label == "column" and max(main_score, column_score) >= 60.0

    safety_gate_passed = True
    safety_warnings: list[str] = []
    forced_action_ids: list[str] = []
    forbidden_ids: list[str] = []

    if _as_bool(features.get("high_pressure_flag")):
        safety_warnings.append("当前为高压运行，禁止直接放风坐料或休风")
        forbidden_ids.extend(["UP-12", "LOW-BLAST-UP-GATE"])
        if main_label in {"column", "lowline", "channel"}:
            forced_action_ids.append("SAFETY-PRESSURE-NORMAL")

    if confirmed_column:
        safety_warnings.append("当前存在悬料征兆，需先解除悬料再考虑休风")
        forced_action_ids.extend(["SAFETY-COLUMN-PLAN", "SAFETY-COLUMN-VERIFY"])
    elif probe_stall:
        safety_warnings.append("探尺停滞信号需结合风压、压差、透气性和现场下料情况复核")

    if _as_float(features.get("Ttop_max15")) > 350:
        safety_gate_passed = False
        safety_warnings.append("炉顶温度超过350℃，存在烧坏炉顶设备风险")
        forced_action_ids.append("SAFETY-TOP-TEMP-350")

    if _as_bool(features.get("tuyere_abnormal_flag")):
        safety_warnings.append("风口状态异常，严禁强行恢复风量")
        forbidden_ids.append("LOW-BLAST-UP-GATE")
        forced_action_ids.append("SAFETY-TUYERE-CHECK")

    if (confirmed_column or main_label == "channel") and _as_bool(
        features.get("TRT_running_flag")
    ):
        forced_action_ids.append("SAFETY-TRT-OFF")

    return {
        "safety_gate_passed": safety_gate_passed,
        "safety_warnings": safety_warnings,
        "forced_action_ids": list(dict.fromkeys(forced_action_ids)),
        "forbidden_ids": list(dict.fromkeys(forbidden_ids)),
    }
