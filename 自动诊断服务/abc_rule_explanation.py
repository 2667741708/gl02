"""Deterministic explanation contracts for ABC33 rule evaluations.

The rule engine remains the only scoring authority.  This module only turns
its auditable evaluation dictionaries into JSON-safe operator and assistant
contexts; it deliberately does not recalculate a rule score.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .abc_rule_catalog import CATALOG_VERSION, RULES, RULE_BY_ID, RuleSpec
    from .abc_term_semantics import term_semantics
except ImportError:  # pragma: no cover - service directory is also a script root.
    from abc_rule_catalog import CATALOG_VERSION, RULES, RULE_BY_ID, RuleSpec
    from abc_term_semantics import term_semantics


SCHEMA_VERSION = "abc_rule_explanation_context.v1"
ASSISTANT_SCHEMA_VERSION = SCHEMA_VERSION


def json_safe_value(value: Any) -> Any:
    """Recursively normalize a value so strict JSON encoding always succeeds."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        if value == value.to_integral_value():
            return int(value)
        number = float(value)
        return number if math.isfinite(number) else str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        normalized = [json_safe_value(item) for item in value]
        return sorted(normalized, key=canonical_json)
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def canonical_json(value: Any) -> str:
    """Return the stable UTF-8 JSON representation used by the contract hash."""
    return json.dumps(
        json_safe_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    """Return a lower-case SHA-256 over :func:`canonical_json`."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_context_hash(value: Any) -> str:
    """Hash a context while excluding its top-level digest field."""
    if isinstance(value, Mapping):
        value = {key: item for key, item in value.items() if str(key) != "context_hash"}
    return canonical_sha256(value)


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _rounded(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _spec_for(evaluation: Mapping[str, Any], spec: RuleSpec | None) -> RuleSpec:
    if spec is not None:
        if spec.rule_id != str(evaluation.get("rule_id")):
            raise ValueError("RuleSpec and evaluation rule_id do not match")
        return spec
    rule_id = str(evaluation.get("rule_id") or "")
    try:
        return RULE_BY_ID[rule_id]
    except KeyError as exc:
        raise ValueError(f"unknown ABC33 rule_id: {rule_id!r}") from exc


def _direction(spec: RuleSpec) -> dict[str, str]:
    if spec.category == "A":
        return {
            "score_type": "maintenance_score",
            "higher_means": "healthier",
            "explanation": "A类为维护分，分数越高表示越接近正常维护状态；其公式为100减风险分。",
        }
    return {
        "score_type": "risk_score",
        "higher_means": "higher_risk",
        "explanation": "B/C类为风险分，分数越高表示规则风险证据越强。",
    }


def _term_rows(evaluation: Mapping[str, Any], spec: RuleSpec) -> list[dict[str, Any]]:
    contributions = {
        str(item.get("feature_key")): item
        for item in evaluation.get("contributions", [])
        if isinstance(item, Mapping) and item.get("feature_key") is not None
    }
    evaluated_weights = evaluation.get("weights")
    weights = dict(spec.terms)
    if isinstance(evaluated_weights, Mapping):
        weights.update({str(key): value for key, value in evaluated_weights.items()})

    available_points = 0.0
    for item in contributions.values():
        points = _finite(item.get("contribution"))
        if points is not None:
            available_points += points

    missing = {str(item) for item in evaluation.get("missing_features", [])}
    rows: list[dict[str, Any]] = []
    for term, configured_weight in weights.items():
        item = contributions.get(term)
        weight = _finite(item.get("weight") if item is not None else configured_weight)
        normalized = _finite(item.get("normalized_value")) if item is not None else None
        points = _finite(item.get("contribution")) if item is not None else None
        semantics = term_semantics(term)
        available = item is not None and normalized is not None and points is not None
        missing_reasons = [] if available else ["missing_or_quality_gated" if term in missing else "not_evaluated"]
        thresholds = json_safe_value(item.get("effective_thresholds", {})) if item is not None else {}
        unit: Any = item.get("unit") if item is not None else None
        if unit is None:
            unit = semantics.get("unit")
        if unit is None and item is not None:
            for metadata_key in ("source_metadata", "metadata"):
                metadata = item.get(metadata_key)
                if isinstance(metadata, Mapping) and metadata.get("unit") is not None:
                    unit = metadata.get("unit")
                    break
        rows.append({
            "term_id": term,
            "term_key": term,
            "display_name": semantics["label"],
            "semantic": semantics["meaning"],
            "unit": json_safe_value(unit),
            "data_state": "available" if available else "missing",
            "missing_reasons": missing_reasons,
            "raw_value": json_safe_value(item.get("raw_value")) if item is not None else None,
            "normalized_score_0_100": _rounded(normalized * 100.0) if normalized is not None else None,
            "weight": _rounded(weight),
            "weighted_points": _rounded(points),
            "contribution_ratio": _rounded(points / available_points) if points is not None and available_points > 0 else None,
            "formula": json_safe_value(item.get("formula")) if item is not None else None,
            "source_features": json_safe_value(item.get("source_features", {})) if item is not None else {},
            "source_values": json_safe_value(item.get("source_values", {})) if item is not None else {},
            "baseline_snapshot": json_safe_value(item.get("baseline_snapshot", {})) if item is not None else {},
            "effective_threshold_description": canonical_json(thresholds) if thresholds else "无可用阈值快照",
        })
    return rows


def build_operator_explanation(
    evaluation: Mapping[str, Any],
    spec: RuleSpec | None = None,
) -> dict[str, Any]:
    """Build one complete, deterministic ABC rule explanation."""
    active_spec = _spec_for(evaluation, spec)
    terms = _term_rows(evaluation, active_spec)
    score = _finite(evaluation.get("score"))
    risk_score = _finite(evaluation.get("risk_score"))
    available_weight = sum(float(row["weight"] or 0) for row in terms if row["data_state"] == "available")
    total_weight = sum(float(row["weight"] or 0) for row in terms)
    weighted_points_sum = sum(float(row["weighted_points"] or 0) for row in terms if row["data_state"] == "available")
    evaluation_ts = evaluation.get("evaluation_ts", evaluation.get("triggered_at"))
    evaluation_id = evaluation.get("evaluation_id")
    if not evaluation_id:
        evaluation_id = canonical_sha256({
            "rule_id": active_spec.rule_id,
            "evaluation_ts": json_safe_value(evaluation_ts),
            "source_snapshot_id": evaluation.get("source_snapshot_id"),
        })[:24]
    context_id = str(evaluation.get("context_id") or f"abc33:{evaluation_id}:{active_spec.rule_id}")
    raw_formula_score = _finite(evaluation.get("raw_formula_score"))
    score_available = (
        score is not None
        and evaluation.get("status") != "needs_data"
        and evaluation.get("score_released") is not False
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "context_id": context_id,
        "context_hash": "",
        "furnace_id": evaluation.get("furnace_id"),
        "evaluation": {
            "evaluation_id": str(evaluation_id),
            "evaluation_ts": json_safe_value(evaluation_ts),
            "catalog_version": evaluation.get("catalog_version", CATALOG_VERSION),
            "config_version": evaluation.get("config_version"),
            "config_hash": evaluation.get("config_hash"),
            "source_snapshot_id": evaluation.get("source_snapshot_id"),
            "data_age_seconds": json_safe_value(evaluation.get("data_age_seconds")),
        },
        "rule": {
            "rule_id": active_spec.rule_id,
            "category": active_spec.category,
            "display_name": active_spec.display_name,
            "score": _rounded(score) if score_available else None,
            "risk_score": _rounded(risk_score),
            "confidence": _rounded(_finite(evaluation.get("confidence"))),
            "status": evaluation.get("status"),
            "alert_state": evaluation.get("alert_state"),
            "score_basis": evaluation.get("score_basis"),
            "score_available": score_available,
            "score_direction": _direction(active_spec),
        },
        "calculation": {
            "available_weight": _rounded(available_weight),
            "total_weight": _rounded(total_weight),
            "weighted_points_sum": _rounded(weighted_points_sum),
            "risk_score": _rounded(risk_score),
            "formula_score": _rounded(raw_formula_score),
            "pre_gate_formula_score": _rounded(raw_formula_score),
            "post_gate_score": _rounded(score),
            "event_confirmation": json_safe_value(evaluation.get("event_confirmation")),
            "event_confirmation_state": evaluation.get("event_confirmation_state"),
            "terms": terms,
        },
        "process_guidance": {
            "observation_window": active_spec.observation_window,
            "approval": active_spec.approval,
            "principle": active_spec.principle,
            "manual_review": list(active_spec.manual_review),
            "intervention_order": list(active_spec.intervention_order),
            "source_refs": list(active_spec.source_refs),
            "safety_event": active_spec.safety_event,
        },
        "sensor_review": {
            "primary_sensors": list(active_spec.primary_sensors),
            "primary_review": list(active_spec.primary_review),
            "expanded_review": list(active_spec.expanded_review),
            "missing_sensors": json_safe_value(evaluation.get("missing_sensors", [])),
        },
        "data_quality": {
            "data_complete": bool(evaluation.get("data_complete", False)),
            "confidence": _rounded(_finite(evaluation.get("confidence"))),
            "data_age_seconds": json_safe_value(evaluation.get("data_age_seconds")),
            "missing_terms": [row["term_id"] for row in terms if row["data_state"] != "available"],
            "required_missing_terms": json_safe_value(evaluation.get("required_missing_features", [])),
            "blocking_reasons": json_safe_value(evaluation.get("blocking_reasons", [])),
        },
        "assistant_policy": {
            "mode": "read_only_explanation",
            "may_change_process_setpoints": False,
            "requires_foreman_approval": True,
            "instruction": "只能基于本上下文解释评分与处置顺序，不得自动写入高炉设定值。",
            "event_confirmation_summary": evaluation.get("event_confirmation_summary"),
        },
    }
    safe_payload = json_safe_value(payload)
    safe_payload["context_hash"] = canonical_context_hash(safe_payload)
    return safe_payload


def build_operator_explanation_context(
    evaluation: Mapping[str, Any],
    spec: RuleSpec | None = None,
) -> dict[str, Any]:
    """Stable public builder name used by backend integrations."""
    return build_operator_explanation(evaluation, spec)


def build_assistant_context(
    value: Mapping[str, Any],
    rule_id: str | None = None,
    spec: RuleSpec | None = None,
) -> dict[str, Any]:
    """Build the same fixed contract for assistant use.

    An engine bundle contains 33 evaluations, so ``rule_id`` is required to
    select the one rule whose explanation is entering a prompt.  This prevents
    an accidental, ambiguous many-rule prompt.
    """
    if value.get("schema_version") == SCHEMA_VERSION and "context_hash" in value:
        return json_safe_value(value)
    if "evaluations" not in value:
        return build_operator_explanation_context(value, spec)
    if not rule_id:
        raise ValueError("rule_id is required when building assistant context from an engine bundle")
    evaluations = value.get("evaluations")
    if not isinstance(evaluations, Iterable) or isinstance(evaluations, (str, bytes, Mapping)):
        raise TypeError("engine bundle evaluations must be a sequence")
    selected = next(
        (item for item in evaluations if isinstance(item, Mapping) and str(item.get("rule_id")) == rule_id),
        None,
    )
    if selected is None:
        raise ValueError(f"rule_id {rule_id!r} is absent from engine bundle")
    enriched = dict(selected)
    for key in ("catalog_version", "config_version", "config_hash", "evaluation_ts", "furnace_id", "source_snapshot_id"):
        if enriched.get(key) is None and value.get(key) is not None:
            enriched[key] = value.get(key)
    return build_operator_explanation_context(enriched, spec)


# Concise aliases for callers that treat the builders as serializers.
operator_explanation = build_operator_explanation
assistant_context = build_assistant_context


def all_rule_specs() -> tuple[RuleSpec, ...]:
    """Expose the exact catalogue order used by the rule engine."""
    return RULES


__all__ = [
    "ASSISTANT_SCHEMA_VERSION", "SCHEMA_VERSION", "all_rule_specs",
    "assistant_context", "build_assistant_context", "build_operator_explanation",
    "build_operator_explanation_context", "canonical_context_hash", "canonical_json",
    "canonical_sha256", "json_safe_value", "operator_explanation",
]
