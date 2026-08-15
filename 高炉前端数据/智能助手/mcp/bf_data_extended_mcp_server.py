"""Extended GL02 MCP surface for diagnosis history and body-temperature queries.

The legacy data server remains the source of the existing tools.  This wrapper
loads its FastMCP instance and registers the two bounded, read-only tools on
the same instance so the Host can expose them without duplicating 18+ tools.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP

SERVER_PATH = Path(__file__).with_name("bf_data_mcp_server.py")
spec = importlib.util.spec_from_file_location("bf_data_mcp_server_extended_base", SERVER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load GL02 MCP server: {SERVER_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

mcp = FastMCP("blast-furnace-gl02-extended-mcp", json_response=True)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _database_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(base.LOCAL_TZ).replace(tzinfo=None)
    return parsed


def _body_temperature_variable(layer: int, position: str) -> dict[str, Any]:
    variable = base.body_temperature_variable_from_text(f"{layer}层{position}炉体温度")
    if not variable or not variable.get("tag_long_name"):
        raise ValueError(f"无法解析炉体温度点位：{layer}层{position}")
    return variable


def _series_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic population statistics without filtering valid values."""
    usable = [row for row in rows if base.numeric_row_value(row) is not None and base.row_datetime(row) is not None]
    usable.sort(key=lambda row: base.row_datetime(row) or datetime.min)
    values = [float(base.numeric_row_value(row)) for row in usable]
    first = usable[0] if usable else None
    last = usable[-1] if usable else None
    first_value = base.numeric_row_value(first or {})
    last_value = base.numeric_row_value(last or {})
    average = sum(values) / len(values) if values else None
    stddev = base.population_std(values)
    return {
        "count": len(values),
        "avg": average,
        "stddev_pop": stddev,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "range": (max(values) - min(values)) if values else None,
        "first": {"ts": first.get("ts"), "value": first_value} if first else None,
        "last": {"ts": last.get("ts"), "value": last_value} if last else None,
        "delta": (last_value - first_value) if first_value is not None and last_value is not None else None,
        "slope_per_min": base.linear_slope_per_min(usable),
        "cv_percent": (stddev / abs(average) * 100.0) if stddev is not None and average not in (None, 0.0) else None,
        "trend": base.trend_label(
            delta=(last_value - first_value) if first_value is not None and last_value is not None else None,
            slope_per_min=base.linear_slope_per_min(usable),
        ),
    }


def _rolling_variation(rows: list[dict[str, Any]], window_minutes: int) -> dict[str, Any]:
    ordered = [row for row in rows if base.numeric_row_value(row) is not None and base.row_datetime(row) is not None]
    ordered.sort(key=lambda row: base.row_datetime(row) or datetime.min)
    windows: list[dict[str, Any]] = []
    first_index = 0
    for current_index, current in enumerate(ordered):
        current_ts = base.row_datetime(current)
        if current_ts is None:
            continue
        lower_bound = current_ts - timedelta(minutes=window_minutes)
        while first_index < current_index:
            candidate_ts = base.row_datetime(ordered[first_index])
            if candidate_ts is not None and candidate_ts > lower_bound:
                break
            first_index += 1
        values = [float(base.numeric_row_value(candidate)) for candidate in ordered[first_index : current_index + 1]]
        if not values:
            continue
        windows.append({
            "ts": current.get("ts"),
            "count": len(values),
            "stddev_pop": base.population_std(values),
            "range": max(values) - min(values),
        })
    first = windows[0] if windows else None
    last = windows[-1] if windows else None
    std_values = [float(item["stddev_pop"]) for item in windows if item.get("stddev_pop") is not None]
    range_values = [float(item["range"]) for item in windows if item.get("range") is not None]
    return {
        "window_minutes": window_minutes,
        "count": len(windows),
        "start": first,
        "end": last,
        "stddev_delta": (
            float(last["stddev_pop"]) - float(first["stddev_pop"])
            if first and last and first.get("stddev_pop") is not None and last.get("stddev_pop") is not None
            else None
        ),
        "range_delta": (
            float(last["range"]) - float(first["range"])
            if first and last and first.get("range") is not None and last.get("range") is not None
            else None
        ),
        "stddev_min": min(std_values) if std_values else None,
        "stddev_max": max(std_values) if std_values else None,
        "range_min": min(range_values) if range_values else None,
        "range_max": max(range_values) if range_values else None,
    }


def _query_body_temperature_batch(
    variables: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, Any]]:
    tags = [str(item["tag_long_name"]) for item in variables]
    with base.raw_pg_connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            """
            SELECT tag_long_name, ts, value, quality, value_type,
                   aggregate, interval_seconds, source_server, collected_at
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = ANY(%s)
              AND ts >= %s::timestamp AND ts <= %s::timestamp
            ORDER BY ts ASC, tag_long_name ASC
            """,
            (tags, start_dt, end_dt),
        ).fetchall()
    return [dict(row) for row in rows]


@mcp.tool()
def query_furnace_diagnosis_history(
    window_minutes: int = 480,
    start_time: str = "",
    end_time: str = "",
    target_labels: list[str] | None = None,
    limit: int = 96,
) -> dict[str, Any]:
    """Read recent 5-minute furnace diagnosis scores from bf_sensor.

    ``target_labels`` filters returned labels or score keys (for example
    ``["channel"]``).  The query always deduplicates a diagnosis timestamp and
    never accepts arbitrary SQL.
    """
    limit = max(1, min(int(limit or 96), 500))
    window_minutes = max(5, min(int(window_minutes or 480), 7 * 24 * 60))
    labels = {str(item).strip().lower() for item in (target_labels or []) if str(item).strip()}
    try:
        with base.raw_pg_connect() as conn:
            end_dt = _database_datetime(end_time) if end_time else None
            if end_dt is None:
                latest = conn.execute("SELECT max(diagnosis_ts) AS ts FROM bf_sensor.diagnosis_snapshots").fetchone()
                end_dt = latest["ts"] if latest and latest.get("ts") else datetime.now().replace(second=0, microsecond=0)
            start_dt = _database_datetime(start_time) if start_time else end_dt - timedelta(minutes=window_minutes)
            rows = conn.execute(
                """
                SELECT *
                FROM (
                    SELECT DISTINCT ON (diagnosis_ts)
                           id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                           window_minutes, source, data_coverage, missing_variables,
                           source_lag_seconds, main_label, main_score, main_confidence,
                           secondary_label, secondary_score, secondary_confidence,
                           raw_scores, feature_snapshot, created_at, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                    ORDER BY diagnosis_ts, updated_at DESC NULLS LAST, id DESC
                ) latest
                ORDER BY diagnosis_ts DESC
                LIMIT %s
                """,
                (start_dt, end_dt, limit),
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "POSTGRES_UNAVAILABLE", "message": str(exc)}

    points: list[dict[str, Any]] = []
    for row in reversed([dict(item) for item in rows]):
        scores = _json_object(row.get("raw_scores"))
        channel_score = scores.get("channel")
        if isinstance(channel_score, dict):
            channel_score = channel_score.get("score", channel_score.get("value"))
        if labels:
            visible_scores = {key: value for key, value in scores.items() if str(key).lower() in labels}
            if not visible_scores and str(row.get("main_label") or "").lower() not in labels:
                continue
            scores = visible_scores
        points.append(
            {
                "diagnosis_ts": row.get("diagnosis_ts"),
                "window_start": row.get("diagnosis_window_start"),
                "window_end": row.get("diagnosis_window_end"),
                "window_minutes": row.get("window_minutes"),
                "main_label": row.get("main_label"),
                "main_score": row.get("main_score"),
                "secondary_label": row.get("secondary_label"),
                "secondary_score": row.get("secondary_score"),
                "channel_score": channel_score,
                "scores": scores,
                "data_coverage": row.get("data_coverage"),
                "source": row.get("source"),
            }
        )
    first = points[0] if points else {}
    last = points[-1] if points else {}
    return {
        "ok": bool(points),
        "error": None if points else "NO_DATA",
        "window_minutes": window_minutes,
        "start_time": start_dt,
        "end_time": end_dt,
        "count": len(points),
        "points": points,
        "trend": {
            "main_score_delta": (last.get("main_score") - first.get("main_score"))
            if isinstance(last.get("main_score"), (int, float)) and isinstance(first.get("main_score"), (int, float))
            else None,
            "channel_score_delta": (last.get("channel_score") - first.get("channel_score"))
            if isinstance(last.get("channel_score"), (int, float)) and isinstance(first.get("channel_score"), (int, float))
            else None,
        },
        "source": {"type": "postgresql", "schema": "bf_sensor", "table": "diagnosis_snapshots", "read_policy": "readonly"},
    }


@mcp.tool()
def query_body_temperature(
    layer: int | None = None,
    position: str = "",
    window_minutes: int = 0,
    start_time: str = "",
    end_time: str = "",
    include_history: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Query one or more furnace-body temperature points (L7-L16, A-H)."""
    if layer is not None and not 7 <= int(layer) <= 16:
        raise ValueError("layer must be between 7 and 16")
    position = str(position or "").strip().upper()
    if position and position not in "ABCDEFGH":
        raise ValueError("position must be A-H")
    if layer is None and not position:
        return {
            "ok": False,
            "error": "AMBIGUOUS_SCOPE",
            "message": "请至少指定炉身层号（7-16）或方位（A-H），避免一次读取全部80个点位。",
        }
    layers = [int(layer)] if layer is not None else list(range(7, 17))
    positions = [position] if position else list("ABCDEFGH")
    variables = [f"T_body_L{item}_{letter}" for item in layers for letter in positions]
    window_minutes = max(0, min(int(window_minutes or 0), 7 * 24 * 60))
    if include_history or window_minutes:
        end_dt = _database_datetime(end_time) if end_time else datetime.now().replace(second=0, microsecond=0)
        start_dt = _database_datetime(start_time) if start_time else end_dt - timedelta(minutes=window_minutes or 60)
    else:
        start_dt = end_dt = None
    results: list[dict[str, Any]] = []
    for variable in variables:
        latest = base.get_latest_gl02_value(variable, source_preference="database")
        item: dict[str, Any] = {"variable": variable, "latest": latest}
        if start_dt is not None and end_dt is not None:
            item["history"] = base.query_gl02_history(
                variable,
                start_dt.isoformat(timespec="seconds"),
                end_dt.isoformat(timespec="seconds"),
                limit=limit,
                source_preference="database",
            )
        results.append(item)
    return {
        "ok": any(bool(item["latest"].get("ok")) for item in results),
        "layers": layers,
        "positions": positions,
        "count": len(results),
        "results": results,
        "source": "bf_sensor.one_minute_values",
    }


@mcp.tool()
def query_body_temperature_statistics(
    start_layer: int,
    end_layer: int,
    start_time: str,
    end_time: str,
    positions: list[str] | None = None,
    rolling_window_minutes: int = 15,
    require_all_positions: bool = True,
    include_point_statistics: bool = False,
) -> dict[str, Any]:
    """Batch-read and deterministically summarize furnace-body temperatures.

    The tool accepts layers 7-16 and physical positions A-H. It performs one
    read-only PostgreSQL query for the full selection, aligns values by minute,
    and calculates per-layer and optional per-point population statistics.
    A layer mean is emitted only when all requested positions exist at that
    timestamp when ``require_all_positions`` is true. Values are never silently
    interpolated or filtered.
    """
    first_layer = int(start_layer)
    last_layer = int(end_layer)
    if not 7 <= first_layer <= 16 or not 7 <= last_layer <= 16:
        raise ValueError("start_layer/end_layer must be between 7 and 16")
    layer_step = 1 if first_layer <= last_layer else -1
    layers = list(range(first_layer, last_layer + layer_step, layer_step))
    selected_positions = [str(item or "").strip().upper() for item in (positions or list("ABCDEFGH"))]
    selected_positions = list(dict.fromkeys(item for item in selected_positions if item))
    if not selected_positions or any(item not in "ABCDEFGH" for item in selected_positions):
        raise ValueError("positions must contain one or more values from A-H")
    rolling_window_minutes = max(2, min(int(rolling_window_minutes or 15), 120))

    start_text, end_text = base.validate_time_range(start_time, end_time)
    start_dt = _database_datetime(start_text)
    end_dt = _database_datetime(end_text)
    if start_dt is None or end_dt is None:
        raise ValueError("start_time/end_time must be valid ISO8601 values")
    if end_dt - start_dt > timedelta(hours=24):
        raise ValueError("炉体分层统计单次时间窗不得超过24小时")

    variables: list[dict[str, Any]] = []
    key_by_tag: dict[str, tuple[int, str, str]] = {}
    for layer in layers:
        for position in selected_positions:
            variable = _body_temperature_variable(layer, position)
            variables.append(variable)
            key_by_tag[str(variable["tag_long_name"])] = (layer, position, str(variable["variable_name"]))

    rows = _query_body_temperature_batch(variables, start_dt, end_dt)
    point_rows: dict[tuple[int, str], list[dict[str, Any]]] = {
        (layer, position): [] for layer in layers for position in selected_positions
    }
    quality_counts: dict[str, int] = {}
    nonfinite_count = 0
    zero_count = 0
    for source_row in rows:
        key = key_by_tag.get(str(source_row.get("tag_long_name") or ""))
        if key is None:
            continue
        value = base.numeric_row_value(source_row)
        if value is None:
            nonfinite_count += 1
            continue
        if value == 0.0:
            zero_count += 1
        quality = str(source_row.get("quality") or "UNKNOWN")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        point_rows[(key[0], key[1])].append({
            "ts": source_row.get("ts"),
            "value": value,
            "quality": quality,
            "collected_at": source_row.get("collected_at"),
        })

    expected_minutes = int((end_dt - start_dt).total_seconds() // 60) + 1
    layer_statistics: list[dict[str, Any]] = []
    for layer in layers:
        by_timestamp: dict[datetime, dict[str, dict[str, Any]]] = {}
        for position in selected_positions:
            for row in point_rows[(layer, position)]:
                row_ts = base.row_datetime(row)
                if row_ts is not None:
                    by_timestamp.setdefault(row_ts, {})[position] = row
        layer_rows: list[dict[str, Any]] = []
        incomplete_timestamp_count = 0
        for row_ts in sorted(by_timestamp):
            available = by_timestamp[row_ts]
            if require_all_positions and any(position not in available for position in selected_positions):
                incomplete_timestamp_count += 1
                continue
            values = [base.numeric_row_value(available[position]) for position in selected_positions if position in available]
            numeric = [float(value) for value in values if value is not None]
            if not numeric:
                continue
            layer_rows.append({
                "ts": row_ts,
                "value": sum(numeric) / len(numeric),
                "position_count": len(numeric),
            })
        summary = _series_summary(layer_rows)
        layer_statistics.append({
            "layer": layer,
            "positions": selected_positions,
            "required_position_count": len(selected_positions),
            "aligned_complete_count": summary["count"],
            "incomplete_timestamp_count": incomplete_timestamp_count,
            "expected_minute_count": expected_minutes,
            "coverage_ratio": summary["count"] / expected_minutes if expected_minutes else 0.0,
            "statistics": summary,
            "rolling_variation": _rolling_variation(layer_rows, rolling_window_minutes),
        })

    point_statistics: list[dict[str, Any]] = []
    if include_point_statistics:
        for layer in layers:
            for position in selected_positions:
                rows_for_point = point_rows[(layer, position)]
                point_statistics.append({
                    "layer": layer,
                    "position": position,
                    "variable": f"T_body_L{layer}_{position}",
                    "unit": "℃",
                    "expected_minute_count": expected_minutes,
                    "coverage_ratio": len(rows_for_point) / expected_minutes if expected_minutes else 0.0,
                    "statistics": _series_summary(rows_for_point),
                    "rolling_variation": _rolling_variation(rows_for_point, rolling_window_minutes),
                })

    return {
        "ok": any(item["statistics"]["count"] > 0 for item in layer_statistics),
        "tool": "query_body_temperature_statistics",
        "layers": layers,
        "positions": selected_positions,
        "start_time": start_dt.isoformat(timespec="seconds"),
        "end_time": end_dt.isoformat(timespec="seconds"),
        "unit": "℃",
        "aggregation": {
            "layer_mean": "同一分钟内所选方位温度的算术平均",
            "stddev": "STDDEV_POP",
            "range": "MAX-MIN",
            "cv": "STDDEV_POP/ABS(AVG)*100%",
            "rolling_window_minutes": rolling_window_minutes,
            "require_all_positions": bool(require_all_positions),
            "interpolation": "none",
            "value_filtering": "none",
        },
        "layer_statistics": layer_statistics,
        "point_statistics": point_statistics,
        "data_quality": {
            "queried_point_count": len(variables),
            "raw_row_count": len(rows),
            "expected_rows": expected_minutes * len(variables),
            "missing_row_count": max(0, expected_minutes * len(variables) - len(rows)),
            "nonfinite_count": nonfinite_count,
            "zero_count": zero_count,
            "quality_counts": quality_counts,
        },
        "source": {
            "service": "blast-furnace-gl02-extended-mcp",
            "profile": "bf_sensor_postgresql",
            "schema": "bf_sensor",
            "object": "one_minute_values",
            "read_policy": "readonly",
        },
    }


if __name__ == "__main__":
    mcp.run(transport=base.os.getenv("MCP_TRANSPORT", "stdio"))
