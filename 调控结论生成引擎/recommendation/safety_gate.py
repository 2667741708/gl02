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
    forced_actions: list[str] = []
    forbidden_ids: list[str] = []

    if _as_bool(features.get("high_pressure_flag")):
        safety_warnings.append("当前为高压运行，禁止直接放风坐料或休风")
        forbidden_ids.extend(["sit_burden", "stop_blast"])
        if main_label in {"column", "lowline"}:
            forced_actions.append("先改常压运行")

    if confirmed_column:
        safety_warnings.append("当前存在悬料征兆，需先解除悬料再考虑休风")
        forbidden_ids.append("stop_blast")
        forced_actions.append("确认悬料硬条件后，按事故预案处置富氧、喷煤、TRT和炉顶打水")
        forced_actions.append("组织现场复核探尺、风压、压差和透气性后再执行坐料相关操作")
    elif probe_stall:
        safety_warnings.append("探尺停滞信号需结合风压、压差、透气性和现场下料情况复核")

    if _as_float(features.get("Ttop_max15")) > 350:
        safety_gate_passed = False
        safety_warnings.append("炉顶温度超过350℃，存在烧坏炉顶设备风险")
        forced_actions.extend(["启动炉顶打水控顶温", "大幅减风"])

    if _as_bool(features.get("tuyere_abnormal_flag")):
        safety_warnings.append("风口状态异常，严禁强行恢复风量")
        forbidden_ids.append("restore_blast")
        forced_actions.append("优先检查风口，严防灌渣")

    if (confirmed_column or main_label == "channel") and _as_bool(
        features.get("TRT_running_flag")
    ):
        forced_actions.append("先解列TRT")

    return {
        "safety_gate_passed": safety_gate_passed,
        "safety_warnings": safety_warnings,
        "forced_actions": forced_actions,
        "forbidden_ids": list(dict.fromkeys(forbidden_ids)),
    }
