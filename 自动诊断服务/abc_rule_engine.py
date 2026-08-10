"""Controlled A9/B13/C11 rule evaluation and public/admin contracts."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from abc_rule_catalog import CATALOG_VERSION, REQUIREMENT_ID, RULES, RULE_BY_ID, RuleSpec, validate_catalog


SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SERVICE_DIR / "config" / "abc_furnace_rules.v1.json"
PUBLIC_FIELDS = {
    "rule_id", "category", "display_name", "score", "score_available", "status", "confidence", "data_complete",
    "trigger_evidence", "primary_sensors", "missing_sensors", "can_open_detail", "alert_state",
    "observation_window", "approval", "principle", "source_refs", "primary_review", "expanded_review",
    "manual_review", "intervention_order", "safety_event", "triggered_at", "data_age_seconds",
    "candidate_for_b",
    "release_state", "score_released", "blocking_reasons",
    "event_confirmation_state", "event_confirmation_summary", "score_basis",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def g_H(value: float, a: float, b: float) -> float:
    if b <= a:
        raise ValueError("g_H requires b > a")
    return _clip((value - a) / (b - a))


def g_L(value: float, a: float, b: float) -> float:
    if a <= b:
        raise ValueError("g_L requires a > b")
    return _clip((a - value) / (a - b))


def g_A(value: float, a: float, b: float) -> float:
    if b <= a:
        raise ValueError("g_A requires b > a")
    return _clip((abs(value) - a) / (b - a))


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path or DEFAULT_CONFIG_PATH)
    config = json.loads(target.read_text(encoding="utf-8"))
    validate_config(config)
    config["config_path"] = str(target)
    config["config_hash"] = _json_hash({k: v for k, v in config.items() if k not in {"config_path", "config_hash"}})
    return config


def validate_config(config: Mapping[str, Any]) -> None:
    validate_catalog()
    required = {"schema_version", "requirement_id", "quality", "score_bands", "term_thresholds", "rules", "release_control"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"ABC configuration missing fields: {sorted(missing)}")
    quality = config["quality"]
    if not 0 < float(quality["minimum_coverage_ratio"]) <= 1:
        raise ValueError("minimum_coverage_ratio must be in (0,1]")
    release = config["release_control"]
    if str(release.get("mode")) not in {"shadow_validation", "score_preview", "published"}:
        raise ValueError("release_control.mode must be shadow_validation, score_preview or published")
    if not isinstance(release.get("scores_visible"), bool) or not isinstance(release.get("alerts_enabled"), bool):
        raise ValueError("release_control score/alert gates must be boolean")
    release_mode = str(release["mode"])
    scores_visible = bool(release["scores_visible"])
    alerts_enabled = bool(release["alerts_enabled"])
    if release_mode == "shadow_validation" and (scores_visible or alerts_enabled):
        raise ValueError("shadow_validation must keep scores and alerts disabled")
    if release_mode == "score_preview" and (not scores_visible or alerts_enabled):
        raise ValueError("score_preview must expose scores while keeping alerts disabled")
    if release_mode == "published" and not scores_visible:
        raise ValueError("published mode must expose scores")
    if float(quality["maximum_age_seconds"]) <= 0:
        raise ValueError("maximum_age_seconds must be positive")
    bands = config["score_bands"]
    if not (bands["A"]["candidate_below"] < bands["A"]["review_below"] <= 100):
        raise ValueError("A score bands are not monotonic")
    if not (0 <= bands["B"]["observe_from"] < bands["B"]["popup_from"] <= bands["B"]["amber_from"] <= bands["B"]["confirm_from"] <= 100):
        raise ValueError("B score bands are not monotonic")
    if not 0 <= bands["C"]["alarm_from"] <= 100:
        raise ValueError("C alarm_from must be 0..100")
    rules = config["rules"]
    if set(rules) != set(RULE_BY_ID):
        raise ValueError("configuration must contain exactly the 33 ABC rule IDs")
    for rule_id, value in rules.items():
        overrides = value.get("weight_overrides", {})
        unknown = set(overrides) - set(RULE_BY_ID[rule_id].terms)
        if unknown:
            raise ValueError(f"unknown normalized factors in {rule_id}: {sorted(unknown)}")
        for number in overrides.values():
            if _finite(number) is None or float(number) < 0:
                raise ValueError(f"invalid weight override for {rule_id}")
        weights = dict(RULE_BY_ID[rule_id].terms)
        weights.update({str(k): float(v) for k, v in overrides.items()})
        if not weights or sum(weights.values()) <= 0:
            raise ValueError(f"rule {rule_id} has no positive weights")
        if abs(sum(weights.values()) - 100.0) > 1e-6:
            raise ValueError(f"rule {rule_id} effective weights must sum to 100")
    for threshold in config["term_thresholds"].values():
        if _finite(threshold.get("a")) is None or _finite(threshold.get("b")) is None or float(threshold["b"]) <= float(threshold["a"]):
            raise ValueError("term threshold requires finite a < b")


def _term_mode(term: str, config: Mapping[str, Any]) -> tuple[str, float, float]:
    thresholds = config.get("term_thresholds", {})
    if term in thresholds:
        item = thresholds[term]
        return str(item.get("mode", "high")), float(item["a"]), float(item["b"])
    name = term.lower()
    if name.startswith("z60_"):
        item = thresholds.get("z60_default", thresholds["default"])
        return str(item.get("mode", "high")), float(item["a"]), float(item["b"])
    if name.startswith("z15std_"):
        item = thresholds.get("z15std_default", thresholds["default"])
        return str(item.get("mode", "high")), float(item["a"]), float(item["b"])
    if "low" in name or name.startswith("neg_"):
        item = thresholds.get("low", thresholds["default"])
    elif "abs" in name or "std" in name or "range" in name:
        item = thresholds.get("absolute", thresholds["default"])
    else:
        item = thresholds["default"]
    return str(item.get("mode", "high")), float(item["a"]), float(item["b"])


def _score_status(spec: RuleSpec, score: float, confidence: float, config: Mapping[str, Any]) -> tuple[str, str]:
    if confidence < float(config["quality"]["minimum_coverage_ratio"]):
        return "needs_data", "needs_data"
    bands = config["score_bands"]
    if spec.category == "A":
        return ("eligible" if score >= bands["A"]["review_below"] else "manual_confirm", "none")
    if spec.category == "B":
        if score < bands["B"]["popup_from"]:
            return "eligible", "observe" if score >= bands["B"]["observe_from"] else "none"
        if score >= bands["B"]["confirm_from"]:
            return "manual_confirm", "deep_amber"
        if score >= bands["B"]["amber_from"]:
            return "manual_confirm", "amber"
        return "manual_confirm", "yellow"
    if score >= bands["C"]["alarm_from"]:
        return "manual_confirm", "red"
    return "eligible", "none"


def _c_event_confirmation(rule_id: str, features: Mapping[str, Any]) -> tuple[float | None, dict[str, float | None]]:
    """Return an independent-evidence gate for the highest-consequence C events.

    The document formula remains fully auditable as ``raw_formula_score``.  The
    operator-facing event score is gated because maxima, range and slope from
    the same furnace-body points are correlated evidence, not three independent
    confirmations of a severe physical event.
    """
    values = {
        "body_concurrence": _finite(features.get("BodyHotConcurrence")),
        "body_escalation": _finite(features.get("BodyHotEscalation")),
        "cooling_concurrence": _finite(features.get("CoolingConcurrence")),
        "top_temperature": _finite(features.get("TopTempRange")),
        "top_pressure": _finite(features.get("TopPressRange")),
        "drainage": _finite(features.get("DrainProxy")),
    }
    if rule_id == "C4":
        required = (values["cooling_concurrence"], values["body_concurrence"])
        gate = min(required) if all(value is not None for value in required) else None
    elif rule_id == "C5":
        required = (values["cooling_concurrence"], values["body_concurrence"], values["body_escalation"])
        gate = min(required) if all(value is not None for value in required) else None
    elif rule_id == "C7":
        body = values["body_concurrence"]
        corroboration_parts = [
            values["cooling_concurrence"], values["top_temperature"],
            values["top_pressure"], values["drainage"],
        ]
        available = [value for value in corroboration_parts if value is not None]
        gate = min(body, max(available)) if body is not None and available else None
    else:
        return 1.0, values
    return (_clip(gate) if gate is not None else None), values


def evaluate_rule(spec: RuleSpec, features: Mapping[str, Any], quality: Mapping[str, Any], config: Mapping[str, Any], *, timestamp: Any = None) -> dict[str, Any]:
    overrides = config["rules"].get(spec.rule_id, {}).get("weight_overrides", {})
    weights = dict(spec.terms)
    weights.update({str(key): float(value) for key, value in overrides.items()})
    contributions: list[dict[str, Any]] = []
    missing: list[str] = []
    available_weight = 0.0
    total_weight = sum(weights.values())
    coverage_value = _finite(quality.get("coverage_ratio"))
    coverage_ok = coverage_value is not None and coverage_value >= float(config["quality"]["minimum_coverage_ratio"])
    age = _finite(quality.get("data_age_seconds"))
    age_ok = age is not None and age <= float(config["quality"]["maximum_age_seconds"])
    factor_audit = quality.get("factor_audit", {}) if isinstance(quality.get("factor_audit", {}), Mapping) else {}
    threshold_snapshots: dict[str, Any] = {}
    for term, weight in weights.items():
        value = _finite(features.get(term))
        term_quality = quality.get(term, {}) if isinstance(quality.get(term, {}), Mapping) else {}
        available = value is not None and bool(term_quality.get("available", True)) and coverage_ok and age_ok
        if not available:
            missing.append(term)
            continue
        # Catalog v2 terms are calibrated 0..1 factors created by the feature
        # builder.  Applying a second generic threshold would distort the
        # document formula and previously caused physical values to saturate.
        normalized = _clip(value)
        available_weight += float(weight)
        audit = factor_audit.get(term, {}) if isinstance(factor_audit.get(term, {}), Mapping) else {}
        threshold_snapshot = audit.get("effective_thresholds") or {
            "factor_stage": {"mode": "precalibrated_0_1", "minimum": 0.0, "maximum": 1.0, "second_threshold_applied": False}
        }
        threshold_snapshots[term] = threshold_snapshot
        contributions.append({
            "feature_key": term,
            "weight": float(weight),
            "raw_value": value,
            "normalized_value": normalized,
            "contribution": normalized * float(weight),
            "formula": audit.get("formula"),
            "source_features": audit.get("source_features", {}),
            "source_values": audit.get("source_values", {}),
            "baseline_snapshot": audit.get("baseline_snapshot", {}),
            "effective_thresholds": threshold_snapshot,
        })
    confidence = available_weight / total_weight if total_weight else 0.0
    risk_score = 100.0 * sum(item["contribution"] for item in contributions) / available_weight if available_weight else 0.0
    raw_formula_score = 100.0 - risk_score if spec.direction == "maintenance" else risk_score
    score = raw_formula_score
    event_confirmation: float | None = 1.0
    event_confirmation_sources: dict[str, float | None] = {}
    event_confirmation_state = "not_applicable"
    event_confirmation_summary = "按规则证据计算"
    score_basis = "document_formula"
    if spec.rule_id in {"C4", "C5", "C7"}:
        event_confirmation, event_confirmation_sources = _c_event_confirmation(spec.rule_id, features)
        score_basis = "independent_evidence_gated"
        if event_confirmation is None:
            event_confirmation_state = "needs_data"
            event_confirmation_summary = "严重事件交叉确认所需数据不足，当前不能形成事件分数"
            score = 0.0
            confidence = 0.0
            missing.append(f"{spec.rule_id}_EventConfirmation")
        else:
            score = raw_formula_score * event_confirmation
            if event_confirmation >= 0.7:
                event_confirmation_state = "confirmed"
                event_confirmation_summary = "炉体与独立工艺系统证据形成交叉确认，请立即人工复核"
            elif event_confirmation > 0:
                event_confirmation_state = "partial"
                event_confirmation_summary = "存在单项或同源趋势，但独立证据尚未形成完整交叉确认"
            else:
                event_confirmation_state = "not_confirmed"
                event_confirmation_summary = "当前仅见单项或同源偏离，未形成严重事件的独立交叉确认"
        threshold_snapshots["__event_confirmation__"] = {
            "mode": "independent_evidence_gate",
            "raw_formula_score": raw_formula_score,
            "gate_value": event_confirmation,
            "source_values": event_confirmation_sources,
            "operator_score": score,
        }
    status, alert_state = _score_status(spec, score, confidence, config)
    release = config.get("release_control") or {"mode": "shadow_validation", "scores_visible": False, "alerts_enabled": False, "reason": "发布门禁配置缺失"}
    score_released = bool(release.get("scores_visible", True)) and str(release.get("mode")) in {"score_preview", "published"}
    if not bool(release.get("alerts_enabled", True)):
        alert_state = "none"
    blocking_reasons: list[str] = []
    if not score_released:
        if status != "needs_data":
            status = "blocked"
        alert_state = "none"
        blocking_reasons.append(str(release.get("reason") or "规则处于影子核验阶段，暂不发布分数"))
    return {
        "rule_id": spec.rule_id,
        "category": spec.category,
        "display_name": spec.display_name,
        "direction": spec.direction,
        "score": round(score, 4),
        "raw_formula_score": round(raw_formula_score, 4),
        "risk_score": round(risk_score, 4),
        "confidence": round(confidence, 4),
        "status": status,
        "alert_state": alert_state,
        "data_complete": not missing,
        "missing_features": missing,
        "formula_terms": [item["feature_key"] for item in contributions],
        "weights": weights,
        "thresholds": threshold_snapshots,
        "contributions": contributions,
        # Production evidence is deliberately phrased at the process level.
        # Internal feature keys and term contributions remain in the protected
        # evaluation item and must never be serialized to the operator page.
        "trigger_evidence": (
            [event_confirmation_summary]
            if spec.rule_id in {"C4", "C5", "C7"}
            else [
                f"{spec.display_name}相关传感器趋势支持进一步复核"
                for item in contributions
                if item["normalized_value"] >= 0.5
            ][:1]
        ),
        "primary_sensors": list(spec.primary_sensors),
        "missing_sensors": [sensor for sensor in spec.primary_sensors if _finite(features.get(sensor)) is None],
        "can_open_detail": True,
        "observation_window": spec.observation_window,
        "approval": spec.approval,
        "principle": spec.principle,
        "source_refs": list(spec.source_refs),
        "primary_review": list(spec.primary_review),
        "expanded_review": list(spec.expanded_review),
        "manual_review": list(spec.manual_review),
        "intervention_order": list(spec.intervention_order),
        "safety_event": spec.safety_event,
        "candidate_for_b": spec.category == "A" and score < float(config["score_bands"]["A"]["candidate_below"]),
        "triggered_at": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "data_age_seconds": age,
        "release_state": str(release.get("mode") or "published"),
        "score_released": score_released,
        "blocking_reasons": blocking_reasons,
        "event_confirmation": event_confirmation,
        "event_confirmation_sources": event_confirmation_sources,
        "event_confirmation_state": event_confirmation_state,
        "event_confirmation_summary": event_confirmation_summary,
        "score_basis": score_basis,
    }


def evaluate(features: Mapping[str, Any], *, quality: Mapping[str, Any] | None = None, timestamp: Any = None, config: Mapping[str, Any] | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    active_config = dict(config) if config is not None else load_config(config_path)
    quality_map = dict(quality or {})
    working = dict(features)
    evaluations = []
    by_id: dict[str, dict[str, Any]] = {}
    for spec in RULES:
        if spec.rule_id == "C2":
            b1 = by_id.get("B1", {})
            b3 = by_id.get("B3", {})
            severe_keys = ("highSlope_Ttop", "SpikeTopP15", "BurdenSlip")
            severe_available = all(_finite(working.get(key)) is not None for key in severe_keys)
            minimum_confidence = float(active_config["quality"]["minimum_coverage_ratio"])
            valid_b = [item for item in (b1, b3) if float(item.get("confidence") or 0) >= minimum_confidence]
            if severe_available and valid_b:
                severe = all(float(working[key]) >= 1.0 for key in severe_keys)
                b_gate = max(float(item.get("risk_score") or 0) for item in valid_b) >= float(active_config["score_bands"]["B"]["amber_from"])
                working["C2CompositeGate"] = 1.0 if severe and b_gate else 0.0
                quality_map["C2CompositeGate"] = {"available": True}
                factor_audit = quality_map.get("factor_audit")
                if isinstance(factor_audit, dict):
                    factor_audit["C2CompositeGate"] = {
                        "factor_value": working["C2CompositeGate"],
                        "formula": "1 if B1/B3 severe gate and highSlope_Ttop=SpikeTopP15=BurdenSlip=1 else 0",
                        "source_features": {
                            **{key: working.get(key) for key in severe_keys},
                            "B1_risk_score": b1.get("risk_score"),
                            "B3_risk_score": b3.get("risk_score"),
                        },
                        "source_values": {},
                        "baseline_snapshot": {},
                        "effective_thresholds": {
                            "factor_stage": {"mode": "binary_gate", "minimum": 0.0, "maximum": 1.0, "second_threshold_applied": False},
                            "B_amber_from": active_config["score_bands"]["B"]["amber_from"],
                        },
                    }
        item = evaluate_rule(spec, working, quality_map, active_config, timestamp=timestamp)
        evaluations.append(item)
        by_id[spec.rule_id] = item
    return {
        "schema_version": "abc_rule_bundle.v1",
        "requirement_id": REQUIREMENT_ID,
        "catalog_version": CATALOG_VERSION,
        "config_version": active_config.get("config_version", "unknown"),
        "config_hash": active_config.get("config_hash") or _json_hash(active_config),
        "evaluation_ts": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "quality": {key: value for key, value in quality_map.items() if key in {"coverage_ratio", "data_age_seconds"}},
        "evaluations": evaluations,
        "public": public_bundle(evaluations),
    }


def public_rule(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: evaluation.get(key) for key in PUBLIC_FIELDS if key in evaluation}
    # A maintenance score is calculated as ``100 - risk``.  With no usable
    # terms the provisional risk is zero, which would otherwise expose a
    # misleading 100-point maintenance score beside ``needs_data``.  The
    # internal provisional score remains in the auditable evaluation item, but
    # the production contract must fail closed and report no score until the
    # minimum data-confidence gate has passed.
    if evaluation.get("status") == "needs_data" or evaluation.get("score_released") is False:
        result["score"] = None
        result["score_available"] = False
    else:
        result["score_available"] = True
    result["internal_details_available"] = True
    return result


def public_bundle(evaluations: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "abc_rule_bundle.v1",
        "rules": [public_rule(item) for item in evaluations],
        "alerts": [public_rule(item) for item in evaluations if item.get("alert_state") in {"yellow", "amber", "deep_amber", "red"}],
        "public_contract": "production-safe.v1",
    }


def admin_bundle(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """Return internal details only after the caller has passed admin auth."""
    return dict(evaluation)


def sanitize_for_model(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Only the production-safe allowlist may enter an LLM prompt."""
    return {"schema_version": "abc_model_evidence.v1", "rules": [public_rule(item) for item in bundle.get("evaluations", [])]}
