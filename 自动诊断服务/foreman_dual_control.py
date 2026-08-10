"""Quantify read-only foreman advice for cold-blast pressure and PCI setpoint.

Requirement: REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any

from recommendation.action_contract import build_action
from recommendation.formatter import RecommendationFormatter


SCOPE_VERSION = "foreman_dual_control.v2"
ALLOWED_CONTROL_VARIABLES = ("P_blast_cold", "PCI_set")
ACTION_CONTROL_MAP: dict[str, tuple[str, str]] = {
    "LOW-BLAST-UP-GATE": ("P_blast_cold", "increase"),
    "LOW-BLAST-DOWN-02": ("P_blast_cold", "decrease"),
    "LOW-BLAST-DOWN-04": ("P_blast_cold", "decrease"),
    "LOW-BLAST-DOWN-05": ("P_blast_cold", "decrease"),
    "LOW-PCI-UP-02": ("PCI_set", "increase"),
    "LOW-PCI-DOWN-02": ("PCI_set", "decrease"),
    "LOW-PCI-DOWN-05": ("PCI_set", "stop"),
}

PRESSURE_HARD_MIN_KPA = 400.0
PCI_EMERGENCY_MIN_TPH = 0.0
PCI_NORMAL_MIN_TPH = 10.0
PCI_MAX_TPH = 45.0
MIN_BASELINE_COVERAGE = 0.75
MAX_CURRENT_LAG_MINUTES = 5
MAX_BASELINE_AGE_DAYS = 1

PRESSURE_BASELINE_FIELDS = (
    "pressure_baseline_p25",
    "pressure_baseline_p75",
    "pressure_baseline_day",
    "pressure_baseline_sample_count",
    "pressure_baseline_coverage_ratio",
    "pressure_baseline_updated_at",
)

_FORMATTER = RecommendationFormatter()


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _iso(value: object) -> str | None:
    parsed = _as_datetime(value)
    return parsed.isoformat(sep=" ") if parsed else None


def _next_full_hour(value: object) -> str | None:
    parsed = _as_datetime(value)
    if parsed is None:
        return None
    return (parsed.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat(sep=" ")


def _severity_step(score: object, variable: str) -> dict[str, Any]:
    value = _finite(score) or 0.0
    if value >= 85:
        severity = "critical"
    elif value >= 75:
        severity = "high"
    elif value >= 60:
        severity = "medium"
    else:
        severity = "low"
    if variable == "P_blast_cold":
        step = 10.0 if value >= 75 else 5.0 if value >= 60 else 3.0
        unit = "kPa"
    else:
        step = 3.0 if value >= 75 else 2.0 if value >= 60 else 1.0
        unit = "t/h"
    return {"severity": severity, "standard_step": step, "unit": unit, "clamped": False}


def _append_unique(items: list[str], *values: str) -> list[str]:
    return list(dict.fromkeys(items + [value for value in values if value]))


def build_foreman_control_context(
    base_features: dict[str, Any],
    current_values: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlay live values, measurement time and exact 30-day pressure quartiles."""
    context = dict(base_features)
    current = current_values or {}
    for field in (
        "P_blast_cold",
        "PCI_set",
        "current_values_timestamp",
        "P_blast_cold_timestamp",
        *PRESSURE_BASELINE_FIELDS,
    ):
        if field in current:
            context[field] = current[field]

    nested = current.get("pressure_baseline")
    if isinstance(nested, dict):
        aliases = {
            "p25": "pressure_baseline_p25",
            "p75": "pressure_baseline_p75",
            "baseline_day": "pressure_baseline_day",
            "sample_count": "pressure_baseline_sample_count",
            "coverage_ratio": "pressure_baseline_coverage_ratio",
            "updated_at": "pressure_baseline_updated_at",
        }
        for source, target in aliases.items():
            if target not in context and source in nested:
                context[target] = nested[source]

    diagnosis = diagnosis or {}
    context["diagnosis_main_score"] = diagnosis.get("main_score")
    context["recommendation_diagnosis_timestamp"] = (
        diagnosis.get("diagnosis_ts")
        or diagnosis.get("timestamp")
        or diagnosis.get("calculated_at")
    )
    return context


def _pressure_limit_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    p25 = _finite(context.get("pressure_baseline_p25"))
    p75 = _finite(context.get("pressure_baseline_p75"))
    return {
        "hard_min": PRESSURE_HARD_MIN_KPA,
        "hard_max": p75,
        "normal_q1": p25,
        "normal_q3": p75,
        "baseline_day": str(context.get("pressure_baseline_day") or "") or None,
        "sample_count": _finite(context.get("pressure_baseline_sample_count")),
        "coverage_ratio": _finite(context.get("pressure_baseline_coverage_ratio")),
        "updated_at": _iso(context.get("pressure_baseline_updated_at")),
        "source": "bf_sensor.daily_baselines:30d:p25_p75",
    }


def _coal_limit_snapshot() -> dict[str, Any]:
    return {
        "hard_min": PCI_EMERGENCY_MIN_TPH,
        "hard_max": PCI_MAX_TPH,
        "normal_min": PCI_NORMAL_MIN_TPH,
        "normal_max": PCI_MAX_TPH,
        "normal_q1": None,
        "normal_q3": None,
        "source": "foreman_approved_fixed_bounds",
    }


def _base_action_contract(
    action: dict[str, Any], context: dict[str, Any], variable: str, direction: str, score: object
) -> dict[str, Any]:
    scoped = copy.deepcopy(action)
    current = _finite(context.get(variable))
    label = "冷风压力" if variable == "P_blast_cold" else "喷煤设定"
    scoped.update(
        {
            "control_variable": variable,
            "control_label": label,
            "adjustment_direction": direction,
            "current_value": current,
            "recommended_change": None,
            "recommended_target": None,
            "unit": "kPa" if variable == "P_blast_cold" else "t/h",
            "step_tier": _severity_step(score, variable),
            "effective_at": None,
            "limit_snapshot": _pressure_limit_snapshot(context)
            if variable == "P_blast_cold"
            else _coal_limit_snapshot(),
            "read_only": True,
            "delta": None,
        }
    )
    approval = dict(scoped.get("approval") or {})
    approval.update({"required": True, "role": approval.get("role") or "值班工长"})
    scoped["approval"] = approval
    scoped["operator_confirm_required"] = True
    return scoped


def _current_timestamp_validation(context: dict[str, Any]) -> tuple[list[str], list[str], datetime | None]:
    value = context.get("P_blast_cold_timestamp") or context.get("current_values_timestamp")
    current_ts = _as_datetime(value)
    diagnosis_ts = _as_datetime(context.get("recommendation_diagnosis_timestamp"))
    missing: list[str] = []
    reasons: list[str] = []
    if current_ts is None:
        missing.append("current_values_timestamp")
        reasons.append("当前测点时间戳缺失或格式无效")
    elif diagnosis_ts is not None and diagnosis_ts - current_ts > timedelta(minutes=MAX_CURRENT_LAG_MINUTES):
        missing.append("current_values_timestamp")
        reasons.append(f"当前测点数据相对诊断时刻滞后超过{MAX_CURRENT_LAG_MINUTES}分钟")
    return missing, reasons, current_ts


def _pressure_data_validation(
    context: dict[str, Any], current: float | None
) -> tuple[list[str], list[str]]:
    missing, reasons, current_ts = _current_timestamp_validation(context)
    if current is None:
        missing.append("P_blast_cold")
        reasons.append("当前冷风压力缺失或不是有限数值")

    p25 = _finite(context.get("pressure_baseline_p25"))
    p75 = _finite(context.get("pressure_baseline_p75"))
    coverage = _finite(context.get("pressure_baseline_coverage_ratio"))
    sample_count = _finite(context.get("pressure_baseline_sample_count"))
    baseline_day = _as_datetime(context.get("pressure_baseline_day"))
    baseline_updated_at = _as_datetime(context.get("pressure_baseline_updated_at"))
    reference_ts = _as_datetime(context.get("recommendation_diagnosis_timestamp")) or current_ts

    if p25 is None:
        missing.append("pressure_baseline_p25")
    if p75 is None:
        missing.append("pressure_baseline_p75")
    if p25 is not None and p75 is not None and p25 >= p75:
        missing.extend(["pressure_baseline_p25", "pressure_baseline_p75"])
        reasons.append("30天压力基线必须满足P25小于P75")
    if coverage is None or coverage < MIN_BASELINE_COVERAGE:
        missing.append("pressure_baseline_coverage_ratio")
        reasons.append(f"30天压力基线覆盖率必须不低于{MIN_BASELINE_COVERAGE:.0%}")
    if sample_count is None or sample_count <= 0:
        missing.append("pressure_baseline_sample_count")
        reasons.append("30天压力基线样本数缺失或无效")
    if baseline_day is None:
        missing.append("pressure_baseline_day")
        reasons.append("30天压力基线日期缺失或格式无效")
    elif reference_ts is not None:
        age_days = (reference_ts.date() - baseline_day.date()).days
        if age_days < 0 or age_days > MAX_BASELINE_AGE_DAYS:
            missing.append("pressure_baseline_day")
            reasons.append("30天压力基线已过期或晚于诊断时刻")
    if baseline_updated_at is None:
        missing.append("pressure_baseline_updated_at")
        reasons.append("30天压力基线更新时间缺失或格式无效")
    elif reference_ts is not None and baseline_updated_at > reference_ts + timedelta(minutes=5):
        missing.append("pressure_baseline_updated_at")
        reasons.append("30天压力基线更新时间晚于诊断时刻，时间口径不一致")
    return list(dict.fromkeys(missing)), list(dict.fromkeys(reasons))


def _mark_needs_data(
    scoped: dict[str, Any], missing: list[str], reasons: list[str]
) -> dict[str, Any]:
    scoped["status"] = "needs_data"
    scoped["missing_inputs"] = list(dict.fromkeys((scoped.get("missing_inputs") or []) + missing))
    scoped["needs_data_reasons"] = list(dict.fromkeys(reasons))
    scoped["delta"] = None
    scoped["recommended_change"] = None
    scoped["recommended_target"] = None
    return scoped


def _mark_blocked(scoped: dict[str, Any], reason: str) -> dict[str, Any]:
    scoped["status"] = "blocked"
    scoped["blocking_reasons"] = _append_unique(scoped.get("blocking_reasons") or [], reason)
    scoped["delta"] = None
    scoped["recommended_change"] = None
    scoped["recommended_target"] = None
    return scoped


def _set_delta(
    scoped: dict[str, Any], *, current: float, target: float, standard_step: float, basis: str
) -> dict[str, Any]:
    target = round(target, 3)
    change = round(target - current, 3)
    amount = round(abs(change), 3)
    scoped["recommended_change"] = change
    scoped["recommended_target"] = target
    scoped["step_tier"]["clamped"] = amount + 1e-9 < standard_step
    scoped["delta"] = {
        "direction": "增加" if change > 0 else "减少" if change < 0 else "保持",
        "min": amount,
        "max": amount,
        "unit": scoped["unit"],
        "current": current,
        "target_min": target,
        "target_max": target,
        "signed_change": change,
        "standard_step": standard_step,
        "clamped": scoped["step_tier"]["clamped"],
        "basis": basis,
    }
    return scoped


def _pressure_action(
    action: dict[str, Any], context: dict[str, Any], direction: str, score: object
) -> dict[str, Any]:
    scoped = _base_action_contract(action, context, "P_blast_cold", direction, score)
    current = scoped["current_value"]
    missing, reasons = _pressure_data_validation(context, current)
    if missing or scoped.get("status") == "needs_data":
        if scoped.get("blocking_reasons"):
            scoped["deferred_blocking_reasons"] = list(scoped["blocking_reasons"])
            scoped["blocking_reasons"] = []
        return _mark_needs_data(scoped, missing, reasons)
    if scoped.get("status") == "blocked":
        return scoped

    limits = scoped["limit_snapshot"]
    p25 = float(limits["normal_q1"])
    p75 = float(limits["normal_q3"])
    step = float(scoped["step_tier"]["standard_step"])
    effective_source = context.get("current_values_timestamp") or context.get("recommendation_diagnosis_timestamp")
    scoped["effective_at"] = _iso(effective_source)

    if direction == "increase":
        if current >= p75:
            return _mark_blocked(scoped, "当前冷风压力已达到或超过30天Q3上边界，禁止继续加压")
        target = min(current + step, p75)
        boundary_basis = "动态30天Q3加压上限"
    else:
        if current <= PRESSURE_HARD_MIN_KPA:
            return _mark_blocked(scoped, "当前冷风压力已达到或低于400kPa硬下限，禁止继续减压")
        target = max(current - step, PRESSURE_HARD_MIN_KPA)
        boundary_basis = "400kPa冷风压力硬下限"

    _set_delta(
        scoped,
        current=current,
        target=target,
        standard_step=step,
        basis=f"按炉况分数采用{step:g}kPa标准步长；{boundary_basis}；Q1仅用于正常区间展示",
    )
    scoped["trigger_evidence"] = list(scoped.get("trigger_evidence") or []) + [
        {"field": "P_blast_cold", "operator": "observed", "actual": current, "expected": target, "source": "one_minute_values"},
        {"field": "pressure_step", "operator": "severity_tier", "actual": step, "expected": step, "source": "foreman_dual_control.v2"},
        {"field": "pressure_baseline_p25", "operator": "normal_lower", "actual": p25, "expected": p25, "source": "daily_baselines"},
        {"field": "pressure_baseline_p75", "operator": "increase_upper", "actual": p75, "expected": p75, "source": "daily_baselines"},
    ]
    return scoped


def _coal_action(
    action: dict[str, Any], context: dict[str, Any], direction: str, score: object
) -> dict[str, Any]:
    scoped = _base_action_contract(action, context, "PCI_set", direction, score)
    current = scoped["current_value"]
    missing, reasons, current_ts = _current_timestamp_validation(context)
    if current is None:
        missing.append("PCI_set")
        reasons.append("当前喷煤设定缺失或不是有限数值")
    if missing or scoped.get("status") == "needs_data":
        if scoped.get("blocking_reasons"):
            scoped["deferred_blocking_reasons"] = list(scoped["blocking_reasons"])
            scoped["blocking_reasons"] = []
        return _mark_needs_data(scoped, missing, reasons)
    if scoped.get("status") == "blocked":
        return scoped

    diagnosis_ts = context.get("recommendation_diagnosis_timestamp") or current_ts
    step = float(scoped["step_tier"]["standard_step"])

    if direction == "stop":
        if current <= PCI_EMERGENCY_MIN_TPH:
            return _mark_blocked(scoped, "当前喷煤设定已为0t/h，无需重复停煤")
        scoped["effective_at"] = _iso(diagnosis_ts)
        scoped["status"] = "manual_confirm"
        scoped["manual_confirmation_reasons"] = ["严重异常停煤必须由值班工长立即确认并通知喷吹站"]
        _set_delta(
            scoped,
            current=current,
            target=PCI_EMERGENCY_MIN_TPH,
            standard_step=current,
            basis="三规二制严重失常停煤条款；紧急目标为0t/h，不受普通10t/h下限约束",
        )
        scoped["step_tier"] = {
            "severity": scoped["step_tier"]["severity"],
            "standard_step": current,
            "unit": "t/h",
            "clamped": False,
            "mode": "emergency_stop",
        }
        return scoped

    scoped["effective_at"] = _next_full_hour(diagnosis_ts)
    if current == 0:
        scoped["status"] = "manual_confirm"
        scoped["manual_confirmation_reasons"] = ["当前处于停煤状态，恢复喷煤需专项确认，不能自动套用普通步长"]
        return scoped
    if 0 < current < PCI_NORMAL_MIN_TPH:
        scoped["status"] = "manual_confirm"
        scoped["manual_confirmation_reasons"] = ["当前喷煤设定低于10t/h正常下限，属于过渡状态，需人工确认后再调整"]
        return scoped

    if direction == "increase":
        if current >= PCI_MAX_TPH:
            return _mark_blocked(scoped, "当前喷煤设定已达到45t/h上限，禁止继续增煤")
        target = min(current + step, PCI_MAX_TPH)
        boundary_basis = "45t/h喷煤设定上限"
    else:
        if current <= PCI_NORMAL_MIN_TPH:
            return _mark_blocked(scoped, "当前喷煤设定已达到10t/h普通下限，禁止继续普通减煤")
        target = max(current - step, PCI_NORMAL_MIN_TPH)
        boundary_basis = "10t/h普通喷煤设定下限"

    _set_delta(
        scoped,
        current=current,
        target=target,
        standard_step=step,
        basis=f"按炉况分数采用{step:g}t/h标准步长；{boundary_basis}；普通建议在下一个整点生效",
    )
    scoped["trigger_evidence"] = list(scoped.get("trigger_evidence") or []) + [
        {"field": "PCI_set", "operator": "observed", "actual": current, "expected": target, "source": "one_minute_values"},
        {"field": "pci_step", "operator": "severity_tier", "actual": step, "expected": step, "source": "foreman_dual_control.v2"},
    ]
    return scoped


def _hold_action(
    variable: str,
    context: dict[str, Any],
    score: object,
    condition_label: str | None,
) -> dict[str, Any]:
    label = "冷风压力" if variable == "P_blast_cold" else "喷煤设定"
    definition = {
        "id": f"FOREMAN-HOLD-{variable.upper()}",
        "scheme": "integrated",
        "source_document": "docs/冀钢炼铁三规二制.md",
        "source_refs": ["5.1.8.1"],
        "name": f"保持{label}不动",
        "user_facing_text": f"当前炉况矩阵不授权调整{label}，保持现有设定并继续观察",
        "required_inputs": [variable],
        "preconditions": [f"当前炉况的双变量动作矩阵规定{label}保持不动"],
        "sequence_rank": 90,
        "sequence_group": "integrated",
        "legacy_stage": "followup",
        "observation_window": {
            "min_minutes": 15,
            "max_minutes": 60,
            "basis": "持续观察炉况诊断、压力制度、透气性和煤气利用率",
        },
        "approval": {
            "required": True,
            "role": "值班工长",
            "kind": "read_only_hold",
        },
    }
    raw = build_action(
        definition,
        status="eligible",
        trigger_evidence=[
            {
                "field": "main_label",
                "operator": "matrix_hold",
                "actual": condition_label,
                "expected": condition_label,
                "source": "foreman_dual_control.v2",
            }
        ],
        precondition_states=[True],
    )
    scoped = _base_action_contract(raw, context, variable, "hold", score)
    current = scoped["current_value"]
    if variable == "P_blast_cold":
        missing, reasons = _pressure_data_validation(context, current)
    else:
        missing, reasons, _ = _current_timestamp_validation(context)
        if current is None:
            missing.append("PCI_set")
            reasons.append("当前喷煤设定缺失或不是有限数值")
    if missing:
        return _mark_needs_data(scoped, missing, reasons)

    scoped["effective_at"] = _iso(
        context.get("current_values_timestamp")
        or context.get("recommendation_diagnosis_timestamp")
    )
    _set_delta(
        scoped,
        current=current,
        target=current,
        standard_step=0.0,
        basis=f"八类炉况双变量矩阵规定{label}保持不动；不生成设备控制指令",
    )
    scoped["step_tier"] = {
        "severity": _severity_step(score, variable)["severity"],
        "standard_step": 0.0,
        "unit": scoped["unit"],
        "clamped": False,
        "mode": "hold",
    }
    return scoped


def _quantified_action(
    action: dict[str, Any], context: dict[str, Any], variable: str, direction: str, score: object
) -> dict[str, Any]:
    if variable == "P_blast_cold":
        return _pressure_action(action, context, direction, score)
    return _coal_action(action, context, direction, score)


def _resolve_pressure_coal_conflict(actions: list[dict[str, Any]]) -> None:
    pressure_reduction = any(
        action.get("control_variable") == "P_blast_cold"
        and action.get("adjustment_direction") == "decrease"
        and action.get("status") in {"eligible", "manual_confirm"}
        for action in actions
    )
    if not pressure_reduction:
        return
    for action in actions:
        if (
            action.get("control_variable") == "PCI_set"
            and action.get("adjustment_direction") == "increase"
            and action.get("status") in {"eligible", "manual_confirm"}
        ):
            _mark_blocked(action, "当前处于减风降压阶段，不具备增加喷煤资格")


def scope_recommendation(
    recommendation: dict[str, Any],
    context: dict[str, Any],
    score: object | None = None,
    condition_label: str | None = None,
) -> dict[str, Any]:
    """Keep only P_blast_cold/PCI_set actions while preserving safety warnings."""
    scoped = copy.deepcopy(recommendation)
    original_actions = list(scoped.get("actions") or [])
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    score = context.get("diagnosis_main_score") if score is None else score
    for action in original_actions:
        mapping = ACTION_CONTROL_MAP.get(str(action.get("id")))
        if not mapping:
            suppressed.append(
                {
                    "id": action.get("id"),
                    "name": action.get("name"),
                    "status": action.get("status"),
                    "reason": "当前工长建议范围仅开放冷风压力和喷煤设定",
                }
            )
            continue
        kept.append(_quantified_action(action, context, *mapping, score))

    present_variables = {str(action.get("control_variable")) for action in kept}
    for variable in ALLOWED_CONTROL_VARIABLES:
        if variable not in present_variables:
            kept.append(_hold_action(variable, context, score, condition_label))

    _resolve_pressure_coal_conflict(kept)
    scoped["actions"] = kept
    scoped["control_scope"] = {
        "schema_version": SCOPE_VERSION,
        "mode": "foreman_dual_control_only",
        "adjustable_variables": list(ALLOWED_CONTROL_VARIABLES),
        "evidence_only_variables": ["Q_blast"],
        "held_variables": ["T_blast", "O2_rate", "Q_O2", "coke_load", "burden_distribution", "basicity"],
        "suppressed_action_count": len(suppressed),
        "suppressed_actions": suppressed,
        "safety_warnings_preserved": True,
        "read_only": True,
    }
    suffix = "当前仅向工长提供冷风压力和喷煤设定的定量建议；冷风流量仅作证据，其他可调变量保持不动。"
    scoped["explanation"] = "；".join(
        filter(None, [str(scoped.get("explanation") or "").strip("；"), suffix])
    )
    return _FORMATTER.format(scoped)


def scope_bundle(
    bundle: dict[str, Any], context: dict[str, Any], engine_version: str
) -> dict[str, Any]:
    """Apply the same dual-control contract to active and hypothetical plans."""
    scoped = copy.deepcopy(bundle)
    conditions: list[dict[str, Any]] = []
    active_plan: dict[str, Any] | None = None
    for item in scoped.get("conditions") or []:
        condition = copy.deepcopy(item)
        recommendation = scope_recommendation(
            condition.get("recommendation") or {},
            context,
            condition.get("score"),
            str(condition.get("label") or ""),
        )
        recommendation.setdefault("engine_meta", {})["version"] = engine_version
        condition["recommendation"] = recommendation
        condition["action_count"] = len(recommendation.get("actions") or [])
        condition["status_counts"] = dict(recommendation.get("action_status_counts") or {})
        conditions.append(condition)
        if condition.get("scope") == "active":
            active_plan = recommendation
    scoped["conditions"] = conditions
    scoped["active_plan"] = active_plan or scope_recommendation(
        scoped.get("active_plan") or {},
        context,
        context.get("diagnosis_main_score"),
        str((scoped.get("active_plan") or {}).get("primary_condition") or ""),
    )
    scoped.setdefault("engine_meta", {})["version"] = engine_version
    scoped["control_scope"] = dict(scoped["active_plan"].get("control_scope") or {})
    return scoped
