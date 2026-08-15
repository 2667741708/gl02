"""Build public ABC33 score explanations without changing scoring.

REQ-8093-A-SCORE-EXPLANATION-20260813
FIX-8093-A-SCORE-DEDUCTION-R2-20260813
REQ-8093-BC-SCORE-CONTRIBUTION-20260814
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any


A_GOOD_SCORE = 80.0
MINIMUM_IMPACT_POINTS = 3.0
B_DISPLAY_THRESHOLD = 40.0
C_DISPLAY_THRESHOLD = 35.0


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _contribution_map(value: Any) -> dict[str, float]:
    value = _json_value(value)
    if isinstance(value, Mapping):
        result: dict[str, float] = {}
        for key, raw_number in value.items():
            number = _finite_number(raw_number)
            if number is not None:
                result[str(key)] = number
        return result
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return {}
    result = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        key = (
            item.get("feature_key")
            or item.get("term")
            or item.get("name")
            or item.get("id")
            or item.get("key")
        )
        number = _finite_number(item.get("contribution"))
        if number is None:
            number = _finite_number(item.get("actual_contribution"))
        if number is None:
            number = _finite_number(item.get("value"))
        if key is not None and number is not None:
            result[str(key)] = number
    return result


def _weight_map(value: Any) -> dict[str, float]:
    value = _json_value(value)
    if isinstance(value, Mapping):
        result: dict[str, float] = {}
        for key, raw_number in value.items():
            number = _finite_number(raw_number)
            if number is not None:
                result[str(key)] = number
        return result
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return {}
    result = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        key = item.get("feature_key") or item.get("term") or item.get("name")
        number = _finite_number(item.get("effective_weight"))
        if number is None:
            number = _finite_number(item.get("weight"))
        if key is not None and number is not None:
            result[str(key)] = number
    return result


def _usable_terms(weights: Any, contributions: Any) -> list[tuple[str, float, float]]:
    weight_map = _weight_map(weights)
    contribution_map = _contribution_map(contributions)
    usable: list[tuple[str, float, float]] = []
    for term, raw_weight in weight_map.items():
        key = str(term)
        weight = _finite_number(raw_weight)
        contribution = contribution_map.get(key)
        if weight is None or contribution is None:
            continue
        if weight <= 0 or contribution < 0 or contribution > weight + 1e-6:
            continue
        usable.append((key, weight, contribution))
    return usable


def _aggregate_scaled_points(
    usable_terms: Sequence[tuple[str, float, float]],
    available_weight: float,
    label_for: Callable[[str], str],
) -> dict[str, dict[str, float]]:
    by_label: dict[str, dict[str, float]] = {}
    for key, weight, contribution in usable_terms:
        label = str(label_for(key) or "").strip()
        if not label:
            continue
        aggregate = by_label.setdefault(label, {"current": 0.0, "maximum": 0.0})
        aggregate["current"] += 100.0 * contribution / available_weight
        aggregate["maximum"] += 100.0 * weight / available_weight
    return by_label


def build_score_explanation(
    *,
    category: Any,
    score: Any,
    status: Any,
    weights: Any,
    contributions: Any,
    label_for: Callable[[str], str],
) -> dict[str, Any] | None:
    """Return a public A deduction or B/C contribution explanation."""

    category_name = str(category or "").upper()
    if category_name not in {"A", "B", "C"}:
        return None

    score_number = _finite_number(score)
    score_unavailable = (
        str(status or "") == "needs_data"
        or score_number is None
        or not 0.0 <= score_number <= 100.0
    )

    if category_name in {"B", "C"}:
        semantics = "risk" if category_name == "B" else "danger"
        noun = "风险" if category_name == "B" else "危险"
        display_threshold = B_DISPLAY_THRESHOLD if category_name == "B" else C_DISPLAY_THRESHOLD
        base = {
            "score_semantics": semantics,
            "display_threshold": display_threshold,
            "minimum_impact_points": MINIMUM_IMPACT_POINTS,
            "important_factors": [],
        }
        if score_unavailable:
            return {**base, "state": "needs_data", "summary": f"数据不足，暂不生成{noun}贡献解释"}
        if score_number < display_threshold:
            return {
                **base,
                "state": "below_threshold",
                "summary": f"当前分值未达到{display_threshold:.0f}分{noun}贡献显示线",
            }

        usable_terms = _usable_terms(weights, contributions)
        available_weight = sum(weight for _key, weight, _contribution in usable_terms)
        if available_weight <= 0:
            return {**base, "state": "needs_data", "summary": f"数据不足，暂不生成{noun}贡献解释"}
        total_current = 100.0 * sum(
            contribution for _key, _weight, contribution in usable_terms
        ) / available_weight
        if abs(total_current - score_number) > 0.2:
            return {**base, "state": "needs_data", "summary": f"数据不足，暂不生成{noun}贡献解释"}

        by_label = _aggregate_scaled_points(usable_terms, available_weight, label_for)
        factors = [
            {
                "label": label,
                "current_contribution_points": round(points["current"], 1),
                "maximum_contribution_points": round(points["maximum"], 1),
            }
            for label, points in by_label.items()
            if points["current"] >= MINIMUM_IMPACT_POINTS
        ]
        factors.sort(key=lambda item: (-item["current_contribution_points"], item["label"]))
        summary = f"主要{noun}贡献" if factors else f"当前分值由多项轻微{noun}贡献共同形成"
        return {
            **base,
            "state": "needs_attention",
            "summary": summary,
            "total_current_contribution_points": round(total_current, 1),
            "important_factors": factors,
        }

    base = {
        "good_threshold": A_GOOD_SCORE,
        "minimum_impact_points": MINIMUM_IMPACT_POINTS,
        "important_factors": [],
    }
    if score_unavailable:
        return {
            **base,
            "state": "needs_data",
            "summary": "数据不足，暂不生成失分解释",
        }
    if score_number >= A_GOOD_SCORE:
        return {**base, "state": "good", "summary": "炉况良好"}

    usable_terms = _usable_terms(weights, contributions)
    available_weight = sum(weight for _key, weight, _contribution in usable_terms)
    if available_weight <= 0:
        return {
            **base,
            "state": "needs_data",
            "summary": "数据不足，暂不生成失分解释",
        }

    total_current_deduction = 100.0 * sum(
        contribution for _key, _weight, contribution in usable_terms
    ) / available_weight
    expected_deduction = 100.0 - score_number
    if abs(total_current_deduction - expected_deduction) > 0.2:
        return {
            **base,
            "state": "needs_data",
            "summary": "数据不足，暂不生成失分解释",
        }

    deduction_by_label = _aggregate_scaled_points(usable_terms, available_weight, label_for)
    factors = [
        {
            "label": label,
            "impact_points": round(points["current"], 1),
            "current_deduction_points": round(points["current"], 1),
            "maximum_deduction_points": round(points["maximum"], 1),
        }
        for label, points in deduction_by_label.items()
        if points["current"] >= MINIMUM_IMPACT_POINTS
    ]
    factors.sort(key=lambda item: (-item["current_deduction_points"], item["label"]))
    summary = "主要失分因素" if factors else "当前分值由多项轻微偏离共同形成"
    return {
        **base,
        "state": "needs_attention",
        "summary": summary,
        "total_current_deduction_points": round(total_current_deduction, 1),
        "important_factors": factors,
    }


def build_a_score_explanation(
    *,
    category: Any,
    score: Any,
    status: Any,
    weights: Any,
    contributions: Any,
    label_for: Callable[[str], str],
) -> dict[str, Any] | None:
    """Backward-compatible A-only entrypoint."""

    if str(category or "").upper() != "A":
        return None
    return build_score_explanation(
        category=category,
        score=score,
        status=status,
        weights=weights,
        contributions=contributions,
        label_for=label_for,
    )
