"""Server-side policy for model-planned MCP tool calls.

The model may choose business tools and arguments, but this module keeps the
execution boundary deterministic: only advertised tools and schema-declared
arguments can reach MCP.

Requirement: REQ-MCP-AGENT-ORCHESTRATION-20260726
Planning: PT/MCP受控自主工具编排规划与通用流程.md
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolPolicyLimits:
    """Generic limits applied before a model-planned MCP call is executed."""

    max_argument_chars: int = 12_000
    max_array_items: int = 80
    max_string_chars: int = 2_000


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _schema_types(schema: dict[str, Any]) -> list[str]:
    raw = schema.get("type")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    types: list[str] = []
    for key in ("anyOf", "oneOf"):
        for option in schema.get(key) or []:
            if isinstance(option, dict):
                types.extend(_schema_types(option))
    return list(dict.fromkeys(types))


def _validate_value(
    value: Any,
    schema: dict[str, Any],
    path: str,
    limits: ToolPolicyLimits,
    errors: list[dict[str, str]],
) -> None:
    allowed_types = _schema_types(schema)
    if allowed_types and not any(_matches_type(value, item) for item in allowed_types):
        errors.append(
            {
                "code": "TYPE_MISMATCH",
                "path": path,
                "message": f"参数类型不符合 Schema，期望 {allowed_types}",
            }
        )
        return
    if isinstance(value, str):
        max_length = min(int(schema.get("maxLength") or limits.max_string_chars), limits.max_string_chars)
        if len(value) > max_length:
            errors.append({"code": "STRING_TOO_LONG", "path": path, "message": f"字符串超过 {max_length} 字符"})
        enum = schema.get("enum")
        if enum and value not in enum:
            errors.append({"code": "ENUM_MISMATCH", "path": path, "message": f"只允许 {enum}"})
    elif isinstance(value, list):
        max_items = min(int(schema.get("maxItems") or limits.max_array_items), limits.max_array_items)
        if len(value) > max_items:
            errors.append({"code": "ARRAY_TOO_LARGE", "path": path, "message": f"数组超过 {max_items} 项"})
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value[: max_items + 1]):
                _validate_value(item, item_schema, f"{path}[{index}]", limits, errors)
    elif isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append({"code": "MISSING_REQUIRED", "path": f"{path}.{key}", "message": "缺少必填参数"})
        for key, item in value.items():
            child_schema = properties.get(key)
            if not isinstance(child_schema, dict):
                errors.append(
                    {
                        "code": "UNKNOWN_ARGUMENT",
                        "path": f"{path}.{key}",
                        "message": "参数未在工具 Schema 中声明",
                    }
                )
                continue
            _validate_value(item, child_schema, f"{path}.{key}", limits, errors)


def validate_tool_call(
    tool_name: str,
    arguments: Any,
    tool_schemas: dict[str, dict[str, Any]],
    limits: ToolPolicyLimits | None = None,
) -> dict[str, Any]:
    """Validate one model-planned call against the live MCP tool catalog."""

    limits = limits or ToolPolicyLimits()
    if tool_name not in tool_schemas:
        return {
            "ok": False,
            "error": "UNKNOWN_TOOL",
            "tool": tool_name,
            "errors": [{"code": "UNKNOWN_TOOL", "path": "tool", "message": "工具不在当前 MCP 白名单"}],
        }
    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "error": "ARGUMENTS_NOT_OBJECT",
            "tool": tool_name,
            "errors": [{"code": "ARGUMENTS_NOT_OBJECT", "path": "arguments", "message": "工具参数必须是 JSON 对象"}],
        }
    encoded = json.dumps(arguments, ensure_ascii=False, default=str)
    if len(encoded) > limits.max_argument_chars:
        return {
            "ok": False,
            "error": "ARGUMENTS_TOO_LARGE",
            "tool": tool_name,
            "errors": [
                {
                    "code": "ARGUMENTS_TOO_LARGE",
                    "path": "arguments",
                    "message": f"参数 JSON 超过 {limits.max_argument_chars} 字符",
                }
            ],
        }
    errors: list[dict[str, str]] = []
    _validate_value(arguments, tool_schemas[tool_name] or {"type": "object"}, "arguments", limits, errors)
    return {
        "ok": not errors,
        "error": errors[0]["code"] if errors else None,
        "tool": tool_name,
        "arguments": arguments,
        "errors": errors,
        "policy": "live_mcp_schema_readonly",
    }
