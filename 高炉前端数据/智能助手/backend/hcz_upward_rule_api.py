"""8093 read-only adapter for the GL02 HCZ upward expert rule.

Requirement: REQ-HCZ-UPWARD-EXPERT-RULE-20260810.

The adapter aggregates registered sensor values into hourly means, calls the
versioned rule engine, and keeps a short in-process cache. It never writes a
prediction, label, process setting, or control value.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULE_ENGINE_DIR = PROJECT_ROOT / "炉况规则引擎"
if str(RULE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(RULE_ENGINE_DIR))

from features.hcz_upward_expert_rule import (  # noqa: E402
    HczRuleSensitivityValidationError,
    evaluate_hcz_rule_sensitivity,
    evaluate_hcz_upward_rule,
    load_hcz_upward_rule_config,
    required_variable_names,
    sensitivity_parameter_contract,
)


REQUIREMENT_ID = "REQ-HCZ-UPWARD-EXPERT-RULE-20260810"
CACHE_SECONDS = 120.0
HISTORY_CACHE_SECONDS = 300.0
MAX_HISTORY_DAYS = 90
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"created": 0.0, "payload": None}
_HISTORY_CACHE: dict[str, Any] = {"created": 0.0, "payload": None}


class HczUpwardRuleDataError(RuntimeError):
    """Raised when the registered GL02 history cannot be read safely."""


def clear_cache() -> None:
    """Clear the process-local rule result cache (used by tests/deploy checks)."""
    with _CACHE_LOCK:
        _CACHE.update({"created": 0.0, "payload": None})
        _HISTORY_CACHE.update({"created": 0.0, "payload": None})


def _normalise_gas_utilisation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert the stored 0..1 GasUtil fraction to percentage points."""
    normalised: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("variable_name") == "GasUtil" and item.get("value") is not None:
            item["value"] = float(item["value"]) * 100.0
        normalised.append(item)
    return normalised


def evaluate_latest(connect_factory: Callable[[], Any]) -> dict[str, Any]:
    """Read the latest six-day sensor horizon and evaluate the expert rule."""
    with _CACHE_LOCK:
        cached = _CACHE.get("payload")
        if cached is not None and time.monotonic() - float(_CACHE.get("created") or 0.0) < CACHE_SECONDS:
            return {**cached, "cache": "hit"}

    config = load_hcz_upward_rule_config()
    variables = list(required_variable_names(config))
    started = time.monotonic()
    try:
        with connect_factory() as connection:
            latest_row = connection.execute(
                """
                SELECT max(v.ts) AS latest_ts
                FROM bf_sensor.sensor_registry r
                JOIN bf_sensor.one_minute_values v
                  ON v.tag_long_name = r.tag_long_name
                WHERE r.variable_name = ANY(%s)
                """,
                (variables,),
            ).fetchone()
            latest = latest_row.get("latest_ts") if latest_row else None
            if latest is None:
                raise HczUpwardRuleDataError("所需传感器没有可用分钟数据")
            if not isinstance(latest, datetime):
                latest = datetime.fromisoformat(str(latest))
            evaluation_hour = latest.replace(minute=0, second=0, microsecond=0)
            history_start = evaluation_hour - timedelta(hours=143)
            rows = connection.execute(
                """
                SELECT date_trunc('hour', v.ts) AS bucket,
                       r.variable_name,
                       avg(v.value)::double precision AS value,
                       count(v.value)::integer AS sample_count
                FROM bf_sensor.sensor_registry r
                JOIN bf_sensor.one_minute_values v
                  ON v.tag_long_name = r.tag_long_name
                WHERE r.variable_name = ANY(%s)
                  AND v.ts >= %s
                  AND v.ts <= %s
                  AND v.value IS NOT NULL
                GROUP BY date_trunc('hour', v.ts), r.variable_name
                ORDER BY date_trunc('hour', v.ts), r.variable_name
                """,
                (variables, history_start, latest),
            ).fetchall()
    except HczUpwardRuleDataError:
        raise
    except Exception as exc:
        raise HczUpwardRuleDataError("读取软熔带上移规则实测历史失败") from exc

    normalised_rows = _normalise_gas_utilisation([dict(row) for row in rows])
    result = evaluate_hcz_upward_rule(normalised_rows, evaluation_time=evaluation_hour)
    payload = {
        **result,
        "source": {
            "database": "220.12 PostgreSQL 16",
            "schema": "bf_sensor",
            "registry_table": "sensor_registry",
            "value_table": "one_minute_values",
            "latest_sample_time": latest.isoformat(),
            "variable_count": len(variables),
            "hourly_record_count": len(normalised_rows),
            "gas_utilisation_storage_unit": "fraction_0_to_1",
            "gas_utilisation_rule_unit": "percentage_point",
            "gas_utilisation_normalised": True,
            "query_elapsed_ms": round((time.monotonic() - started) * 1000),
            "read_only": True,
        },
        "sensitivity": {
            "endpoint": "/api/hcz-rule-sensitivity",
            "max_history_days": MAX_HISTORY_DAYS,
            "parameters": sensitivity_parameter_contract(config),
            "read_only_trial": True,
        },
        "cache": "miss",
    }
    with _CACHE_LOCK:
        _CACHE.update({"created": time.monotonic(), "payload": payload})
    return payload


def _parse_sensitivity_query(query_string: str) -> tuple[int, dict[str, float | int]]:
    query = parse_qs(query_string or "", keep_blank_values=False)
    allowed = {"days", "t", "deploy", *sensitivity_parameter_contract().keys()}
    unknown = sorted(set(query) - allowed)
    if unknown:
        raise HczRuleSensitivityValidationError(f"不支持的查询参数：{','.join(unknown)}")
    try:
        days = int(query.get("days", [str(MAX_HISTORY_DAYS)])[0])
    except (TypeError, ValueError) as exc:
        raise HczRuleSensitivityValidationError("days必须是整数") from exc
    if not 7 <= days <= MAX_HISTORY_DAYS:
        raise HczRuleSensitivityValidationError(f"days必须在7到{MAX_HISTORY_DAYS}之间")
    contract = sensitivity_parameter_contract()
    overrides: dict[str, float | int] = {}
    for key, spec in contract.items():
        if key not in query:
            continue
        raw = query[key][0]
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise HczRuleSensitivityValidationError(f"{key}必须是数字") from exc
        overrides[key] = int(number) if spec["integer"] and number.is_integer() else number
    return days, overrides


def _load_history_rows(connect_factory: Callable[[], Any]) -> tuple[dict[str, Any], str]:
    with _CACHE_LOCK:
        cached = _HISTORY_CACHE.get("payload")
        if cached is not None and time.monotonic() - float(_HISTORY_CACHE.get("created") or 0.0) < HISTORY_CACHE_SECONDS:
            return cached, "hit"

    config = load_hcz_upward_rule_config()
    variables = list(required_variable_names(config))
    started = time.monotonic()
    try:
        with connect_factory() as connection:
            latest_row = connection.execute(
                """
                SELECT max(v.ts) AS latest_ts
                FROM bf_sensor.sensor_registry r
                JOIN bf_sensor.one_minute_values v
                  ON v.tag_long_name = r.tag_long_name
                WHERE r.variable_name = ANY(%s)
                """,
                (variables,),
            ).fetchone()
            latest = latest_row.get("latest_ts") if latest_row else None
            if latest is None:
                raise HczUpwardRuleDataError("所需传感器没有可用分钟数据")
            if not isinstance(latest, datetime):
                latest = datetime.fromisoformat(str(latest))
            latest_hour = latest.replace(minute=0, second=0, microsecond=0)
            full_evaluation_start = latest_hour - timedelta(hours=MAX_HISTORY_DAYS * 24 - 1)
            query_start = full_evaluation_start - timedelta(hours=143)
            rows = connection.execute(
                """
                SELECT date_trunc('hour', v.ts) AS bucket,
                       r.variable_name,
                       avg(v.value)::double precision AS value,
                       count(v.value)::integer AS sample_count
                FROM bf_sensor.sensor_registry r
                JOIN bf_sensor.one_minute_values v
                  ON v.tag_long_name = r.tag_long_name
                WHERE r.variable_name = ANY(%s)
                  AND v.ts >= %s
                  AND v.ts <= %s
                  AND v.value IS NOT NULL
                GROUP BY date_trunc('hour', v.ts), r.variable_name
                ORDER BY date_trunc('hour', v.ts), r.variable_name
                """,
                (variables, query_start, latest),
            ).fetchall()
    except HczUpwardRuleDataError:
        raise
    except Exception as exc:
        raise HczUpwardRuleDataError("读取软熔带阈值试算历史失败") from exc

    payload = {
        "latest": latest,
        "latest_hour": latest_hour,
        "query_start": query_start,
        "rows": _normalise_gas_utilisation([dict(row) for row in rows]),
        "variable_count": len(variables),
        "query_elapsed_ms": round((time.monotonic() - started) * 1000),
    }
    with _CACHE_LOCK:
        _HISTORY_CACHE.update({"created": time.monotonic(), "payload": payload})
    return payload, "miss"


def evaluate_sensitivity(connect_factory: Callable[[], Any], query_string: str = "") -> dict[str, Any]:
    """Replay editable thresholds against up to 90 days of measured history."""
    days, overrides = _parse_sensitivity_query(query_string)
    history, cache_state = _load_history_rows(connect_factory)
    latest_hour = history["latest_hour"]
    evaluation_start = latest_hour - timedelta(hours=days * 24 - 1)
    evaluation_hours = [
        evaluation_start + timedelta(hours=offset)
        for offset in range(days * 24)
    ]
    started = time.monotonic()
    result = evaluate_hcz_rule_sensitivity(
        history["rows"],
        evaluation_hours,
        threshold_overrides=overrides,
    )
    return {
        **result,
        "history_days": days,
        "source": {
            "database": "220.12 PostgreSQL 16",
            "schema": "bf_sensor",
            "registry_table": "sensor_registry",
            "value_table": "one_minute_values",
            "latest_sample_time": history["latest"].isoformat(),
            "baseline_query_start": history["query_start"].isoformat(),
            "variable_count": history["variable_count"],
            "hourly_record_count": len(history["rows"]),
            "gas_utilisation_storage_unit": "fraction_0_to_1",
            "gas_utilisation_rule_unit": "percentage_point",
            "gas_utilisation_normalised": True,
            "query_elapsed_ms": history["query_elapsed_ms"] if cache_state == "miss" else 0,
            "evaluation_elapsed_ms": round((time.monotonic() - started) * 1000),
            "history_cache": cache_state,
            "read_only": True,
        },
    }


__all__ = [
    "HczRuleSensitivityValidationError",
    "HczUpwardRuleDataError",
    "clear_cache",
    "evaluate_latest",
    "evaluate_sensitivity",
]
