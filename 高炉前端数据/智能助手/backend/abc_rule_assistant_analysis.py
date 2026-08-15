from __future__ import annotations

"""Authoritative ABC-rule context adapter for contextual QA conversations.

REQ-ABC-CONTEXTUAL-QA-20260811: callers pass identifiers only. This module
reloads the corresponding database row and delegates canonical formatting to
``自动诊断服务/abc_rule_explanation.py``.
"""

import json
import re
from collections.abc import Mapping
from typing import Any


INITIAL_ANALYSIS_FIELDS = (
    "summary",
    "score_explanation",
    "process_interpretation",
    "recommended_sequence",
    "data_limits",
    "safety_notes",
    "suggested_questions",
    "context_citations",
)


class InitialAnalysisValidationError(ValueError):
    """The model response does not satisfy the read-only ABC explanation contract."""


def _contract() -> Any:
    import abc_rule_explanation

    return abc_rule_explanation


def _row_dict(row: Any, fallback_columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip(fallback_columns, row, strict=False))


def load_authoritative_evaluation(
    conn: Any,
    *,
    rule_id: str,
    evaluation_id: int,
) -> dict[str, Any] | None:
    """Load one immutable rule evaluation from the ABC runtime tables."""
    row = conn.execute(
        """
        SELECT i.*, b.evaluation_ts, b.catalog_version, b.config_version,
               b.config_hash, b.source_snapshot_id, b.furnace_id,
               b.data_age_seconds
        FROM bf_sensor.abc_rule_evaluation_items i
        JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id = i.batch_id
        WHERE i.batch_id = %s AND i.rule_id = %s
        LIMIT 1
        """,
        (evaluation_id, rule_id),
    ).fetchone()
    if row is None:
        return None
    result = _row_dict(
        row,
        (
            "id", "batch_id", "rule_id", "category", "display_name",
            "score", "confidence", "status", "weights", "normalized_values",
            "contributions", "missing_features", "public_detail", "evaluation_ts",
            "catalog_version", "config_version", "config_hash",
            "source_snapshot_id", "furnace_id", "data_age_seconds",
        ),
    )
    for key in (
        "formula_terms", "weights", "thresholds", "normalized_values",
        "contributions", "missing_features", "public_detail",
    ):
        value = result.get(key)
        if isinstance(value, str):
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = {} if key in {"weights", "thresholds", "normalized_values", "public_detail"} else []
    public_detail = result.get("public_detail")
    if isinstance(public_detail, Mapping):
        result = {**dict(public_detail), **result}
    contributions = result.get("contributions")
    if result.get("risk_score") is None and isinstance(contributions, list):
        usable = [item for item in contributions if isinstance(item, Mapping)]
        try:
            available_weight = sum(float(item.get("weight") or 0) for item in usable)
            weighted_points = sum(float(item.get("contribution") or 0) for item in usable)
            if available_weight > 0:
                result["risk_score"] = 100.0 * weighted_points / available_weight
        except (TypeError, ValueError, OverflowError):
            pass
    if result.get("raw_formula_score") is None and result.get("risk_score") is not None:
        risk_score = float(result["risk_score"])
        result["raw_formula_score"] = 100.0 - risk_score if str(result.get("category")) == "A" else risk_score
    result["evaluation_id"] = result.get("batch_id", evaluation_id)
    result["rule_id"] = str(result.get("rule_id") or rule_id)
    return result


def build_context_artifacts(
    evaluation: Mapping[str, Any],
    *,
    spec: Any = None,
) -> dict[str, Any]:
    """Build operator and assistant views through the shared ABC contract."""
    contract = _contract()
    operator = contract.build_operator_explanation_context(evaluation, spec=spec)
    assistant = contract.build_assistant_context(operator)
    context_hash = contract.canonical_context_hash(assistant)
    return {
        "operator_explanation": operator,
        "assistant_context": assistant,
        "context_hash": str(context_hash),
    }


def canonical_json(value: Any) -> str:
    """Serialize contract payloads consistently for PostgreSQL text columns."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def bounded_prompt_context(
    assistant_context: Mapping[str, Any],
    *,
    max_bytes: int = 24 * 1024,
) -> dict[str, Any]:
    """Keep every formula term while bounding verbose sensor/baseline evidence."""
    payload = json.loads(canonical_json(assistant_context))
    if len(canonical_json(payload).encode("utf-8")) <= max_bytes:
        return payload
    calculation = payload.get("calculation") if isinstance(payload.get("calculation"), dict) else {}
    terms = calculation.get("terms") if isinstance(calculation.get("terms"), list) else []
    for term in terms:
        if not isinstance(term, dict):
            continue
        term["source_values"] = {}
        term["source_features"] = {}
        term["baseline_snapshot"] = {}
    data_quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    data_quality["truncation"] = {
        "applied": True,
        "reason": "prompt_context_byte_limit",
        "preserved": "all_formula_terms_and_process_guidance",
    }
    payload["data_quality"] = data_quality
    size = len(canonical_json(payload).encode("utf-8"))
    if size > max_bytes:
        raise ValueError("assistant prompt context exceeds configured byte limit")
    return payload


def context_summary(operator_explanation: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact, stable summary suitable for conversation lists."""
    rule = operator_explanation.get("rule") if isinstance(operator_explanation.get("rule"), Mapping) else {}
    evaluation = (
        operator_explanation.get("evaluation")
        if isinstance(operator_explanation.get("evaluation"), Mapping)
        else {}
    )
    return {
        "schema_version": operator_explanation.get("schema_version"),
        "rule_id": rule.get("rule_id"),
        "evaluation_id": evaluation.get("evaluation_id"),
        "evaluation_ts": evaluation.get("evaluation_ts"),
        "display_name": rule.get("display_name"),
        "status": rule.get("status"),
        "score": rule.get("score"),
    }


def initial_analysis_prompt(assistant_context: Mapping[str, Any]) -> str:
    """Return strict JSON-only instructions derived from one immutable context."""
    terms = (assistant_context.get("calculation") or {}).get("terms") or []
    term_ids = [str(item.get("term_id")) for item in terms if isinstance(item, Mapping) and item.get("term_id")]
    citations = [
        "/rule", "/evaluation", "/process_guidance", "/data_quality",
        "/sensor_review", "/assistant_policy",
        *[f"/calculation/terms/{term_id}" for term_id in term_ids],
    ]
    sequence = list((assistant_context.get("process_guidance") or {}).get("intervention_order") or [])
    return (
        "本轮是ABC规则首次解释。只输出一个JSON对象，不要Markdown代码栏或额外文字。"
        f"顶层必须且只能有{list(INITIAL_ANALYSIS_FIELDS)}。"
        "score_explanation为对象数组，每项必须且只能有term_id和explanation两个字段；"
        f"term_id只能来自{term_ids}。"
        "summary和process_interpretation为字符串；其余字段均为字符串数组。"
        f"recommended_sequence必须原样复制为{sequence}，不得调换、改写或新增处置。"
        f"context_citations只能使用{citations}。"
        "不得写入上下文中不存在的任何数值。C类规则safety_notes必须非空。"
    )


def initial_analysis_json_schema(assistant_context: Mapping[str, Any]) -> dict[str, Any]:
    """Build the Ollama structured-output schema from authoritative context only."""
    terms = (assistant_context.get("calculation") or {}).get("terms") or []
    term_ids = [
        str(item.get("term_id"))
        for item in terms
        if isinstance(item, Mapping) and item.get("term_id")
    ]
    citations = [
        "/rule", "/evaluation", "/process_guidance", "/data_quality",
        "/sensor_review", "/assistant_policy",
        *[f"/calculation/terms/{term_id}" for term_id in term_ids],
    ]
    sequence = list((assistant_context.get("process_guidance") or {}).get("intervention_order") or [])
    string_array: dict[str, Any] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }
    safety_schema = dict(string_array)
    if str((assistant_context.get("rule") or {}).get("category") or "") == "C":
        safety_schema["minItems"] = 1
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(INITIAL_ANALYSIS_FIELDS),
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "score_explanation": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["term_id", "explanation"],
                    "properties": {
                        "term_id": {"type": "string", "enum": term_ids},
                        "explanation": {"type": "string", "minLength": 1},
                    },
                },
            },
            "process_interpretation": {"type": "string", "minLength": 1},
            "recommended_sequence": {"const": sequence},
            "data_limits": dict(string_array),
            "safety_notes": safety_schema,
            "suggested_questions": dict(string_array),
            "context_citations": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "enum": citations},
            },
        },
    }


def initial_analysis_repair_messages(
    messages: list[dict[str, str]],
    candidate: Any,
    error: Exception,
) -> list[dict[str, str]]:
    """Request one clean regeneration without changing or patching model semantics."""
    compact_error = re.sub(r"\s+", " ", str(error or "validation failed")).strip()[:320]
    candidate_text = str(candidate or "")[:12_000]
    return [
        *messages,
        {"role": "assistant", "content": candidate_text},
        {
            "role": "user",
            "content": (
                "上一候选未通过严格校验。只重新生成完整JSON对象，不要解释校验过程，"
                "不要修改权威处置顺序，不要新增数值、term_id或引用路径。"
                f"校验错误：{compact_error}"
            ),
        },
    ]


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InitialAnalysisValidationError("initial analysis is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise InitialAnalysisValidationError("initial analysis must be a JSON object")
    return dict(parsed)


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise InitialAnalysisValidationError(f"{field} must be an array of non-empty strings")
    return [item.strip() for item in value]


def validate_initial_analysis(value: Any, assistant_context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate model JSON without allowing new evidence, numbers, terms or actions."""
    parsed = _parse_json_object(value)
    if set(parsed) != set(INITIAL_ANALYSIS_FIELDS):
        raise InitialAnalysisValidationError("initial analysis fields do not match the contract")
    for field in ("summary", "process_interpretation"):
        if not isinstance(parsed[field], str) or not parsed[field].strip():
            raise InitialAnalysisValidationError(f"{field} must be a non-empty string")
        parsed[field] = parsed[field].strip()
    terms = (assistant_context.get("calculation") or {}).get("terms") or []
    term_ids = {str(item.get("term_id")) for item in terms if isinstance(item, Mapping) and item.get("term_id")}
    explanations = parsed["score_explanation"]
    if not isinstance(explanations, list) or not explanations:
        raise InitialAnalysisValidationError("score_explanation must be non-empty")
    seen: set[str] = set()
    for item in explanations:
        if not isinstance(item, Mapping) or set(item) != {"term_id", "explanation"}:
            raise InitialAnalysisValidationError("invalid score_explanation item")
        term_id = str(item.get("term_id") or "")
        if term_id not in term_ids or term_id in seen:
            raise InitialAnalysisValidationError("score_explanation contains an unknown or duplicate term_id")
        if not isinstance(item.get("explanation"), str) or not item["explanation"].strip():
            raise InitialAnalysisValidationError("score explanation text is empty")
        seen.add(term_id)
    for field in ("recommended_sequence", "data_limits", "safety_notes", "suggested_questions", "context_citations"):
        parsed[field] = _strings(parsed[field], field)
    expected_sequence = list((assistant_context.get("process_guidance") or {}).get("intervention_order") or [])
    if parsed["recommended_sequence"] != expected_sequence:
        raise InitialAnalysisValidationError("recommended_sequence changed the authoritative intervention order")
    allowed_citations = {
        "/rule", "/evaluation", "/process_guidance", "/data_quality", "/sensor_review", "/assistant_policy",
        *{f"/calculation/terms/{term_id}" for term_id in term_ids},
    }
    if not parsed["context_citations"] or any(item not in allowed_citations for item in parsed["context_citations"]):
        raise InitialAnalysisValidationError("context_citations contains an unsupported path")
    category = str((assistant_context.get("rule") or {}).get("category") or "")
    if category == "C" and (
        not parsed["safety_notes"]
        or not any(
            token in "".join(parsed["safety_notes"])
            for token in ("安全", "确认", "审批", "制度", "风险")
        )
    ):
        raise InitialAnalysisValidationError("C-category analysis requires an explicit safety note")
    source_numbers = set(re.findall(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?![A-Za-z_])", canonical_json(assistant_context)))
    output_numbers = set(re.findall(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?![A-Za-z_])", canonical_json(parsed)))
    if not output_numbers.issubset(source_numbers):
        raise InitialAnalysisValidationError("analysis introduced a number absent from the context")
    return parsed


def render_initial_analysis(value: Mapping[str, Any]) -> str:
    """Render validated JSON as concise operator-facing Markdown."""
    lines = [str(value["summary"]), "", "评分形成："]
    lines.extend(f"- {item['explanation']}" for item in value["score_explanation"])
    lines.extend(["", "过程解读：", str(value["process_interpretation"]), "", "建议顺序："])
    lines.extend(f"- {item}" for item in value["recommended_sequence"])
    for title, field in (("数据边界", "data_limits"), ("安全提示", "safety_notes"), ("可继续追问", "suggested_questions")):
        lines.extend(["", f"{title}："])
        lines.extend(f"- {item}" for item in value[field])
    return "\n".join(lines).strip()
