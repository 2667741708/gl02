"""把诊断事实映射为三规二制四类调剂动作。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .action_contract import build_action


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "policy"
    / "three_rules_two_systems.yaml"
)


@lru_cache(maxsize=1)
def load_policy_catalog() -> dict[str, Any]:
    """加载 JSON 兼容 YAML；不引入远端运行时的新依赖。"""
    catalog = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    source_document = str(catalog.get("source_document") or "")
    for action_id, definition in catalog.get("actions", {}).items():
        definition["id"] = action_id
        definition["source_document"] = source_document
    return catalog


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "on", "1", "是"}:
            return True
        if normalized in {"false", "no", "n", "off", "0", "否", ""}:
            return False
    number = _finite(value)
    return number == 1.0 if number is not None else False


def _has_value(features: dict[str, Any], field: str) -> bool:
    return field in features and features.get(field) is not None and features.get(field) != ""


def _missing(features: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if not _has_value(features, field)]


def _diagnosis_evidence(diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = [
        {
            "field": "main_label",
            "operator": "equals",
            "actual": diagnosis.get("main_label"),
            "expected": diagnosis.get("main_label"),
            "source": "diagnosis_snapshot",
        }
    ]
    if diagnosis.get("secondary_label"):
        evidence.append(
            {
                "field": "secondary_label",
                "operator": "equals",
                "actual": diagnosis.get("secondary_label"),
                "expected": diagnosis.get("secondary_label"),
                "source": "diagnosis_snapshot",
            }
        )
    score = _finite(diagnosis.get("main_score"))
    if score is not None:
        evidence.append(
            {
                "field": "main_score",
                "operator": "observed",
                "actual": score,
                "expected": None,
                "source": "diagnosis_snapshot",
            }
        )
    return evidence


def _feature_evidence(
    features: dict[str, Any], fields: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "operator": "observed",
            "actual": features[field],
            "expected": None,
            "source": "recommendation_context",
        }
        for field in fields
        if _has_value(features, field)
    ]


def _status_for_action(
    action_id: str,
    definition: dict[str, Any],
    diagnosis: dict[str, Any],
    features: dict[str, Any],
    active_labels: set[str],
) -> tuple[str, list[str], list[str], list[bool | None], list[str]]:
    """返回状态、缺失输入、阻断原因、前置状态和额外证据字段。"""
    required = list(definition.get("required_inputs") or [])
    missing = _missing(features, required)
    blockers: list[str] = []
    states: list[bool | None] = []
    evidence_fields: list[str] = []

    if action_id in {"KEEP-STABLE", "LOW-O2-STABLE-01"}:
        return "eligible", [], [], [True], []

    if action_id == "LOW-TBLAST-UP-06":
        return ("needs_data", missing, [], [True, None], []) if missing else (
            "eligible", [], [], [True, True], ["T_blast"]
        )

    if action_id == "LOW-PCI-UP-02":
        pressure_mode = str(features.get("pressure_mode") or "").lower()
        severe = _as_bool(features.get("serious_abnormal_flag")) or bool(
            active_labels.intersection({"channel", "column"})
        )
        pressure_block = _as_bool(features.get("blast_reduced_flag")) or pressure_mode in {
            "normal_pressure",
            "low_pressure",
            "stopped",
            "常压",
            "低压",
            "休风",
        }
        coal_ash = _finite(features.get("coal_ash_pct"))
        coal_fineness = _finite(features.get("anthracite_200mesh_pct"))
        coal_moisture = _finite(features.get("coal_moisture_pct"))
        if coal_ash is not None and coal_ash > 13.0:
            blockers.append("原煤灰分超过13.0%，不具备增加喷煤的质量资格")
        if coal_fineness is not None and coal_fineness < 75.0:
            blockers.append("无烟煤200目细度低于75%，不具备增加喷煤的质量资格")
        if coal_moisture is not None and coal_moisture >= 1.0:
            blockers.append("煤粉水分不低于1.0%，不具备增加喷煤的质量资格")
        if _has_value(features, "coal_analysis_current_flag") and not _as_bool(
            features.get("coal_analysis_current_flag")
        ):
            blockers.append("煤粉化验已过期或成分稳定性未确认")
        if severe:
            blockers.append("炉况严重失常规则优先，增加喷煤被停止/减少喷煤规则阻断")
        if pressure_block:
            blockers.append("当前处于减风降压、常压、低压或休风阶段，不具备增煤条件")
        if blockers:
            return "blocked", missing, blockers, [True, False, False, False], ["serious_abnormal_flag", "blast_reduced_flag", "pressure_mode", "coal_ash_pct", "anthracite_200mesh_pct", "coal_moisture_pct", "coal_analysis_current_flag"]
        if missing:
            return "needs_data", missing, [], [True, None, True, True], []
        return "eligible", [], [], [True, True, True, True], ["PCI_rate", "coal_ash_pct", "anthracite_200mesh_pct", "coal_moisture_pct", "coal_analysis_current_flag"]

    if action_id == "LOW-O2-DOWN-01":
        if missing:
            return "needs_data", missing, [], [True, None], []
        return "eligible", [], [], [True, None], ["O2_rate"]

    if action_id == "LOW-BLAST-DOWN-02":
        score = _finite(diagnosis.get("main_score")) or 0.0
        severe = _as_bool(features.get("serious_cold_flag")) or score >= 75.0
        if not severe:
            return "blocked", [], ["热制度尚未达到严重下行减压条件，一般情况不主动降低冷风压力"], [False], []
        if missing:
            return "needs_data", missing, [], [True], ["serious_cold_flag"]
        if not _as_bool(features.get("serious_cold_flag")):
            return "manual_confirm", [], [], [True], ["P_blast_cold", "serious_cold_flag"]
        return "eligible", [], [], [True], ["P_blast_cold", "serious_cold_flag"]

    if action_id == "LOAD-DOWN-07":
        if not _as_bool(features.get("other_adjustments_exhausted_flag")):
            missing = list(dict.fromkeys(missing + ["other_adjustments_exhausted_flag"]))
        if missing:
            return "needs_data", missing, [], [None, None], []
        return "manual_confirm", [], [], [True, True], required

    if action_id in {"NET-COKE-01", "NET-COKE-05", "NET-COKE-04", "UP-11"}:
        if missing:
            return "needs_data", missing, [], [None] * len(definition.get("preconditions") or []), []
        return "manual_confirm", [], [], [True] * len(definition.get("preconditions") or []), required

    if action_id == "LOW-BLAST-UP-GATE":
        dp = _finite(features.get("DP_total"))
        dp_limit = _finite(features.get("approved_dp_limit"))
        current = _finite(features.get("P_blast_cold"))
        if _as_bool(features.get("high_pressure_flag")):
            blockers.append("当前为高压运行，增加冷风压力资格被压力制度门禁阻断")
        if active_labels.intersection({"lowline", "channel", "column"}):
            blockers.append("当前伴随低料线、管道或悬料，不具备加压承受条件")
        if _as_bool(features.get("tuyere_abnormal_flag")):
            blockers.append("风口异常，严禁强行恢复或增加冷风压力")
        if dp is not None and dp_limit is not None and dp >= dp_limit:
            blockers.append("当前压差不低于现场批准上限")
        for flag, text in (
            ("blast_stable_flag", "风量、风压未确认平稳"),
            ("hot_state_sufficient_flag", "炉温充沛条件未满足"),
            ("slag_iron_drained_flag", "渣铁出净条件未满足"),
        ):
            if _has_value(features, flag) and not _as_bool(features.get(flag)):
                blockers.append(text)
        if blockers:
            return "blocked", missing, blockers, [False, False], required
        if missing:
            return "needs_data", missing, [], [None, True], required
        return "eligible", [], [], [True, True], required

    if action_id == "LOW-O2-UP-GATE":
        tft = _finite(features.get("TFT"))
        tft_limit = _finite(features.get("approved_tft_limit"))
        if "edge" in active_labels:
            blockers.append("边缘煤气流已发展，富氧会进一步发展边缘，禁止加氧")
        if active_labels.intersection({"channel", "column", "lowline"}):
            blockers.append("当前炉况不顺，不具备加氧条件")
        if tft is not None and tft_limit is not None and tft >= tft_limit:
            blockers.append("理论燃烧温度已达到或超过现场批准上限")
        if _has_value(features, "oxygen_coal_coordinated_flag") and not _as_bool(
            features.get("oxygen_coal_coordinated_flag")
        ):
            blockers.append("富氧与喷煤协同条件未满足")
        if blockers:
            return "blocked", missing, blockers, [False, False, False], required
        if missing:
            return "needs_data", missing, [], [None, True, None], required
        return "eligible", [], [], [True, True, True], required

    if action_id == "LOAD-UP-01":
        if missing:
            return "needs_data", missing, [], [True, None], []
        return "manual_confirm", [], [], [True, True], required

    if action_id in {"LOW-PCI-DOWN-02", "LOW-TBLAST-DOWN-08", "LOW-BLAST-DOWN-05"}:
        if missing:
            return "needs_data", missing, [], [True], []
        return "eligible", [], [], [True], required

    if action_id in {"UP-03", "UP-04", "UP-05", "UP-07"}:
        if missing:
            return "needs_data", missing, [], [True, None, None], []
        return "manual_confirm", [], [], [True, True, True], required

    if action_id == "EDGE-O2-BLOCK":
        return "blocked", [], ["边缘煤气流发展时加氧会进一步发展边缘"], [True], []

    if action_id == "LOW-BLAST-DOWN-04":
        confirmed = bool(active_labels.intersection({"channel", "column"})) or _as_bool(
            features.get("unsmooth_condition_flag")
        )
        center_only = active_labels == {"center"}
        if not confirmed:
            if center_only:
                if missing:
                    return "needs_data", missing, [], [None], []
                return "manual_confirm", [], [], [None], ["unsmooth_condition_confirmation"]
            return "manual_confirm", [], [], [None], ["unsmooth_condition_confirmation"]
        if missing:
            return "needs_data", missing, [], [True], []
        return "eligible", [], [], [True], required

    if action_id == "UP-10":
        if not _has_value(features, "burden_surface_confirmed_flag"):
            return "needs_data", ["burden_surface_confirmed_flag"], [], [None], []
        if not _as_bool(features.get("burden_surface_confirmed_flag")):
            return "blocked", [], ["管道或料面偏斜尚未通过现场复核"], [False], ["burden_surface_confirmed_flag"]
        return "manual_confirm", [], [], [True], ["burden_surface_confirmed_flag"]

    if action_id == "UP-12":
        if _as_bool(features.get("high_pressure_flag")):
            blockers.append("当前为高压运行，禁止直接坐料")
        for flag, text in (
            ("hot_state_sufficient_flag", "炉温充足条件未满足"),
            ("serious_channel_or_bias_flag", "严重管道或偏料条件未满足"),
            ("top_water_stopped_flag", "炉顶打水尚未确认停止"),
        ):
            if _has_value(features, flag) and not _as_bool(features.get(flag)):
                blockers.append(text)
        if blockers:
            return "blocked", missing, blockers, [False] * 4, required
        if missing:
            return "needs_data", missing, [], [None] * 4, []
        return "manual_confirm", [], [], [True] * 4, required

    if action_id == "LOW-PCI-DOWN-05":
        pci = _finite(features.get("PCI_rate"))
        if missing:
            return "needs_data", missing, [], [True, None], []
        if pci is not None and pci <= 0:
            return "blocked", [], ["当前喷煤量已为零，无可继续停止的喷煤量"], [True, True], ["PCI_rate"]
        return "manual_confirm", [], [], [True, None], ["PCI_rate"]

    if action_id == "BASICITY-07":
        if missing:
            return "needs_data", missing, [], [True, None], []
        return "manual_confirm", [], [], [True, True], required

    if action_id.startswith("SAFETY-"):
        return "manual_confirm", [], [], [True] * len(definition.get("preconditions") or []), []

    if missing:
        return "needs_data", missing, [], [None] * len(definition.get("preconditions") or []), []
    return "manual_confirm", [], [], [None] * len(definition.get("preconditions") or []), []


def _basicity_triggered(features: dict[str, Any]) -> bool:
    r2 = _finite(features.get("slag_r2_actual"))
    return any(
        _as_bool(features.get(field))
        for field in (
            "basicity_recalc_flag",
            "burden_mix_changed_flag",
            "sulfur_abnormal_flag",
            "long_stop_plan_flag",
            "start_stop_plan_flag",
            "hearth_accumulation_flag",
        )
    ) or (r2 is not None and not 1.15 <= r2 <= 1.22)


def _materialize(
    action_id: str,
    diagnosis: dict[str, Any],
    features: dict[str, Any],
    active_labels: set[str],
) -> dict[str, Any]:
    catalog = load_policy_catalog()
    definition = catalog["actions"][action_id]
    status, missing, blockers, states, evidence_fields = _status_for_action(
        action_id, definition, diagnosis, features, active_labels
    )
    evidence = _diagnosis_evidence(diagnosis) + _feature_evidence(features, evidence_fields)
    return build_action(
        definition,
        status=status,
        trigger_evidence=evidence,
        missing_inputs=missing,
        blocking_reasons=blockers,
        precondition_states=states,
    )


def evaluate_policy_actions(
    diagnosis: dict[str, Any], safety_result: dict[str, Any]
) -> list[dict[str, Any]]:
    """同时评估主、次炉况和独立碱度触发，不再枚举两两组合。"""
    catalog = load_policy_catalog()
    features = diagnosis.get("features_snapshot") or {}
    main_label = str(diagnosis.get("main_label") or "normal")
    secondary_label = diagnosis.get("secondary_label")
    ordered_labels = [main_label]
    if secondary_label and secondary_label != main_label:
        ordered_labels.append(str(secondary_label))
    active_labels = set(ordered_labels)

    action_ids: list[str] = []
    for label in ordered_labels:
        if label == "normal" and len(ordered_labels) > 1:
            continue
        action_ids.extend(catalog.get("label_actions", {}).get(label, []))
    if _basicity_triggered(features):
        action_ids.append("BASICITY-07")
    if (
        "cold" in active_labels
        and _as_bool(features.get("serious_abnormal_flag"))
    ):
        action_ids.append("LOW-PCI-DOWN-05")
    action_ids.extend(safety_result.get("forced_action_ids") or [])

    unique_ids = list(dict.fromkeys(action_ids))
    return [
        _materialize(action_id, diagnosis, features, active_labels)
        for action_id in unique_ids
    ]
