from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd
import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_ENGINE_DIR = PROJECT_ROOT / "炉况规则引擎"
if str(RULE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(RULE_ENGINE_DIR))

from features.prediction_features import build_prediction_feature_frame, recommended_covariates_for  # noqa: E402
from recommendation_adapter import (  # noqa: E402
    ENGINE_VERSION as RECOMMENDATION_ENGINE_VERSION,
    generate_recommendation_bundle,
)
from recommendation_audit_store import (
    latest_foreman_guidance,
    persist_foreman_guidance,
    persist_recommendation_bundle,
)  # noqa: E402
from abc_burden_rate import fetch_burden_rate_snapshot  # noqa: E402
from abc_feature_builder import build_feature_snapshot as build_abc_feature_snapshot  # noqa: E402
from abc_rule_catalog import CATALOG_VERSION as ABC_CATALOG_VERSION  # noqa: E402
from abc_rule_engine import evaluate as evaluate_abc, load_config as load_abc_config, public_bundle as abc_public_bundle  # noqa: E402
from abc_runtime_store import persist_bundle as persist_abc_bundle  # noqa: E402


HOST = os.getenv("BF_WS_HOST", "0.0.0.0")
PORT = int(os.getenv("BF_WS_PORT", "8767"))
HISTORY_HOURS = float(os.getenv("BF_WS_HISTORY_HOURS", "8"))
DIAGNOSIS_HISTORY_HOURS = float(os.getenv("BF_WS_DIAGNOSIS_HISTORY_HOURS", "2"))
DIAGNOSIS_HISTORY_LIMIT = int(os.getenv("BF_WS_DIAGNOSIS_HISTORY_LIMIT", "96"))
TICK_SECONDS = float(os.getenv("BF_WS_TICK_SECONDS", "30"))
RECOMMENDATION_AUDIT_ENABLED = os.getenv(
    "BF_RECOMMENDATION_AUDIT_ENABLED", "1"
).strip().lower() not in {"0", "false", "no", "off"}
CHRONOS_BASE_URL = os.getenv("BF_CHRONOS_BASE_URL", "").rstrip("/")
CHRONOS_TIMEOUT_SECONDS = float(os.getenv("BF_CHRONOS_TIMEOUT_SECONDS", "900"))
COHESIVE_ZONE_ENABLED = os.getenv("BF_WS_COHESIVE_ZONE_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
COHESIVE_ZONE_HISTORY_MINUTES = max(
    45,
    int(os.getenv("BF_WS_COHESIVE_ZONE_HISTORY_MINUTES", "480")),
)
COHESIVE_ZONE_COMPUTE_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("BF_WS_COHESIVE_ZONE_COMPUTE_INTERVAL_SECONDS", "60")),
)
COHESIVE_ZONE_STALE_AFTER_SECONDS = max(
    60.0,
    float(os.getenv("BF_WS_COHESIVE_ZONE_STALE_AFTER_SECONDS", "600")),
)
COHESIVE_ZONE_CONFIG_PATH = os.getenv("BF_WS_COHESIVE_ZONE_CONFIG_PATH", "").strip() or None

COHESIVE_ZONE_BODY_HEIGHTS = {
    7: 16.860,
    8: 18.335,
    9: 20.125,
    10: 21.860,
    11: 23.711,
    12: 25.441,
    13: 27.171,
    14: 28.901,
    15: 30.631,
    16: 32.361,
}
COHESIVE_ZONE_STATIC_PRESSURE_LAYOUT = (
    ("lower", 20.350),
    ("middle", 23.488),
    ("upper", 28.976),
)
COHESIVE_ZONE_STATIC_PRESSURE_VARIABLES = tuple(
    f"P_static_{height}_{azimuth}"
    for height, _ in COHESIVE_ZONE_STATIC_PRESSURE_LAYOUT
    for azimuth in "ABCDEF"
)
COHESIVE_ZONE_STOCKLINE_VARIABLES = ("L", "L_south", "L_north")
COHESIVE_ZONE_BLAST_VARIABLES = (
    "Q_blast",
    "P_blast",
    "P_blast_cold",
    "T_blast",
    "O2_rate",
    "Q_O2",
    "PCI_rate",
    "PCI_set",
    "TFT",
    "PI",
    "DP_upper",
    "DP_lower",
    "DP_total",
)
COHESIVE_ZONE_DISPLAY_VARIABLES = (
    *(
        f"T_body_L{layer}_{azimuth}"
        for layer in range(7, 17)
        for azimuth in "ABCDEFGH"
    ),
    *COHESIVE_ZONE_STATIC_PRESSURE_VARIABLES,
    *COHESIVE_ZONE_STOCKLINE_VARIABLES,
    *COHESIVE_ZONE_BLAST_VARIABLES,
)

_COHESIVE_ZONE_SNAPSHOT_CACHE: dict[str, Any] = {
    "computed_monotonic": 0.0,
    "source_key": None,
    "snapshot": None,
}

FRONTEND_VARIABLES = [
    "L",
    "L_south",
    "L_north",
    "Hopper_weight",
    "Hopper_weight_set",
    "P_top",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "P_top_A",
    "P_top_B",
    "P_top_C",
    "P_top_D",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "Q_blast",
    "PCI_rate",
    "PCI_set",
    "Q_O2",
    "O2_rate",
    "TFT",
    "PI",
    "GasUtil",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "P_static_20m35",
    "P_static_23m49",
    "P_static_28m98",
    "T_throat_A",
    "T_throat_B",
    "T_throat_C",
    "T_throat_D",
    "T_taphole_1",
    "T_taphole_2",
]
FRONTEND_VARIABLES.extend(
    f"T_body_L{layer}_{suffix}"
    for layer in range(7, 17)
    for suffix in "ABCDEFGH"
)

# Inputs used by the server-side ABC common-feature builder.  They must not be
# added to FRONTEND_VARIABLES: the production websocket contract intentionally
# exposes only operator-facing variables, while cooling/N2 and sectional
# static-pressure points remain internal evidence inputs.
ABC_SERVER_ONLY_VARIABLES = (
    "BlastEnergy",
    "Q_soft_water",
    "P_soft_water",
    "Q_high_pressure_water",
    "P_high_pressure_water",
    "Q_medium_pressure_water",
    "P_medium_pressure_water",
    "ExpansionTankLevel",
    "Q_N2",
    "P_N2",
    *COHESIVE_ZONE_STATIC_PRESSURE_VARIABLES,
)
ABC_HISTORY_VARIABLES = tuple(dict.fromkeys((*FRONTEND_VARIABLES, *ABC_SERVER_ONLY_VARIABLES)))

BASELINE_COMPARE_VARIABLES = [
    "P_top",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "GasUtil",
    "TFT",
    "T_blast",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "O2_rate",
    "Q_O2",
    "PI",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "L",
    "L_south",
    "L_north",
    "PCI_rate",
    "PCI_set",
    "T_taphole_1",
    "T_taphole_2",
]

DIAGNOSIS_SCORE_KEYS = ("normal", "lowline", "edge", "center", "channel", "cold", "hot", "column")

CHRONOS_TARGET_IDS = (
    "P_top",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "GasUtil",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "PI",
)

CHRONOS_CORE_COVARIATES = (
    "Q_blast",
    "T_blast",
    "P_blast",
    "P_blast_cold",
    "P_top",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "L",
    "L_south",
    "L_north",
    "PCI_rate",
    "PCI_set",
    "DP_total",
    "DP_lower",
    "DP_upper",
    "GasUtil",
    "T_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
)

CHRONOS_TARGET_STRATEGY = {
    "P_top": {"context_minutes": 480, "feature_type": "detailed"},
    "P_top_gas_A": {"context_minutes": 480, "feature_type": "detailed"},
    "P_top_gas_B": {"context_minutes": 480, "feature_type": "detailed"},
    "P_top_gas_C": {"context_minutes": 480, "feature_type": "detailed"},
    "P_top_gas_D": {"context_minutes": 480, "feature_type": "detailed"},
    "Q_blast": {"context_minutes": 480, "feature_type": "summary"},
    "P_blast_cold": {"context_minutes": 240, "feature_type": "summary"},
    "P_blast": {"context_minutes": 240, "feature_type": "summary"},
    "T_blast": {"context_minutes": 480, "feature_type": "summary"},
    "PI": {"context_minutes": 480, "feature_type": "detailed"},
    "DP_total": {"context_minutes": 120, "feature_type": "summary"},
    "DP_lower": {"context_minutes": 120, "feature_type": "summary"},
    "DP_upper": {"context_minutes": 480, "feature_type": "summary"},
    "GasUtil": {"context_minutes": 120, "feature_type": "detailed"},
    "T_top": {"context_minutes": 480, "feature_type": "summary"},
    "T_top_A": {"context_minutes": 480, "feature_type": "summary"},
    "T_top_B": {"context_minutes": 480, "feature_type": "summary"},
    "T_top_C": {"context_minutes": 480, "feature_type": "summary"},
    "T_top_D": {"context_minutes": 480, "feature_type": "summary"},
}

CHRONOS_TOP_SUMMARY_EXTRAS = (
    "T_body_L14_mean",
    "T_body_L15_mean",
    "T_body_L16_mean",
    "T_body_L14_max",
    "T_body_L15_max",
    "T_body_L16_max",
    "T_body_L14_span",
    "T_body_L15_span",
    "T_body_L16_span",
    "T_body_upper_mean",
    "T_body_upper_mean_delta_5m",
)

DISPLAY_NAMES = {
    "PI": "透气性指数",
    "DP_total": "全压差",
    "DP_lower": "下部压差",
    "DP_upper": "上部压差",
    "GasUtil": "煤气利用率",
    "T_top": "综合顶温",
    "T_top_A": "顶温A",
    "T_top_B": "顶温B",
    "T_top_C": "顶温C",
    "T_top_D": "顶温D",
}


def pg_params() -> dict[str, Any]:
    user = os.getenv("GL02_PGUSER", "").strip()
    if not user:
        raise RuntimeError("GL02_PGUSER/GL02_PGPASSWORD are required")
    return {
        "host": os.getenv("GL02_PGHOST", "10.30.220.12"),
        "port": int(os.getenv("GL02_PGPORT", "5432")),
        "dbname": os.getenv("GL02_PGDATABASE", "bf_trend"),
        "user": user,
        "password": os.getenv("GL02_PGPASSWORD", ""),
        "connect_timeout": 8,
    }


def json_default(value: Any) -> str:
    return str(value)


def source_payload() -> dict[str, Any]:
    return {
        "type": "local_postgresql",
        "read_policy": os.getenv("BF_WS_READ_POLICY", "local_database_primary_synced_from_22012"),
        "pg_host": os.getenv("GL02_PGHOST", "10.30.220.12"),
        "pg_port": os.getenv("GL02_PGPORT", "5432"),
        "pg_database": os.getenv("GL02_PGDATABASE", "bf_trend"),
    }


def replay_payload() -> dict[str, Any]:
    return {
        "mode": "postgresql_realtime",
        "source": source_payload(),
        "history_hours": HISTORY_HOURS,
        "tick_seconds": TICK_SECONDS,
        "chronos_base_url": CHRONOS_BASE_URL,
    }


def empty_history_payload() -> dict[str, Any]:
    history: dict[str, Any] = {"timestamps": []}
    for var in FRONTEND_VARIABLES:
        history[var] = []
    return history


def fetch_abc_baselines(conn, evaluation_time: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Load the 30-day baseline applicable to an evaluation timestamp.

    Historical replay must never use a future baseline.  If the exact day was
    not materialised, use the latest earlier baseline and preserve its actual
    ``baseline_day`` in every row for audit.
    """
    evaluation_day = (evaluation_time or datetime.now()).date()
    row = conn.execute(
        """SELECT max(baseline_day) AS day
           FROM bf_sensor.daily_baselines
           WHERE baseline_days=30 AND baseline_day <= %s""",
        (evaluation_day,),
    ).fetchone()
    day = row["day"] if row else None
    if not day:
        return {}
    rows = conn.execute(
        """SELECT variable_name, median_ref, iqr_ref, p25, p75,
                  coverage_ratio, sample_count, baseline_day,
                  baseline_window_start, baseline_window_end, updated_at
           FROM bf_sensor.daily_baselines WHERE baseline_days=30 AND baseline_day=%s""",
        (day,),
    ).fetchall()
    return {str(item["variable_name"]): dict(item) for item in rows}


def empty_values_payload() -> dict[str, Any]:
    return {var: None for var in FRONTEND_VARIABLES}


def database_unavailable_reason(exc: Exception) -> str:
    if isinstance(exc, psycopg.errors.UndefinedTable):
        return "数据库实时分钟表不可用，请检查本地同步库表结构。"
    return "数据库实时链路暂不可用，请检查本地同步库连接。"


def unavailable_quality_payload(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": "local_postgresql",
        "message": reason,
        "missing_files": [],
        "missing_points_before_fill": {},
    }


def unavailable_diagnosis_payload(timestamp: str, reason: str) -> dict[str, Any]:
    raw_scores = {key: 0.0 for key in DIAGNOSIS_SCORE_KEYS}
    raw_scores["normal"] = 40.0
    return {
        "timestamp": timestamp,
        "diagnosis_ts": timestamp,
        "main_label": "normal",
        "label": "normal",
        "main_score": raw_scores["normal"],
        "score": raw_scores["normal"],
        "main_confidence": 0.0,
        "confidence": 0.0,
        "secondary_label": None,
        "secondary": None,
        "secondary_score": 0.0,
        "secondary_confidence": 0.0,
        "evidence": [reason],
        "raw_scores": raw_scores,
        "raw": raw_scores,
        "baseline_compare": {
            "mode": "unavailable",
            "coverage_hours": 0,
            "updated_at": timestamp,
            "items": [],
        },
    }


def unavailable_bf3d_snapshot(timestamp: str, reason: str) -> dict[str, Any]:
    """Return a schema-compatible empty 3D snapshot without fabricating measurements."""
    measured = {
        "stockline": {
            **{variable: None for variable in COHESIVE_ZONE_STOCKLINE_VARIABLES},
            "sample_time": None,
            "evidence": "no-data",
        },
        "static_pressure": [
            {
                "semantic_id": f"P_static_{height}_{azimuth}",
                "height_m": height_m,
                "azimuth": azimuth,
                "value": None,
                "unit": "kPa",
                "sample_time": None,
                "evidence": "no-data",
                "quality_state": "missing",
            }
            for height, height_m in COHESIVE_ZONE_STATIC_PRESSURE_LAYOUT
            for azimuth in "ABCDEF"
        ],
        "body_temperature": [
            {
                "semantic_id": f"T_body_L{layer}_{azimuth}",
                "layer": f"L{layer}",
                "height_m": height_m,
                "azimuth": azimuth,
                "value": None,
                "unit": "°C",
                "sample_time": None,
                "evidence": "no-data",
                "quality_state": "missing",
            }
            for layer, height_m in COHESIVE_ZONE_BODY_HEIGHTS.items()
            for azimuth in "ABCDEFGH"
        ],
        "blast": {
            **{variable: None for variable in COHESIVE_ZONE_BLAST_VARIABLES},
            "sample_time": None,
            "evidence": "no-data",
        },
        "active_tap": None,
    }
    quality = _cohesive_zone_snapshot_quality(
        frame=pd.DataFrame(),
        estimate={"status": "unavailable", "reason_codes": ["source_unavailable"]},
        measured=measured,
        missing=list(COHESIVE_ZONE_DISPLAY_VARIABLES),
        stale=[],
        warnings=[reason],
        evaluation_time=timestamp,
    )
    return {
        "schema_version": "bf3d_snapshot.v1",
        "furnace_id": "GL02",
        "mode": "live",
        "render_time": timestamp,
        "knowledge_time": timestamp,
        "heat_no": None,
        "watermarks": {
            "sensor_sample_time": None,
            "mes_event_time": None,
            "lab_published_at": None,
        },
        "measured": measured,
        "estimated": {
            "pressure_field": None,
            "cohesive_zone": None,
            "burden_state": None,
            "hearth_inventory": None,
        },
        "quality": quality,
    }


def unavailable_payload(payload_type: str, exc: Exception) -> dict[str, Any]:
    timestamp = datetime.now().isoformat(sep=" ")
    reason = database_unavailable_reason(exc)
    return {
        "type": payload_type,
        "timestamp": timestamp,
        "history": empty_history_payload() if payload_type == "init" else None,
        "diagnosis_history": [],
        "values": empty_values_payload(),
        "data_quality": unavailable_quality_payload(reason),
        "diagnosis": unavailable_diagnosis_payload(timestamp, reason),
        "bf3d_snapshot": unavailable_bf3d_snapshot(timestamp, reason),
        "source": source_payload(),
        "replay": replay_payload(),
    }


def latest_data_ts(conn) -> datetime | None:
    row = conn.execute("SELECT max(ts) AS ts FROM bf_sensor.one_minute_values").fetchone()
    return row["ts"] if row and row["ts"] else None


def fetch_variable_map(conn) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT variable_name, tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE is_enabled = true AND is_derived = false
        """
    ).fetchall()
    mapping = {str(row["variable_name"]): str(row["tag_long_name"]) for row in rows}
    # Derived frontend aliases.
    top_tags = [mapping.get(name) for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if mapping.get(name)]
    if top_tags:
        mapping["T_top"] = top_tags[0]
    return mapping


def fetch_history(conn, since: datetime) -> dict[str, Any]:
    mapping = fetch_variable_map(conn)
    tag_to_var = {tag: var for var, tag in mapping.items() if var != "T_top"}
    tags = sorted(set(tag_to_var))
    rows = []
    if tags:
        rows = conn.execute(
            """
            SELECT tag_long_name, ts, value
            FROM bf_sensor.one_minute_values
            WHERE ts >= %s AND tag_long_name = ANY(%s)
            ORDER BY ts ASC
            """,
            (since, tags),
        ).fetchall()
    by_ts: dict[datetime, dict[str, float]] = {}
    for row in rows:
        ts = row["ts"]
        var = tag_to_var.get(row["tag_long_name"])
        if not var:
            continue
        by_ts.setdefault(ts, {})[var] = float(row["value"]) if row["value"] is not None else None
    timestamps = sorted(by_ts)
    history: dict[str, Any] = {"timestamps": [ts.isoformat(sep=" ") for ts in timestamps]}
    for var in FRONTEND_VARIABLES:
        if var == "T_top":
            values = []
            for ts in timestamps:
                row = by_ts.get(ts, {})
                top = [row.get(name) for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if row.get(name) is not None]
                values.append(sum(top) / len(top) if top else None)
            history[var] = values
        else:
            history[var] = [by_ts.get(ts, {}).get(var) for ts in timestamps]
    return history


def fetch_abc_history(conn, since: datetime, evaluation_time: datetime) -> dict[str, Any]:
    """Return an internal-only, minute-aligned ABC feature window.

    The complete minute grid is deliberate: missing acquisition minutes remain
    ``None`` so z60/std15/slope30 coverage checks cannot be defeated by
    compressing sparse samples.  Server-only cooling/N2/static-pressure points
    never flow into the ordinary websocket ``history`` payload.
    """
    mapping = fetch_variable_map(conn)
    selected_mapping = {
        variable: mapping[variable]
        for variable in ABC_HISTORY_VARIABLES
        if variable != "T_top" and mapping.get(variable)
    }
    tag_to_var = {tag: variable for variable, tag in selected_mapping.items()}
    rows = []
    if tag_to_var:
        rows = conn.execute(
            """SELECT tag_long_name, date_trunc('minute', ts) AS minute_ts,
                      avg(value) AS value
               FROM bf_sensor.one_minute_values
               WHERE ts >= %s AND ts <= %s AND tag_long_name = ANY(%s)
               GROUP BY tag_long_name, date_trunc('minute', ts)
               ORDER BY minute_ts ASC""",
            (since, evaluation_time, sorted(tag_to_var)),
        ).fetchall()
    by_minute: dict[datetime, dict[str, float | None]] = {}
    for row in rows:
        variable = tag_to_var.get(row["tag_long_name"])
        if not variable:
            continue
        by_minute.setdefault(row["minute_ts"], {})[variable] = finite_float(row["value"])

    start_minute = since.replace(second=0, microsecond=0)
    end_minute = evaluation_time.replace(second=0, microsecond=0)
    timestamps: list[datetime] = []
    cursor = start_minute
    while cursor <= end_minute:
        timestamps.append(cursor)
        cursor += timedelta(minutes=1)
    history: dict[str, Any] = {
        "timestamps": [item.isoformat(sep=" ") for item in timestamps],
    }
    for variable in ABC_HISTORY_VARIABLES:
        if variable == "T_top":
            values = []
            for ts in timestamps:
                sample = by_minute.get(ts, {})
                top = [
                    sample.get(name)
                    for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D")
                    if sample.get(name) is not None
                ]
                values.append(sum(top) / len(top) if top else None)
            history[variable] = values
        else:
            history[variable] = [by_minute.get(ts, {}).get(variable) for ts in timestamps]
    return history


def abc_aligned_current(history: dict[str, Any]) -> dict[str, float]:
    """Take only values present in the final common minute bucket.

    Cross-sensor ranges must not combine five-minute-old A with current B/C/D.
    Standardized window features still use the full sparse 90-minute history.
    """
    timestamps = history.get("timestamps") or []
    if not timestamps:
        return {}
    index = len(timestamps) - 1
    result: dict[str, float] = {}
    for variable in ABC_HISTORY_VARIABLES:
        series = history.get(variable) or []
        if index >= len(series):
            continue
        value = finite_float(series[index])
        if value is not None:
            result[variable] = value
    return result


def fetch_chronos_feature_frame(conn, since: datetime) -> pd.DataFrame:
    """Build the Chronos feature table from all enabled physical PostgreSQL points."""
    mapping = fetch_variable_map(conn)
    physical_mapping = {var: tag for var, tag in mapping.items() if var != "T_top" and tag}
    tag_to_var = {tag: var for var, tag in physical_mapping.items()}
    rows = []
    if tag_to_var:
        rows = conn.execute(
            """
            SELECT tag_long_name, ts, value
            FROM bf_sensor.one_minute_values
            WHERE ts >= %s AND tag_long_name = ANY(%s)
            ORDER BY ts ASC
            """,
            (since, sorted(tag_to_var)),
        ).fetchall()

    by_ts: dict[datetime, dict[str, float | None]] = {}
    for row in rows:
        var = tag_to_var.get(row["tag_long_name"])
        if not var:
            continue
        value = row["value"]
        by_ts.setdefault(row["ts"], {})[var] = float(value) if value is not None else None
    if not by_ts:
        return pd.DataFrame()

    frame = pd.DataFrame.from_dict(by_ts, orient="index").sort_index()
    frame.index = pd.to_datetime(frame.index)
    top_cols = [name for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if name in frame.columns]
    if top_cols:
        frame["T_top"] = frame[top_cols].mean(axis=1)

    features = build_prediction_feature_frame(frame)
    for layer in range(7, 17):
        mean_col = f"T_body_L{layer}_mean"
        if mean_col in features.columns:
            features[f"{mean_col}_delta_5m"] = features[mean_col].diff(5)
    for col in ("T_body_lower_mean", "T_body_middle_mean", "T_body_upper_mean"):
        if col in features.columns:
            features[f"{col}_delta_5m"] = features[col].diff(5)
    return features.replace([float("inf"), float("-inf")], pd.NA).ffill().bfill()


def fetch_cohesive_zone_input_frame(
    conn,
    since: datetime,
    evaluation_time: datetime,
) -> pd.DataFrame:
    """Read the raw physical wide table up to the requested knowledge time.

    The upper timestamp bound is intentional: the C2 estimator must never see
    rows newer than the snapshot knowledge time. Missing values remain missing;
    this adapter does not backfill from later samples.
    """
    mapping = fetch_variable_map(conn)
    physical_mapping = {var: tag for var, tag in mapping.items() if var != "T_top" and tag}
    tag_to_var = {tag: var for var, tag in physical_mapping.items()}
    if not tag_to_var:
        return pd.DataFrame()
    rows = conn.execute(
        """
        SELECT tag_long_name, ts, value
        FROM bf_sensor.one_minute_values
        WHERE ts >= %s
          AND ts <= %s
          AND tag_long_name = ANY(%s)
        ORDER BY ts ASC
        """,
        (since, evaluation_time, sorted(tag_to_var)),
    ).fetchall()
    by_ts: dict[datetime, dict[str, float | None]] = {}
    for row in rows:
        variable = tag_to_var.get(row["tag_long_name"])
        if not variable:
            continue
        value = row["value"]
        by_ts.setdefault(row["ts"], {})[variable] = float(value) if value is not None else None
    if not by_ts:
        return pd.DataFrame()
    frame = pd.DataFrame.from_dict(by_ts, orient="index").sort_index()
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "timestamp"
    return frame.replace([float("inf"), float("-inf")], pd.NA)


def latest_values(conn) -> tuple[str | None, dict[str, Any]]:
    anchor = latest_data_ts(conn) or datetime.now()
    history = fetch_history(conn, anchor - timedelta(minutes=90))
    timestamps = history.get("timestamps") or []
    if not timestamps:
        return None, {var: None for var in FRONTEND_VARIABLES}
    # Different tags can land a minute or two apart.  Using the final timestamp
    # of the union for every variable incorrectly turns otherwise fresh values
    # into None.  Select each variable's own latest finite value, but never
    # carry it forward beyond the five-minute production freshness gate.
    latest_ts = parse_ts(timestamps[-1])
    values: dict[str, Any] = {}
    for var in FRONTEND_VARIABLES:
        series = history.get(var) or []
        selected = None
        for idx in range(min(len(series), len(timestamps)) - 1, -1, -1):
            value = finite_float(series[idx])
            if value is None:
                continue
            sample_ts = parse_ts(timestamps[idx])
            age_seconds = max(0.0, (latest_ts - sample_ts).total_seconds())
            if age_seconds <= 300:
                selected = value
            break
        values[var] = selected
    return timestamps[-1], values


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return datetime.now()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return pd.Timestamp(value).isoformat(sep=" ")
    except (TypeError, ValueError):
        return None


def _frame_at_or_before(frame: pd.DataFrame, evaluation_time: Any) -> pd.DataFrame:
    """Defensively enforce the knowledge-time boundary before estimation."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    bounded = frame.copy()
    bounded.index = pd.to_datetime(bounded.index, errors="coerce")
    bounded = bounded.loc[~bounded.index.isna()].sort_index()
    if bounded.empty:
        return bounded
    cutoff = pd.Timestamp(evaluation_time)
    frame_tz = bounded.index.tz
    if frame_tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(frame_tz)
    elif frame_tz is None and cutoff.tzinfo is not None:
        cutoff = cutoff.tz_localize(None)
    elif frame_tz is not None and cutoff.tzinfo is not None:
        cutoff = cutoff.tz_convert(frame_tz)
    return bounded.loc[bounded.index <= cutoff]


def _latest_frame_measurement(frame: pd.DataFrame, variable: str) -> tuple[float | None, str | None]:
    if frame.empty or variable not in frame.columns:
        return None, None
    values = pd.to_numeric(frame[variable], errors="coerce").dropna()
    if values.empty:
        return None, None
    return finite_float(values.iloc[-1]), _iso_timestamp(values.index[-1])


def _timestamp_age_seconds(later: Any, earlier: Any) -> float | None:
    if later is None or earlier is None:
        return None
    try:
        later_ts = pd.Timestamp(later)
        earlier_ts = pd.Timestamp(earlier)
        if later_ts.tzinfo is not None and earlier_ts.tzinfo is None:
            earlier_ts = earlier_ts.tz_localize(later_ts.tzinfo)
        elif later_ts.tzinfo is None and earlier_ts.tzinfo is not None:
            earlier_ts = earlier_ts.tz_localize(None)
        elif later_ts.tzinfo is not None and earlier_ts.tzinfo is not None:
            earlier_ts = earlier_ts.tz_convert(later_ts.tzinfo)
        return max(0.0, float((later_ts - earlier_ts).total_seconds()))
    except (TypeError, ValueError):
        return None


def _measurement_quality(value: float | None, sample_time: str | None, evaluation_time: Any) -> str:
    if value is None or sample_time is None:
        return "missing"
    age_seconds = _timestamp_age_seconds(evaluation_time, sample_time)
    if age_seconds is not None and age_seconds > COHESIVE_ZONE_STALE_AFTER_SECONDS:
        return "stale"
    return "good"


def _cohesive_zone_cache_source_key() -> tuple[str, str, str, str]:
    """Identify the live database/profile used by the cached C2 snapshot."""
    return (
        os.getenv("GL02_PGHOST", "10.30.220.12"),
        os.getenv("GL02_PGPORT", "5432"),
        os.getenv("GL02_PGDATABASE", "bf_trend"),
        os.getenv("BF_WS_READ_POLICY", "local_database_primary_synced_from_22012"),
    )


def _comparison_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp


def _validate_cohesive_zone_available_contract(
    result: dict[str, Any],
    evaluation_time: Any,
) -> list[str]:
    """Validate the bounded, non-control C2 contract before exposing geometry."""
    issues: list[str] = []

    def number(name: str, lower: float, upper: float) -> float | None:
        value = result.get(name)
        if isinstance(value, bool):
            issues.append(f"{name}:not_finite")
            return None
        numeric = finite_float(value)
        if numeric is None:
            issues.append(f"{name}:not_finite")
            return None
        if numeric < lower or numeric > upper:
            issues.append(f"{name}:out_of_range")
            return None
        return numeric

    center_height = number("centerHeight", 0.0, 50.0)
    thickness = number("thickness", 0.1, 10.0)
    inner_radius = number("innerRadius", 0.0, 10.0)
    outer_radius = number("outerRadius", 0.1, 10.0)
    number("eccentricity", 0.0, 5.0)
    number("eccentricAngle", -2.0 * math.pi, 2.0 * math.pi)
    number("amplitude", 0.0, 10.0)
    number("uncertainty", 0.0, 10.0)
    number("confidence", 0.0, 0.45)
    if inner_radius is not None and outer_radius is not None and outer_radius <= inner_radius:
        issues.append("radii:outer_not_greater_than_inner")
    if center_height is not None and thickness is not None:
        if center_height - thickness / 2.0 < 0.0 or center_height + thickness / 2.0 > 50.0:
            issues.append("thickness:outside_furnace_bounds")
    if not isinstance(result.get("shape"), str) or not result["shape"].strip():
        issues.append("shape:missing")
    if result.get("evidence") != "estimated":
        issues.append("evidence:not_estimated")
    if result.get("calibration_status") != "uncalibrated":
        issues.append("calibration_status:not_uncalibrated")
    if result.get("control_use") != "prohibited":
        issues.append("control_use:not_prohibited")
    if result.get("root_definition") != "wall_thermal_activity_centroid":
        issues.append("root_definition:invalid")
    if result.get("azimuth_reference") != "sensor_relative_A_zero":
        issues.append("azimuth_reference:invalid")
    if result.get("absolute_azimuth_status") != "unconfirmed":
        issues.append("absolute_azimuth_status:invalid")
    if not isinstance(result.get("model_version"), str) or not result["model_version"].strip():
        issues.append("model_version:missing")

    sample_time = result.get("sample_time")
    if not isinstance(sample_time, str) or not sample_time.strip():
        issues.append("sample_time:missing")
    else:
        try:
            parsed_sample_time = _comparison_timestamp(sample_time)
            if pd.isna(parsed_sample_time):
                issues.append("sample_time:invalid")
            elif parsed_sample_time > _comparison_timestamp(evaluation_time):
                issues.append("sample_time:after_knowledge_time")
        except (TypeError, ValueError):
            issues.append("sample_time:invalid")

    movement = result.get("movement")
    if not isinstance(movement, dict):
        issues.append("movement:missing")
    else:
        if movement.get("direction") not in {"up", "down", "stable"}:
            issues.append("movement.direction:invalid")
        velocity_raw = movement.get("velocity_m_per_h")
        velocity = None if isinstance(velocity_raw, bool) else finite_float(velocity_raw)
        if velocity is None or not math.isfinite(velocity):
            issues.append("movement.velocity_m_per_h:not_finite")
        elif abs(velocity) > 5.0:
            issues.append("movement.velocity_m_per_h:out_of_range")
        horizon_raw = movement.get("forecast_horizon_minutes")
        horizon = None if isinstance(horizon_raw, bool) else finite_float(horizon_raw)
        if horizon is None or horizon <= 0.0 or horizon > 240.0:
            issues.append("movement.forecast_horizon_minutes:invalid")
        forecast_raw = movement.get("forecast_height_m")
        forecast_height = (
            None if isinstance(forecast_raw, bool) else finite_float(forecast_raw)
        )
        if forecast_height is None or forecast_height < 0.0 or forecast_height > 50.0:
            issues.append("movement.forecast_height_m:invalid")
        if movement.get("forecast_assumption") != "constant_velocity_uncalibrated":
            issues.append("movement.forecast_assumption:invalid")

    return list(dict.fromkeys(issues))


def _load_cohesive_zone_estimator():
    """Load the optional C2 estimator lazily so 8767 can start without it."""
    try:
        from features.cohesive_zone_estimator import estimate_cohesive_zone

        return estimate_cohesive_zone, None
    except Exception as exc:  # noqa: BLE001
        return None, f"cohesive_zone_estimator_import_failed:{type(exc).__name__}"


def _build_bf3d_measured(
    frame: pd.DataFrame,
    evaluation_time: Any,
) -> tuple[dict[str, Any], list[str], list[str]]:
    missing: list[str] = []
    stale: list[str] = []

    def read(variable: str) -> tuple[float | None, str | None, str]:
        value, sample_time = _latest_frame_measurement(frame, variable)
        quality_state = _measurement_quality(value, sample_time, evaluation_time)
        if variable in COHESIVE_ZONE_DISPLAY_VARIABLES:
            if quality_state == "missing":
                missing.append(variable)
            elif quality_state == "stale":
                stale.append(variable)
        return value, sample_time, quality_state

    stockline: dict[str, Any] = {}
    stockline_times: list[str] = []
    for variable in COHESIVE_ZONE_STOCKLINE_VARIABLES:
        value, sample_time, _ = read(variable)
        stockline[variable] = value
        if sample_time:
            stockline_times.append(sample_time)
    stockline["sample_time"] = max(stockline_times) if stockline_times else None
    stockline["evidence"] = "measured" if stockline.get("L") is not None else "no-data"

    static_pressure = []
    for height, height_m in COHESIVE_ZONE_STATIC_PRESSURE_LAYOUT:
        for azimuth in "ABCDEF":
            variable = f"P_static_{height}_{azimuth}"
            value, sample_time, quality_state = read(variable)
            static_pressure.append(
                {
                    "semantic_id": variable,
                    "height_m": height_m,
                    "azimuth": azimuth,
                    "value": value,
                    "unit": "kPa",
                    "sample_time": sample_time,
                    "evidence": "measured" if value is not None else "no-data",
                    "quality_state": quality_state,
                }
            )

    body_temperature = []
    for layer, height_m in COHESIVE_ZONE_BODY_HEIGHTS.items():
        for azimuth in "ABCDEFGH":
            variable = f"T_body_L{layer}_{azimuth}"
            value, sample_time, quality_state = read(variable)
            body_temperature.append(
                {
                    "semantic_id": variable,
                    "layer": f"L{layer}",
                    "height_m": height_m,
                    "azimuth": azimuth,
                    "value": value,
                    "unit": "°C",
                    "sample_time": sample_time,
                    "evidence": "measured" if value is not None else "no-data",
                    "quality_state": quality_state,
                }
            )

    blast: dict[str, Any] = {}
    blast_times: list[str] = []
    for variable in COHESIVE_ZONE_BLAST_VARIABLES:
        value, sample_time, _ = read(variable)
        blast[variable] = value
        if sample_time:
            blast_times.append(sample_time)
    blast["sample_time"] = max(blast_times) if blast_times else None
    blast["evidence"] = (
        "measured"
        if any(blast.get(variable) is not None for variable in COHESIVE_ZONE_BLAST_VARIABLES)
        else "no-data"
    )

    measured = {
        "stockline": stockline,
        "static_pressure": static_pressure,
        "body_temperature": body_temperature,
        "blast": blast,
        "active_tap": None,
    }
    return measured, sorted(set(missing)), sorted(set(stale))


def _latest_measured_sample_time(measured: dict[str, Any]) -> str | None:
    """Return the newest actual sample timestamp present in the measured block."""
    candidates: list[tuple[pd.Timestamp, str]] = []

    def add(value: Any) -> None:
        text = _iso_timestamp(value)
        if text is None:
            return
        timestamp = pd.Timestamp(text)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        candidates.append((timestamp, text))

    add((measured.get("stockline") or {}).get("sample_time"))
    add((measured.get("blast") or {}).get("sample_time"))
    for group in ("static_pressure", "body_temperature"):
        for row in measured.get(group) or []:
            add(row.get("sample_time"))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _cohesive_zone_snapshot_quality(
    *,
    frame: pd.DataFrame,
    estimate: dict[str, Any] | None,
    measured: dict[str, Any],
    missing: list[str],
    stale: list[str],
    warnings: list[str],
    evaluation_time: Any,
) -> dict[str, Any]:
    estimate_payload = estimate if isinstance(estimate, dict) else {}
    estimate_status = (
        str(estimate_payload.get("status"))
        if isinstance(estimate_payload.get("status"), str)
        else "unavailable"
    )
    raw_reason_codes = estimate_payload.get("reason_codes") or []
    if isinstance(raw_reason_codes, (list, tuple, set)):
        reason_codes = [str(item) for item in raw_reason_codes]
    else:
        reason_codes = [str(raw_reason_codes)]
    estimate_quality = (
        estimate_payload.get("quality")
        if isinstance(estimate_payload.get("quality"), dict)
        else {}
    )
    coverage_by_group = (
        estimate_quality.get("coverage_by_group")
        if isinstance(estimate_quality.get("coverage_by_group"), dict)
        else {}
    )

    def coverage(group: str) -> float:
        value = finite_float(coverage_by_group.get(group))
        return max(0.0, min(1.0, value)) if value is not None else 0.0

    def group_count(rows: list[dict[str, Any]]) -> dict[str, Any]:
        available = sum(finite_float(row.get("value")) is not None for row in rows)
        total = len(rows)
        return {
            "available": available,
            "total": total,
            "ratio": round(available / total, 6) if total else 0.0,
        }

    stockline_rows = [
        {"value": (measured.get("stockline") or {}).get(variable)}
        for variable in COHESIVE_ZONE_STOCKLINE_VARIABLES
    ]
    blast_rows = [
        {"value": (measured.get("blast") or {}).get(variable)}
        for variable in COHESIVE_ZONE_BLAST_VARIABLES
    ]
    display_groups = {
        "stockline": group_count(stockline_rows),
        "static_pressure_18": group_count(list(measured.get("static_pressure") or [])),
        "body_temperature_80": group_count(list(measured.get("body_temperature") or [])),
        "blast_and_pressure": group_count(blast_rows),
    }
    display_available = sum(group["available"] for group in display_groups.values())
    display_total = sum(group["total"] for group in display_groups.values())
    if missing:
        warnings.append(
            f"display_measurements_incomplete:{display_available}/{display_total}"
        )

    source_age = _timestamp_age_seconds(datetime.now(), evaluation_time)
    source_is_stale = (
        source_age is not None and source_age > COHESIVE_ZONE_STALE_AFTER_SECONDS
    )
    if source_is_stale:
        stale = sorted(set([*stale, "sensor_watermark"]))
    estimate_is_stale = any(code.startswith("stale_") for code in reason_codes)
    if frame.empty:
        state = "missing"
    elif source_is_stale or estimate_is_stale:
        state = "stale"
    elif estimate_status != "available":
        state = "degraded"
    else:
        state = "good"

    body_reason = any(
        code
        in {
            "insufficient_current_body_layers",
            "insufficient_reference_body_layers",
            "insufficient_common_body_layers",
            "insufficient_common_eccentric_sectors",
            "missing_body_temperature",
            "body_profile_not_estimable",
        }
        for code in reason_codes
    )
    pressure_reason = "insufficient_pressure_or_permeability_data" in reason_codes
    pressure_stale = "stale_pressure_or_permeability" in reason_codes
    minimum_groups = {
        "body_temperature": {
            "state": (
                "stale"
                if "stale_body_temperature" in reason_codes
                else "insufficient"
                if body_reason
                else "satisfied"
                if estimate_status == "available"
                else "unknown"
            ),
            "coverage": coverage("body_temperature"),
        },
        "pressure_permeability": {
            "state": (
                "stale"
                if pressure_stale
                else "insufficient"
                if pressure_reason
                else "satisfied"
                if estimate_status == "available"
                else "unknown"
            ),
            "coverage": coverage("pressure_permeability"),
        },
    }
    input_coverage = finite_float(estimate_payload.get("input_coverage"))

    def text_field(name: str) -> str | None:
        value = estimate_payload.get(name)
        return value if isinstance(value, str) else None

    return {
        "state": state,
        "missing": missing,
        "stale": stale,
        "bad": [],
        "warnings": list(dict.fromkeys(warnings)),
        "estimator_minimum_groups": minimum_groups,
        "optional_enhancements": {
            "static_pressure_18": display_groups["static_pressure_18"],
            "thermal_forcing": {"coverage": coverage("thermal_forcing")},
            "top_distribution": {"coverage": coverage("top_distribution")},
            "burden_descent": {"coverage": coverage("burden_descent")},
        },
        "display_completeness": {
            "available": display_available,
            "total": display_total,
            "ratio": round(display_available / display_total, 6) if display_total else 0.0,
            "groups": display_groups,
            "missing": missing,
            "stale": stale,
        },
        "cohesive_zone": {
            "status": estimate_status,
            "model_version": text_field("model_version"),
            "calibration_status": text_field("calibration_status"),
            "control_use": text_field("control_use"),
            "root_definition": text_field("root_definition"),
            "azimuth_reference": text_field("azimuth_reference"),
            "absolute_azimuth_status": text_field("absolute_azimuth_status"),
            "sample_time": _iso_timestamp(estimate_payload.get("sample_time")),
            "input_coverage": (
                max(0.0, min(1.0, input_coverage)) if input_coverage is not None else 0.0
            ),
            "reason_codes": reason_codes,
        },
    }


def build_bf3d_snapshot(conn, evaluation_time: Any) -> dict[str, Any]:
    """Build one cached live ``bf3d_snapshot.v1`` for REQ-BF3D-C2-001.

    Estimator import, data insufficiency, or estimator execution failures are
    represented as ``estimated.cohesive_zone = null`` and quality warnings.
    They never abort the existing WebSocket init/tick message.
    """
    evaluation_dt = parse_ts(evaluation_time)
    evaluation_iso = _iso_timestamp(evaluation_dt) or datetime.now().isoformat(sep=" ")
    now_monotonic = time.monotonic()
    source_key = _cohesive_zone_cache_source_key()
    cached_snapshot = _COHESIVE_ZONE_SNAPSHOT_CACHE.get("snapshot")
    cached_at = float(_COHESIVE_ZONE_SNAPSHOT_CACHE.get("computed_monotonic") or 0.0)
    cached_source_key = _COHESIVE_ZONE_SNAPSHOT_CACHE.get("source_key")
    cached_knowledge_time = (
        cached_snapshot.get("knowledge_time")
        if isinstance(cached_snapshot, dict)
        else None
    )
    cache_is_forward_safe = False
    if cached_knowledge_time is not None:
        try:
            cache_is_forward_safe = _comparison_timestamp(
                cached_knowledge_time
            ) <= _comparison_timestamp(evaluation_dt)
        except (TypeError, ValueError):
            cache_is_forward_safe = False
    if (
        cached_snapshot is not None
        and cached_source_key == source_key
        and cache_is_forward_safe
        and now_monotonic - cached_at < COHESIVE_ZONE_COMPUTE_INTERVAL_SECONDS
    ):
        return cached_snapshot

    render_time = datetime.now().isoformat(sep=" ")
    warnings: list[str] = []
    estimate_result: dict[str, Any] | None = None
    try:
        frame = fetch_cohesive_zone_input_frame(
            conn,
            evaluation_dt - timedelta(minutes=COHESIVE_ZONE_HISTORY_MINUTES),
            evaluation_dt,
        )
        frame = _frame_at_or_before(frame, evaluation_dt)
    except Exception as exc:  # noqa: BLE001
        frame = pd.DataFrame()
        warnings.append(f"cohesive_zone_input_failed:{type(exc).__name__}")

    measured, missing, stale = _build_bf3d_measured(frame, evaluation_dt)
    if not COHESIVE_ZONE_ENABLED:
        warnings.append("cohesive_zone_estimator_disabled")
    elif frame.empty:
        warnings.append("cohesive_zone_input_empty")
    else:
        estimator, import_warning = _load_cohesive_zone_estimator()
        if import_warning:
            warnings.append(import_warning)
        if estimator is not None:
            try:
                kwargs: dict[str, Any] = {"evaluation_time": evaluation_dt}
                if COHESIVE_ZONE_CONFIG_PATH:
                    kwargs["config_path"] = COHESIVE_ZONE_CONFIG_PATH
                raw_result = estimator(frame, **kwargs)
                if isinstance(raw_result, dict):
                    estimate_result = raw_result
                    if raw_result.get("status") == "available":
                        contract_issues = _validate_cohesive_zone_available_contract(
                            raw_result,
                            evaluation_dt,
                        )
                        if contract_issues:
                            warnings.extend(
                                f"cohesive_zone_estimator_contract_invalid:{issue}"
                                for issue in contract_issues
                            )
                            estimate_result = {
                                **raw_result,
                                "status": "contract_invalid",
                                "reason_codes": contract_issues,
                            }
                    else:
                        warnings.extend(
                            f"cohesive_zone_unavailable:{code}"
                            for code in (raw_result.get("reason_codes") or ["unspecified"])
                        )
                else:
                    warnings.append("cohesive_zone_estimator_invalid_result")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"cohesive_zone_estimator_failed:{type(exc).__name__}")

    cohesive_zone = (
        estimate_result
        if isinstance(estimate_result, dict) and estimate_result.get("status") == "available"
        else None
    )
    quality = _cohesive_zone_snapshot_quality(
        frame=frame,
        estimate=estimate_result,
        measured=measured,
        missing=missing,
        stale=stale,
        warnings=warnings,
        evaluation_time=evaluation_dt,
    )
    sensor_sample_time = _latest_measured_sample_time(measured)
    snapshot = {
        "schema_version": "bf3d_snapshot.v1",
        "furnace_id": "GL02",
        "mode": "live",
        "render_time": render_time,
        "knowledge_time": evaluation_iso,
        "heat_no": None,
        "watermarks": {
            "sensor_sample_time": sensor_sample_time,
            "mes_event_time": None,
            "lab_published_at": None,
        },
        "measured": measured,
        "estimated": {
            "pressure_field": None,
            "cohesive_zone": cohesive_zone,
            "burden_state": None,
            "hearth_inventory": None,
        },
        "quality": quality,
    }
    _COHESIVE_ZONE_SNAPSHOT_CACHE["computed_monotonic"] = now_monotonic
    _COHESIVE_ZONE_SNAPSHOT_CACHE["source_key"] = source_key
    _COHESIVE_ZONE_SNAPSHOT_CACHE["snapshot"] = snapshot
    return snapshot


def safe_build_bf3d_snapshot(conn, evaluation_time: Any) -> dict[str, Any]:
    """Protect the existing 8767 stream from any unexpected C2 adapter error."""
    try:
        return build_bf3d_snapshot(conn, evaluation_time)
    except Exception as exc:  # noqa: BLE001
        timestamp = _iso_timestamp(evaluation_time) or datetime.now().isoformat(sep=" ")
        return unavailable_bf3d_snapshot(
            timestamp,
            f"cohesive_zone_snapshot_failed:{type(exc).__name__}",
        )


def future_timestamps(cutoff: Any, horizon: int) -> list[str]:
    base = parse_ts(cutoff)
    return [(base + timedelta(minutes=idx)).isoformat(sep=" ") for idx in range(1, horizon + 1)]


def clean_series(values: list[Any], limit: int) -> list[float | None]:
    return [finite_float(value) for value in list(values)[-limit:]]


def clean_feature_series(values: Any, limit: int) -> list[float | None]:
    if hasattr(values, "tail"):
        values = values.tail(limit).tolist()
    return clean_series(list(values), limit)


def chronos_covariates_for_target(target_id: str, frame: pd.DataFrame) -> list[str]:
    covariates = recommended_covariates_for(target_id, frame.columns)
    if target_id.startswith("T_top"):
        covariates = [
            item
            for item in covariates
            if not (item.startswith("T_body_L14_") or item.startswith("T_body_L15_") or item.startswith("T_body_L16_"))
        ]
        for item in CHRONOS_TOP_SUMMARY_EXTRAS:
            if item in frame.columns and item not in covariates:
                covariates.append(item)
    if not covariates:
        covariates = [item for item in CHRONOS_CORE_COVARIATES if item != target_id and item in frame.columns]
    ordered = [target_id, *covariates]
    return [item for item in dict.fromkeys(ordered) if item in frame.columns]


def chronos_context_minutes_for_target(target_id: str, requested_context_mins: int) -> int:
    strategy = CHRONOS_TARGET_STRATEGY.get(target_id, {})
    target_context = int(strategy.get("context_minutes") or requested_context_mins or 480)
    if requested_context_mins:
        target_context = min(target_context, requested_context_mins)
    return max(30, min(24 * 60, target_context))


def build_chronos_job(frame: pd.DataFrame, target_id: str, horizon: int, context_mins: int) -> dict[str, Any]:
    if target_id not in CHRONOS_TARGET_IDS:
        raise ValueError(f"unsupported Chronos target: {target_id}")
    if target_id not in frame.columns:
        raise ValueError(f"target column is not available in database feature frame: {target_id}")
    context = frame.tail(context_mins)
    timestamps = [ts.isoformat(sep=" ") for ts in context.index.to_pydatetime()]
    target_values = clean_feature_series(context[target_id], context_mins)
    if len(target_values) < 30 or not any(value is not None for value in target_values):
        raise ValueError(f"not enough Chronos context for {target_id}: {len(target_values)}")
    cutoff = timestamps[-1] if timestamps else datetime.now().isoformat(sep=" ")
    covariates = []
    covariate_ids = chronos_covariates_for_target(target_id, context)
    for cov_id in covariate_ids:
        values = clean_feature_series(context[cov_id], len(target_values))
        if len(values) < 30 or not any(value is not None for value in values):
            continue
        payload_cov_id = f"{target_id}__self_history" if cov_id == target_id else cov_id
        payload_cov_name = f"{DISPLAY_NAMES.get(target_id, target_id)}自身历史" if cov_id == target_id else DISPLAY_NAMES.get(cov_id, cov_id)
        covariates.append(
            {
                "id": payload_cov_id,
                "source_id": cov_id,
                "name": payload_cov_name,
                "values": values,
                "nonnull_count": sum(value is not None for value in values),
            }
        )
    strategy = CHRONOS_TARGET_STRATEGY.get(target_id, {})
    return {
        "job_id": target_id,
        "target": {
            "id": target_id,
            "name": DISPLAY_NAMES.get(target_id, target_id),
            "values": target_values,
            "nonnull_count": sum(value is not None for value in target_values),
        },
        "covariates": covariates,
        "context_minutes": len(target_values),
        "prediction_minutes": horizon,
        "feature_type": strategy.get("feature_type", "recommended"),
        "feature_engine": "炉况规则引擎.features.prediction_features.recommended_covariates_for",
        "covariate_ids": [item["id"] for item in covariates],
        "cutoff_time": cutoff,
        "future_timestamps": future_timestamps(cutoff, horizon),
    }


def build_chronos_payload(request: dict[str, Any]) -> dict[str, Any]:
    horizon = max(1, min(240, int(request.get("prediction_minutes") or 120)))
    requested_context_mins = max(30, min(24 * 60, int(request.get("context_minutes") or 480)))
    requested = request.get("target_ids") if request.get("type") == "chronos_predict_recommended_batch" else None
    if not requested:
        single = str(request.get("target_id") or "").strip()
        requested = [single] if single else list(CHRONOS_TARGET_IDS)
    target_ids = [str(item).strip() for item in requested if str(item).strip()]
    if not target_ids:
        target_ids = list(CHRONOS_TARGET_IDS)
    context_by_target = {
        target_id: chronos_context_minutes_for_target(target_id, requested_context_mins)
        for target_id in target_ids
    }
    fetch_context_mins = max(context_by_target.values()) if context_by_target else requested_context_mins

    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        anchor = latest_data_ts(conn) or datetime.now()
        frame = fetch_chronos_feature_frame(conn, anchor - timedelta(minutes=fetch_context_mins + 10))

    jobs = []
    skipped = []
    for target_id in target_ids:
        try:
            jobs.append(build_chronos_job(frame, target_id, horizon, context_by_target[target_id]))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"target_id": target_id, "reason": str(exc)})
    if not jobs:
        raise RuntimeError(f"no Chronos target has enough context: {skipped}")
    return {
        "jobs": jobs,
        "skipped": skipped,
        "source": source_payload(),
        "feature_source": {
            "type": "postgresql_115_points_with_prediction_feature_frame",
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "time_start": frame.index[0].isoformat(sep=" ") if len(frame.index) else None,
            "time_end": frame.index[-1].isoformat(sep=" ") if len(frame.index) else None,
        },
        "request": {
            "prediction_minutes": horizon,
            "context_minutes": requested_context_mins,
            "context_minutes_by_target": context_by_target,
            "target_ids": target_ids,
            "data_source": request.get("data_source") or "postgresql_history",
        },
    }


def call_chronos_service(payload: dict[str, Any]) -> dict[str, Any]:
    if not CHRONOS_BASE_URL:
        raise RuntimeError("BF_CHRONOS_BASE_URL is not configured; start or select a Chronos prediction service.")
    req = Request(
        CHRONOS_BASE_URL + "/api/chronos/predict",
        data=json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=CHRONOS_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(result, dict):
        raise RuntimeError("Chronos service returned a non-object JSON payload")
    result.setdefault("type", "chronos_prediction_batch")
    result.setdefault("status", "success")
    result.setdefault("chronos_base_url", CHRONOS_BASE_URL)
    return result


async def handle_foreman_guidance_request(websocket, request: dict[str, Any]) -> bool:
    if request.get("type") != "foreman_guidance_save":
        return False
    request_id = request.get("request_id")
    try:
        result = await asyncio.to_thread(save_foreman_guidance_request, request)
        message = {"type": "foreman_guidance_saved", "request_id": request_id, **result}
    except Exception as exc:
        message = {"type": "foreman_guidance_error", "request_id": request_id, "state": "rejected", "read_only": True, "error_type": type(exc).__name__, "message": str(exc)}
    await websocket.send(json.dumps(message, ensure_ascii=False, default=json_default))
    return True


async def handle_chronos_request(websocket, request: dict[str, Any]) -> None:
    request_type = request.get("type")
    if request_type not in {"chronos_predict", "chronos_predict_recommended_batch"}:
        return
    target_id = request.get("target_id") or "recommended_batch"
    await websocket.send(
        json.dumps(
            {
                "type": "chronos_prediction_status",
                "status": "running_batch" if request_type == "chronos_predict_recommended_batch" else "running",
                "target_id": target_id,
                "engine": "chronos_service",
                "chronos_base_url": CHRONOS_BASE_URL,
            },
            ensure_ascii=False,
        )
    )
    loop = asyncio.get_running_loop()
    try:
        payload = await loop.run_in_executor(None, lambda: build_chronos_payload(request))
        result = await loop.run_in_executor(None, lambda: call_chronos_service(payload))
    except Exception as exc:  # noqa: BLE001
        result = {
            "type": "chronos_prediction_batch" if request_type == "chronos_predict_recommended_batch" else "chronos_prediction",
            "status": "error",
            "message": str(exc),
            "chronos_base_url": CHRONOS_BASE_URL,
        }
    await websocket.send(json.dumps(result, ensure_ascii=False, default=json_default))


def build_baseline_compare(conn, current_values: dict[str, Any] | None = None) -> dict[str, Any]:
    if current_values is None:
        _, current_values = latest_values(conn)

    day_row = conn.execute(
        """
        SELECT max(baseline_day) AS baseline_day
        FROM bf_sensor.daily_baselines
        WHERE baseline_days = 30
        """
    ).fetchone()
    baseline_day = day_row["baseline_day"] if day_row else None
    if not baseline_day:
        return {
            "mode": "database_daily_30d",
            "coverage_hours": 0,
            "updated_at": datetime.now().isoformat(sep=" "),
            "items": [],
        }

    rows = conn.execute(
        """
        SELECT baseline_day, baseline_window_start, baseline_window_end,
               variable_name, median_ref, iqr_ref, p10, p25, p75, p90, sample_count,
               coverage_ratio, updated_at
        FROM bf_sensor.daily_baselines
        WHERE baseline_day = %s
          AND baseline_days = 30
          AND variable_name = ANY(%s)
        ORDER BY array_position(%s, variable_name)
        """,
        (baseline_day, BASELINE_COMPARE_VARIABLES, BASELINE_COMPARE_VARIABLES),
    ).fetchall()

    items = []
    updated_values = []
    for row in rows:
        variable = row["variable_name"]
        current = finite_float(current_values.get(variable))
        reference = finite_float(row["median_ref"])
        iqr = finite_float(row["iqr_ref"])
        if current is None or reference is None:
            continue
        scale = max(abs(iqr or 0), 1e-6)
        normal_low = finite_float(row["p25"])
        normal_high = finite_float(row["p75"])
        updated_values.append(row["updated_at"])
        items.append(
            {
                "id": variable,
                "name": variable,
                "current": current,
                "mean_ref": reference,
                "z": (current - reference) / scale,
                "normal_low": normal_low,
                "normal_high": normal_high,
                "sample_count": row["sample_count"],
                "iqr_ref": iqr,
                "coverage_ratio": row["coverage_ratio"],
                "baseline_start": row["baseline_window_start"],
                "baseline_end": row["baseline_window_end"],
            }
        )

    latest_update = max((v for v in updated_values if v is not None), default=datetime.now())
    return {
        "mode": "database_daily_30d",
        "coverage_hours": 24 * 30,
        "updated_at": latest_update,
        "baseline_day": baseline_day,
        "items": items,
    }


def build_foreman_recommendation_context(
    conn: Any,
    current_values: dict[str, Any] | None,
    current_ts: Any,
) -> dict[str, Any]:
    """Attach the exact 30-day pressure quartiles required by the control contract."""
    context = dict(current_values or {})
    context["current_values_timestamp"] = current_ts
    context["P_blast_cold_timestamp"] = current_ts
    row = conn.execute(
        """
        SELECT baseline_day, p25, p75, sample_count, coverage_ratio, updated_at
        FROM bf_sensor.daily_baselines
        WHERE baseline_days = 30
          AND variable_name = 'P_blast_cold'
        ORDER BY baseline_day DESC, updated_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row:
        baseline = {
            "p25": row["p25"],
            "p75": row["p75"],
            "baseline_day": row["baseline_day"],
            "sample_count": row["sample_count"],
            "coverage_ratio": row["coverage_ratio"],
            "updated_at": row["updated_at"],
        }
        context["pressure_baseline"] = baseline
        for key, value in baseline.items():
            context[f"pressure_baseline_{key}"] = value
    return context


def normalize_diagnosis_scores(raw_scores: Any) -> dict[str, float]:
    raw = raw_scores if isinstance(raw_scores, dict) else {}
    scores: dict[str, float] = {}
    for key in DIAGNOSIS_SCORE_KEYS:
        value = finite_float(raw.get(key))
        scores[key] = value if value is not None else 0.0
    return scores


def diagnosis_snapshot_payload(
    row: dict[str, Any],
    *,
    include_diagnosis_json: bool = True,
    current_values: dict[str, Any] | None = None,
    audit_conn: Any | None = None,
) -> dict[str, Any]:
    payload = dict(row.get("diagnosis_json") or {}) if include_diagnosis_json else {}
    # Never pass server-side ABC formula snapshots through the production
    # WebSocket.  Only the allowlisted public contract is reconstructed below.
    internal_abc = payload.pop("abc_rule_bundle_internal", None)
    payload.pop("abc_rule_bundle_admin", None)
    payload.pop("abc_config_hash", None)
    raw_scores = normalize_diagnosis_scores(row.get("raw_scores") or payload.get("raw_scores") or payload.get("scores"))
    timestamp = row["diagnosis_ts"]
    main_label = row.get("main_label") or payload.get("main_label") or payload.get("label") or "normal"
    secondary_label = row.get("secondary_label") or payload.get("secondary_label")
    main_score = finite_float(row.get("main_score"))
    secondary_score = finite_float(row.get("secondary_score"))
    main_confidence = finite_float(row.get("main_confidence"))
    secondary_confidence = finite_float(row.get("secondary_confidence"))
    payload.update(
        {
            "timestamp": timestamp,
            "diagnosis_ts": timestamp,
            "main_label": main_label,
            "label": main_label,
            "main_score": main_score if main_score is not None else raw_scores.get(main_label, 0.0),
            "score": main_score if main_score is not None else raw_scores.get(main_label, 0.0),
            "main_confidence": main_confidence if main_confidence is not None else 0.0,
            "confidence": main_confidence if main_confidence is not None else 0.0,
            "secondary_label": secondary_label,
            "secondary": secondary_label,
            "secondary_score": secondary_score if secondary_score is not None else 0.0,
            "secondary_confidence": secondary_confidence if secondary_confidence is not None else 0.0,
            "evidence": row.get("evidence") or payload.get("evidence") or [],
            "raw_scores": raw_scores,
            "raw": raw_scores,
        }
    )
    try:
        if (
            isinstance(internal_abc, dict)
            and internal_abc.get("evaluations")
            and internal_abc.get("catalog_version") == ABC_CATALOG_VERSION
        ):
            abc_internal = internal_abc
        else:
            # The legacy diagnosis snapshot stores derived features in
            # ``feature_snapshot`` while the live bridge owns the current raw
            # sensor values.  ABC33 requires both.  The previous adapter passed
            # only the derived snapshot and also looked for quality fields on
            # unselected SQL columns, forcing coverage to 0 and all 33 rules to
            # ``needs_data`` despite healthy production data.
            combined_values = dict(current_values or {})
            combined_values.update(payload.get("feature_snapshot") or row.get("feature_snapshot") or {})
            coverage_source = payload.get("data_coverage") or row.get("data_coverage") or {}
            coverage = finite_float(coverage_source.get("coverage_ratio"))
            source_age = finite_float(payload.get("source_lag_seconds"))
            if source_age is None:
                source_age = finite_float(row.get("source_lag_seconds"))
            if isinstance(timestamp, datetime):
                anchor = timestamp.replace(tzinfo=None)
            elif timestamp:
                # one_minute_values/diagnosis_ts are PostgreSQL timestamps
                # without time zone.  Preserve the displayed plant wall-clock
                # fields if an API string happens to carry +08:00; converting
                # it to UTC would query the wrong eight-hour history window.
                anchor = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                anchor = datetime.now()
            abc_history: dict[str, Any] = {}
            abc_baseline: dict[str, Any] = {}
            burden_snapshot: dict[str, Any] = {}
            abc_config = load_abc_config()
            if audit_conn is not None:
                # Keep optional ABC tables and feature queries off the live
                # read transaction.  PostgreSQL marks a transaction aborted
                # after any statement error, even when Python catches it.
                with psycopg.connect(**pg_params(), row_factory=dict_row) as abc_read_conn:
                    abc_history = fetch_abc_history(abc_read_conn, anchor - timedelta(minutes=89), anchor)
                    abc_baseline = fetch_abc_baselines(abc_read_conn, anchor)
                    burden_snapshot = fetch_burden_rate_snapshot(
                        abc_read_conn,
                        anchor,
                        (abc_config.get("feature_thresholds") or {}).get("burden_rate"),
                    )
            if abc_history:
                for variable in ABC_HISTORY_VARIABLES:
                    combined_values.pop(variable, None)
                combined_values.update(abc_aligned_current(abc_history))
            combined_values.update(burden_snapshot.get("values") or {})
            abc_features, abc_quality = build_abc_feature_snapshot(
                combined_values,
                baseline=abc_baseline,
                history=abc_history,
                data_age_seconds=source_age,
                coverage_ratio=coverage if coverage is not None else 0.0,
                thresholds=abc_config.get("feature_thresholds") or {},
            )
            abc_internal = evaluate_abc(abc_features, quality=abc_quality, timestamp=timestamp, config=abc_config)
        payload["abc_rule_bundle"] = abc_internal.get("public") or abc_public_bundle(abc_internal["evaluations"])
        if audit_conn is not None and abc_internal.get("evaluations"):
            # ABC persistence is deliberately isolated from the live read
            # transaction.  A schema mismatch in an audit table must not
            # abort the connection used to build the production payload.
            try:
                with psycopg.connect(**pg_params(), row_factory=dict_row) as abc_audit_conn:
                    persist_abc_bundle(abc_audit_conn, abc_internal, source_snapshot_id=row.get("id"))
            except Exception as persist_exc:
                print(f"abc audit persistence failed: {type(persist_exc).__name__}", file=sys.stderr)
    except Exception as exc:
        payload["abc_rule_bundle"] = {"schema_version": "abc_rule_bundle.v1", "state": "needs_data", "error_type": type(exc).__name__, "rules": [], "alerts": []}
    if include_diagnosis_json:
        try:
            bundle = generate_recommendation_bundle(payload, current_values)
            audit_result: dict[str, Any]
            if RECOMMENDATION_AUDIT_ENABLED:
                if audit_conn is None:
                    raise RuntimeError("recommendation audit connection is unavailable")
                # Recommendation audit writes use their own connection for
                # the same reason as ABC persistence above.  The contract may
                # fail closed when audit storage is unavailable, but it must
                # never poison the live sensor read transaction.
                with psycopg.connect(**pg_params(), row_factory=dict_row) as recommendation_audit_conn:
                    audit_result = persist_recommendation_bundle(
                        recommendation_audit_conn,
                        payload,
                        current_values,
                        bundle,
                        diagnosis_snapshot_id=row.get("id"),
                        write_source="ws_bridge",
                    )
                bundle = audit_result.pop("bundle")
            else:
                audit_result = {
                    "state": "disabled",
                    "audit_schema_version": "recommendation_audit.v2",
                    "read_only": True,
                }
            payload["recommendation"] = bundle["active_plan"]
            payload["recommendation_bundle"] = bundle
            payload["recommendation_audit"] = audit_result
            payload["recommendation_status"] = {
                "state": "ready",
                "engine": "blast_furnace_recommendation_engine",
                "version": RECOMMENDATION_ENGINE_VERSION,
                "audit_state": audit_result.get("state"),
                "audit_batch_id": audit_result.get("batch_id"),
            }
        except Exception as exc:
            payload.pop("recommendation", None)
            payload.pop("recommendation_bundle", None)
            payload["recommendation_audit"] = {
                "state": "failed",
                "audit_schema_version": "recommendation_audit.v2",
                "error_type": type(exc).__name__,
                "read_only": True,
            }
            payload["recommendation_status"] = {
                "state": "failed",
                "engine": "blast_furnace_recommendation_engine",
                "error_type": type(exc).__name__,
                "reason": "full_audit_persistence_required",
            }
    if audit_conn is not None:
        try:
            with psycopg.connect(**pg_params(), row_factory=dict_row) as guidance_conn:
                payload["foreman_guidance"] = latest_foreman_guidance(guidance_conn)
        except Exception as exc:
            payload["foreman_guidance"] = {"state": "unavailable", "read_only": True, "reason": type(exc).__name__, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
    return payload


def save_foreman_guidance_request(request: dict[str, Any]) -> dict[str, Any]:
    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        return persist_foreman_guidance(conn, request)

def fetch_diagnosis_history(conn) -> list[dict[str, Any]]:
    anchor_row = conn.execute("SELECT max(diagnosis_ts) AS ts FROM bf_sensor.diagnosis_snapshots").fetchone()
    anchor = anchor_row["ts"] if anchor_row and anchor_row["ts"] else datetime.now()
    since = anchor - timedelta(hours=DIAGNOSIS_HISTORY_HOURS)
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (diagnosis_ts)
                   id, diagnosis_ts, main_label, main_score, main_confidence,
                   secondary_label, secondary_score, secondary_confidence,
                   evidence, raw_scores, diagnosis_json, created_at, updated_at
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= %s
            ORDER BY diagnosis_ts, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        ),
        limited AS (
            SELECT *
            FROM latest
            ORDER BY diagnosis_ts DESC
            LIMIT %s
        )
        SELECT *
        FROM limited
        ORDER BY diagnosis_ts ASC
        """,
        (since, DIAGNOSIS_HISTORY_LIMIT),
    ).fetchall()
    return [diagnosis_snapshot_payload(row, include_diagnosis_json=False) for row in rows]


def latest_diagnosis(conn, current_values: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, diagnosis_ts, main_label, main_score, main_confidence,
               secondary_label, secondary_score, secondary_confidence,
               evidence, raw_scores, diagnosis_json, created_at, updated_at
        FROM bf_sensor.diagnosis_snapshots
        ORDER BY diagnosis_ts DESC, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return {
            "timestamp": datetime.now().isoformat(sep=" "),
            "main_label": "normal",
            "main_score": 0,
            "main_confidence": 0,
            "secondary_label": None,
            "secondary_score": 0,
            "secondary_confidence": 0,
            "evidence": [],
            "raw_scores": {},
            "recommendation_status": {
                "state": "empty",
                "engine": "blast_furnace_recommendation_engine",
            },
            "abc_rule_bundle": {
                "schema_version": "abc_rule_bundle.v1",
                "state": "needs_data",
                "rules": [],
                "alerts": [],
                "public_contract": "production-safe.v1",
            },
            "baseline_compare": build_baseline_compare(conn, current_values),
        }
    payload = diagnosis_snapshot_payload(row, current_values=current_values, audit_conn=conn)
    payload["baseline_compare"] = build_baseline_compare(conn, current_values)
    return payload


def latest_quality(conn, current_ts: Any = None) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT checked_at, latest_data_ts, source_lag_seconds, expected_minutes,
               observed_minutes, coverage_ratio, missing_variables, status
        FROM bf_sensor.data_quality_status
        ORDER BY checked_at DESC
        LIMIT 1
        """
    ).fetchone()
    payload = dict(row) if row else {"status": "unknown"}
    anchor = current_ts or latest_data_ts(conn)
    now_row = conn.execute("SELECT localtimestamp AS db_now").fetchone()
    db_now = now_row["db_now"] if now_row else datetime.now()
    if anchor:
        anchor_dt = parse_ts(anchor)
        payload["latest_data_ts"] = anchor_dt
        payload["source_lag_seconds"] = max(0, int((db_now - anchor_dt).total_seconds()))
        payload["status"] = payload.get("status") or "ok"
        payload["freshness_source"] = "bf_sensor.one_minute_values.max_ts"
    return {
        **payload,
        "source": "local_postgresql",
        "missing_files": [],
        "missing_points_before_fill": {},
    }


def build_init_payload() -> dict[str, Any]:
    try:
        with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
            anchor = latest_data_ts(conn) or datetime.now()
            history = fetch_history(conn, anchor - timedelta(hours=HISTORY_HOURS))
            diagnosis_history = fetch_diagnosis_history(conn)
            ts = (history.get("timestamps") or [datetime.now().isoformat(sep=" ")])[-1]
            values = {var: (history.get(var) or [None])[-1] if history.get(var) else None for var in FRONTEND_VARIABLES}
            recommendation_values = build_foreman_recommendation_context(conn, values, ts)
            bf3d_snapshot = safe_build_bf3d_snapshot(conn, ts)
            return {
                "type": "init",
                "timestamp": ts,
                "history": history,
                "diagnosis_history": diagnosis_history,
                "values": values,
                "data_quality": latest_quality(conn, ts),
                "diagnosis": latest_diagnosis(conn, recommendation_values),
                "bf3d_snapshot": bf3d_snapshot,
                "source": source_payload(),
                "replay": replay_payload(),
            }
    except (psycopg.Error, RuntimeError) as exc:
        return unavailable_payload("init", exc)


def build_tick_payload() -> dict[str, Any]:
    try:
        with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
            ts, values = latest_values(conn)
            diagnosis_history = fetch_diagnosis_history(conn)
            payload_timestamp = ts or datetime.now().isoformat(sep=" ")
            recommendation_values = build_foreman_recommendation_context(conn, values, payload_timestamp)
            bf3d_snapshot = safe_build_bf3d_snapshot(conn, payload_timestamp)
            return {
                "type": "tick",
                "timestamp": payload_timestamp,
                "values": values,
                "diagnosis_history": diagnosis_history,
                "data_quality": latest_quality(conn, ts),
                "diagnosis": latest_diagnosis(conn, recommendation_values),
                "bf3d_snapshot": bf3d_snapshot,
                "source": source_payload(),
                "replay": replay_payload(),
            }
    except (psycopg.Error, RuntimeError) as exc:
        return unavailable_payload("tick", exc)


CLIENTS: set[Any] = set()


async def handler(websocket):
    CLIENTS.add(websocket)
    try:
        # PostgreSQL history queries are synchronous and may be slow. Running
        # them on the event loop prevents all new WebSocket handshakes.
        init_payload = await asyncio.to_thread(build_init_payload)
        await websocket.send(json.dumps(init_payload, ensure_ascii=False, default=json_default))
        async for message in websocket:
            try:
                request = json.loads(message)
            except json.JSONDecodeError:
                continue
            if await handle_foreman_guidance_request(websocket, request):
                continue
            await handle_chronos_request(websocket, request)
    finally:
        CLIENTS.discard(websocket)


async def ticker() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if not CLIENTS:
            continue
        tick_payload = await asyncio.to_thread(build_tick_payload)
        payload = json.dumps(tick_payload, ensure_ascii=False, default=json_default)
        dead = []
        for ws in list(CLIENTS):
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            CLIENTS.discard(ws)


async def main() -> None:
    import websockets

    print(f"local PostgreSQL WebSocket bridge: ws://{HOST}:{PORT}")
    print(f"history_hours={HISTORY_HOURS} tick_seconds={TICK_SECONDS}")
    print(f"chronos_base_url={CHRONOS_BASE_URL or '(disabled)'}")
    async with websockets.serve(handler, HOST, PORT):
        await ticker()


if __name__ == "__main__":
    asyncio.run(main())
