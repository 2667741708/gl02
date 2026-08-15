"""Structured, read-only LLM review contract for furnace diagnosis scores.

The model review explains whether the deterministic rule score is supported by the
provided evidence and recent history.  It never replaces rule scores, action states,
amplitudes, sequence, safety gates, or approval requirements.

Corresponding requirement:
REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import diag_ai_evidence


SCHEMA_VERSION = "diagnosis_model_review.v1"
PROMPT_VERSION = "diagnosis-score-review.v1"
FIVE_MINUTE_SCHEMA_VERSION = "diagnosis_ai_analysis.v4"
FIVE_MINUTE_PROMPT_VERSION = "diagnosis-single-condition-five-minute.v7-abc33-b4"
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
DISPLAY_NAMES = {
    "normal": "正常顺行",
    "lowline": "低料线",
    "edge": "边缘发展",
    "center": "中心发展",
    "channel": "管道行程",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "column": "悬料",
}
VERDICTS = {"agree", "partial_agree", "disagree", "insufficient_data"}
RISK_CHANGES = {"rising", "stable", "falling", "uncertain"}
FIVE_MINUTE_VERDICTS = {
    "supported",
    "possible",
    "not_supported",
    "insufficient_data",
}


class ModelReviewValidationError(ValueError):
    """Raised when request context or model JSON violates the review contract."""


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_text(value: object, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _text_list(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value[:limit]:
        if isinstance(item, Mapping):
            text = _safe_text(
                item.get("text")
                or item.get("name")
                or item.get("message")
                or item.get("description")
                or json.dumps(dict(item), ensure_ascii=False, default=str)
            )
        else:
            text = _safe_text(item)
        if text:
            items.append(text)
    return items


def _identifier_list(value: object, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value[:limit]:
        identifier = _safe_text(item, 180)
        if identifier and identifier not in output:
            output.append(identifier)
    return output


def _score_map(source: object) -> dict[str, float]:
    raw = source if isinstance(source, Mapping) else {}
    return {
        label: (_finite(raw.get(label)) if _finite(raw.get(label)) is not None else 0.0)
        for label in DIAGNOSIS_LABELS
    }


def _baseline_items(source: object) -> list[dict[str, Any]]:
    if isinstance(source, Mapping):
        raw_items = source.get("items")
        if not isinstance(raw_items, list):
            raw_items = [
                {"id": key, **dict(value)}
                for key, value in source.items()
                if isinstance(value, Mapping)
            ]
    else:
        raw_items = source
    if not isinstance(raw_items, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw_items[:16]:
        if not isinstance(item, Mapping):
            continue
        row = {
            "id": _safe_text(item.get("id") or item.get("name"), 80),
            "z": _finite(item.get("z")),
            "current": _finite(
                item.get("current") if item.get("current") is not None else item.get("value")
            ),
            "baseline": _finite(
                item.get("baseline")
                if item.get("baseline") is not None
                else item.get("mean")
            ),
        }
        if row["id"]:
            rows.append(row)
    return rows


def _data_coverage(source: object) -> float | None:
    if isinstance(source, Mapping):
        ratio = _finite(source.get("ratio"))
        if ratio is None:
            ratio = _finite(source.get("coverage"))
        if ratio is not None:
            return ratio
        available = _finite(source.get("available"))
        total = _finite(source.get("total"))
        if available is not None and total and total > 0:
            return available / total
        return None
    return _finite(source)


def _action_summaries(source: object) -> list[dict[str, Any]]:
    if not isinstance(source, Mapping):
        return []
    actions = source.get("actions")
    if not isinstance(actions, list):
        return []
    rows: list[dict[str, Any]] = []
    for action in actions[:24]:
        if not isinstance(action, Mapping):
            continue
        rows.append(
            {
                "id": _safe_text(action.get("id"), 100),
                "name": _safe_text(action.get("name") or action.get("user_facing_text")),
                "status": _safe_text(action.get("status"), 40),
                "trigger_evidence": _text_list(action.get("trigger_evidence"), limit=8),
                "blocking_reasons": _text_list(action.get("blocking_reasons"), limit=8),
                "missing_inputs": _text_list(action.get("missing_inputs"), limit=8),
            }
        )
    return rows


def _history_rows(source: object) -> list[dict[str, Any]]:
    if not isinstance(source, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in source[-12:]:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("main_label") or item.get("label") or "normal")
        scores = _score_map(item.get("raw_scores") or item.get("raw") or item.get("scores"))
        rows.append(
            {
                "timestamp": _safe_text(
                    item.get("diagnosis_ts") or item.get("timestamp") or item.get("calculated_at"),
                    64,
                ),
                "main_label": label if label in DIAGNOSIS_LABELS else "normal",
                "secondary_label": _safe_text(
                    item.get("secondary_label") or item.get("secondary"), 40
                ),
                "scores": scores,
            }
        )
    return rows


def normalize_review_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Whitelist and normalize browser context before it enters the model prompt."""
    diagnosis = payload.get("diagnosis")
    if not isinstance(diagnosis, Mapping):
        raise ModelReviewValidationError("缺少有效诊断快照")

    main_label = str(diagnosis.get("main_label") or diagnosis.get("label") or "normal")
    if main_label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("主炉况不在允许的8类炉况中")
    reviewed_label = str(payload.get("reviewed_label") or main_label)
    if reviewed_label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("待复核炉况不在允许的8类炉况中")

    scores = _score_map(
        diagnosis.get("raw_scores") or diagnosis.get("raw") or diagnosis.get("scores")
    )
    main_score = _finite(diagnosis.get("main_score"))
    if main_score is None:
        main_score = _finite(diagnosis.get("score"))
    if main_score is not None:
        scores[main_label] = main_score
    reviewed_score = scores[reviewed_label]
    recommendation = payload.get("recommendation")
    recommendation = recommendation if isinstance(recommendation, Mapping) else {}
    return {
        "diagnosis_ts": _safe_text(
            diagnosis.get("diagnosis_ts")
            or diagnosis.get("timestamp")
            or diagnosis.get("calculated_at"),
            64,
        ),
        "main_label": main_label,
        "main_display_name": DISPLAY_NAMES[main_label],
        "secondary_label": _safe_text(
            diagnosis.get("secondary_label") or diagnosis.get("secondary"), 40
        ),
        "reviewed_label": reviewed_label,
        "reviewed_display_name": DISPLAY_NAMES[reviewed_label],
        "reviewed_score": reviewed_score,
        "scores": scores,
        "evidence": _text_list(diagnosis.get("evidence"), limit=24),
        "baseline_items": _baseline_items(diagnosis.get("baseline_compare")),
        "data_coverage": _data_coverage(diagnosis.get("data_coverage")),
        "diagnosis_history": _history_rows(payload.get("diagnosis_history")),
        "recommendation": {
            "goal": _safe_text(recommendation.get("goal")),
            "safety_gate_passed": bool(recommendation.get("safety_gate_passed", True)),
            "safety_warnings": _text_list(recommendation.get("safety_warnings"), limit=12),
            "actions": _action_summaries(recommendation),
        },
    }


def review_cache_key(context: Mapping[str, Any], model_identity: str) -> str:
    """Hash the immutable review inputs and model identity for deterministic caching."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_identity": model_identity,
        "context": context,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_review_messages(context: Mapping[str, Any]) -> list[dict[str, str]]:
    """Build the strict JSON-only prompt used by the backend furnace model."""
    system = (
        "你是高炉炉况诊断分数复核助手。规则引擎分数是确定性结果，你只能判断其与给定证据、"
        "历史趋势和数据质量是否一致，不能修改分数，不能新增调剂动作，不能覆盖安全门禁、幅度、"
        "顺序或审批。不得编造输入中没有的数据。只返回一个JSON对象，不要Markdown，不要解释JSON格式。"
    )
    contract = {
        "verdict": "agree|partial_agree|disagree|insufficient_data",
        "model_support_score": "0-100整数，表示对规则结论的支持程度，不是替代分数",
        "summary": "面向高炉长的简明复核结论",
        "supporting_evidence": ["支持证据"],
        "contradicting_evidence": ["矛盾证据"],
        "missing_data": ["缺失数据"],
        "attention_items": ["下一观察窗口需要关注的项目"],
        "risk_change": "rising|stable|falling|uncertain",
        "manual_review_recommended": True,
    }
    user = (
        "请复核以下结构化诊断快照。输出必须严格符合返回合同。\n"
        f"返回合同：{json.dumps(contract, ensure_ascii=False)}\n"
        f"诊断资料：{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_model_payload(text: str) -> dict[str, Any]:
    """Extract and validate one model JSON object without accepting free-form fallback."""
    content = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content, flags=re.I)
    candidate = fenced.group(1) if fenced else content
    if not (candidate.startswith("{") and candidate.endswith("}")):
        start, end = candidate.find("{"), candidate.rfind("}")
        candidate = candidate[start : end + 1] if start >= 0 and end > start else ""
    if not candidate:
        raise ModelReviewValidationError("大模型未返回结构化复核结果")
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ModelReviewValidationError("大模型复核JSON无法解析") from exc
    if not isinstance(payload, dict):
        raise ModelReviewValidationError("大模型复核结果不是JSON对象")

    verdict = str(payload.get("verdict") or "")
    if verdict not in VERDICTS:
        raise ModelReviewValidationError("大模型复核结论状态无效")
    support = _finite(payload.get("model_support_score"))
    if support is None:
        raise ModelReviewValidationError("大模型未返回有效支持程度")
    summary = _safe_text(payload.get("summary"), 1200)
    if not summary:
        raise ModelReviewValidationError("大模型未返回复核摘要")
    risk_change = str(payload.get("risk_change") or "uncertain")
    if risk_change not in RISK_CHANGES:
        risk_change = "uncertain"
    return {
        "verdict": verdict,
        "model_support_score": int(round(max(0.0, min(100.0, support)))),
        "summary": summary,
        "supporting_evidence": _text_list(payload.get("supporting_evidence"), limit=16),
        "contradicting_evidence": _text_list(
            payload.get("contradicting_evidence"), limit=16
        ),
        "missing_data": _text_list(payload.get("missing_data"), limit=16),
        "attention_items": _text_list(payload.get("attention_items"), limit=16),
        "risk_change": risk_change,
        "manual_review_recommended": bool(payload.get("manual_review_recommended", False)),
    }


def build_completed_review(
    context: Mapping[str, Any],
    model_payload: Mapping[str, Any],
    *,
    public_model_name: str,
    snapshot_hash: str,
    cache_hit: bool = False,
) -> dict[str, Any]:
    """Return the stable browser/API response while hiding the internal model identifier."""
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "completed",
        "verdict": model_payload["verdict"],
        "diagnosis_ts": context.get("diagnosis_ts"),
        "reviewed_label": context["reviewed_label"],
        "reviewed_display_name": context["reviewed_display_name"],
        "rule_score": context["reviewed_score"],
        "model_support_score": model_payload["model_support_score"],
        "summary": model_payload["summary"],
        "supporting_evidence": list(model_payload.get("supporting_evidence") or []),
        "contradicting_evidence": list(model_payload.get("contradicting_evidence") or []),
        "missing_data": list(model_payload.get("missing_data") or []),
        "attention_items": list(model_payload.get("attention_items") or []),
        "risk_change": model_payload.get("risk_change") or "uncertain",
        "manual_review_recommended": bool(
            model_payload.get("manual_review_recommended", False)
        ),
        "read_only": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_meta": {
            "public_name": public_model_name,
            "prompt_version": PROMPT_VERSION,
            "snapshot_hash": snapshot_hash,
            "cache_hit": cache_hit,
        },
    }


def five_minute_bucket(value: object, bucket_minutes: int = 5) -> datetime:
    """Return the UTC-aligned bucket for one diagnosis timestamp.

    Corresponding requirement:
    REQ-8093-DIAGNOSIS-AI-FIVE-MINUTE-ANALYSIS-20260805.
    """
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            raise ModelReviewValidationError("缺少诊断时间，无法生成5分钟智能分析")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ModelReviewValidationError("诊断时间格式无效") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    safe_minutes = max(1, int(bucket_minutes))
    minute = parsed.minute - parsed.minute % safe_minutes
    return parsed.replace(minute=minute, second=0, microsecond=0)


def normalize_five_minute_context(
    canonical_context: Mapping[str, Any],
    diagnosis_history: object,
    *,
    bucket_minutes: int = 5,
) -> dict[str, Any]:
    """Build a server-owned context for one eight-condition analysis batch."""
    if not canonical_context.get("available"):
        raise ModelReviewValidationError("当前没有可分析的诊断快照")
    main_label = str(canonical_context.get("main_label") or "normal")
    if main_label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("主炉况不在允许的8类炉况中")
    diagnosis_ts = _safe_text(canonical_context.get("diagnosis_ts"), 64)
    scores = _score_map(
        canonical_context.get("display_scores")
        if isinstance(canonical_context.get("display_scores"), Mapping)
        else canonical_context.get("raw_scores")
    )
    main_score = _finite(
        canonical_context.get("display_main_score")
        if "display_main_score" in canonical_context
        else canonical_context.get("main_score")
    )
    if main_score is not None:
        scores[main_label] = main_score
    bucket = five_minute_bucket(diagnosis_ts, bucket_minutes)
    secondary = canonical_context.get("secondary")
    secondary_rows = secondary if isinstance(secondary, list) else []
    return {
        "furnace_id": _safe_text(canonical_context.get("furnace_id") or "BF", 40),
        "snapshot_id": _safe_text(canonical_context.get("snapshot_id"), 120),
        "snapshot_source": _safe_text(
            canonical_context.get("snapshot_source") or "live_readonly", 40
        ),
        "diagnosis_ts": diagnosis_ts,
        "bucket_ts": bucket.isoformat(),
        "bucket_minutes": max(1, int(bucket_minutes)),
        "main_label": main_label,
        "main_display_name": DISPLAY_NAMES[main_label],
        "secondary": secondary_rows[:4],
        "scores": scores,
        "score_sources": dict(canonical_context.get("score_sources") or {})
        if isinstance(canonical_context.get("score_sources"), Mapping)
        else {},
        "evidence": _text_list(canonical_context.get("evidence"), limit=24),
        "data_coverage": canonical_context.get("data_coverage")
        if isinstance(canonical_context.get("data_coverage"), Mapping)
        else {},
        "diagnosis_history": _history_rows(diagnosis_history),
        "feature_snapshot": dict(canonical_context.get("feature_snapshot") or {})
        if isinstance(canonical_context.get("feature_snapshot"), Mapping)
        else {},
        "variable_stats": dict(canonical_context.get("variable_stats") or {})
        if isinstance(canonical_context.get("variable_stats"), Mapping)
        else {},
        "rule_drivers": dict(canonical_context.get("rule_drivers") or {})
        if isinstance(canonical_context.get("rule_drivers"), Mapping)
        else {},
        "recommendation_context": dict(
            canonical_context.get("recommendation_context") or {}
        )
        if isinstance(canonical_context.get("recommendation_context"), Mapping)
        else {},
        "knowledge_context": dict(canonical_context.get("knowledge_context") or {})
        if isinstance(canonical_context.get("knowledge_context"), Mapping)
        else {},
        "sensor_deviation_summary": dict(
            canonical_context.get("sensor_deviation_summary") or {}
        )
        if isinstance(canonical_context.get("sensor_deviation_summary"), Mapping)
        else {},
    }


def five_minute_analysis_key(
    context: Mapping[str, Any], model_identity: str, target_label: str | None = None
) -> str:
    """Hash the canonical five-minute snapshot and model identity."""
    payload = {
        "schema_version": FIVE_MINUTE_SCHEMA_VERSION,
        "prompt_version": FIVE_MINUTE_PROMPT_VERSION,
        "model_identity": model_identity,
        "target_label": target_label,
        "context": context,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prompt_five_minute_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Compact trusted evidence while retaining exact values and provenance IDs."""
    rule_drivers = context.get("rule_drivers")
    rule_drivers = rule_drivers if isinstance(rule_drivers, Mapping) else {}
    recommendation = context.get("recommendation_context")
    recommendation = recommendation if isinstance(recommendation, Mapping) else {}
    conditions = recommendation.get("conditions")
    conditions = conditions if isinstance(conditions, Mapping) else {}
    condition_context: dict[str, Any] = {}
    for label in DIAGNOSIS_LABELS:
        drivers = rule_drivers.get(label)
        drivers = drivers if isinstance(drivers, list) else []
        plan = conditions.get(label)
        plan = plan if isinstance(plan, Mapping) else {}
        actions = plan.get("actions")
        actions = actions if isinstance(actions, list) else []
        condition_context[label] = {
            "display_name": DISPLAY_NAMES[label],
            "rule_score": float((context.get("scores") or {}).get(label, 0.0)),
            "drivers": [
                {
                    "driver_id": item.get("driver_id"),
                    "name": item.get("name"),
                    "signal_state": item.get("signal_state"),
                    "configured_weight": item.get("configured_weight"),
                    "colloquial_evidence": item.get("colloquial_evidence"),
                }
                for item in drivers[:5]
                if isinstance(item, Mapping)
            ],
            "recommendation": {
                "scope": plan.get("scope"),
                "goal": plan.get("goal"),
                "safety_gate_passed": plan.get("safety_gate_passed"),
                "safety_warnings": [
                    _safe_text(item, 120)
                    for item in list(plan.get("safety_warnings") or [])[:3]
                ],
                "observe_items": [
                    _safe_text(item, 80)
                    for item in list(plan.get("observe_items") or [])[:4]
                ],
                "recheck_minutes": plan.get("recheck_minutes"),
                "actions": [
                    {
                        "id": action.get("id"),
                        "status": action.get("status"),
                        "text": _safe_text(action.get("text"), 160),
                        "delta": _safe_text(action.get("delta"), 100),
                        "observation_window": _safe_text(
                            action.get("observation_window"), 120
                        ),
                        "blocking_reasons": [
                            _safe_text(item, 80)
                            for item in list(action.get("blocking_reasons") or [])[:2]
                        ],
                        "missing_inputs": [
                            _safe_text(item, 80)
                            for item in list(action.get("missing_inputs") or [])[:2]
                        ],
                        "source_refs": list(action.get("source_refs") or [])[:2],
                    }
                    for action in actions[:2]
                    if isinstance(action, Mapping)
                ],
            },
        }
    knowledge = context.get("knowledge_context")
    knowledge = knowledge if isinstance(knowledge, Mapping) else {}
    knowledge_rows = knowledge.get("evidence")
    knowledge_rows = knowledge_rows if isinstance(knowledge_rows, list) else []
    sensor_summary = context.get("sensor_deviation_summary")
    sensor_summary = sensor_summary if isinstance(sensor_summary, Mapping) else {}
    sensor_rows = sensor_summary.get("sensors")
    sensor_rows = sensor_rows if isinstance(sensor_rows, list) else []
    control_candidates = sensor_summary.get("control_candidates")
    control_candidates = control_candidates if isinstance(control_candidates, list) else []
    raw_coverage = context.get("data_coverage")
    raw_coverage = raw_coverage if isinstance(raw_coverage, Mapping) else {}
    # Keep the aggregate freshness context, but do not expose per-variable
    # sampling density to the model as a missing-data signal.  The server later
    # computes truthful data_limits from actual variable_stats.
    prompt_coverage = {
        key: raw_coverage.get(key)
        for key in ("coverage_ratio", "expected_minutes", "observed_minutes")
        if raw_coverage.get(key) is not None
    }
    return {
        "diagnosis_ts": context.get("diagnosis_ts"),
        "bucket_ts": context.get("bucket_ts"),
        "bucket_minutes": context.get("bucket_minutes"),
        "main_label": context.get("main_label"),
        "secondary": context.get("secondary"),
        "scores": context.get("scores"),
        "score_sources": context.get("score_sources"),
        "data_coverage": prompt_coverage,
        "sensor_deviation_summary": {
            "rule_score": sensor_summary.get("rule_score"),
            "score_gap_to_100": sensor_summary.get("score_gap_to_100"),
            "total_sensor_count": sensor_summary.get("total_sensor_count"),
            "baseline_available_count": sensor_summary.get("baseline_available_count"),
            "average_abs_baseline_z": sensor_summary.get("average_abs_baseline_z"),
            "max_abs_baseline_z": sensor_summary.get("max_abs_baseline_z"),
            "deviation_label": sensor_summary.get("deviation_label"),
            "summary": sensor_summary.get("summary"),
            "sensors": [
                {
                    "id": row.get("id"),
                    "display_name": row.get("display_name"),
                    "unit": row.get("unit"),
                    "current_value": row.get("current_value"),
                    "delta_5m": row.get("delta_5m"),
                    "baseline_median_30d": row.get("baseline_median_30d"),
                    "baseline_z_60m": row.get("baseline_z_60m"),
                    "direction_5m": row.get("direction_5m"),
                    "deviation_state": row.get("deviation_state"),
                }
                for row in sensor_rows[:19]
                if isinstance(row, Mapping)
            ],
            "control_candidates": [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "text": row.get("text"),
                    "data_basis": list(row.get("data_basis") or [])[:8],
                }
                for row in control_candidates[:4]
                if isinstance(row, Mapping)
            ],
        },
        "diagnosis_history": [
            {
                "diagnosis_ts": row.get("diagnosis_ts"),
                "main_label": row.get("main_label"),
                "scores": row.get("scores"),
            }
            for row in list(context.get("diagnosis_history") or [])[-6:]
            if isinstance(row, Mapping)
        ],
        "conditions": condition_context,
        "knowledge_evidence": [
            {
                "chunk_id": item.get("chunk_id"),
                "title": item.get("title"),
                "source_file": item.get("source_file"),
                "content": _safe_text(item.get("content"), 360),
            }
            for item in knowledge_rows[:4]
            if isinstance(item, Mapping)
        ],
    }


def build_five_minute_analysis_messages(
    context: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build one JSON-only prompt that evaluates all eight furnace conditions."""
    system = (
        "你是高炉炉况智能分析助手。一次任务必须同时分析固定的8类炉况。"
        "规则符合度是确定性规则分，不是概率；你的支持分只表示当前证据与该炉况描述的吻合程度，"
        "不能替换规则分、不能修改主诊断、不能下达生产控制指令。"
        "只能使用输入中的规则分、规则变量实测值、30天基线、诊断证据、调剂引擎只读动作和知识库片段，不得编造现场数据。"
        "解释必须用高炉长容易理解的口语说明哪些变量升高、下降或偏离基线；涉及数值时只能复述输入中的数值。"
        "数据限制只能填写确实没有当前值和趋势序列的项目；已有有效当前值或60分钟序列的传感器，哪怕采样不是每分钟一条，也不得标为数据限制。"
        "指导意见只能引用输入中的action id和knowledge chunk id，不能新增动作、幅度、顺序、安全门禁或审批要求；64主题知识库只作为只读依据，不调用三规二制调控引擎。"
        "详细数据卡由服务端追加；模型文字要简洁，每类只提炼最关键的1至3个依据，不要复写全部输入。"
        "只返回一个JSON对象，不要Markdown。"
    )
    contract = {
        "analyses": [
            {
                "label": "normal|lowline|edge|center|channel|cold|hot|column",
                "verdict": "supported|possible|not_supported|insufficient_data",
                "model_support_score": "0-100整数；证据吻合度，不是概率",
                "summary": "不超过50个汉字的当前5分钟判断",
                "score_explanation": "不超过100个汉字；引用1至3项具体数值、近5分钟变化或30天基线",
                "key_driver_ids": ["只能填写输入conditions[label].drivers中的driver_id"],
                "supporting_evidence": ["最多1条支持证据"],
                "contradicting_evidence": ["最多1条矛盾证据，没有则空数组"],
                "attention_items": ["最多2条下一5分钟关注项"],
        "data_limits": ["仅填写服务端已确认的无可用数据项；已有当前值或趋势序列的传感器不算数据限制"],
                "guidance_summary": "不超过100个汉字；结合已有调剂动作和知识依据的只读指导",
                "recommendation_action_ids": ["只能填写输入中该炉况已有action id"],
                "knowledge_chunk_ids": ["只能填写输入中已有knowledge chunk id"],
                "risk_change": "rising|stable|falling|uncertain",
            }
        ]
    }
    user = (
        "请为8类炉况各返回且只返回一条分析，label不得遗漏或重复。"
        "每条判断都必须面向当前同一个5分钟诊断时间点。严格控制篇幅，整批JSON不要附加解释文字。\n"
        f"返回合同：{json.dumps(contract, ensure_ascii=False)}\n"
        f"诊断资料：{json.dumps(_prompt_five_minute_context(context), ensure_ascii=False, default=str)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def single_condition_prompt_version(target_label: str) -> str:
    """Return an isolated durable version key for one selected condition."""
    label = str(target_label or "")
    if label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("请选择有效的8类炉况")
    return f"{FIVE_MINUTE_PROMPT_VERSION}.{label}"


def build_single_condition_analysis_messages(
    context: Mapping[str, Any], target_label: str
) -> list[dict[str, str]]:
    """Build one compact prompt for only the condition selected by the foreman."""
    label = str(target_label or "")
    if label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("请选择有效的8类炉况")
    compact = _prompt_five_minute_context(context)
    selected = dict((compact.get("conditions") or {}).get(label) or {})
    selected_history = []
    for row in list(compact.get("diagnosis_history") or []):
        if not isinstance(row, Mapping):
            continue
        row_scores = row.get("scores")
        row_scores = row_scores if isinstance(row_scores, Mapping) else {}
        selected_history.append(
            {
                "diagnosis_ts": row.get("diagnosis_ts"),
                "main_label": row.get("main_label"),
                "target_score": row_scores.get(label),
            }
        )
    payload = {
        "diagnosis_ts": compact.get("diagnosis_ts"),
        "bucket_ts": compact.get("bucket_ts"),
        "bucket_minutes": compact.get("bucket_minutes"),
        "main_label": compact.get("main_label"),
        "data_coverage": compact.get("data_coverage"),
        "diagnosis_history": selected_history,
        "target_label": label,
        "target_display_name": DISPLAY_NAMES[label],
        "target_score_source": dict(
            (compact.get("score_sources") or {}).get(label) or {}
        ),
        "condition": selected,
        "knowledge_evidence": compact.get("knowledge_evidence"),
    }
    system = (
        "你是高炉炉况智能分析助手。本次只分析用户点击的一种炉况，不分析或撰写其他七种炉况。"
        "系统规则符合度不是概率，你只能解释既有分数，不能重算或覆盖规则分、主诊断、人工评分和安全门禁。"
        "只能使用输入中该炉况的公式驱动项、实测值、近5分钟变化、30天基线、调剂引擎只读动作和知识片段。"
        "请用高炉长容易理解的口语说明哪些项目升高、下降、偏离基线或未触发；数值必须原样来自输入。"
        "数据限制只能填写确实没有当前值和趋势序列的项目；已有有效当前值或60分钟序列的传感器，哪怕采样不是每分钟一条，也不得标为数据限制。"
        "建议只能引用输入中的action id和knowledge chunk id，不能新增动作、幅度、顺序、审批或生产控制；64主题知识库只作为只读依据，不调用三规二制调控引擎。"
        "正常顺行必须说明正常分数距离100分的差值、每个可用核心传感器的变化和基线偏离；详细数据卡由服务端追加。模型只提炼最关键的1至3个依据。只返回一个JSON对象，不要Markdown。"
    )
    contract = {
        "analysis": {
            "label": label,
            "verdict": "supported|possible|not_supported|insufficient_data",
            "model_support_score": "0-100整数；证据吻合度，不是概率",
            "summary": "不超过80个汉字的当前5分钟判断",
            "score_explanation": "不超过180个汉字；说明该炉况公式条目值、变化和基线如何支持或不支持当前分数",
            "key_driver_ids": ["只能填写condition.drivers中的driver_id"],
            "supporting_evidence": ["最多2条"],
            "contradicting_evidence": ["最多2条，没有则空数组"],
            "attention_items": ["最多3条下一5分钟关注项"],
        "data_limits": ["仅填写服务端已确认的无可用数据项；已有当前值或趋势序列的传感器不算数据限制"],
            "guidance_summary": "不超过180个汉字；结合已有调剂动作和知识依据的只读指导",
            "recommendation_action_ids": ["只能填写condition.recommendation.actions中的id"],
            "knowledge_chunk_ids": ["只能填写knowledge_evidence中的chunk_id"],
            "risk_change": "rising|stable|falling|uncertain",
        }
    }
    user = (
        f"只分析{DISPLAY_NAMES[label]}（{label}），禁止输出其他炉况的文案。\n"
        f"返回合同：{json.dumps(contract, ensure_ascii=False)}\n"
        f"该炉况资料：{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_five_minute_analysis_payload(
    text: str,
    context: Mapping[str, Any] | None = None,
    expected_labels: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Validate one complete eight-condition model response."""
    content = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content, flags=re.I)
    candidate = fenced.group(1) if fenced else content
    if not (candidate.startswith("{") and candidate.endswith("}")):
        start, end = candidate.find("{"), candidate.rfind("}")
        candidate = candidate[start : end + 1] if start >= 0 and end > start else ""
    if not candidate:
        raise ModelReviewValidationError("智能助手未返回结构化的8类炉况分析")
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ModelReviewValidationError("8类炉况分析JSON无法解析") from exc
    raw_analyses = payload.get("analyses") if isinstance(payload, Mapping) else None
    if not isinstance(raw_analyses, list) and isinstance(payload, Mapping):
        single = payload.get("analysis")
        if isinstance(single, Mapping):
            raw_analyses = [single]
    if not isinstance(raw_analyses, list):
        raise ModelReviewValidationError("智能助手没有返回analyses数组")

    expected = expected_labels or DIAGNOSIS_LABELS

    analyses: dict[str, dict[str, Any]] = {}
    for item in raw_analyses:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "")
        if label not in expected or label in analyses:
            raise ModelReviewValidationError("8类炉况分析包含无效或重复标签")
        verdict = str(item.get("verdict") or "")
        if verdict not in FIVE_MINUTE_VERDICTS:
            raise ModelReviewValidationError(f"{DISPLAY_NAMES[label]}的判断状态无效")
        support = _finite(item.get("model_support_score"))
        summary = _safe_text(item.get("summary"), 1200)
        score_explanation = _safe_text(item.get("score_explanation"), 2400)
        guidance_summary = _safe_text(item.get("guidance_summary"), 1800)
        if support is None or not summary or not score_explanation or not guidance_summary:
            raise ModelReviewValidationError(
                f"{DISPLAY_NAMES[label]}缺少支持分、分析摘要、分数解释或指导意见"
            )
        risk_change = str(item.get("risk_change") or "uncertain")
        if risk_change not in RISK_CHANGES:
            risk_change = "uncertain"
        key_driver_ids = _identifier_list(item.get("key_driver_ids"), limit=8)
        action_ids = _identifier_list(item.get("recommendation_action_ids"), limit=8)
        knowledge_ids = _identifier_list(item.get("knowledge_chunk_ids"), limit=8)
        if context is not None:
            drivers_by_label = context.get("rule_drivers")
            drivers_by_label = drivers_by_label if isinstance(drivers_by_label, Mapping) else {}
            allowed_driver_ids = {
                str(driver.get("driver_id"))
                for driver in (drivers_by_label.get(label) or [])
                if isinstance(driver, Mapping) and driver.get("driver_id")
            }
            recommendation_context = context.get("recommendation_context")
            recommendation_context = recommendation_context if isinstance(recommendation_context, Mapping) else {}
            condition_map = recommendation_context.get("conditions")
            condition_map = condition_map if isinstance(condition_map, Mapping) else {}
            condition = condition_map.get(label)
            condition = condition if isinstance(condition, Mapping) else {}
            allowed_action_ids = {
                str(action.get("id"))
                for action in (condition.get("actions") or [])
                if isinstance(action, Mapping) and action.get("id")
            }
            knowledge_context = context.get("knowledge_context")
            knowledge_context = knowledge_context if isinstance(knowledge_context, Mapping) else {}
            allowed_knowledge_ids = {
                str(chunk.get("chunk_id"))
                for chunk in (knowledge_context.get("evidence") or [])
                if isinstance(chunk, Mapping) and chunk.get("chunk_id")
            }
            unknown = (
                set(key_driver_ids).difference(allowed_driver_ids)
                | set(action_ids).difference(allowed_action_ids)
                | set(knowledge_ids).difference(allowed_knowledge_ids)
            )
            if unknown:
                raise ModelReviewValidationError(
                    f"{DISPLAY_NAMES[label]}引用了输入中不存在的证据ID"
                )
        analyses[label] = {
            "label": label,
            "display_name": DISPLAY_NAMES[label],
            "verdict": verdict,
            "model_support_score": int(round(max(0.0, min(100.0, support)))),
            "summary": summary,
            "score_explanation": score_explanation,
            "key_driver_ids": key_driver_ids,
            "supporting_evidence": _text_list(
                item.get("supporting_evidence"), limit=12
            ),
            "contradicting_evidence": _text_list(
                item.get("contradicting_evidence"), limit=12
            ),
            "attention_items": _text_list(item.get("attention_items"), limit=12),
            "data_limits": _text_list(item.get("data_limits"), limit=12),
            "guidance_summary": guidance_summary,
            "recommendation_action_ids": action_ids,
            "knowledge_chunk_ids": knowledge_ids,
            "risk_change": risk_change,
        }
    missing = [label for label in expected if label not in analyses]
    if missing:
        raise ModelReviewValidationError(
            "智能助手未完整返回8类炉况：" + ",".join(missing)
        )
    return {"analyses": [analyses[label] for label in expected]}


def parse_single_condition_analysis_payload(
    text: str, target_label: str, context: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a response that contains exactly the one requested condition."""
    label = str(target_label or "")
    if label not in DIAGNOSIS_LABELS:
        raise ModelReviewValidationError("请选择有效的8类炉况")
    parsed = parse_five_minute_analysis_payload(
        text, context=context, expected_labels=(label,)
    )
    return {"analysis": parsed["analyses"][0]}


def _enrich_five_minute_analysis(
    context: Mapping[str, Any], item: Mapping[str, Any]
) -> dict[str, Any]:
    label = str(item.get("label") or "")
    rule_drivers = context.get("rule_drivers")
    rule_drivers = rule_drivers if isinstance(rule_drivers, Mapping) else {}
    driver_rows = [
        dict(row)
        for row in (rule_drivers.get(label) or [])
        if isinstance(row, Mapping)
    ]
    requested_drivers = set(item.get("key_driver_ids") or [])
    selected_drivers = [
        row for row in driver_rows if row.get("driver_id") in requested_drivers
    ]
    if not selected_drivers:
        selected_drivers = [
            row
            for row in driver_rows
            if row.get("signal_state") in {"supporting", "not_supporting"}
        ][:5]
    if not selected_drivers:
        selected_drivers = driver_rows[:5]

    recommendation_context = context.get("recommendation_context")
    recommendation_context = recommendation_context if isinstance(recommendation_context, Mapping) else {}
    condition_map = recommendation_context.get("conditions")
    condition_map = condition_map if isinstance(condition_map, Mapping) else {}
    condition = condition_map.get(label)
    condition = condition if isinstance(condition, Mapping) else {}
    actions = [
        dict(row)
        for row in (condition.get("actions") or [])
        if isinstance(row, Mapping)
    ]
    requested_actions = set(item.get("recommendation_action_ids") or [])
    selected_actions = [row for row in actions if row.get("id") in requested_actions]
    if not selected_actions:
        selected_actions = [
            row
            for row in actions
            if row.get("status") in {"eligible", "manual_confirm"}
        ][:4]
    if not selected_actions:
        selected_actions = actions[:4]

    knowledge_context = context.get("knowledge_context")
    knowledge_context = knowledge_context if isinstance(knowledge_context, Mapping) else {}
    chunks = [
        dict(row)
        for row in (knowledge_context.get("evidence") or [])
        if isinstance(row, Mapping)
    ]
    requested_chunks = set(item.get("knowledge_chunk_ids") or [])
    selected_chunks = [
        row for row in chunks if row.get("chunk_id") in requested_chunks
    ]
    if not selected_chunks:
        selected_chunks = chunks[:3]

    enriched = dict(item)
    enriched["variable_evidence"] = selected_drivers[:8]
    enriched["sensor_deviation_summary"] = dict(
        context.get("sensor_deviation_summary") or {}
    )
    variable_stats = context.get("variable_stats")
    variable_stats = variable_stats if isinstance(variable_stats, Mapping) else {}
    # The model may describe evidence, but it does not own data-quality facts.
    # Replace its free-form data_limits with a server-owned result so sparse
    # yet usable minute series cannot be reported as missing data.
    enriched["data_limits"] = diag_ai_evidence.build_truthful_data_limits(
        label,
        driver_rows,
        variable_stats,
    )
    enriched["core_variable_evidence"] = diag_ai_evidence.build_core_variable_evidence(
        variable_stats, selected_drivers
    )
    enriched["core_variable_count"] = len(
        diag_ai_evidence.CORE_EVIDENCE_VARIABLES
    )
    enriched["core_series_window_minutes"] = 60
    enriched["recommendation_basis"] = {
        "available": bool(condition),
        "source_mode": recommendation_context.get("source_mode") or "foreman_knowledge_only",
        "source_doc_ids": list(
            (recommendation_context.get("engine_meta") or {}).get("source_doc_id")
            and [(recommendation_context.get("engine_meta") or {}).get("source_doc_id")]
            or []
        ),
        "engine_meta": dict(recommendation_context.get("engine_meta") or {}),
        "scope": condition.get("scope"),
        "goal": condition.get("goal"),
        "safety_gate_passed": condition.get("safety_gate_passed"),
        "safety_warnings": list(condition.get("safety_warnings") or []),
        "observe_items": list(condition.get("observe_items") or []),
        "recheck_minutes": condition.get("recheck_minutes"),
        "actions": selected_actions[:8],
        "read_only": True,
    }
    public_chunks: list[dict[str, Any]] = []
    for chunk in selected_chunks[:6]:
        public_chunk = dict(chunk)
        public_chunk.pop("content", None)
        public_chunk["detail_url"] = public_chunk.get("detail_url") or (
            f"/api/qa/knowledge/chunk?chunk_id={public_chunk.get('chunk_id')}&format=html"
            if public_chunk.get("chunk_id")
            else ""
        )
        public_chunks.append(public_chunk)
    enriched["knowledge_basis"] = {
        "available": bool(public_chunks),
        "source_doc_ids": [diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID],
        "source_mode": "foreman_knowledge_only",
        "retrieval_mode": knowledge_context.get("retrieval_mode"),
        "evidence": public_chunks,
        "read_only": True,
    }
    return enriched


def build_completed_five_minute_analysis(
    context: Mapping[str, Any],
    model_payload: Mapping[str, Any],
    *,
    public_model_name: str,
    snapshot_hash: str,
) -> dict[str, Any]:
    """Return the durable API/store representation for one five-minute batch."""
    return {
        "schema_version": FIVE_MINUTE_SCHEMA_VERSION,
        "prompt_version": FIVE_MINUTE_PROMPT_VERSION,
        "state": "completed",
        "furnace_id": context.get("furnace_id") or "BF",
        "snapshot_id": context.get("snapshot_id"),
        "snapshot_source": context.get("snapshot_source") or "live_readonly",
        "diagnosis_ts": context.get("diagnosis_ts"),
        "bucket_ts": context.get("bucket_ts"),
        "bucket_minutes": context.get("bucket_minutes") or 5,
        "main_label": context.get("main_label") or "normal",
        "scores": dict(context.get("scores") or {}),
        "analyses": [
            _enrich_five_minute_analysis(context, item)
            for item in (model_payload.get("analyses") or [])
            if isinstance(item, Mapping)
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "evidence_contract": {
            "variables": "diagnosis feature snapshot + read-only minute values + 30-day daily baseline",
            "recommendations": "64主题高炉长知识库候选建议，只读、人工确认",
            "knowledge": "PostgreSQL knowledge retrieval with source provenance",
            "no_score_rewrite": True,
            "no_control_write": True,
        },
        "score_semantics": "规则符合度与模型证据吻合度，均不是概率",
        "model_meta": {
            "public_name": public_model_name,
            "snapshot_hash": snapshot_hash,
            "prompt_version": FIVE_MINUTE_PROMPT_VERSION,
        },
    }


def build_fixture_five_minute_analysis(
    context: Mapping[str, Any], *, bucket_minutes: int = 5
) -> dict[str, Any]:
    """Return deterministic loopback-only fixture output without calling a model."""
    normalized = normalize_five_minute_context(
        context, [], bucket_minutes=bucket_minutes
    )
    normalized.update(diag_ai_evidence.build_fixture_enrichment(normalized))
    analyses = []
    for label in DIAGNOSIS_LABELS:
        rule_score = int(round(float(normalized["scores"].get(label, 0.0))))
        driver_ids = [
            row.get("driver_id")
            for row in (normalized.get("rule_drivers", {}).get(label) or [])[:4]
            if isinstance(row, Mapping) and row.get("driver_id")
        ]
        condition = (
            normalized.get("recommendation_context", {})
            .get("conditions", {})
            .get(label, {})
        )
        action_ids = [
            row.get("id")
            for row in (condition.get("actions") or [])[:2]
            if isinstance(row, Mapping) and row.get("id")
        ]
        analyses.append(
            {
                "label": label,
                "display_name": DISPLAY_NAMES[label],
                "verdict": "supported" if label == normalized["main_label"] else "possible",
                "model_support_score": rule_score,
                "summary": f"本机测试场景：当前资料对{DISPLAY_NAMES[label]}的规则符合度为{rule_score}分。",
                "score_explanation": "本机测试场景按规则变量、近5分钟变化和30天测试基线生成口语化说明；所有数值均明确标记为测试资料。",
                "key_driver_ids": driver_ids,
                "supporting_evidence": ["使用固定测试诊断分和测试证据"],
                "contradicting_evidence": [],
                "attention_items": ["该结果只用于页面交互验收"],
                "data_limits": ["本机测试场景不代表真实生产炉况"],
                "guidance_summary": "先核对变量趋势和现场现象，再按小幅、分步、观察反馈原则处理；测试场景不形成生产操作指令。",
                "recommendation_action_ids": action_ids,
                "knowledge_chunk_ids": ["fixture-three-rules"],
                "risk_change": "uncertain",
            }
        )
    return build_completed_five_minute_analysis(
        normalized,
        {"analyses": analyses},
        public_model_name="高炉大模型服务",
        snapshot_hash="local-fixture",
    )


class DiagnosisModelReviewCache:
    """Small thread-safe TTL cache keyed by diagnosis snapshot and selected condition."""

    def __init__(self, ttl_seconds: float = 900.0, max_items: int = 128) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_items = max(8, int(max_items))
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a defensive copy of an unexpired cached review."""
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            created, value = item
            if now - created > self.ttl_seconds:
                self._items.pop(key, None)
                return None
            result = copy.deepcopy(value)
        result.setdefault("model_meta", {})["cache_hit"] = True
        return result

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        """Store one review and evict the oldest entry when the bound is reached."""
        now = time.monotonic()
        with self._lock:
            if len(self._items) >= self.max_items:
                oldest = min(self._items, key=lambda item_key: self._items[item_key][0])
                self._items.pop(oldest, None)
            self._items[key] = (now, copy.deepcopy(dict(value)))

    def clear(self) -> None:
        """Clear cached reviews for isolated tests or controlled service maintenance."""
        with self._lock:
            self._items.clear()
