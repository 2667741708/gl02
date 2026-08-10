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


if __name__ == "__main__":
    mcp.run(transport=base.os.getenv("MCP_TRANSPORT", "stdio"))
