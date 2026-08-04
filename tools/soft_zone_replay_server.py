"""Independent spatiotemporal replay page for the GL02 cohesive-zone baseline.

REQ-BF3D-C2-REPLAY-SPACE-TIME-20260721

The service intentionally stays outside 8092/8093.  It exposes a small
read-only HTTP API and serves the static replay UI.  The API returns measured
L7-L16 wall temperatures and the 18 measured static-pressure points alongside
the existing C2 *estimated* cohesive-zone root series.

Security and process boundary:
* Reads only ``bf_sensor.sensor_registry`` and ``bf_sensor.one_minute_values``.
* Never persists predictions or changes production data.
* C2 output remains ``estimated/uncalibrated/control_use=prohibited``.
* Database credentials are read from inherited environment or an existing
  managed-service JSON file; they are never returned by an API or written to
  logs.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import mimetypes
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd
import psycopg
from psycopg.rows import dict_row


REQUIREMENT_ID = "REQ-BF3D-C2-REPLAY-SPACE-TIME-20260721"
MODEL_VERSION = "C2-ROOT-BASELINE-2026.07"
MAX_HOURS = 72
MAX_FRAMES = 720
C2_LOOKBACK_MINUTES = 45

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_ENGINE_DIR = PROJECT_ROOT / "炉况规则引擎"
if str(RULE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(RULE_ENGINE_DIR))

from features.cohesive_zone_estimator import CohesiveZoneEstimator  # noqa: E402


BODY_LAYOUT: tuple[dict[str, Any], ...] = tuple(
    {
        "id": f"T_body_L{layer}_{sector}",
        "metric": "temperature",
        "layer": layer,
        "height_m": height,
        "azimuth": sector,
        "angle_deg": index * 45,
        "region": region,
        "unit": "°C",
    }
    for layer, height, region in (
        (7, 16.860, "belly"),
        (8, 18.335, "belly"),
        (9, 20.125, "waist"),
        (10, 21.860, "stack_lower"),
        (11, 23.711, "stack_lower"),
        (12, 25.441, "stack_lower"),
        (13, 27.171, "stack_lower"),
        (14, 28.901, "stack_middle"),
        (15, 30.631, "stack_upper"),
        (16, 32.361, "stack_upper"),
    )
    for index, sector in enumerate("ABCDEFGH")
)

STATIC_LAYOUT: tuple[dict[str, Any], ...] = tuple(
    {
        "id": f"P_static_{band}_{sector}",
        "metric": "pressure",
        "height_m": height,
        "azimuth": sector,
        "angle_deg": index * 60,
        "region": region,
        "pressure_band": band,
        "unit": "kPa",
    }
    for band, height, region in (
        ("lower", 20.350, "waist"),
        ("middle", 23.488, "stack_lower"),
        ("upper", 28.976, "stack_middle"),
    )
    for index, sector in enumerate("ABCDEF")
)

REGIONS: tuple[dict[str, str], ...] = (
    {"id": "all", "label": "全炉"},
    {"id": "belly", "label": "炉腹"},
    {"id": "waist", "label": "炉腰"},
    {"id": "stack_lower", "label": "炉身下"},
    {"id": "stack_middle", "label": "炉身中"},
    {"id": "stack_upper", "label": "炉身上"},
    {"id": "stack", "label": "炉身（全部）"},
)

C2_AUXILIARY_VARIABLES = (
    "DP_total",
    "DP_lower",
    "DP_upper",
    "PI",
    "Q_blast",
    "P_blast",
    "P_blast_cold",
    "T_blast",
    "O2_rate",
    "Q_O2",
    "PCI_rate",
    "PCI_set",
    "TFT",
    "L",
    "L_south",
    "L_north",
)
DISPLAY_LAYOUT = BODY_LAYOUT + STATIC_LAYOUT
DISPLAY_IDS = tuple(item["id"] for item in DISPLAY_LAYOUT)
REQUIRED_VARIABLES = tuple(dict.fromkeys((*DISPLAY_IDS, *C2_AUXILIARY_VARIABLES)))


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _parse_datetime(raw: str) -> datetime:
    text = str(raw or "").strip().replace("Z", "+00:00")
    if not text:
        raise ValueError("时间不能为空")
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(second=0, microsecond=0)


def _quantile_scale(values: Iterable[Any]) -> dict[str, float | None]:
    valid = sorted(number for value in values if (number := _finite(value)) is not None)
    if not valid:
        return {"low": None, "high": None, "method": "p05_p95_fixed_window"}
    low_index = max(0, round((len(valid) - 1) * 0.05))
    high_index = min(len(valid) - 1, round((len(valid) - 1) * 0.95))
    low = valid[low_index]
    high = valid[high_index]
    if math.isclose(low, high, abs_tol=1e-9):
        pad = max(abs(low) * 0.02, 1.0)
        low, high = low - pad, high + pad
    return {"low": round(low, 6), "high": round(high, 6), "method": "p05_p95_fixed_window"}


def _region_matches(region_filter: str, point_region: str) -> bool:
    if region_filter in {"", "all"}:
        return True
    if region_filter == "stack":
        return point_region.startswith("stack_")
    return region_filter == point_region


def _profile_radius(height_m: float) -> float:
    """Linearly interpolate the display furnace radius used by existing Web runtime."""
    profile = ((0.0, 2.05), (4.8, 2.35), (8.8, 2.95), (13.8, 4.15), (18.6, 4.46),
               (24.5, 4.05), (30.6, 3.36), (35.2, 2.78), (37.2, 2.42), (40.0, 2.18))
    if height_m <= profile[0][0]:
        return profile[0][1]
    for (h0, r0), (h1, r1) in zip(profile, profile[1:]):
        if height_m <= h1:
            ratio = (height_m - h0) / (h1 - h0)
            return r0 + (r1 - r0) * ratio
    return profile[-1][1]


def service_config_env(config_path: Path | None) -> dict[str, str]:
    """Read only GL02 PostgreSQL env values from an existing managed-service file."""
    if not config_path or not config_path.is_file():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    env = payload.get("env") if isinstance(payload, dict) else None
    if not isinstance(env, dict):
        return {}
    allowed = {"GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD"}
    return {key: str(value) for key, value in env.items() if key in allowed and value not in (None, "")}


def db_params(config_path: Path | None) -> dict[str, Any]:
    configured = service_config_env(config_path)
    def pick(name: str, default: str = "") -> str:
        return os.getenv(name, "").strip() or configured.get(name, "").strip() or default

    params = {
        "host": pick("GL02_PGHOST", "127.0.0.1"),
        "port": int(pick("GL02_PGPORT", "5432")),
        "dbname": pick("GL02_PGDATABASE", "bf_trend"),
        "user": pick("GL02_PGUSER"),
        "password": pick("GL02_PGPASSWORD"),
        "connect_timeout": 10,
    }
    if not params["user"] or not params["password"]:
        raise RuntimeError("未找到 GL02 PostgreSQL 只读连接配置。")
    return params


@dataclass(frozen=True)
class ReplayRequest:
    start: datetime
    end: datetime
    step_minutes: int

    @property
    def cache_key(self) -> tuple[str, str, int]:
        return (self.start.isoformat(), self.end.isoformat(), self.step_minutes)


class SensorRepository:
    """Read-only PostgreSQL adapter for the isolated replay service."""

    def __init__(self, config_path: Path | None):
        self.config_path = config_path

    def connect(self):
        return psycopg.connect(**db_params(self.config_path), row_factory=dict_row)

    def latest_timestamp(self) -> datetime | None:
        with self.connect() as conn:
            row = conn.execute("SELECT max(ts) AS ts FROM bf_sensor.one_minute_values").fetchone()
        return row.get("ts") if row else None

    def read_window(self, start: datetime, end: datetime) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
        with self.connect() as conn:
            registry_rows = conn.execute(
                """
                SELECT variable_name, tag_long_name, unit, description
                FROM bf_sensor.sensor_registry
                WHERE is_enabled = true
                  AND variable_name = ANY(%s)
                """,
                (list(REQUIRED_VARIABLES),),
            ).fetchall()
            metadata = {
                str(row["variable_name"]): {
                    "tag_long_name": str(row["tag_long_name"]),
                    "unit": str(row.get("unit") or ""),
                    "description": str(row.get("description") or ""),
                }
                for row in registry_rows
            }
            tags = [item["tag_long_name"] for item in metadata.values()]
            if not tags:
                return metadata, pd.DataFrame()
            rows = conn.execute(
                """
                SELECT r.variable_name, v.ts, v.value
                FROM bf_sensor.one_minute_values AS v
                JOIN bf_sensor.sensor_registry AS r ON r.tag_long_name = v.tag_long_name
                WHERE v.tag_long_name = ANY(%s)
                  AND v.ts >= %s
                  AND v.ts <= %s
                ORDER BY v.ts ASC
                """,
                (tags, start, end),
            ).fetchall()
        if not rows:
            return metadata, pd.DataFrame()
        table: dict[datetime, dict[str, float | None]] = {}
        for row in rows:
            ts = row["ts"]
            variable = str(row["variable_name"])
            table.setdefault(ts, {})[variable] = _finite(row.get("value"))
        frame = pd.DataFrame.from_dict(table, orient="index").sort_index()
        frame.index = pd.to_datetime(frame.index)
        frame.index.name = "timestamp"
        return metadata, frame


def downsample_frame(frame: pd.DataFrame, start: datetime, end: datetime, step_minutes: int) -> pd.DataFrame:
    """Use each completed bucket's last measured value; never backfill future samples."""
    if frame.empty:
        return frame.copy()
    sampled = frame.resample(f"{step_minutes}min", label="right", closed="right").last()
    return sampled.loc[(sampled.index >= pd.Timestamp(start)) & (sampled.index <= pd.Timestamp(end))]


def compact_estimate(estimate: dict[str, Any], evaluation_time: datetime) -> dict[str, Any]:
    if estimate.get("status") != "available":
        return {
            "time": evaluation_time.isoformat(timespec="seconds"),
            "status": "unavailable",
            "reason_codes": list(estimate.get("reason_codes") or []),
            "evidence": "estimated",
            "calibration_status": "uncalibrated",
            "control_use": "prohibited",
        }
    movement = estimate.get("movement") or {}
    return {
        "time": evaluation_time.isoformat(timespec="seconds"),
        "status": "available",
        "center_height_m": _finite(estimate.get("centerHeight")),
        "thickness_m": _finite(estimate.get("thickness")),
        "eccentricity_m": _finite(estimate.get("eccentricity")),
        "eccentric_angle_rad": _finite(estimate.get("eccentricAngle")),
        "direction": movement.get("direction"),
        "velocity_m_per_h": _finite(movement.get("velocity_m_per_h")),
        "forecast_height_m": _finite(movement.get("forecast_height_m")),
        "confidence": _finite(estimate.get("confidence")),
        "input_coverage": _finite(estimate.get("input_coverage")),
        "sample_time": estimate.get("sample_time"),
        "evidence": estimate.get("evidence", "estimated"),
        "calibration_status": estimate.get("calibration_status", "uncalibrated"),
        "control_use": estimate.get("control_use", "prohibited"),
        "root_definition": estimate.get("root_definition", "wall_thermal_activity_centroid"),
        "forecast_assumption": movement.get("forecast_assumption", "constant_velocity_uncalibrated"),
    }


def build_cohesive_series(raw_frame: pd.DataFrame, display_index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    if raw_frame.empty:
        return []
    estimator = CohesiveZoneEstimator()
    items: list[dict[str, Any]] = []
    for timestamp in display_index:
        evaluation = timestamp.to_pydatetime()
        try:
            estimate = estimator.estimate(raw_frame.loc[:timestamp], evaluation_time=evaluation)
        except (ValueError, TypeError, KeyError) as exc:
            logging.warning("C2 estimator failed at %s: %s", evaluation.isoformat(), type(exc).__name__)
            estimate = {"status": "unavailable", "reason_codes": ["estimator_input_error"]}
        items.append(compact_estimate(estimate, evaluation))
    return items


def point_payload(
    layout: Iterable[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
    sampled: pd.DataFrame,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in layout:
        point = dict(item)
        point_id = point["id"]
        meta = metadata.get(point_id) or {}
        point["description"] = meta.get("description") or point_id
        point["unit"] = meta.get("unit") or point.get("unit")
        point["radius_m"] = round(_profile_radius(float(point["height_m"])) + (0.14 if point["metric"] == "pressure" else 0.08), 4)
        if point_id in sampled.columns:
            point["values"] = [_finite(value) for value in sampled[point_id].tolist()]
        else:
            point["values"] = [None] * len(sampled.index)
        point["available_count"] = sum(value is not None for value in point["values"])
        points.append(point)
    return points


def build_replay_payload(
    request: ReplayRequest,
    metadata: dict[str, dict[str, Any]],
    raw_frame: pd.DataFrame,
) -> dict[str, Any]:
    sampled = downsample_frame(raw_frame, request.start, request.end, request.step_minutes)
    temperature_points = point_payload(BODY_LAYOUT, metadata, sampled)
    pressure_points = point_payload(STATIC_LAYOUT, metadata, sampled)
    timestamps = [timestamp.to_pydatetime().isoformat(timespec="seconds") for timestamp in sampled.index]
    all_temperature = [value for point in temperature_points for value in point["values"]]
    all_pressure = [value for point in pressure_points for value in point["values"]]
    return {
        "ok": bool(timestamps),
        "requirement_id": REQUIREMENT_ID,
        "model_version": MODEL_VERSION,
        "source": "bf_sensor.one_minute_values",
        "aggregation": f"{request.step_minutes}min_last_valid_in_bucket",
        "start_time": request.start.isoformat(timespec="seconds"),
        "end_time": request.end.isoformat(timespec="seconds"),
        "timeline": timestamps,
        "points": temperature_points + pressure_points,
        "scales": {
            "temperature": {**_quantile_scale(all_temperature), "unit": "°C"},
            "pressure": {**_quantile_scale(all_pressure), "unit": "kPa"},
        },
        "coverage": {
            "temperature": round(sum(point["available_count"] for point in temperature_points) / max(1, len(temperature_points) * len(timestamps)), 6),
            "pressure": round(sum(point["available_count"] for point in pressure_points) / max(1, len(pressure_points) * len(timestamps)), 6),
        },
        "cohesive_zone": build_cohesive_series(raw_frame, sampled.index),
        "evidence": {
            "temperature": "measured",
            "static_pressure": "measured",
            "cohesive_zone": "estimated",
            "calibration_status": "uncalibrated",
            "control_use": "prohibited",
            "confidence_cap": 0.45,
        },
        "notes": [
            "亮度在本次已加载时间窗内使用固定 P05-P95 色阶，不会随拖动时间轴重标定。",
            "温度和静压力点均为实测离散点；点间颜色或软熔带覆盖仅作估计展示，非连续实测场。",
            "静压力只在 20.350m、23.488m、28.976m 三个物理标高存在；炉腹和炉身上部不外推静压力。",
            "软熔带为 C2 炉墙热活动根部代理，未标定、禁止用于控制。",
        ],
    }


class ReplayService:
    """Bounded request validation plus a short-lived, read-only replay cache."""

    def __init__(self, repository: SensorRepository):
        self.repository = repository
        self._cache: dict[tuple[str, str, int], tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def resolve_request(self, query: dict[str, list[str]]) -> ReplayRequest:
        latest = self.repository.latest_timestamp()
        if latest is None:
            raise RuntimeError("传感器分钟表没有可用时间戳。")
        end = _parse_datetime(query.get("end", [""])[0]) if query.get("end", [""])[0] else latest.replace(second=0, microsecond=0)
        start = _parse_datetime(query.get("start", [""])[0]) if query.get("start", [""])[0] else end - timedelta(hours=6)
        step = int(query.get("step_minutes", ["5"])[0] or 5)
        if step < 1 or step > 60:
            raise ValueError("step_minutes 必须在 1 到 60 之间。")
        if start >= end:
            raise ValueError("开始时间必须早于结束时间。")
        if end > latest + timedelta(minutes=1):
            raise ValueError("结束时间不能晚于数据库最新有效采样时间。")
        if end - start > timedelta(hours=MAX_HOURS):
            raise ValueError(f"单次回放最长 {MAX_HOURS} 小时。")
        frame_count = math.ceil((end - start).total_seconds() / 60 / step)
        if frame_count > MAX_FRAMES:
            raise ValueError(f"时间轴最多 {MAX_FRAMES} 帧；请缩短时间窗或增大步长。")
        return ReplayRequest(start=start, end=end, step_minutes=step)

    def replay(self, query: dict[str, list[str]]) -> dict[str, Any]:
        request = self.resolve_request(query)
        with self._lock:
            cached = self._cache.get(request.cache_key)
            if cached and time.monotonic() - cached[0] < 45:
                return {**cached[1], "cache": "hit"}
        metadata, raw_frame = self.repository.read_window(request.start - timedelta(minutes=C2_LOOKBACK_MINUTES), request.end)
        payload = build_replay_payload(request, metadata, raw_frame)
        if not payload["ok"]:
            raise RuntimeError("所选时间窗内没有可回放的传感器数据。")
        with self._lock:
            self._cache = {request.cache_key: (time.monotonic(), payload)}
        return {**payload, "cache": "miss"}

    def config(self) -> dict[str, Any]:
        return {
            "requirement_id": REQUIREMENT_ID,
            "regions": REGIONS,
            "temperature_layers": [
                {"layer": layer, "height_m": height, "region": region}
                for layer, height, region in (
                    (7, 16.860, "belly"), (8, 18.335, "belly"), (9, 20.125, "waist"),
                    (10, 21.860, "stack_lower"), (11, 23.711, "stack_lower"),
                    (12, 25.441, "stack_lower"), (13, 27.171, "stack_lower"),
                    (14, 28.901, "stack_middle"), (15, 30.631, "stack_upper"), (16, 32.361, "stack_upper"),
                )
            ],
            "static_pressure_heights": [
                {"band": "lower", "height_m": 20.350, "region": "waist", "azimuths": "ABCDEF"},
                {"band": "middle", "height_m": 23.488, "region": "stack_lower", "azimuths": "ABCDEF"},
                {"band": "upper", "height_m": 28.976, "region": "stack_middle", "azimuths": "ABCDEF"},
            ],
            "soft_zone": {
                "evidence": "estimated",
                "calibration_status": "uncalibrated",
                "control_use": "prohibited",
                "confidence_cap": 0.45,
                "root_definition": "wall_thermal_activity_centroid",
            },
        }


class ReplayHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], service: ReplayService, static_dir: Path):
        super().__init__(address, handler)
        self.service = service
        self.static_dir = static_dir.resolve()
        self.frontend_dir = self.static_dir.parent


class ReplayHandler(BaseHTTPRequestHandler):
    server: ReplayHttpServer
    server_version = "GL02SoftZoneReplay/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, relative_path: str) -> None:
        if relative_path in {"", "/"}:
            target = self.server.static_dir / "index.html"
        elif relative_path.startswith("/libs/"):
            target = self.server.frontend_dir / relative_path.lstrip("/")
        else:
            target = self.server.static_dir / relative_path.lstrip("/")
        try:
            target = target.resolve()
            allowed = target.is_relative_to(self.server.static_dir) or target.is_relative_to(self.server.frontend_dir / "libs")
        except (OSError, ValueError):
            allowed = False
        if not allowed or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "资源不存在")
            return
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime.endswith("javascript") else mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                latest = self.server.service.repository.latest_timestamp()
                self._json(HTTPStatus.OK, {"ok": bool(latest), "latest_sample_time": latest, "requirement_id": REQUIREMENT_ID})
                return
            if parsed.path == "/api/config":
                self._json(HTTPStatus.OK, self.server.service.config())
                return
            if parsed.path == "/api/replay":
                self._json(HTTPStatus.OK, self.server.service.replay(parse_qs(parsed.query)))
                return
            self._static(unquote(parsed.path))
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_REQUEST", "message": str(exc)})
        except (RuntimeError, psycopg.Error, OSError) as exc:
            logging.exception("replay request failed")
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "DATA_UNAVAILABLE", "message": "数据链暂不可用，请检查只读数据库连接或缩小时间窗。"})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GL02 软熔带时空回放独立页面服务。")
    parser.add_argument("--host", default=os.getenv("BF_SOFT_ZONE_REPLAY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BF_SOFT_ZONE_REPLAY_PORT", "8128")))
    parser.add_argument("--static-dir", type=Path, default=PROJECT_ROOT / "高炉前端数据" / "soft_zone_replay")
    parser.add_argument(
        "--db-config",
        type=Path,
        default=PROJECT_ROOT / "tools" / "service_configs" / "22012_BFV4PreviewProxy8093.json",
        help="现有托管服务 JSON，只读取 GL02 PostgreSQL 环境变量；不会复制或打印凭据。",
    )
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")
    if not args.static_dir.is_dir():
        raise SystemExit(f"静态页面目录不存在：{args.static_dir}")
    service = ReplayService(SensorRepository(args.db_config))
    server = ReplayHttpServer((args.host, args.port), ReplayHandler, service, args.static_dir)
    logging.info("soft-zone replay page listening on http://%s:%s/", args.host, args.port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
