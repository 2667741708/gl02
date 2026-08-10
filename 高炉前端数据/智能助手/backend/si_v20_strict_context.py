"""Strict whole-hour full-context features and portable LightGBM inference.

Only rows whose source timestamp and first local availability timestamp are not
later than the whole-hour slot are visible.  The module reads the 220.12 local
PostgreSQL mirror only; it never connects to IMES/Vastbase directly.

Requirement: REQ-SI-V20-STRICT-HOURLY-20260810.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import threading
from typing import Any, Iterable


MODEL_ENV = "BF_SI_V20_STRICT_MODEL_PATH"
DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "si_v20_strict_context_lgbm_v1.json.gz"
)
SENSOR_WINDOWS_MINUTES = (30, 60, 120, 240, 360, 480, 720)
PCI_WINDOWS_HOURS = (1, 2, 4, 6, 8, 12)
SENSOR_FEATURE_RE = re.compile(r"^v20_sensor__(?P<short>.+?)__(?P<window>\d+)m_")
CHEMISTRY_DATASET_HINTS = (
    "sinter_chemistry",
    "sinter_machine_sample_insp_final",
    "v_qpes_sinter_machine_sample_insp_final",
)
CHEMISTRY_FIELDS = {
    "tfe": ("tfevalue", "TFe", "tfe"),
    "feo": ("feovalue", "FeO", "feo"),
    "sio2": ("sio2value", "SiO2", "sio2"),
    "al2o3": ("al2o3value", "Al2O3", "al2o3"),
    "cao": ("caovalue", "CaO", "cao"),
    "mgo": ("mgovalue", "MgO", "mgo"),
    "p": ("pvalue", "P", "p"),
    "s": ("svalue", "S", "s"),
    "tio2": ("tio2value", "TiO2", "tio2"),
    "mno": ("mnovalue", "MnO", "mno"),
    "zn": ("znvalue", "Zn", "zn"),
    "cr": ("crvalue", "Cr", "cr"),
    "r2": ("r2value", "R2", "r2"),
    "mgal": ("mgalvalue", "Mg/Al", "mgal"),
    "alsi": ("alsivalue", "Al/Si", "alsi"),
    "qd": ("qdvalue", "QD", "qd"),
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("T", " ")).replace(tzinfo=None)
    except ValueError:
        return None


def _safe_token(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_")


def _linear_slope_per_hour(points: list[tuple[datetime, float]]) -> float | None:
    if len(points) < 2:
        return None
    origin = points[0][0]
    xs = [(ts - origin).total_seconds() / 3600.0 for ts, _ in points]
    ys = [value for _, value in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator <= 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


def _window_stats(
    points: Iterable[tuple[datetime, float]],
    *,
    cutoff_ts: datetime,
    window_minutes: int,
) -> dict[str, float | None]:
    start_ts = cutoff_ts - timedelta(minutes=window_minutes)
    visible = sorted(
        ((ts, value) for ts, value in points if start_ts <= ts <= cutoff_ts),
        key=lambda item: item[0],
    )
    if not visible:
        return {
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "last": None,
            "delta": None,
            "coverage_minutes": 0.0,
            "coverage_ratio": 0.0,
            "slope_per_hour": None,
        }
    values = [value for _, value in visible]
    return {
        "mean": sum(values) / len(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "last": values[-1],
        "delta": values[-1] - values[0],
        "coverage_minutes": float(len({ts.replace(second=0, microsecond=0) for ts, _ in visible})),
        "coverage_ratio": min(len(visible) / max(window_minutes, 1), 1.0),
        "slope_per_hour": _linear_slope_per_hour(visible),
    }


class PortableLightGBMModel:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.path = path
        self.sha256 = hashlib.sha256(raw).hexdigest()
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            self.payload = json.load(handle)
        self.schema = str(self.payload["schema"])
        self.model_name = str(self.payload["model_name"])
        self.feature_columns = [str(item) for item in self.payload["feature_columns"]]
        self.fill_values = dict(self.payload.get("fill_values") or {})
        self.trees = list((self.payload.get("lightgbm") or {}).get("tree_info") or [])
        self.quantiles = dict(self.payload.get("residual_quantiles") or {})
        if not self.feature_columns or not self.trees:
            raise RuntimeError("严格整点完整上下文模型合同为空")

    @staticmethod
    def _leaf(node: dict[str, Any], row: list[float]) -> float:
        current = node
        while "leaf_value" not in current:
            index = int(current["split_feature"])
            value = row[index]
            missing = not math.isfinite(value)
            if missing:
                go_left = bool(current.get("default_left", True))
            elif str(current.get("decision_type") or "<=") == "<=":
                go_left = value <= float(current["threshold"])
            else:
                allowed = {str(item) for item in str(current.get("threshold") or "").split("||")}
                go_left = str(int(value)) in allowed
            current = current["left_child"] if go_left else current["right_child"]
        return float(current["leaf_value"])

    def predict_one(self, features: dict[str, Any]) -> float:
        row: list[float] = []
        for name in self.feature_columns:
            value = _number(features.get(name))
            if value is None:
                value = _number(self.fill_values.get(name))
            row.append(value if value is not None else float("nan"))
        return sum(self._leaf(tree["tree_structure"], row) for tree in self.trees)

    def interval(self, point: float) -> dict[str, float]:
        def quantile(name: str) -> float:
            return _number(self.quantiles.get(name)) or 0.0

        return {
            "p10": point + quantile("q10"),
            "p50": point + quantile("q50"),
            "p90": point + quantile("q90"),
        }


_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: tuple[str, int, PortableLightGBMModel] | None = None


def load_strict_context_model() -> PortableLightGBMModel:
    global _MODEL_CACHE
    path = Path(os.getenv(MODEL_ENV) or DEFAULT_MODEL_PATH).resolve()
    if not path.exists():
        raise RuntimeError(f"严格整点完整上下文模型不存在：{path}")
    key = str(path)
    mtime = path.stat().st_mtime_ns
    with _MODEL_LOCK:
        if _MODEL_CACHE is None or _MODEL_CACHE[0] != key or _MODEL_CACHE[1] != mtime:
            _MODEL_CACHE = (key, mtime, PortableLightGBMModel(path))
        return _MODEL_CACHE[2]


def _sensor_short_names(feature_columns: Iterable[str]) -> list[str]:
    names: set[str] = set()
    for column in feature_columns:
        match = SENSOR_FEATURE_RE.match(column)
        if match:
            names.add(match.group("short"))
    return sorted(names)


def _read_sensor_points(
    connection: Any,
    *,
    cutoff_ts: datetime,
    short_names: list[str],
) -> tuple[dict[str, list[tuple[datetime, float]]], dict[str, Any], list[tuple[datetime, float]]]:
    if not short_names:
        return {}, {"available": False, "reason": "model_has_no_sensor_features"}, []
    start_ts = cutoff_ts - timedelta(minutes=max(SENSOR_WINDOWS_MINUTES))
    rows = connection.execute(
        """
        SELECT r.short_name, r.variable_name, v.ts, v.value, v.collected_at
          FROM bf_sensor.sensor_registry r
          JOIN bf_sensor.one_minute_values v ON v.tag_long_name = r.tag_long_name
         WHERE r.is_enabled IS TRUE
           AND r.is_derived IS FALSE
           AND r.short_name = ANY(%s::text[])
           AND v.ts >= %s
           AND v.ts <= %s
           AND v.collected_at <= %s
           AND v.value IS NOT NULL
         ORDER BY r.short_name, v.ts
        """,
        (short_names, start_ts, cutoff_ts, cutoff_ts),
    ).fetchall()
    grouped: dict[str, list[tuple[datetime, float]]] = {}
    pci_points: list[tuple[datetime, float]] = []
    max_source: datetime | None = None
    max_ingested: datetime | None = None
    for source in rows:
        item = dict(source)
        ts = _datetime(item.get("ts"))
        collected = _datetime(item.get("collected_at"))
        value = _number(item.get("value"))
        if ts is None or collected is None or value is None:
            continue
        short_name = str(item.get("short_name") or "")
        grouped.setdefault(short_name, []).append((ts, value))
        if str(item.get("variable_name") or "") == "PCI_rate":
            pci_points.append((ts, value))
        max_source = ts if max_source is None or ts > max_source else max_source
        max_ingested = collected if max_ingested is None or collected > max_ingested else max_ingested
    expected = len(short_names) * max(SENSOR_WINDOWS_MINUTES)
    return grouped, {
        "available": bool(rows),
        "source": "bf_sensor.one_minute_values",
        "row_count": len(rows),
        "sensor_count": len(grouped),
        "expected_sensor_count": len(short_names),
        "approximate_row_coverage": len(rows) / expected if expected else 0.0,
        "max_source_ts": max_source,
        "max_ingested_at": max_ingested,
        "cutoff_rule": "source_ts<=slot_ts and collected_at<=slot_ts",
    }, pci_points


def _sensor_features(
    grouped: dict[str, list[tuple[datetime, float]]],
    *,
    cutoff_ts: datetime,
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for short_name, points in grouped.items():
        prefix = f"v20_sensor__{_safe_token(short_name)}"
        for window in SENSOR_WINDOWS_MINUTES:
            stats = _window_stats(points, cutoff_ts=cutoff_ts, window_minutes=window)
            for name, value in stats.items():
                features[f"{prefix}__{window}m_{name}"] = value
    return features


def _pci_features(points: list[tuple[datetime, float]], *, cutoff_ts: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    features: dict[str, Any] = {}
    for hours in PCI_WINDOWS_HOURS:
        stats = _window_stats(points, cutoff_ts=cutoff_ts, window_minutes=hours * 60)
        prefix = f"v20_pci__{hours}h"
        coverage = _number(stats["coverage_minutes"]) or 0.0
        average = _number(stats["mean"])
        features[f"{prefix}_amount_t"] = average * coverage / 60.0 if average is not None and coverage else None
        features[f"{prefix}_avg_tph"] = average
        features[f"{prefix}_std_tph"] = stats["std"]
        features[f"{prefix}_coverage_minutes"] = coverage
        features[f"{prefix}_coverage_ratio"] = min(coverage / (hours * 60.0), 1.0)
        features[f"{prefix}_slope_tph_per_hour"] = stats["slope_per_hour"]
    return features, {
        "available": bool(points),
        "source": "bf_sensor.one_minute_values:PCI_rate",
        "row_count": len(points),
        "max_source_ts": max((item[0] for item in points), default=None),
        "cutoff_rule": "source_ts<=slot_ts and collected_at<=slot_ts",
    }


def _first_value(payload: dict[str, Any], names: Iterable[str]) -> Any:
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for name in names:
        if name in payload:
            return payload[name]
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _chemistry_features(connection: Any, *, cutoff_ts: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    relation = connection.execute("SELECT to_regclass('bf_imes.raw_rows') AS name").fetchone()
    if not relation or not relation["name"]:
        return {}, {"available": False, "reason": "bf_imes.raw_rows_missing"}
    datasets = connection.execute(
        """
        SELECT dataset_key
          FROM bf_imes.raw_rows
         WHERE dataset_key = ANY(%s::text[])
            OR dataset_key ILIKE '%%sinter%%chem%%'
         GROUP BY dataset_key
        """,
        (list(CHEMISTRY_DATASET_HINTS),),
    ).fetchall()
    keys = [str(dict(row)["dataset_key"]) for row in datasets]
    if not keys:
        return {}, {
            "available": False,
            "reason": "local_sinter_chemistry_dataset_not_mirrored",
            "source": "bf_imes.raw_rows",
            "lineage_confidence": 0.0,
        }
    rows = connection.execute(
        """
        SELECT row_json, COALESCE(fetched_at, updated_at) AS ingested_at
          FROM bf_imes.raw_rows
         WHERE dataset_key = ANY(%s::text[])
           AND COALESCE(fetched_at, updated_at) <= %s
           AND COALESCE(fetched_at, updated_at) >= %s
         ORDER BY COALESCE(fetched_at, updated_at)
        """,
        (keys, cutoff_ts, cutoff_ts - timedelta(hours=72)),
    ).fetchall()
    prepared: list[dict[str, Any]] = []
    for source in rows:
        item = dict(source)
        payload = dict(item.get("row_json") or {})
        published = _datetime(_first_value(payload, ("发布时间", "published_ts", "publishTime")))
        ingested = _datetime(item.get("ingested_at"))
        machine = str(_first_value(payload, ("加工中心编码", "machine", "machineCode")) or "").upper()
        if published is None or ingested is None or published > cutoff_ts or machine not in {"JS1", "JS2"}:
            continue
        values = {name: _number(_first_value(payload, aliases)) for name, aliases in CHEMISTRY_FIELDS.items()}
        prepared.append({"published_ts": published, "ingested_at": ingested, "machine": machine, **values})
    if not prepared:
        return {}, {
            "available": False,
            "reason": "no_visible_local_chemistry_rows",
            "source": "bf_imes.raw_rows",
            "dataset_keys": keys,
            "lineage_confidence": 0.0,
        }
    features: dict[str, Any] = {
        "chem_context__lineage_confidence": 0.0,
        "chem_context__stale_hours_limit": 48.0,
    }
    latest_published = max(item["published_ts"] for item in prepared)
    for machine in ("JS1", "JS2"):
        machine_rows = [item for item in prepared if item["machine"] == machine]
        latest = max(machine_rows, key=lambda item: item["published_ts"], default=None)
        if latest:
            for field in CHEMISTRY_FIELDS:
                features[f"chem_context__{field}__latest__{machine}"] = latest[field]
            features[f"chem_context__latest_age_hours__{machine}"] = (cutoff_ts - latest["published_ts"]).total_seconds() / 3600.0
    for hours in (12, 24):
        visible = [item for item in prepared if item["published_ts"] >= cutoff_ts - timedelta(hours=hours)]
        features[f"chem_context__sample_count__{hours}h"] = float(len(visible))
        for field in CHEMISTRY_FIELDS:
            values = [item[field] for item in visible if item[field] is not None]
            features[f"chem_context__{field}__mean__{hours}h"] = sum(values) / len(values) if values else None
            features[f"chem_context__{field}__std__{hours}h"] = statistics.pstdev(values) if len(values) > 1 else (0.0 if values else None)
    latest_age = (cutoff_ts - latest_published).total_seconds() / 3600.0
    features["chem_context__stale_flag"] = 1.0 if latest_age > 48.0 else 0.0
    return features, {
        "available": True,
        "source": "bf_imes.raw_rows",
        "dataset_keys": keys,
        "visible_row_count": len(prepared),
        "max_source_ts": latest_published,
        "max_ingested_at": max(item["ingested_at"] for item in prepared),
        "lineage_confidence": 0.0,
        "boundary": "time_background_only_no_batch_bin_charge_heat_lineage",
    }


def build_strict_context_features(
    connection: Any,
    *,
    cutoff_ts: datetime,
    history_features: dict[str, Any],
    feature_columns: Iterable[str],
    lead_minutes: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return scored features and per-source as-of watermarks for one slot."""

    columns = list(feature_columns)
    grouped, sensor_watermark, pci_points = _read_sensor_points(
        connection,
        cutoff_ts=cutoff_ts,
        short_names=_sensor_short_names(columns),
    )
    sensor = _sensor_features(grouped, cutoff_ts=cutoff_ts)
    pci, pci_watermark = _pci_features(pci_points, cutoff_ts=cutoff_ts)
    chemistry, chemistry_watermark = _chemistry_features(connection, cutoff_ts=cutoff_ts)
    features = {
        **history_features,
        **pci,
        **sensor,
        **chemistry,
        "v20_protocol__lead_minutes": float(lead_minutes),
        "v20_protocol__is_lead_60m": 1.0 if abs(float(lead_minutes) - 60.0) < 0.5 else 0.0,
    }
    missing_scored = [name for name in columns if _number(features.get(name)) is None]
    watermarks = {
        "cutoff_ts": cutoff_ts,
        "history": {
            "visible_label_count": history_features.get("v20_history__visible_label_count"),
            "latest_available_age_hours": history_features.get("history_mean__previous_label_age_hours"),
            "cutoff_rule": "si_available_at<=slot_ts",
        },
        "pci": pci_watermark,
        "sensors": sensor_watermark,
        "chemistry": chemistry_watermark,
        "scored_feature_count": len(columns),
        "available_scored_feature_count": len(columns) - len(missing_scored),
        "missing_scored_feature_count": len(missing_scored),
        "missing_scored_feature_sample": missing_scored[:100],
        "future_source_rows_allowed": False,
        "future_ingested_rows_allowed": False,
    }
    return features, watermarks
