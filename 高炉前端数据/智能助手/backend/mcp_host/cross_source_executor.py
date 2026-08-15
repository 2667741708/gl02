"""DAG executor for CrossSourcePlan instances.

Requirement: REQ-8093-CROSS-SOURCE-MCP-20260805

Executes a CrossSourcePlan with these rules:

* Different server_ids → concurrent within a topology layer.
* Same server_id → serial (service-level asyncio.Lock).
* Each step: policy validation → 30 s cache → MCP call (15 s timeout).
* argument_bindings resolve upstream step results before execution.
* Dependency failure → downstream steps skipped with DEPENDENCY_FAILED.
* Budget exhaustion → CROSS_SOURCE_BUDGET_EXCEEDED.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from typing import Any

from mcp_host.cross_source_plan import (
    CrossSourceFact,
    CrossSourcePlan,
    CrossSourceSnapshot,
    CrossSourceStep,
    failed_snapshot,
    partial_snapshot,
    success_snapshot,
)


# Authoritative public units for canonical GL02 variables whose legacy MCP
# payload may omit variable.unit. This mirrors the established assistant
# evidence contract and must not be extended by guessing from value shape.
_CANONICAL_UNIT_FALLBACKS: dict[str, str] = {
    "P_top": "kPa",
    "DP_total": "kPa",
    "L_south": "m",
    "L_north": "m",
    "P_top_A": "kPa",
    "P_top_B": "kPa",
    "P_top_C": "kPa",
    "P_top_D": "kPa",
    "P_blast_cold": "kPa",
    "Q_O2": "Nm³/h",
    "O2_rate": "%",
}

# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

ERROR_CODES = {
    "PLAN_CONTRACT_INVALID": "内部计划合同无效",
    "TOOL_SCHEMA_REJECTED": "工具参数未通过Schema策略校验",
    "SOURCE_SERVER_UNAVAILABLE": "数据源服务不可用",
    "SOURCE_TIMEOUT": "数据源查询超时",
    "DEPENDENCY_FAILED": "上游依赖步骤失败，跳过执行",
    "CROSS_SOURCE_BUDGET_EXCEEDED": "跨源执行总预算已用尽",
    "PARTIAL_DATA": "部分数据源返回空结果",
    "ANALYSIS_SKIPPED_INCOMPLETE_EVIDENCE": "证据不完整，跳过分析",
}


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _topological_layers(steps: tuple[CrossSourceStep, ...]) -> list[list[CrossSourceStep]]:
    """Group steps into layers so that all dependencies of a step are in earlier layers.

    Raises ValueError on cyclic dependencies.
    """
    step_map: dict[str, CrossSourceStep] = {s.step_id: s for s in steps}
    in_degree: dict[str, int] = {s.step_id: len(s.depends_on) for s in steps}
    dependents: dict[str, list[str]] = defaultdict(list)
    for s in steps:
        for dep in s.depends_on:
            dependents[dep].append(s.step_id)

    layers: list[list[CrossSourceStep]] = []
    remaining = set(in_degree)

    while remaining:
        ready = sorted(
            [sid for sid in remaining if in_degree[sid] == 0]
        )
        if not ready:
            cycle_candidates = ", ".join(sorted(remaining))
            raise ValueError(
                f"Cyclic dependency detected among steps: {cycle_candidates}"
            )
        layer_steps = [step_map[sid] for sid in ready]
        layers.append(layer_steps)
        for sid in ready:
            remaining.remove(sid)
            for dep_sid in dependents[sid]:
                in_degree[dep_sid] -= 1

    return layers


# ---------------------------------------------------------------------------
# Argument binding resolution
# ---------------------------------------------------------------------------


def _resolve_argument_bindings(
    step: CrossSourceStep,
    upstream_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve argument_bindings by walking dotted paths into upstream step results.

    Only ``steps.<step_id>.<field>.*`` paths are accepted.  The binding value
    is extracted via dict-key traversal; missing keys produce ``None``.
    """
    if not step.argument_bindings:
        return dict(step.arguments)

    resolved = dict(step.arguments)
    for arg_name, binding_path in step.argument_bindings.items():
        parts = binding_path.split(".")
        if parts[0] != "steps" or len(parts) < 3:
            raise ValueError(
                f"Invalid argument_binding path {binding_path!r} in step {step.step_id!r}"
            )
        upstream_id = parts[1]
        if upstream_id not in upstream_results:
            raise ValueError(
                f"Step {step.step_id!r} depends on {upstream_id!r} but no result available"
            )
        # Upstream status keeps the MCP payload in ``result_text``.  Expose
        # decoded payload keys alongside status metadata so a dependency such
        # as ``steps.resolve_heat.resolved_heat_no`` binds the formal meltno
        # instead of silently producing an empty argument object.
        upstream = upstream_results[upstream_id]
        payload = _json_payload(str(upstream.get("result_text") or "")) if isinstance(upstream, dict) else {}
        value = {**payload, **(upstream if isinstance(upstream, dict) else {})}
        for key in parts[2:]:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                value = None
                break
        # Keep a validated explicit fallback (for example the spoken short
        # meltno ``072``) when an upstream resolver returned no value. The
        # downstream IMES tool performs the same strict 72-hour resolution and
        # will return a precise NOT_FOUND/AMBIGUOUS error instead of receiving
        # an invalid ``null`` argument.
        if value is not None or arg_name not in resolved or resolved[arg_name] in (None, ""):
            resolved[arg_name] = value
    return resolved


# ---------------------------------------------------------------------------
# Per-step execution
# ---------------------------------------------------------------------------


async def _execute_step(
    step: CrossSourceStep,
    upstream_results: dict[str, dict[str, Any]],
    session,  # MCP execution scope
    tool_schemas: dict[str, dict[str, Any]],
    tool_servers: dict[str, dict[str, Any]],
    policy_limits,
    tool_cache_get,
    tool_cache_put,
    emit,
    orchestration_id: str,
    budget_remaining: float,
    child_timeout: float,
) -> dict[str, Any]:
    """Execute one CrossSourceStep and return a source_status dict."""

    step_start = time.monotonic()
    status: dict[str, Any] = {
        "step_id": step.step_id,
        "server_id": step.server_id,
        "tool": step.tool,
        "required_for_answer": step.required_for_answer,
        "required_for_analysis": step.required_for_analysis,
        "ok": False,
        "elapsed_ms": 0.0,
        "cache_hit": False,
        "error_code": None,
    }

    # Check budget
    if budget_remaining <= 0:
        status["error_code"] = "CROSS_SOURCE_BUDGET_EXCEEDED"
        status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
        return status

    # Check dependency failures
    for dep_id in step.depends_on:
        dep_result = upstream_results.get(dep_id, {})
        if not dep_result.get("ok"):
            status["error_code"] = "DEPENDENCY_FAILED"
            status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
            return status

    # Resolve arguments
    try:
        resolved_args = _resolve_argument_bindings(step, upstream_results)
    except ValueError as exc:
        status["error_code"] = "PLAN_CONTRACT_INVALID"
        status["error_message"] = str(exc)
        status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
        return status

    # Policy validation
    from mcp_tool_policy import validate_tool_call

    policy = validate_tool_call(step.tool, resolved_args, tool_schemas, policy_limits)
    if not policy["ok"]:
        status["error_code"] = (
            "SOURCE_SERVER_UNAVAILABLE"
            if step.tool not in tool_schemas
            else "TOOL_SCHEMA_REJECTED"
        )
        status["policy_errors"] = policy.get("errors", [])
        status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
        return status

    # Emit tool_start
    tool_name = step.tool
    if emit:
        emit("tool_start", {
            "tool": tool_name,
            "arguments": resolved_args,
            "orchestration_id": orchestration_id,
            "step_id": step.step_id,
            "required_for_analysis": step.required_for_analysis,
            "elapsed_ms": 0,
        })

    # Cache check
    cache_key = _cache_key(tool_name, resolved_args)
    result_text = tool_cache_get(tool_name, resolved_args)
    cache_hit = result_text is not None

    if cache_hit:
        status["ok"] = True
        status["cache_hit"] = True
        status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
        status["result_text"] = result_text
    else:
        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, resolved_args),
                timeout=min(child_timeout, budget_remaining),
            )
            result_text = _mcp_result_to_text(result)
            tool_cache_put(tool_name, resolved_args, result_text)
            status["ok"] = True
            status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
            status["result_text"] = result_text
        except asyncio.TimeoutError:
            status["error_code"] = "SOURCE_TIMEOUT"
            status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
            result_text = json.dumps({
                "ok": False,
                "error": "SOURCE_TIMEOUT",
                "message": f"步骤 {step.step_id} 超时（{child_timeout:.0f}秒）",
            }, ensure_ascii=False)
        except Exception as exc:
            status["error_code"] = "SOURCE_SERVER_UNAVAILABLE"
            status["error_message"] = str(exc)
            status["elapsed_ms"] = (time.monotonic() - step_start) * 1000
            result_text = json.dumps({
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }, ensure_ascii=False)

    result_payload = _json_payload(result_text)
    payload_error = result_payload.get("error_code") or result_payload.get("error")
    resolver_missing = (
        step.tool == "imes__resolve_spoken_heat_reference"
        and not result_payload.get("resolved_heat_no")
    )
    if result_payload.get("ok") is False or result_payload.get("missing") is True or resolver_missing:
        status["ok"] = False
        status["error_code"] = str(payload_error or "DATA_MISSING")

    # Emit tool_result
    status["arguments"] = resolved_args
    if emit:
        emit("tool_result", {
            "tool": tool_name,
            "orchestration_id": orchestration_id,
            "step_id": step.step_id,
            "required_for_analysis": step.required_for_analysis,
            "elapsed_ms": status["elapsed_ms"],
            "cache_hit": cache_hit,
            "ok": status["ok"],
            "server_id": step.server_id,
            "result": _compact_result(result_text),
        })

    return status


def _cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
    import json as _json
    normalized = _json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    return f"{tool_name}:{normalized}"


def _mcp_result_to_text(result) -> str:
    """Convert MCP call result to text, matching proxy's mcp_result_to_text."""
    if result is None:
        return ""
    if hasattr(result, "content"):
        parts = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "data"):
                parts.append(str(item.data))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(result)


def _compact_result(result_text: str) -> dict[str, Any]:
    """Compact a result for SSE events (matching proxy's pattern)."""
    try:
        payload = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": result_text[:500] if result_text else ""}
    if not isinstance(payload, dict):
        return {"raw": str(payload)[:500]}
    compact: dict[str, Any] = {}
    for key in ("ok", "count", "success_count", "sample_count", "missing",
                "error", "error_code", "message", "image_url", "as_of_time",
                "current_heat_no", "previous_heat_no", "resolved_heat_no"):
        if key in payload:
            compact[key] = payload[key]
    # Truncate long list fields
    for key in ("variables", "rows"):
        if key in payload:
            val = payload[key]
            if isinstance(val, list) and len(val) > 3:
                compact[key] = f"[{len(val)} items]"
            else:
                compact[key] = val
    return compact


def _json_payload(result_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(result_text or "")
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fact_payload_status(
    payload: dict[str, Any],
    fact_id: str,
    step: CrossSourceStep,
) -> tuple[bool, str | None]:
    """Return (missing, error_code) using per-item MCP semantics."""

    if not payload:
        return True, "EMPTY_RESULT"
    if payload.get("ok") is False:
        return True, str(payload.get("error_code") or payload.get("error") or "DATA_MISSING")
    if step.tool == "imes__get_current_previous_heat_si_summary":
        if fact_id in {"current_heat_no", "previous_heat_no", "sample_count"}:
            return (not bool(payload.get(fact_id))), "DATA_MISSING" if not payload.get(fact_id) else None
        if payload.get("missing") is True:
            return True, str(payload.get("error_code") or "NO_SI_SAMPLES")
    elif payload.get("missing") is True:
        return True, str(payload.get("error_code") or payload.get("error") or "DATA_MISSING")

    if step.tool in {"query_gl02_sensors", "gl02ext__query_body_temperature"}:
        items = payload.get("items") or payload.get("results") or []
        if not isinstance(items, list) or not items:
            return True, "NO_SENSOR_ITEMS"
        matched = None
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("requested_variable") or item.get("variable")
            if name == fact_id:
                matched = item
                break
        if matched is None:
            # A body-temperature adapter returns variable names in `results`.
            matched = next(
                (item for item in items if str(item.get("variable") or "") == fact_id),
                None,
            )
        if not matched:
            return True, "VARIABLE_NOT_RETURNED"
        if matched.get("ok") is False:
            return True, str(matched.get("error_code") or matched.get("error") or "DATA_MISSING")
        latest = matched.get("latest") or {}
        if latest and latest.get("ok") is False:
            return True, str(latest.get("error_code") or latest.get("error") or "DATA_MISSING")
        if not latest and not (matched.get("statistics") or matched.get("history")):
            return True, "EMPTY_SENSOR_VALUE"
        return False, None

    if step.tool == "gl02ext__query_body_temperature_statistics":
        layer_statistics = payload.get("layer_statistics") or []
        if fact_id != "body_temperature_statistics" or not isinstance(layer_statistics, list):
            return True, "VARIABLE_NOT_RETURNED"
        if not any(
            isinstance(item, dict) and ((item.get("statistics") or {}).get("count") or 0) > 0
            for item in layer_statistics
        ):
            return True, "NO_SENSOR_ITEMS"
        return False, None

    if step.tool == "plot_gl02_analysis":
        correlation = (payload.get("derived") or {}).get("correlation") or {}
        correlation_values = {
            "pearson_r": correlation.get("pearson_r"),
            "aligned_count": correlation.get("aligned_count"),
            "correlation_left": correlation.get("left"),
            "correlation_right": correlation.get("right"),
            "correlation_window": payload.get("start_time") and payload.get("end_time"),
        }
        if fact_id == "chart":
            return (not bool(payload.get("image_url"))), "DATA_MISSING" if not payload.get("image_url") else None
        if fact_id in correlation_values:
            value = correlation_values[fact_id]
            return (value is None or value is False), "DATA_MISSING" if value is None or value is False else None

    return False, None


def _extract_heat_reference(
    plan: CrossSourcePlan,
    upstream_results: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Preserve resolved official meltno metadata in the snapshot."""

    for step in plan.steps:
        status = upstream_results.get(step.step_id) or {}
        payload = _json_payload(status.get("result_text", ""))
        if payload.get("resolved_heat_no") or payload.get("requested_heat_reference"):
            return {
                key: payload.get(key)
                for key in (
                    "requested_heat_reference", "requested_heat_no", "resolved_heat_no",
                    "resolution_policy", "heat_context_missing", "heat_time_window",
                    "error_code", "candidates",
                )
                if payload.get(key) is not None
            }
    ref = plan.requested_heat_reference
    if isinstance(ref, dict):
        return dict(ref)
    if ref:
        return {"requested_heat_reference": ref}
    return None


# ---------------------------------------------------------------------------
# Main executor entry point
# ---------------------------------------------------------------------------


async def execute_cross_source_plan(
    plan: CrossSourcePlan,
    manager,  # McpClientManager
    session,  # MCP execution scope
    tool_schemas: dict[str, dict[str, Any]],
    tool_servers: dict[str, dict[str, Any]],
    policy_limits,
    tool_cache_get,
    tool_cache_put,
    execution_started: float,
    budget_seconds: float,
    child_timeout_seconds: float,
    emit=None,
) -> CrossSourceSnapshot:
    """Execute a CrossSourcePlan and return a standardised snapshot."""

    orchestration_id = uuid.uuid4().hex[:12]
    plan_start = time.monotonic()

    # Validate plan
    if not plan.steps:
        return failed_snapshot(
            "PLAN_CONTRACT_INVALID",
            source_status=(),
            total_elapsed_ms=0.0,
        )

    try:
        layers = _topological_layers(plan.steps)
    except ValueError:
        return failed_snapshot(
            "PLAN_CONTRACT_INVALID",
            source_status=(),
            total_elapsed_ms=0.0,
        )

    # Per-server locks for serial execution within the same server_id
    server_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    upstream_results: dict[str, dict[str, Any]] = {}
    all_status: list[dict[str, Any]] = []

    for layer_steps in layers:
        async def _run_with_lock(step: CrossSourceStep) -> dict[str, Any]:
            async with server_locks[step.server_id]:
                remaining = budget_seconds - (time.monotonic() - execution_started)
                return await _execute_step(
                    step=step,
                    upstream_results=upstream_results,
                    session=session,
                    tool_schemas=tool_schemas,
                    tool_servers=tool_servers,
                    policy_limits=policy_limits,
                    tool_cache_get=tool_cache_get,
                    tool_cache_put=tool_cache_put,
                    emit=emit,
                    orchestration_id=orchestration_id,
                    budget_remaining=max(0, remaining),
                    child_timeout=child_timeout_seconds,
                )

        tasks = [_run_with_lock(step) for step in layer_steps]
        layer_results = await asyncio.gather(*tasks, return_exceptions=True)

        for step, result in zip(layer_steps, layer_results):
            if isinstance(result, Exception):
                status = {
                    "step_id": step.step_id,
                    "server_id": step.server_id,
                    "tool": step.tool,
                    "ok": False,
                    "error_code": "SOURCE_SERVER_UNAVAILABLE",
                    "error_message": str(result),
                    "elapsed_ms": 0.0,
                }
                upstream_results[step.step_id] = status
                all_status.append(status)
            else:
                upstream_results[step.step_id] = result
                all_status.append(result)

    total_elapsed_ms = (time.monotonic() - plan_start) * 1000

    # Build facts from successful steps
    facts: list[CrossSourceFact] = []
    missing_fact_ids: list[str] = []
    required_for_analysis_ok = True

    for step in plan.steps:
        status = upstream_results.get(step.step_id, {})
        step_ok = status.get("ok", False)

        # Check if this step produced data (ok=True and result not empty/missing)
        result_text = status.get("result_text", "")
        has_data = step_ok and result_text
        payload = _json_payload(result_text) if has_data else {}

        for fact_id in step.produces_fact_ids:
            is_missing, fact_error = _fact_payload_status(payload, fact_id, step)
            if not step_ok:
                is_missing = True
                fact_error = status.get("error_code") or "SOURCE_SERVER_UNAVAILABLE"
            if is_missing:
                missing_fact_ids.append(fact_id)
                if step.required_for_analysis:
                    required_for_analysis_ok = False
                facts.append(CrossSourceFact(
                    fact_id=fact_id,
                    label=fact_id,
                    value=None,
                    source_service=step.server_id,
                    missing=True,
                    error_code=fact_error or status.get("error_code") or "DATA_MISSING",
                ))
            else:
                # Extract fact value from payload
                fact_value = _extract_fact_value(payload, fact_id, step)
                facts.append(CrossSourceFact(
                    fact_id=fact_id,
                    label=fact_id,
                    value=fact_value.get("value"),
                    unit=fact_value.get("unit"),
                    data_time=fact_value.get("data_time"),
                    quality=fact_value.get("quality"),
                    source_service=step.server_id,
                    source_object=payload.get("source_object"),
                    missing=fact_value.get("value") is None,
                    error_code="EMPTY_FACT_VALUE" if fact_value.get("value") is None else None,
                ))
                if fact_value.get("value") is None:
                    missing_fact_ids.append(fact_id)
                    if step.required_for_analysis:
                        required_for_analysis_ok = False

    # Determine snapshot state
    success_count = sum(1 for f in facts if not f.missing)
    missing_count = len(missing_fact_ids)

    if success_count == 0:
        return failed_snapshot(
            "PARTIAL_DATA" if missing_count > 0 else "SOURCE_SERVER_UNAVAILABLE",
            source_status=tuple(all_status),
            heat_reference=_extract_heat_reference(plan, upstream_results),
            total_elapsed_ms=total_elapsed_ms,
        )

    if missing_count == 0:
        return success_snapshot(
            facts=tuple(facts),
            source_status=tuple(all_status),
            heat_reference=_extract_heat_reference(plan, upstream_results),
            total_elapsed_ms=total_elapsed_ms,
        )

    return partial_snapshot(
        facts=tuple(facts),
        missing_fact_ids=tuple(missing_fact_ids),
        source_status=tuple(all_status),
        analysis_allowed=required_for_analysis_ok,
        heat_reference=_extract_heat_reference(plan, upstream_results),
        total_elapsed_ms=total_elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Fact-value extraction
# ---------------------------------------------------------------------------


def _extract_fact_value(
    payload: dict[str, Any],
    fact_id: str,
    step: CrossSourceStep,
) -> dict[str, Any]:
    """Extract a single fact value from a tool result payload.

    Returns a dict with value/unit/data_time/quality keys.
    """
    result: dict[str, Any] = {
        "value": None,
        "unit": None,
        "data_time": payload.get("as_of_time"),
        "quality": None,
    }

    # --- IMES tools ---
    if step.tool.startswith("imes__"):
        if fact_id == "heat_resolution":
            result["value"] = payload.get("resolved_heat_no")
            result["data_time"] = payload.get("heat_time_window")
        elif fact_id == "imes_result":
            result["value"] = payload
            result["unit"] = None
        elif fact_id in ("current_heat_no", "previous_heat_no"):
            result["value"] = payload.get(fact_id)
        elif fact_id == "si_avg":
            result["value"] = payload.get("si_avg")
            result["unit"] = payload.get("unit", "%")
        elif fact_id == "si_values":
            result["value"] = payload.get("si_values")
            result["unit"] = payload.get("unit", "%")
        elif fact_id == "heat_status":
            result["value"] = payload.get("status")
        elif fact_id == "sample_count":
            result["value"] = payload.get("sample_count")
        elif fact_id == "hot_metal_chemistry":
            result["value"] = payload.get("rows")
            result["unit"] = payload.get("unit")

    # --- GL02 sensor tools ---
    elif step.tool in ("query_gl02_sensors", "gl02ext__query_body_temperature"):
        items = payload.get("items") or payload.get("results") or []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                requested = item.get("requested_variable") or item.get("variable_name")
                if requested == fact_id:
                    latest = item.get("latest") or {}
                    stats = item.get("statistics") or {}
                    variable = item.get("variable") or {}
                    result["value"] = latest.get("value") if latest else stats.get("avg")
                    payload_unit = variable.get("unit") if isinstance(variable, dict) else item.get("unit")
                    result["unit"] = payload_unit or _CANONICAL_UNIT_FALLBACKS.get(fact_id)
                    result["data_time"] = latest.get("ts") if latest else item.get("as_of_time")
                    result["quality"] = latest.get("quality") or item.get("quality")
                    break

    elif step.tool == "gl02ext__query_body_temperature_statistics":
        if fact_id == "body_temperature_statistics":
            result["value"] = payload.get("layer_statistics")
            result["unit"] = payload.get("unit") or "℃"
            result["data_time"] = {
                "start": payload.get("start_time"),
                "end": payload.get("end_time"),
            }
            result["quality"] = payload.get("data_quality")

    # --- GL02 chart/analysis/matrix ---
    elif step.tool in ("plot_gl02_trends", "plot_gl02_analysis", "plot_gl02_body_temperature_matrix"):
        correlation = (payload.get("derived") or {}).get("correlation") or {}
        window = f"{payload.get('start_time', '')} – {payload.get('end_time', '')}"
        result["data_time"] = window
        if fact_id == "pearson_r":
            result["value"] = correlation.get("pearson_r")
        elif fact_id == "aligned_count":
            result["value"] = correlation.get("aligned_count")
            result["unit"] = "个"
        elif fact_id == "correlation_left":
            result["value"] = correlation.get("left")
        elif fact_id == "correlation_right":
            result["value"] = correlation.get("right")
        elif fact_id == "correlation_window":
            result["value"] = window
        else:
            result["value"] = payload.get("image_url")

    return result
