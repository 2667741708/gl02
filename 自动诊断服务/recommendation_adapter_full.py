"""把数据库炉况诊断适配为完整调控结论。

对应需求：REQ-OPT-FULL-ENGINE-20260715、REQ-THREE-RULES-RECOMMENDATION-ALIGNMENT-20260804。
该模块只生成只读建议，不执行任何生产控制写入。
"""

from __future__ import annotations

import copy
import hashlib
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE_DIR = PROJECT_ROOT / "调控结论生成引擎"
ENGINE_DIR = Path(os.getenv("BF_RECOMMENDATION_ENGINE_DIR", str(DEFAULT_ENGINE_DIR))).resolve()
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from recommendation.core import RecommendationEngine  # noqa: E402


ENGINE_NAME = "blast_furnace_recommendation_engine"
ENGINE_VERSION = "v5-three-rules-two-systems"
POLICY_PATH = ENGINE_DIR / "policy" / "three_rules_two_systems.yaml"
POLICY_SHA256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest().upper()
_ENGINE = RecommendationEngine()

DIAGNOSIS_LABELS = (
    "normal",
    "lowline",
    "edge",
    "center",
    "channel",
    "cold",
    "hot",
    "column",
)
DIAGNOSIS_DISPLAY_NAMES = {
    "normal": "正常顺行",
    "lowline": "低料线",
    "edge": "边缘发展",
    "center": "中心发展",
    "channel": "管道行程",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "column": "悬料",
}


RECOMMENDATION_CONTEXT_FIELDS = {
    # 28个核心变量及建议引擎直接使用的实时量
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "GasUtil", "TFT", "T_blast", "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D",
    "Q_blast", "P_blast_cold", "P_blast", "O2_rate", "Q_O2",
    "PI", "DP_upper", "DP_lower", "DP_total",
    "L", "L_south", "L_north", "PCI_rate", "PCI_set", "T_taphole_1", "T_taphole_2",
    # 现场配置、人工事件、布料、负荷和炉次化验；缺失时由策略层明确返回 needs_data
    "approved_best_blast", "approved_dp_limit", "approved_tft_limit", "blast_stable_flag",
    "hot_state_sufficient_flag", "slag_iron_drained_flag", "oxygen_coal_coordinated_flag",
    "coal_ash_pct", "anthracite_200mesh_pct", "coal_moisture_pct", "coal_analysis_current_flag",
    "serious_abnormal_flag", "serious_cold_flag", "blast_reduced_flag", "pressure_mode",
    "unsmooth_condition_flag", "burden_surface_confirmed_flag", "serious_channel_or_bias_flag",
    "top_water_stopped_flag", "lowline_duration_minutes", "lowline_depth", "post_slip_line_depth",
    "coke_load_current", "coke_load_target", "other_adjustments_exhausted_flag",
    "net_coke_target", "net_coke_plan_approved_flag", "ore_restore_plan",
    "ore_total_rings", "ore_edge_rings_current", "ore_edge_rings_target",
    "coke_total_rings", "coke_edge_rings_current", "coke_edge_rings_target",
    "gamma_ore_current", "gamma_ore_target", "gamma_coke_current", "gamma_coke_target",
    "chute_direction", "slag_r2_actual", "burden_r2_theoretical", "sample_batch_id",
    "sample_published_at", "basicity_recalc_flag", "burden_mix_changed_flag",
    "sulfur_abnormal_flag", "long_stop_plan_flag", "start_stop_plan_flag",
    "hearth_accumulation_flag", "high_pressure_flag", "probe_stall_flag",
    "tuyere_abnormal_flag", "TRT_running_flag", "Ttop_max15", "T_top_max15",
    "T_top_effective", "DeltaL", "L_current",
}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


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


def build_features_snapshot(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """兼容数据库 ``feature_snapshot`` 与历史引擎 ``features_snapshot`` 字段。"""
    current = current_values or {}
    stored = diagnosis.get("features_snapshot") or diagnosis.get("feature_snapshot") or {}
    features = dict(stored) if isinstance(stored, dict) else {}
    for field in RECOMMENDATION_CONTEXT_FIELDS:
        if field not in features and field in current:
            features[field] = current[field]

    top_candidates = [
        features.get("Ttop_max15"),
        features.get("T_top_max15"),
        features.get("T_top_effective"),
        features.get("T_top"),
        current.get("T_top"),
        current.get("T_top_A"),
        current.get("T_top_B"),
        current.get("T_top_C"),
        current.get("T_top_D"),
    ]
    top_values = [number for number in (_finite(value) for value in top_candidates) if number is not None]
    p_top = _finite(features.get("P_top"))
    line = _finite(features.get("L_current"))
    if line is None:
        line = _finite(features.get("L"))

    features["high_pressure_flag"] = int(
        _as_bool(features.get("high_pressure_flag"))
        or (p_top is not None and p_top > 200.0)
    )
    features["probe_stall_flag"] = int(_as_bool(features.get("probe_stall_flag", 0)))
    features["tuyere_abnormal_flag"] = int(_as_bool(features.get("tuyere_abnormal_flag", 0)))
    features["TRT_running_flag"] = int(_as_bool(features.get("TRT_running_flag", 0)))
    if top_values:
        features["Ttop_max15"] = max(top_values)
    if "DeltaL" not in features and line is not None:
        features["DeltaL"] = line - 1.5
    return features


def _normalized_scores(diagnosis: dict[str, Any]) -> dict[str, float]:
    """Return the stable eight-label score map used by the recommendation matrix."""
    source = diagnosis.get("raw_scores") or diagnosis.get("raw") or diagnosis.get("scores") or {}
    source = source if isinstance(source, dict) else {}
    scores: dict[str, float] = {}
    for label in DIAGNOSIS_LABELS:
        score = _finite(source.get(label))
        scores[label] = score if score is not None else 0.0
    main_label = str(diagnosis.get("main_label") or "normal")
    main_score = _finite(diagnosis.get("main_score"))
    if main_label in scores and main_score is not None:
        scores[main_label] = main_score
    return scores


def _with_engine_meta(recommendation: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Attach the read-only engine provenance shared by active and hypothetical plans."""
    recommendation["engine_meta"] = {
        "name": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "schema_version": recommendation.get("schema_version"),
        "source": source,
        "read_only": True,
        "policy_source": "调控结论生成引擎/policy/three_rules_two_systems.yaml",
        "policy_sha256": POLICY_SHA256,
    }
    return recommendation


def _status_counts(actions: object) -> dict[str, int]:
    counts = {"eligible": 0, "blocked": 0, "needs_data": 0, "manual_confirm": 0}
    for action in actions if isinstance(actions, list) else []:
        status = action.get("status") if isinstance(action, dict) else None
        if status in counts:
            counts[status] += 1
    return counts


def generate_recommendation_bundle(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Generate the active main/secondary plan and eight read-only condition plans.

    ``active_plan`` is the only plan resolved with the current secondary condition and is
    therefore the current operational reference.  Every other condition recommendation is
    explicitly marked ``hypothetical`` and must not be merged into the active action queue.

    Corresponding requirement:
    REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805.
    """
    normalized = dict(diagnosis)
    normalized["features_snapshot"] = build_features_snapshot(normalized, current_values)
    scores = _normalized_scores(normalized)
    main_label = str(normalized.get("main_label") or "normal")
    if main_label not in DIAGNOSIS_LABELS:
        main_label = "normal"
    secondary_label = normalized.get("secondary_label")
    if secondary_label not in DIAGNOSIS_LABELS or secondary_label == main_label:
        secondary_label = None

    normalized["main_label"] = main_label
    normalized["main_score"] = scores[main_label]
    normalized["secondary_label"] = secondary_label
    normalized["raw_scores"] = scores
    active_plan = _with_engine_meta(
        _ENGINE.generate(copy.deepcopy(normalized)), source="diagnosis_snapshot"
    )

    ordered_labels = [main_label]
    if secondary_label:
        ordered_labels.append(str(secondary_label))
    ordered_labels.extend(
        label
        for label in sorted(
            DIAGNOSIS_LABELS,
            key=lambda key: (-scores[key], DIAGNOSIS_LABELS.index(key)),
        )
        if label not in ordered_labels
    )

    conditions: list[dict[str, Any]] = []
    for label in ordered_labels:
        if label == main_label:
            recommendation = active_plan
            role = "main"
            scope = "active"
        else:
            candidate = copy.deepcopy(normalized)
            candidate["main_label"] = label
            candidate["main_score"] = scores[label]
            candidate["secondary_label"] = None
            recommendation = _with_engine_meta(
                _ENGINE.generate(candidate), source="condition_hypothesis"
            )
            role = "secondary" if label == secondary_label else "watch"
            scope = "supporting" if label == secondary_label else "hypothetical"
        actions = recommendation.get("actions") or []
        conditions.append(
            {
                "label": label,
                "display_name": DIAGNOSIS_DISPLAY_NAMES[label],
                "score": scores[label],
                "role": role,
                "scope": scope,
                "read_only": True,
                "action_count": len(actions),
                "status_counts": _status_counts(actions),
                "recommendation": recommendation,
            }
        )

    return {
        "schema_version": "multi_condition_recommendation.v1",
        "timestamp": active_plan.get("timestamp"),
        "main_label": main_label,
        "secondary_label": secondary_label,
        "active_plan": active_plan,
        "conditions": conditions,
        "engine_meta": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "schema_version": active_plan.get("schema_version"),
            "policy_source": "调控结论生成引擎/policy/three_rules_two_systems.yaml",
            "policy_sha256": POLICY_SHA256,
            "read_only": True,
        },
    }


def generate_recommendation(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """使用完整建议引擎生成结构化建议并附带可审计元数据。"""
    return generate_recommendation_bundle(diagnosis, current_values)["active_plan"]
