"""V20 history-Si shadow prediction, replay and later-actual comparison.

The module is shared by the 8093 and 8094 proxy processes.  It never changes
process settings or the heat-quality fact table.  Operator-triggered shadow
predictions are appended to a dedicated audit table; actual mean Si is joined
from ``heat_performance_quality_summary`` when it later becomes available.

Requirement: REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Iterable
from uuid import uuid4

from psycopg.types.json import Jsonb

from heat_performance_quality import HeatPerformanceQualityStore
from si_v20_strict_context import build_strict_context_features, load_strict_context_model


TABLE_NAME = "bf_assistant.si_v20_prediction_audit"
SCHEDULE_TABLE = "bf_assistant.si_v20_prediction_schedule"
RUN_TABLE = "bf_assistant.si_v20_prediction_run"
STRICT_SLOT_TABLE = "bf_assistant.si_v20_strict_hourly_slot"
HEAT_TABLE = "bf_assistant.heat_performance_quality_summary"
SCHEMA_VERSION = "bf.si.v20.shadow_workbench.v1"
MODEL_ENV = "BF_SI_V20_MODEL_PATH"
DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "si_v20_history_portable_v1.json.gz"
)
MELTNO_RE = re.compile(r"^(?P<furnace>\d+)#(?P<date>\d{8})-(?P<seq>\d{3})$")
MAX_REPLAY_HEATS = 200
ALLOWED_CADENCE_MINUTES = (1, 10, 30, 60, 1440)
MAX_SCHEDULE_REPLAY_POINTS = 5000
_SCHEDULE_SCHEMA_LOCK = threading.Lock()
_SCHEDULE_SCHEMA_READY = False


TABLE_DDL = f"""
CREATE SCHEMA IF NOT EXISTS bf_assistant;
CREATE TABLE IF NOT EXISTS {SCHEDULE_TABLE} (
    schedule_id bigserial PRIMARY KEY,
    schedule_key text NOT NULL UNIQUE,
    furnace_no text NOT NULL DEFAULT '2',
    enabled boolean NOT NULL DEFAULT true,
    cadence_minutes integer NOT NULL DEFAULT 60
        CHECK (cadence_minutes IN (1, 10, 30, 60, 1440)),
    next_slot_ts timestamp without time zone,
    last_slot_ts timestamp without time zone,
    last_run_status text,
    last_error text,
    created_by text NOT NULL DEFAULT 'system',
    updated_by text NOT NULL DEFAULT 'system',
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
    run_id bigserial PRIMARY KEY,
    run_kind text NOT NULL,
    schedule_id bigint,
    cadence_minutes integer NOT NULL
        CHECK (cadence_minutes IN (1, 10, 30, 60, 1440)),
    range_start_ts timestamp without time zone,
    range_end_ts timestamp without time zone,
    requested_by text NOT NULL,
    requested_at timestamp with time zone NOT NULL DEFAULT now(),
    started_at timestamp with time zone NOT NULL DEFAULT now(),
    completed_at timestamp with time zone,
    run_status text NOT NULL DEFAULT 'running',
    point_count integer NOT NULL DEFAULT 0,
    success_count integer NOT NULL DEFAULT 0,
    failure_count integer NOT NULL DEFAULT 0,
    parameters jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    error_summary jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE TABLE IF NOT EXISTS {STRICT_SLOT_TABLE} (
    slot_id bigserial PRIMARY KEY,
    furnace_no text NOT NULL DEFAULT '2',
    schedule_slot_ts timestamp without time zone NOT NULL,
    slot_status text NOT NULL DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    next_retry_at timestamp with time zone NOT NULL DEFAULT now(),
    last_error text,
    initial_target_meltno text,
    prediction_id bigint,
    requested_at timestamp with time zone,
    completed_at timestamp with time zone,
    matched_actual_meltno text,
    matched_actual_open_ts timestamp without time zone,
    matched_at timestamp with time zone,
    match_rule_version text NOT NULL DEFAULT 'first_open_strictly_after_prediction_completed.v1',
    feature_watermarks jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (furnace_no, schedule_slot_ts)
);
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    prediction_id bigserial PRIMARY KEY,
    request_id text NOT NULL UNIQUE,
    target_meltno text NOT NULL,
    furnace_no text NOT NULL,
    target_open_ts timestamp without time zone NOT NULL,
    prediction_cutoff_ts timestamp without time zone NOT NULL,
    requested_at timestamp with time zone NOT NULL DEFAULT now(),
    requested_by text NOT NULL,
    requested_role text,
    request_mode text NOT NULL,
    lead_minutes numeric(12,3),
    prediction_si_mean numeric(12,6) NOT NULL,
    prediction_p10 numeric(12,6),
    prediction_p50 numeric(12,6),
    prediction_p90 numeric(12,6),
    actual_si_at_prediction numeric(12,6),
    actual_available_ts_at_prediction timestamp without time zone,
    model_schema text NOT NULL,
    model_name text NOT NULL,
    model_sha256 text NOT NULL,
    feature_snapshot jsonb NOT NULL,
    model_contract jsonb NOT NULL,
    prediction_status text NOT NULL DEFAULT 'experimental_shadow',
    schedule_id bigint,
    schedule_run_id bigint,
    schedule_slot_ts timestamp without time zone,
    cadence_minutes integer,
    execution_completed_at timestamp with time zone,
    dispatch_delay_seconds numeric(12,3),
    attempt_count integer NOT NULL DEFAULT 1,
    initial_target_meltno text,
    matched_actual_meltno text,
    matched_actual_open_ts timestamp without time zone,
    matched_at timestamp with time zone,
    match_rule_version text,
    feature_watermarks jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS schedule_id bigint;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS schedule_run_id bigint;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS schedule_slot_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS cadence_minutes integer;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS execution_completed_at timestamp with time zone;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS dispatch_delay_seconds numeric(12,3);
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 1;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS initial_target_meltno text;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS matched_actual_meltno text;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS matched_actual_open_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS matched_at timestamp with time zone;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS match_rule_version text;
ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS feature_watermarks jsonb NOT NULL DEFAULT '{{}}'::jsonb;
UPDATE {TABLE_NAME} AS prediction
   SET requested_at = slot.requested_at
  FROM {STRICT_SLOT_TABLE} AS slot
 WHERE prediction.request_mode = 'strict_hourly'
   AND prediction.prediction_id = slot.prediction_id
   AND prediction.execution_completed_at IS NOT NULL
   AND prediction.requested_at > prediction.execution_completed_at
   AND slot.requested_at IS NOT NULL
   AND slot.requested_at <= prediction.execution_completed_at;
CREATE INDEX IF NOT EXISTS idx_si_v20_prediction_target
    ON {TABLE_NAME} (target_meltno, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_si_v20_prediction_open
    ON {TABLE_NAME} (target_open_ts DESC, requested_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_si_v20_hourly_cutoff
    ON {TABLE_NAME} (furnace_no, prediction_cutoff_ts)
    WHERE request_mode = 'hourly_schedule';
CREATE UNIQUE INDEX IF NOT EXISTS uq_si_v20_schedule_slot
    ON {TABLE_NAME} (schedule_id, schedule_slot_ts)
    WHERE schedule_id IS NOT NULL AND schedule_slot_ts IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_si_v20_replay_run_slot
    ON {TABLE_NAME} (schedule_run_id, schedule_slot_ts)
    WHERE schedule_run_id IS NOT NULL AND schedule_slot_ts IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_si_v20_strict_hourly_slot
    ON {TABLE_NAME} (furnace_no, schedule_slot_ts, model_sha256)
    WHERE request_mode = 'strict_hourly' AND schedule_slot_ts IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_si_v20_schedule_history
    ON {TABLE_NAME} (schedule_slot_ts DESC, cadence_minutes, request_mode);
INSERT INTO {SCHEDULE_TABLE}
    (schedule_key, furnace_no, enabled, cadence_minutes, next_slot_ts, created_by, updated_by)
VALUES ('production_default', '2', true, 60, date_trunc('hour', now() AT TIME ZONE 'Asia/Shanghai') + interval '1 hour', 'system', 'system')
ON CONFLICT (schedule_key) DO NOTHING;
COMMENT ON TABLE {TABLE_NAME} IS
    'V20 history-Si shadow predictions; production hourly rows are idempotent per furnace and whole-hour cutoff, and actual Si remains sourced from heat_performance_quality_summary.';
"""


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def require_login() -> bool:
    return _bool_env("BF_SI_V20_REQUIRE_LOGIN", False)


def validate_cadence_minutes(value: Any) -> int:
    try:
        cadence = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("预测周期只能是1、10、30、60或1440分钟") from exc
    if cadence not in ALLOWED_CADENCE_MINUTES:
        raise ValueError("预测周期只能是1、10、30、60或1440分钟")
    return cadence


def floor_schedule_slot(value: datetime, cadence_minutes: int) -> datetime:
    cadence = validate_cadence_minutes(cadence_minutes)
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = int((value - midnight).total_seconds() // 60)
    return midnight + timedelta(minutes=(elapsed_minutes // cadence) * cadence)


def next_schedule_slot(value: datetime, cadence_minutes: int) -> datetime:
    slot = floor_schedule_slot(value, cadence_minutes)
    return slot + timedelta(minutes=validate_cadence_minutes(cadence_minutes))


def schedule_slots(start: datetime, end: datetime, cadence_minutes: int) -> list[datetime]:
    cadence = validate_cadence_minutes(cadence_minutes)
    if end < start:
        raise ValueError("结束时间不能早于开始时间")
    slots: list[datetime] = []
    cursor = start.replace(second=0, microsecond=0)
    while cursor <= end:
        slots.append(cursor)
        if len(slots) > MAX_SCHEDULE_REPLAY_POINTS:
            raise ValueError(f"单次批量预测最多{MAX_SCHEDULE_REPLAY_POINTS}个时间点，请缩小时间范围")
        cursor += timedelta(minutes=cadence)
    return slots


def ensure_schedule_schema_once(store: Any) -> None:
    global _SCHEDULE_SCHEMA_READY
    if _SCHEDULE_SCHEMA_READY:
        return
    ensurer = getattr(store, "ensure_schema", None)
    if not callable(ensurer):
        return
    with _SCHEDULE_SCHEMA_LOCK:
        if not _SCHEDULE_SCHEMA_READY:
            ensurer()
            _SCHEDULE_SCHEMA_READY = True


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("T", " ")).replace(tzinfo=None)
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _local_elapsed_seconds(later: datetime, earlier: datetime) -> float:
    """Subtract server-local business timestamps without mixing tz-aware/naive values."""

    def local_naive(value: datetime) -> datetime:
        return value.astimezone().replace(tzinfo=None) if value.tzinfo is not None else value

    return (local_naive(later) - local_naive(earlier)).total_seconds()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _sample_si_values(details: Any) -> list[float]:
    """Extract each valid Si assay from the preserved per-heat sample snapshot."""

    values: list[float] = []
    for sample in details if isinstance(details, list) else []:
        if not isinstance(sample, dict):
            continue
        value = None
        for key in ("Si", "si", "SI", "value_02"):
            value = _number(sample.get(key))
            if value is not None:
                break
        if value is not None:
            values.append(value)
    return values


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2.0
    y_mean = sum(values) / len(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator <= 0:
        return None
    numerator = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    )
    return numerator / denominator


class PortableExtraTreesModel:
    """Pure-Python traversal of the verified portable ExtraTrees artifact."""

    def __init__(self, path: Path):
        self.path = path
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest().upper()
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("schema") != "bf.si.v20.portable_extra_trees.v1":
            raise RuntimeError("V20便携模型schema不受支持")
        self.payload = payload
        self.schema = str(payload["schema"])
        self.model_name = str(payload.get("model_name") or "v20_history")
        self.feature_columns = [str(item) for item in payload["feature_columns"]]
        self.fill_values = {
            str(key): float(value)
            for key, value in dict(payload.get("fill_values", {})).items()
        }
        self.quantiles = dict(payload.get("residual_quantiles", {}))
        self.trees = list(payload["trees"])
        if not self.trees:
            raise RuntimeError("V20便携模型没有决策树")

    def predict_one(self, features: dict[str, Any]) -> float:
        row = [
            _number(features.get(name))
            if _number(features.get(name)) is not None
            else self.fill_values.get(name, 0.0)
            for name in self.feature_columns
        ]
        total = 0.0
        for tree in self.trees:
            node = 0
            left = tree["children_left"]
            right = tree["children_right"]
            feature = tree["feature"]
            threshold = tree["threshold"]
            values = tree["value"]
            while left[node] != right[node]:
                feature_index = feature[node]
                node = left[node] if row[feature_index] <= threshold[node] else right[node]
            total += float(values[node])
        return total / len(self.trees)

    def interval(self, point: float) -> dict[str, float]:
        def q(name: str, default: float = 0.0) -> float:
            return _number(self.quantiles.get(name)) or default

        return {
            "p10": point + q("q10"),
            "p50": point + q("q50"),
            "p90": point + q("q90"),
        }


_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: tuple[str, int, PortableExtraTreesModel] | None = None


def load_model() -> PortableExtraTreesModel:
    global _MODEL_CACHE
    path = Path(os.getenv(MODEL_ENV) or DEFAULT_MODEL_PATH).resolve()
    if not path.exists():
        raise RuntimeError(f"V20模型文件不存在：{path}")
    mtime = path.stat().st_mtime_ns
    key = str(path)
    with _MODEL_LOCK:
        if _MODEL_CACHE is None or _MODEL_CACHE[0] != key or _MODEL_CACHE[1] != mtime:
            _MODEL_CACHE = (key, mtime, PortableExtraTreesModel(path))
        return _MODEL_CACHE[2]


def build_history_features(
    *,
    target_meltno: str,
    target_open_ts: datetime,
    cutoff_ts: datetime,
    heats: Iterable[dict[str, Any]],
    strict_availability: bool = False,
) -> dict[str, Any]:
    """Reproduce the selected V20 history feature contract without target leakage."""

    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sorted(
        (dict(item) for item in heats),
        key=lambda item: (_datetime(item.get("open_ts")) or datetime.min, str(item.get("meltno") or "")),
    ):
        meltno = str(source.get("meltno") or source.get("official_meltno") or "").strip()
        open_ts = _datetime(source.get("open_ts"))
        if not meltno or open_ts is None or meltno in seen:
            continue
        seen.add(meltno)
        prepared.append(
            {
                "meltno": meltno,
                "open_ts": open_ts,
                "label_available_ts": _datetime(
                    source.get("si_available_at")
                    if strict_availability
                    else source.get("label_available_ts") or source.get("source_updated_at")
                ),
                "availability_confidence": source.get("si_availability_confidence"),
                "si_avg": _number(source.get("si_avg") if "si_avg" in source else source.get("target__Si_mean")),
            }
        )
    if target_meltno not in seen:
        prepared.append(
            {
                "meltno": target_meltno,
                "open_ts": target_open_ts,
                "label_available_ts": None,
                "availability_confidence": None,
                "si_avg": None,
            }
        )
        prepared.sort(key=lambda item: (item["open_ts"], item["meltno"]))
    order = {item["meltno"]: index for index, item in enumerate(prepared)}
    earlier = [item for item in prepared if item["open_ts"] < target_open_ts]
    visible = [
        item
        for item in earlier
        if item["label_available_ts"] is not None
        and item["label_available_ts"] <= cutoff_ts
        and item["si_avg"] is not None
    ]
    values = [float(item["si_avg"]) for item in visible]
    features: dict[str, Any] = {
        "v20_history__visible_label_count": float(len(values)),
    }
    for lag in range(1, 6):
        features[f"history_mean__Si_lag_{lag}"] = values[-lag] if len(values) >= lag else None
    recent3 = values[-3:]
    recent5 = values[-5:]
    features["history_mean__Si_mean_3"] = _mean(recent3)
    features["history_mean__Si_mean_5"] = _mean(recent5)
    features["history_mean__Si_slope_5"] = _slope(recent5)
    if visible:
        latest = visible[-1]
        features["history_mean__previous_label_age_hours"] = (
            cutoff_ts - latest["label_available_ts"]
        ).total_seconds() / 3600.0
        features["v20_history__latest_label_age_hours_from_open"] = (
            cutoff_ts - latest["open_ts"]
        ).total_seconds() / 3600.0
        distance = order[target_meltno] - order[latest["meltno"]]
        features["v20_history__latest_label_meltno_distance"] = float(distance)
        features["v20_history__unlabeled_heat_gap"] = float(max(distance - 1, 0))
    else:
        features.update(
            {
                "history_mean__previous_label_age_hours": None,
                "v20_history__latest_label_age_hours_from_open": None,
                "v20_history__latest_label_meltno_distance": None,
                "v20_history__unlabeled_heat_gap": None,
            }
        )
    visible_recent = {item["meltno"] for item in visible[-5:]}
    features["v20_history__recent5_unpublished_count"] = float(
        sum(item["meltno"] not in visible_recent for item in earlier[-5:])
    )
    return features


def _melt_sequence(meltno: Any) -> int | None:
    match = MELTNO_RE.match(str(meltno or "").strip())
    return int(match.group("seq")) if match else None


def _recent_open_interval_minutes(targets: Iterable[dict[str, Any]]) -> float:
    ordered = sorted(
        (_datetime(item.get("open_ts")) for item in targets),
        key=lambda value: value or datetime.min,
    )
    values = [value for value in ordered if value is not None]
    gaps = [
        (current - previous).total_seconds() / 60.0
        for previous, current in zip(values, values[1:])
        if 20.0 <= (current - previous).total_seconds() / 60.0 <= 360.0
    ]
    if not gaps:
        return 90.0
    gaps.sort()
    middle = len(gaps) // 2
    return gaps[middle] if len(gaps) % 2 else (gaps[middle - 1] + gaps[middle]) / 2.0


def build_candidate_targets(
    historical_targets: Iterable[dict[str, Any]],
    mirror_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mark real local-mirror candidates and estimate only missing open times."""

    history = [dict(item) for item in historical_targets]
    historical_melts = {str(item.get("meltno") or "") for item in history}
    anchors = [item for item in history if _datetime(item.get("open_ts")) is not None]
    anchor = max(anchors, key=lambda item: _datetime(item.get("open_ts")) or datetime.min, default=None)
    anchor_open = _datetime((anchor or {}).get("open_ts"))
    anchor_close = _datetime((anchor or {}).get("close_ts"))
    anchor_seq = _melt_sequence((anchor or {}).get("meltno"))
    gap_minutes = _recent_open_interval_minutes(history)
    candidates: list[dict[str, Any]] = []
    for source in mirror_rows:
        item = dict(source)
        meltno = str(item.get("meltno") or "").strip()
        if not meltno or (meltno in historical_melts and item.get("si_avg") is not None):
            continue
        official_open = _datetime(item.get("official_open_ts"))
        official_close = _datetime(item.get("official_close_ts"))
        estimated_open = None
        seq = _melt_sequence(meltno)
        # A no-time MES placeholder older than the latest completed heat is stale,
        # not a valid next-heat target.  Keep rows with official timestamps so a
        # genuinely opened heat that is still waiting for Si remains auditable.
        if (
            official_open is None
            and official_close is None
            and anchor_seq is not None
            and seq is not None
            and seq <= anchor_seq
        ):
            continue
        if official_open is None and anchor_open is not None and anchor_seq is not None and seq is not None:
            distance = max(1, seq - anchor_seq)
            estimated_open = anchor_open + timedelta(minutes=gap_minutes * distance)
            if distance == 1 and anchor_close and estimated_open < anchor_close:
                estimated_open = anchor_close
        if official_close is not None:
            status = "completed_pending_summary"
            status_text = "已堵口，等待汇总补齐"
        elif official_open is not None:
            status = "opened_waiting_si"
            status_text = "已开口，等待平均Si"
        else:
            status = "planned_not_opened"
            status_text = "MES候选，尚无开口时间"
        candidate_open = official_open or estimated_open
        candidates.append({
            "meltno": meltno,
            "furnace_no": str(meltno.split("#", 1)[0] or "2"),
            "work_date": item.get("work_date"),
            "open_ts": candidate_open.isoformat(sep=" ") if candidate_open else None,
            "official_open_ts": official_open.isoformat(sep=" ") if official_open else None,
            "estimated_open_ts": estimated_open.isoformat(sep=" ") if estimated_open else None,
            "official_close_ts": official_close.isoformat(sep=" ") if official_close else None,
            "si_avg": _number(item.get("si_avg")),
            "candidate_status": status,
            "candidate_status_text": status_text,
            "candidate_time_source": "MES正式开口时间" if official_open else "近期炉次间隔估算",
            "candidate_time_is_estimated": official_open is None,
            "source_type": "22012_local_imes_mirror",
            "mirrored_at": item.get("mirrored_at"),
            "recent_median_interval_minutes": gap_minutes,
        })
    candidates.sort(key=lambda item: (_melt_sequence(item.get("meltno")) or 10**9, str(item.get("meltno"))))
    if not candidates and anchor and anchor_open and anchor_seq is not None:
        estimated = anchor_open + timedelta(minutes=gap_minutes)
        if anchor_close and estimated < anchor_close:
            estimated = anchor_close
        match = MELTNO_RE.match(str(anchor.get("meltno") or ""))
        if match:
            meltno = f"{match.group('furnace')}#{estimated:%Y%m%d}-{anchor_seq + 1:03d}"
            candidates.append({
                "meltno": meltno,
                "furnace_no": match.group("furnace"),
                "work_date": estimated.date().isoformat(),
                "open_ts": estimated.isoformat(sep=" "),
                "official_open_ts": None,
                "estimated_open_ts": estimated.isoformat(sep=" "),
                "official_close_ts": None,
                "si_avg": None,
                "candidate_status": "inferred_not_confirmed",
                "candidate_status_text": "推测下一炉，MES尚无候选记录",
                "candidate_time_source": "近期炉次间隔估算",
                "candidate_time_is_estimated": True,
                "source_type": "inferred_from_latest_heat",
                "mirrored_at": None,
                "recent_median_interval_minutes": gap_minutes,
            })
    return candidates


def resolve_hourly_target(
    status: dict[str, Any],
    cutoff_ts: datetime,
) -> dict[str, Any] | None:
    """Resolve a provisional next heat for a whole-hour production forecast.

    Official/estimated candidates after the cutoff are preferred.  If every
    mirrored candidate is already stale, advance the newest known heat by the
    recent median interval until its estimated open is after the cutoff.  The
    final evaluation is deliberately decoupled from this provisional identity:
    it is matched later to the first real open after the request timestamp.
    """

    candidates = [dict(item) for item in status.get("candidate_targets") or []]
    future = [item for item in candidates if (_datetime(item.get("open_ts")) or datetime.min) > cutoff_ts]
    if future:
        return min(future, key=lambda item: _datetime(item.get("open_ts")) or datetime.max)

    known = candidates + [dict(item) for item in status.get("targets") or []]
    known = [item for item in known if _melt_sequence(item.get("meltno")) is not None]
    if not known:
        return None
    seed = max(
        known,
        key=lambda item: (
            _datetime(item.get("open_ts")) or datetime.min,
            _melt_sequence(item.get("meltno")) or -1,
        ),
    )
    match = MELTNO_RE.match(str(seed.get("meltno") or ""))
    seed_open = _datetime(seed.get("open_ts"))
    if not match or seed_open is None:
        return None
    gap_minutes = _number(seed.get("recent_median_interval_minutes"))
    if gap_minutes is None:
        gap_minutes = _recent_open_interval_minutes(status.get("targets") or [])
    gap_minutes = min(360.0, max(20.0, float(gap_minutes or 90.0)))
    seq = int(match.group("seq"))
    estimated_open = seed_open
    while estimated_open <= cutoff_ts:
        seq += 1
        estimated_open += timedelta(minutes=gap_minutes)
    meltno = f"{match.group('furnace')}#{estimated_open:%Y%m%d}-{seq:03d}"
    return {
        "meltno": meltno,
        "furnace_no": match.group("furnace"),
        "work_date": estimated_open.date().isoformat(),
        "open_ts": estimated_open.isoformat(sep=" "),
        "official_open_ts": None,
        "estimated_open_ts": estimated_open.isoformat(sep=" "),
        "official_close_ts": None,
        "si_avg": None,
        "candidate_status": "hourly_inferred_next_after_cutoff",
        "candidate_status_text": "整点预测推测下一炉，等待MES确认",
        "candidate_time_source": "最新炉次与近期炉次间隔推算",
        "candidate_time_is_estimated": True,
        "source_type": "hourly_inferred_from_latest_known_heat",
        "mirrored_at": seed.get("mirrored_at") or seed.get("source_updated_at"),
        "recent_median_interval_minutes": gap_minutes,
    }


class SiV20ShadowStore:
    def connect(self, *, read_only: bool):
        return HeatPerformanceQualityStore().connect(read_only=read_only)

    def ensure_schema(self) -> None:
        # The strict-hourly leakage contract depends on the first-observed Si
        # availability fields owned by the heat-quality store.  Run that
        # idempotent migration before creating/using the prediction ledger.
        HeatPerformanceQualityStore().ensure_schema()
        with self.connect(read_only=False) as connection:
            connection.execute(TABLE_DDL)

    def table_ready(self) -> bool:
        with self.connect(read_only=True) as connection:
            row = connection.execute("SELECT to_regclass(%s) AS name", (TABLE_NAME,)).fetchone()
        return bool(row and row["name"])

    def strict_schema_ready(self) -> bool:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT to_regclass(%s) AS audit_name, to_regclass(%s) AS slot_name",
                (TABLE_NAME, STRICT_SLOT_TABLE),
            ).fetchone()
        return bool(row and row["audit_name"] and row["slot_name"])

    def get_target(self, meltno: str) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT meltno, furnace_no, work_date, open_ts, close_ts,
                       si_avg, hot_metal_sample_count, source_updated_at,
                       source_status,
                       COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) AS future_pending
                  FROM {HEAT_TABLE} AS h
                 WHERE meltno = %s
                """,
                (meltno,),
            ).fetchone()
        return dict(row) if row else None

    def all_heats_until(self, furnace_no: str, target_open_ts: datetime) -> list[dict[str, Any]]:
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT meltno, furnace_no, open_ts, source_updated_at, si_avg,
                       si_available_at, si_availability_confidence,
                       hot_metal_sample_count
                  FROM {HEAT_TABLE}
                 WHERE furnace_no = %s
                   AND open_ts IS NOT NULL
                   AND open_ts <= %s
                 ORDER BY open_ts, meltno
                """,
                (furnace_no, target_open_ts),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_targets(self, limit: int = 120) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 300))
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT meltno, furnace_no, work_date, open_ts, close_ts, si_avg,
                       hot_metal_sample_count, source_updated_at, source_status
                  FROM {HEAT_TABLE} AS h
                 WHERE COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE
                   AND open_ts IS NOT NULL
                 ORDER BY open_ts DESC, meltno DESC
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def local_imes_candidates(self, limit: int = 12) -> list[dict[str, Any]]:
        """Return locally mirrored heat placeholders without calling IMES."""

        limit = max(1, min(int(limit), 50))
        with self.connect(read_only=True) as connection:
            exists = connection.execute(
                "SELECT to_regclass('bf_imes.raw_rows') AS relation_name"
            ).fetchone()
            if not exists or not exists["relation_name"]:
                return []
            rows = connection.execute(
                f"""
                WITH latest AS (
                    SELECT DISTINCT ON (meltno)
                           meltno,
                           COALESCE(workdate, NULLIF(row_json->>'workDate', '')::date) AS work_date,
                           NULLIF(row_json->>'openTime', '')::timestamp AS official_open_ts,
                           NULLIF(row_json->>'closeTime', '')::timestamp AS official_close_ts,
                           NULLIF(row_json->>'workClass', '') AS work_class,
                           NULLIF(row_json->>'remark4', '') AS output_refs,
                           COALESCE(fetched_at, updated_at) AS mirrored_at
                      FROM (
                            SELECT COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                                   workdate, row_json, fetched_at, updated_at
                              FROM bf_imes.raw_rows
                             WHERE dataset_key = 'bf2_output_list_cond_data'
                               AND COALESCE(workdate, NULLIF(row_json->>'workDate', '')::date)
                                   >= current_date - 2
                               AND COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE '2#%%'
                           ) source
                     WHERE meltno IS NOT NULL
                     ORDER BY meltno, mirrored_at DESC NULLS LAST
                )
                SELECT l.*, h.si_avg
                  FROM latest l
                  LEFT JOIN {HEAT_TABLE} h ON h.meltno = l.meltno
                 WHERE h.meltno IS NULL OR h.si_avg IS NULL
                 ORDER BY substring(l.meltno from '([0-9]+)$')::integer,
                          l.meltno
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def targets_for_range(self, date_from: date, date_to: date, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), MAX_REPLAY_HEATS))
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT meltno, furnace_no, work_date, open_ts, close_ts, si_avg,
                       hot_metal_sample_count, source_updated_at, source_status
                  FROM {HEAT_TABLE} AS h
                 WHERE COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE
                   AND open_ts IS NOT NULL
                   AND open_ts >= %s::date
                   AND open_ts < (%s::date + interval '1 day')
                 ORDER BY open_ts, meltno
                 LIMIT %s
                """,
                (date_from, date_to, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def first_heat_after(self, furnace_no: str, cutoff_ts: datetime) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT meltno, furnace_no, work_date, open_ts, close_ts, si_avg,
                       hot_metal_sample_count, source_updated_at, source_status
                  FROM {HEAT_TABLE} AS h
                 WHERE furnace_no = %s
                   AND open_ts >= %s
                   AND COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE
                 ORDER BY open_ts, meltno
                 LIMIT 1
                """,
                (furnace_no, cutoff_ts),
            ).fetchone()
        return dict(row) if row else None

    def get_schedule(self, schedule_key: str = "production_default") -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"SELECT * FROM {SCHEDULE_TABLE} WHERE schedule_key = %s",
                (schedule_key,),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def ensure_strict_hourly_slots(self, furnace_no: str, current_slot: datetime) -> int:
        """Create every missing whole-hour slot without coupling to operator cadence."""

        with self.connect(read_only=False) as connection:
            row = connection.execute(
                f"SELECT max(schedule_slot_ts) AS latest FROM {STRICT_SLOT_TABLE} WHERE furnace_no = %s",
                (furnace_no,),
            ).fetchone()
            latest = _datetime((row or {}).get("latest")) if row else None
            start = latest + timedelta(hours=1) if latest is not None else current_slot
            if start > current_slot:
                return 0
            inserted = connection.execute(
                f"""
                INSERT INTO {STRICT_SLOT_TABLE} (furnace_no, schedule_slot_ts)
                SELECT %s, slot
                  FROM generate_series(%s::timestamp, %s::timestamp, interval '1 hour') slot
                ON CONFLICT (furnace_no, schedule_slot_ts) DO NOTHING
                RETURNING slot_id
                """,
                (furnace_no, start, current_slot),
            ).fetchall()
        return len(inserted)

    def claim_strict_hourly_slots(self, now: datetime, limit: int = 24) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 48))
        with self.connect(read_only=False) as connection:
            rows = connection.execute(
                f"""
                WITH picked AS (
                    SELECT slot_id
                      FROM {STRICT_SLOT_TABLE}
                     WHERE schedule_slot_ts <= %s
                       AND (
                            (slot_status IN ('pending', 'failed_retryable') AND next_retry_at <= now())
                            OR (slot_status = 'running' AND requested_at < now() - interval '10 minutes')
                       )
                     ORDER BY schedule_slot_ts
                     FOR UPDATE SKIP LOCKED
                     LIMIT %s
                )
                UPDATE {STRICT_SLOT_TABLE} target
                   SET slot_status = 'running',
                       attempt_count = target.attempt_count + 1,
                       requested_at = now(),
                       last_error = NULL,
                       updated_at = now()
                  FROM picked
                 WHERE target.slot_id = picked.slot_id
                RETURNING target.*
                """,
                (now, limit),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def mark_strict_hourly_failure(self, slot_id: int, error: str) -> None:
        with self.connect(read_only=False) as connection:
            connection.execute(
                f"""
                UPDATE {STRICT_SLOT_TABLE}
                   SET slot_status = 'failed_retryable',
                       last_error = %s,
                       next_retry_at = now() + interval '1 minute',
                       updated_at = now()
                 WHERE slot_id = %s
                """,
                (error[:2000], int(slot_id)),
            )

    def mark_strict_hourly_success(
        self,
        *,
        slot_id: int,
        prediction_id: int,
        initial_target_meltno: str,
        completed_at: datetime,
        feature_watermarks: dict[str, Any],
    ) -> None:
        with self.connect(read_only=False) as connection:
            connection.execute(
                f"""
                UPDATE {STRICT_SLOT_TABLE}
                   SET slot_status = 'success', prediction_id = %s,
                       initial_target_meltno = %s, completed_at = %s,
                       feature_watermarks = %s, next_retry_at = now(),
                       last_error = NULL, updated_at = now()
                 WHERE slot_id = %s
                """,
                (
                    int(prediction_id), initial_target_meltno, completed_at,
                    Jsonb(_json_safe(feature_watermarks)), int(slot_id),
                ),
            )

    def strict_hourly_slot(self, furnace_no: str, slot_ts: datetime) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"SELECT * FROM {STRICT_SLOT_TABLE} WHERE furnace_no = %s AND schedule_slot_ts = %s",
                (furnace_no, slot_ts),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def list_strict_hourly_slots(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return every strict-hour slot, including retryable failures without predictions."""

        limit = max(1, min(int(limit), 5000))
        clauses = ["1 = 1"]
        params: list[Any] = []
        if date_from:
            clauses.append("schedule_slot_ts >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append("schedule_slot_ts < (%s::date + interval '1 day')")
            params.append(date_to)
        params.append(limit)
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                  FROM {STRICT_SLOT_TABLE}
                 WHERE {' AND '.join(clauses)}
                 ORDER BY schedule_slot_ts DESC, slot_id DESC
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def get_strict_prediction(self, furnace_no: str, slot_ts: datetime, model_sha256: str) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT * FROM {TABLE_NAME}
                 WHERE request_mode = 'strict_hourly'
                   AND furnace_no = %s
                   AND schedule_slot_ts = %s
                   AND model_sha256 = %s
                 ORDER BY prediction_id DESC LIMIT 1
                """,
                (furnace_no, slot_ts, model_sha256),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def reconcile_strict_hourly_matches(self) -> int:
        """Freeze the first real heat opened strictly after prediction completion."""

        with self.connect(read_only=False) as connection:
            rows = connection.execute(
                f"""
                WITH matched AS (
                    SELECT p.prediction_id, h.meltno, h.open_ts
                      FROM {TABLE_NAME} p
                      JOIN LATERAL (
                            SELECT source_heat.meltno, source_heat.open_ts
                              FROM {HEAT_TABLE} source_heat
                             WHERE source_heat.furnace_no = p.furnace_no
                               AND source_heat.open_ts > (p.execution_completed_at AT TIME ZONE 'Asia/Shanghai')
                               AND COALESCE((to_jsonb(source_heat)->>'future_pending')::boolean, false) IS NOT TRUE
                             ORDER BY source_heat.open_ts, source_heat.meltno
                             LIMIT 1
                      ) h ON TRUE
                     WHERE p.request_mode = 'strict_hourly'
                       AND p.execution_completed_at IS NOT NULL
                       AND p.matched_actual_meltno IS NULL
                ), updated_predictions AS (
                    UPDATE {TABLE_NAME} p
                       SET matched_actual_meltno = matched.meltno,
                           matched_actual_open_ts = matched.open_ts,
                           matched_at = now(),
                           match_rule_version = 'first_open_strictly_after_prediction_completed.v1'
                      FROM matched
                     WHERE p.prediction_id = matched.prediction_id
                    RETURNING p.prediction_id, p.matched_actual_meltno, p.matched_actual_open_ts, p.matched_at
                )
                UPDATE {STRICT_SLOT_TABLE} slot
                   SET matched_actual_meltno = updated_predictions.matched_actual_meltno,
                       matched_actual_open_ts = updated_predictions.matched_actual_open_ts,
                       matched_at = updated_predictions.matched_at,
                       updated_at = now()
                  FROM updated_predictions
                 WHERE slot.prediction_id = updated_predictions.prediction_id
                RETURNING slot.slot_id
                """
            ).fetchall()
        return len(rows)

    def configure_schedule(
        self,
        *,
        schedule_key: str,
        furnace_no: str,
        cadence_minutes: int,
        enabled: bool,
        actor: str,
        next_slot_ts: datetime,
    ) -> dict[str, Any]:
        with self.connect(read_only=False) as connection:
            row = connection.execute(
                f"""
                INSERT INTO {SCHEDULE_TABLE}
                    (schedule_key, furnace_no, enabled, cadence_minutes,
                     next_slot_ts, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (schedule_key) DO UPDATE SET
                    furnace_no = EXCLUDED.furnace_no,
                    enabled = EXCLUDED.enabled,
                    cadence_minutes = EXCLUDED.cadence_minutes,
                    next_slot_ts = EXCLUDED.next_slot_ts,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING *
                """,
                (
                    schedule_key, furnace_no, enabled, cadence_minutes,
                    next_slot_ts, actor, actor,
                ),
            ).fetchone()
        return _json_safe(dict(row))

    def due_schedules(self, now: datetime) -> list[dict[str, Any]]:
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                  FROM {SCHEDULE_TABLE}
                 WHERE enabled IS TRUE
                   AND next_slot_ts IS NOT NULL
                   AND next_slot_ts <= %s
                 ORDER BY next_slot_ts, schedule_id
                """,
                (now,),
            ).fetchall()
        return [_json_safe(dict(row)) for row in rows]

    def mark_schedule_result(
        self,
        *,
        schedule_id: int,
        slot_ts: datetime,
        next_slot_ts: datetime,
        status: str,
        error: str | None,
    ) -> None:
        with self.connect(read_only=False) as connection:
            connection.execute(
                f"""
                UPDATE {SCHEDULE_TABLE}
                   SET last_slot_ts = %s,
                       next_slot_ts = %s,
                       last_run_status = %s,
                       last_error = %s,
                       updated_at = now()
                 WHERE schedule_id = %s
                """,
                (slot_ts, next_slot_ts, status, error, schedule_id),
            )

    def create_schedule_run(
        self,
        *,
        run_kind: str,
        schedule_id: int | None,
        cadence_minutes: int,
        range_start_ts: datetime,
        range_end_ts: datetime,
        requested_by: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect(read_only=False) as connection:
            row = connection.execute(
                f"""
                INSERT INTO {RUN_TABLE}
                    (run_kind, schedule_id, cadence_minutes, range_start_ts,
                     range_end_ts, requested_by, parameters)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    run_kind, schedule_id, cadence_minutes, range_start_ts,
                    range_end_ts, requested_by, Jsonb(parameters),
                ),
            ).fetchone()
        return _json_safe(dict(row))

    def finish_schedule_run(
        self,
        *,
        run_id: int,
        status: str,
        point_count: int,
        success_count: int,
        failures: list[dict[str, Any]],
    ) -> None:
        with self.connect(read_only=False) as connection:
            connection.execute(
                f"""
                UPDATE {RUN_TABLE}
                   SET completed_at = now(), run_status = %s,
                       point_count = %s, success_count = %s,
                       failure_count = %s, error_summary = %s
                 WHERE run_id = %s
                """,
                (status, point_count, success_count, len(failures), Jsonb(failures), run_id),
            )

    def get_scheduled_prediction(
        self,
        *,
        schedule_id: int | None,
        schedule_run_id: int | None,
        slot_ts: datetime,
    ) -> dict[str, Any] | None:
        if schedule_id is None and schedule_run_id is None:
            return None
        column = "schedule_id" if schedule_id is not None else "schedule_run_id"
        value = schedule_id if schedule_id is not None else schedule_run_id
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT * FROM {TABLE_NAME}
                 WHERE {column} = %s AND schedule_slot_ts = %s
                 ORDER BY prediction_id DESC LIMIT 1
                """,
                (value, slot_ts),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def get_hourly_prediction(self, furnace_no: str, cutoff_ts: datetime) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT *
                  FROM {TABLE_NAME}
                 WHERE request_mode = 'hourly_schedule'
                   AND furnace_no = %s
                   AND prediction_cutoff_ts = %s
                 ORDER BY prediction_id DESC
                 LIMIT 1
                """,
                (furnace_no, cutoff_ts),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def insert_prediction(self, row: dict[str, Any]) -> dict[str, Any]:
        columns = (
            "request_id", "target_meltno", "furnace_no", "target_open_ts",
            "prediction_cutoff_ts", "requested_at", "requested_by", "requested_role", "request_mode",
            "lead_minutes", "prediction_si_mean", "prediction_p10", "prediction_p50",
            "prediction_p90", "actual_si_at_prediction", "actual_available_ts_at_prediction",
            "model_schema", "model_name", "model_sha256", "feature_snapshot",
            "model_contract", "prediction_status", "schedule_id",
            "schedule_run_id", "schedule_slot_ts", "cadence_minutes",
            "execution_completed_at", "dispatch_delay_seconds", "attempt_count",
            "initial_target_meltno", "matched_actual_meltno",
            "matched_actual_open_ts", "matched_at", "match_rule_version",
            "feature_watermarks",
        )
        values = []
        for column in columns:
            value = row.get(column)
            if column in {"feature_snapshot", "model_contract", "feature_watermarks"}:
                value = Jsonb(_json_safe(value))
            values.append(value)
        with self.connect(read_only=False) as connection:
            if row.get("schedule_id") is not None and row.get("schedule_slot_ts") is not None:
                query = f"""
                INSERT INTO {TABLE_NAME} AS existing ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                ON CONFLICT (schedule_id, schedule_slot_ts)
                    WHERE schedule_id IS NOT NULL AND schedule_slot_ts IS NOT NULL
                DO UPDATE SET request_id = existing.request_id
                RETURNING prediction_id, request_id, requested_at, created_at
                """
            elif row.get("schedule_run_id") is not None and row.get("schedule_slot_ts") is not None:
                query = f"""
                INSERT INTO {TABLE_NAME} AS existing ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                ON CONFLICT (schedule_run_id, schedule_slot_ts)
                    WHERE schedule_run_id IS NOT NULL AND schedule_slot_ts IS NOT NULL
                DO UPDATE SET request_id = existing.request_id
                RETURNING prediction_id, request_id, requested_at, created_at
                """
            elif row.get("request_mode") == "hourly_schedule":
                query = f"""
                INSERT INTO {TABLE_NAME} AS existing ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                ON CONFLICT (furnace_no, prediction_cutoff_ts)
                    WHERE request_mode = 'hourly_schedule'
                DO UPDATE SET request_id = existing.request_id
                RETURNING prediction_id, request_id, requested_at, created_at
                """
            elif row.get("request_mode") == "strict_hourly":
                query = f"""
                INSERT INTO {TABLE_NAME} AS existing ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                ON CONFLICT (furnace_no, schedule_slot_ts, model_sha256)
                    WHERE request_mode = 'strict_hourly' AND schedule_slot_ts IS NOT NULL
                DO UPDATE SET request_id = existing.request_id
                RETURNING prediction_id, request_id, requested_at, created_at
                """
            else:
                query = f"""
                INSERT INTO {TABLE_NAME} ({', '.join(columns)})
                VALUES ({', '.join(['%s'] * len(columns))})
                RETURNING prediction_id, request_id, requested_at, created_at
                """
            inserted = connection.execute(query, values).fetchone()
        result = _json_safe(dict(inserted))
        result["deduplicated"] = result.get("request_id") != row.get("request_id")
        return result

    def get_prediction_detail(self, prediction_id: int) -> dict[str, Any] | None:
        with self.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                SELECT p.*, h.si_avg AS actual_si_mean,
                       h.source_updated_at AS actual_available_ts,
                       h.hot_metal_sample_count AS actual_sample_count,
                       h.si_min AS actual_si_min, h.si_max AS actual_si_max,
                       h.quality_status AS actual_quality_status,
                       h.source_status AS actual_source_status
                  FROM {TABLE_NAME} p
                  LEFT JOIN LATERAL (
                        SELECT source_heat.*
                          FROM {HEAT_TABLE} source_heat
                         WHERE source_heat.furnace_no = p.furnace_no
                           AND COALESCE((to_jsonb(source_heat)->>'future_pending')::boolean, false) IS NOT TRUE
                           AND (
                               (p.request_mode IN ('hourly_schedule', 'scheduled_interval')
                                    AND source_heat.open_ts >= (p.requested_at AT TIME ZONE 'Asia/Shanghai'))
                               OR (p.request_mode = 'scheduled_time_replay'
                                    AND source_heat.open_ts >= p.schedule_slot_ts)
                               OR (p.request_mode = 'strict_hourly'
                                    AND source_heat.meltno = p.matched_actual_meltno)
                               OR (p.request_mode NOT IN ('hourly_schedule', 'scheduled_interval', 'scheduled_time_replay', 'strict_hourly')
                                    AND source_heat.meltno = p.target_meltno)
                           )
                         ORDER BY source_heat.open_ts, source_heat.meltno
                         LIMIT 1
                  ) h ON TRUE
                 WHERE p.prediction_id = %s
                """,
                (int(prediction_id),),
            ).fetchone()
        return _json_safe(dict(row)) if row else None

    def list_history(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        meltno: str | None,
        limit: int,
        latest_per_heat: bool,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        time_expression = "COALESCE(p.target_open_ts, h.open_ts)" if latest_per_heat else "p.target_open_ts"
        melt_expression = "COALESCE(p.target_meltno, h.meltno)" if latest_per_heat else "p.target_meltno"
        if date_from:
            clauses.append(f"{time_expression} >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append(f"{time_expression} < (%s::date + interval '1 day')")
            params.append(date_to)
        if meltno:
            clauses.append(f"{melt_expression} = %s")
            params.append(meltno)
        if latest_per_heat:
            clauses.append(
                "(h.meltno IS NULL OR COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE)"
            )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect(read_only=True) as connection:
            if latest_per_heat:
                query = f"""
                WITH p AS (
                    SELECT DISTINCT ON (target_meltno) *
                      FROM {TABLE_NAME}
                     ORDER BY target_meltno, requested_at DESC, prediction_id DESC
                )
                SELECT p.prediction_id, p.request_id,
                       COALESCE(p.target_meltno, h.meltno) AS target_meltno,
                       COALESCE(p.furnace_no, h.furnace_no) AS furnace_no,
                       COALESCE(p.target_open_ts, h.open_ts) AS target_open_ts,
                       p.prediction_cutoff_ts, p.requested_at,
                       p.requested_by, p.requested_role, p.request_mode, p.lead_minutes,
                       p.prediction_si_mean, p.prediction_p10, p.prediction_p50,
                       p.prediction_p90, p.actual_si_at_prediction,
                       p.actual_available_ts_at_prediction, p.model_schema, p.model_name,
                       p.model_sha256, p.prediction_status, p.feature_snapshot,
                       h.si_avg AS actual_si_mean,
                       h.source_updated_at AS actual_available_ts,
                       h.hot_metal_sample_count AS actual_sample_count,
                       h.si_min AS actual_si_min, h.si_max AS actual_si_max,
                       h.work_class, h.shift, h.quality_status, h.source_status
                  FROM {HEAT_TABLE} h
                  FULL OUTER JOIN p ON p.target_meltno = h.meltno
                  {where}
                 ORDER BY COALESCE(p.target_open_ts, h.open_ts) DESC,
                          p.requested_at DESC NULLS LAST
                 LIMIT %s
                """
            else:
                query = f"""
                SELECT p.prediction_id, p.request_id, p.target_meltno, p.furnace_no,
                       p.target_open_ts, p.prediction_cutoff_ts, p.requested_at,
                       p.requested_by, p.requested_role, p.request_mode, p.lead_minutes,
                       p.prediction_si_mean, p.prediction_p10, p.prediction_p50,
                       p.prediction_p90, p.actual_si_at_prediction,
                       p.actual_available_ts_at_prediction, p.model_schema, p.model_name,
                       p.model_sha256, p.prediction_status, p.feature_snapshot,
                       h.si_avg AS actual_si_mean,
                       h.source_updated_at AS actual_available_ts,
                       h.hot_metal_sample_count AS actual_sample_count,
                       h.si_min AS actual_si_min, h.si_max AS actual_si_max,
                       h.work_class, h.shift, h.quality_status, h.source_status
                  FROM {TABLE_NAME} p
                  LEFT JOIN {HEAT_TABLE} h ON h.meltno = p.target_meltno
                  {where}
                 ORDER BY p.target_open_ts DESC, p.requested_at DESC
                 LIMIT %s
                """
            rows = connection.execute(query, tuple(params)).fetchall()
        items = [_json_safe(dict(row)) for row in rows]
        for item in items:
            actual = _number(item.get("actual_si_mean"))
            prediction = _number(item.get("prediction_si_mean"))
            item["has_prediction"] = prediction is not None
            item["actual_ready"] = actual is not None
            item["history_status"] = (
                "compared" if prediction is not None and actual is not None
                else "prediction_waiting_actual" if prediction is not None
                else "actual_only"
            )
            item["signed_error"] = prediction - actual if actual is not None and prediction is not None else None
            item["absolute_error"] = abs(item["signed_error"]) if item["signed_error"] is not None else None
            item["hit_abs_le_005"] = (
                item["absolute_error"] <= 0.05 if item["absolute_error"] is not None else None
            )
        return items

    def list_hourly_outcomes(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Match each production-hour prediction to the next real heat open."""

        limit = max(1, min(int(limit), 2000))
        clauses = ["p.request_mode = 'hourly_schedule'"]
        params: list[Any] = []
        if date_from:
            clauses.append("p.prediction_cutoff_ts >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append("p.prediction_cutoff_ts < (%s::date + interval '1 day')")
            params.append(date_to)
        params.append(limit)
        where = " AND ".join(clauses)
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT p.prediction_id, p.request_id,
                       p.target_meltno AS predicted_target_meltno,
                       p.target_open_ts AS predicted_target_open_ts,
                       p.furnace_no, p.prediction_cutoff_ts, p.requested_at,
                       p.requested_by, p.requested_role, p.request_mode,
                       p.lead_minutes AS predicted_lead_minutes,
                       p.prediction_si_mean, p.prediction_p10, p.prediction_p50,
                       p.prediction_p90, p.model_schema, p.model_name,
                       p.model_sha256, p.prediction_status, p.feature_snapshot,
                       next_heat.meltno AS matched_actual_meltno,
                       next_heat.open_ts AS matched_actual_open_ts,
                       next_heat.close_ts AS matched_actual_close_ts,
                       next_heat.si_avg AS actual_si_mean,
                       next_heat.source_updated_at AS actual_available_ts,
                       next_heat.hot_metal_sample_count AS actual_sample_count,
                       next_heat.sample_details AS actual_sample_details,
                       next_heat.si_min AS actual_si_min,
                       next_heat.si_max AS actual_si_max,
                       next_heat.work_class, next_heat.shift,
                       next_heat.quality_status, next_heat.source_status
                  FROM {TABLE_NAME} p
                  LEFT JOIN LATERAL (
                        SELECT h.*
                          FROM {HEAT_TABLE} h
                         WHERE h.furnace_no = p.furnace_no
                           AND h.open_ts IS NOT NULL
                           AND h.open_ts >= (p.requested_at AT TIME ZONE 'Asia/Shanghai')
                           AND COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE
                         ORDER BY h.open_ts, h.meltno
                         LIMIT 1
                  ) next_heat ON TRUE
                 WHERE {where}
                 ORDER BY p.prediction_cutoff_ts DESC, p.prediction_id DESC
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        items = [_json_safe(dict(row)) for row in rows]
        for item in items:
            prediction = _number(item.get("prediction_si_mean"))
            actual = _number(item.get("actual_si_mean"))
            requested_at = _datetime(item.get("requested_at"))
            cutoff = _datetime(item.get("prediction_cutoff_ts"))
            actual_open = _datetime(item.get("matched_actual_open_ts"))
            item["target_meltno"] = item.get("matched_actual_meltno") or item.get("predicted_target_meltno")
            item["target_open_ts"] = item.get("matched_actual_open_ts") or item.get("predicted_target_open_ts")
            item["has_prediction"] = prediction is not None
            item["actual_ready"] = actual is not None
            item["actual_si_values"] = _sample_si_values(item.get("actual_sample_details"))
            item["match_status"] = (
                "matched_actual_ready" if actual is not None
                else "matched_waiting_si" if item.get("matched_actual_meltno")
                else "waiting_next_real_heat"
            )
            item["history_status"] = (
                "compared" if prediction is not None and actual is not None
                else "prediction_waiting_actual"
            )
            item["request_to_actual_open_minutes"] = (
                (actual_open - requested_at).total_seconds() / 60.0
                if actual_open is not None and requested_at is not None else None
            )
            item["cutoff_to_actual_open_minutes"] = (
                (actual_open - cutoff).total_seconds() / 60.0
                if actual_open is not None and cutoff is not None else None
            )
            item["lead_minutes"] = item["request_to_actual_open_minutes"]
            item["signed_error"] = prediction - actual if prediction is not None and actual is not None else None
            item["absolute_error"] = abs(item["signed_error"]) if item["signed_error"] is not None else None
            item["hit_abs_le_005"] = (
                item["absolute_error"] <= 0.05 if item["absolute_error"] is not None else None
            )
        return items

    def list_scheduled_outcomes(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        cadence_minutes: int | None,
        schedule_run_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 10000))
        clauses = ["p.request_mode IN ('scheduled_interval', 'scheduled_time_replay')"]
        params: list[Any] = []
        if date_from:
            clauses.append("p.schedule_slot_ts >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append("p.schedule_slot_ts < (%s::date + interval '1 day')")
            params.append(date_to)
        if cadence_minutes is not None:
            clauses.append("p.cadence_minutes = %s")
            params.append(validate_cadence_minutes(cadence_minutes))
        if schedule_run_id is not None:
            clauses.append("p.schedule_run_id = %s")
            params.append(int(schedule_run_id))
        params.append(limit)
        where = " AND ".join(clauses)
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT p.prediction_id, p.request_id,
                       p.target_meltno AS predicted_target_meltno,
                       p.target_open_ts AS predicted_target_open_ts,
                       p.furnace_no, p.prediction_cutoff_ts, p.requested_at,
                       p.requested_by, p.requested_role, p.request_mode,
                       p.lead_minutes AS predicted_lead_minutes,
                       p.prediction_si_mean, p.prediction_p10, p.prediction_p50,
                       p.prediction_p90, p.model_schema, p.model_name,
                       p.model_sha256, p.prediction_status, p.feature_snapshot,
                       p.schedule_id, p.schedule_run_id, p.schedule_slot_ts,
                       p.cadence_minutes,
                       next_heat.meltno AS matched_actual_meltno,
                       next_heat.open_ts AS matched_actual_open_ts,
                       next_heat.close_ts AS matched_actual_close_ts,
                       next_heat.si_avg AS actual_si_mean,
                       next_heat.source_updated_at AS actual_available_ts,
                       next_heat.hot_metal_sample_count AS actual_sample_count,
                       next_heat.sample_details AS actual_sample_details,
                       next_heat.si_min AS actual_si_min,
                       next_heat.si_max AS actual_si_max,
                       next_heat.work_class, next_heat.shift,
                       next_heat.quality_status, next_heat.source_status
                  FROM {TABLE_NAME} p
                  LEFT JOIN LATERAL (
                        SELECT h.*
                          FROM {HEAT_TABLE} h
                         WHERE h.furnace_no = p.furnace_no
                           AND h.open_ts IS NOT NULL
                           AND h.open_ts >= CASE
                               WHEN p.request_mode = 'scheduled_time_replay'
                                   THEN p.schedule_slot_ts
                               ELSE (p.requested_at AT TIME ZONE 'Asia/Shanghai')
                           END
                           AND COALESCE((to_jsonb(h)->>'future_pending')::boolean, false) IS NOT TRUE
                         ORDER BY h.open_ts, h.meltno
                         LIMIT 1
                  ) next_heat ON TRUE
                 WHERE {where}
                 ORDER BY p.schedule_slot_ts DESC, p.prediction_id DESC
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        items = [_json_safe(dict(row)) for row in rows]
        for item in items:
            prediction = _number(item.get("prediction_si_mean"))
            actual = _number(item.get("actual_si_mean"))
            slot = _datetime(item.get("schedule_slot_ts"))
            requested_at = _datetime(item.get("requested_at"))
            actual_open = _datetime(item.get("matched_actual_open_ts"))
            item["target_meltno"] = item.get("matched_actual_meltno") or item.get("predicted_target_meltno")
            item["target_open_ts"] = item.get("matched_actual_open_ts") or item.get("predicted_target_open_ts")
            item["has_prediction"] = prediction is not None
            item["actual_ready"] = actual is not None
            item["actual_si_values"] = _sample_si_values(item.get("actual_sample_details"))
            item["match_status"] = (
                "matched_actual_ready" if actual is not None
                else "matched_waiting_si" if item.get("matched_actual_meltno")
                else "waiting_next_real_heat"
            )
            item["history_status"] = "compared" if actual is not None else "prediction_waiting_actual"
            anchor = slot if item.get("request_mode") == "scheduled_time_replay" else requested_at
            item["anchor_to_actual_open_minutes"] = (
                (actual_open - anchor).total_seconds() / 60.0
                if actual_open is not None and anchor is not None else None
            )
            item["lead_minutes"] = item["anchor_to_actual_open_minutes"]
            item["signed_error"] = prediction - actual if prediction is not None and actual is not None else None
            item["absolute_error"] = abs(item["signed_error"]) if item["signed_error"] is not None else None
            item["hit_abs_le_005"] = item["absolute_error"] <= 0.05 if item["absolute_error"] is not None else None
        return items

    def list_strict_hourly_outcomes(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        meltno_from: str | None,
        meltno_to: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        clauses = ["p.request_mode = 'strict_hourly'"]
        params: list[Any] = []
        if date_from:
            clauses.append("p.schedule_slot_ts >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append("p.schedule_slot_ts < (%s::date + interval '1 day')")
            params.append(date_to)
        if meltno_from:
            clauses.append("COALESCE(p.matched_actual_meltno, p.initial_target_meltno) >= %s")
            params.append(meltno_from)
        if meltno_to:
            clauses.append("COALESCE(p.matched_actual_meltno, p.initial_target_meltno) <= %s")
            params.append(meltno_to)
        params.append(limit)
        with self.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT p.prediction_id, p.request_id, p.furnace_no,
                       p.schedule_slot_ts, p.prediction_cutoff_ts,
                       p.requested_at, p.execution_completed_at,
                       p.dispatch_delay_seconds, p.attempt_count,
                       p.initial_target_meltno AS predicted_target_meltno,
                       p.target_open_ts AS predicted_target_open_ts,
                       p.matched_actual_meltno, p.matched_actual_open_ts,
                       p.matched_at, p.match_rule_version,
                       p.prediction_si_mean, p.prediction_p10, p.prediction_p50,
                       p.prediction_p90, p.model_schema, p.model_name,
                       p.model_sha256, p.prediction_status, p.feature_snapshot,
                       p.feature_watermarks, p.model_contract, p.request_mode,
                       h.si_avg AS actual_si_mean,
                       h.close_ts AS matched_actual_close_ts,
                       h.si_available_at AS actual_available_ts,
                       h.si_availability_confidence,
                       h.hot_metal_sample_count AS actual_sample_count,
                       h.sample_details AS actual_sample_details,
                       h.si_min AS actual_si_min, h.si_max AS actual_si_max,
                       h.work_class, h.shift, h.quality_status, h.source_status,
                       slot.slot_status, slot.last_error AS slot_last_error
                  FROM {TABLE_NAME} p
                  LEFT JOIN {HEAT_TABLE} h ON h.meltno = p.matched_actual_meltno
                  LEFT JOIN {STRICT_SLOT_TABLE} slot ON slot.prediction_id = p.prediction_id
                 WHERE {' AND '.join(clauses)}
                 ORDER BY p.schedule_slot_ts DESC, p.prediction_id DESC
                 LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        items = [_json_safe(dict(row)) for row in rows]
        for item in items:
            prediction = _number(item.get("prediction_si_mean"))
            actual = _number(item.get("actual_si_mean"))
            completed = _datetime(item.get("execution_completed_at"))
            actual_open = _datetime(item.get("matched_actual_open_ts"))
            item["target_meltno"] = item.get("matched_actual_meltno") or item.get("predicted_target_meltno")
            item["target_open_ts"] = item.get("matched_actual_open_ts") or item.get("predicted_target_open_ts")
            item["has_prediction"] = prediction is not None
            item["actual_ready"] = actual is not None
            item["actual_si_values"] = _sample_si_values(item.get("actual_sample_details"))
            item["match_status"] = (
                "matched_actual_ready" if actual is not None
                else "matched_waiting_si" if item.get("matched_actual_meltno")
                else "waiting_next_real_heat"
            )
            item["history_status"] = "compared" if actual is not None else "prediction_waiting_actual"
            item["lead_minutes"] = (
                (actual_open - completed).total_seconds() / 60.0
                if actual_open is not None and completed is not None else None
            )
            item["signed_error"] = prediction - actual if prediction is not None and actual is not None else None
            item["absolute_error"] = abs(item["signed_error"]) if item["signed_error"] is not None else None
            item["hit_abs_le_005"] = item["absolute_error"] <= 0.05 if item["absolute_error"] is not None else None
        return items


class SiV20ShadowService:
    def __init__(self, store: SiV20ShadowStore | None = None):
        self.store = store or SiV20ShadowStore()

    def status(self, *, target_limit: int = 120) -> dict[str, Any]:
        model = load_model()
        table_ready = self.store.table_ready()
        targets = self.store.recent_targets(target_limit)
        candidate_reader = getattr(self.store, "local_imes_candidates", None)
        mirror_candidates = candidate_reader(12) if callable(candidate_reader) else []
        candidates = build_candidate_targets(targets, mirror_candidates)
        recommended = next(
            (
                item for item in candidates
                if item.get("candidate_status")
                in {"planned_not_opened", "opened_waiting_si", "inferred_not_confirmed"}
            ),
            candidates[0] if candidates else None,
        )
        return {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "status": "experimental_shadow",
            "model": {
                "schema": model.schema,
                "name": model.model_name,
                "sha256": model.sha256,
                "feature_count": len(model.feature_columns),
                "trained_lead_minutes": model.payload.get("lead_minutes", 60),
            },
            "audit_table_ready": table_ready,
            "require_login": require_login(),
            "targets": targets,
            "candidate_targets": candidates,
            "recommended_target": recommended,
            "contracts": {
                "actual_source": f"{HEAT_TABLE}.si_avg",
                "candidate_source": "bf_imes.raw_rows on 220.12",
                "target_mean": "每炉全部有效Si试样算术平均",
                "current_heat_target_excluded": True,
                "published_history_only": True,
                "production_control_write": False,
                "estimated_candidate_time_marked": True,
            },
        }

    def _predict_row(
        self,
        *,
        target_meltno: str,
        target_open_ts: datetime | None,
        cutoff_ts: datetime,
        request_mode: str,
        requested_by: str,
        requested_role: str | None,
        persist: bool,
        audit_context: dict[str, Any] | None = None,
        record_context: dict[str, Any] | None = None,
        strict_context: bool = False,
        attempt_count: int = 1,
    ) -> dict[str, Any]:
        execution_started_at = datetime.now().astimezone()
        match = MELTNO_RE.fullmatch(target_meltno)
        if not match:
            raise ValueError("target_meltno格式应为2#YYYYMMDD-NNN")
        now = datetime.now()
        if cutoff_ts > now + timedelta(minutes=1):
            raise ValueError("预测截止时间不能位于服务器当前时刻之后")
        target = self.store.get_target(target_meltno)
        resolved_open = _datetime(target.get("open_ts")) if target else None
        resolved_open = resolved_open or target_open_ts
        if resolved_open is None:
            raise ValueError("目标炉次尚无开口时间，请填写预计开口时间")
        furnace_no = str((target or {}).get("furnace_no") or match.group("furnace"))
        heats = self.store.all_heats_until(furnace_no, resolved_open)
        features = build_history_features(
            target_meltno=target_meltno,
            target_open_ts=resolved_open,
            cutoff_ts=cutoff_ts,
            heats=heats,
            strict_availability=strict_context,
        )
        feature_watermarks: dict[str, Any] = {
            "cutoff_ts": cutoff_ts,
            "history": {
                "visible_label_count": features.get("v20_history__visible_label_count"),
                "cutoff_rule": (
                    "si_available_at<=slot_ts"
                    if strict_context else "source_updated_at<=cutoff_ts"
                ),
            },
        }
        lead_minutes = (resolved_open - cutoff_ts).total_seconds() / 60.0
        if strict_context:
            model = load_strict_context_model()
            with self.store.connect(read_only=True) as connection:
                features, feature_watermarks = build_strict_context_features(
                    connection,
                    cutoff_ts=cutoff_ts,
                    history_features=features,
                    feature_columns=model.feature_columns,
                    lead_minutes=lead_minutes,
                )
        else:
            model = load_model()
        point = model.predict_one(features)
        interval = model.interval(point)
        execution_completed_at = datetime.now().astimezone()
        actual = _number((target or {}).get("si_avg"))
        actual_ts = _datetime((target or {}).get("source_updated_at"))
        warnings: list[str] = []
        if abs(lead_minutes - float(model.payload.get("lead_minutes", 60))) > 20:
            warnings.append("当前提前量偏离模型训练的开口前60分钟场景，结果仅作影子参考")
        if lead_minutes < 0:
            warnings.append("截止时间晚于开口时间，不属于开口前预测")
        if features.get("v20_history__visible_label_count", 0) < 5:
            warnings.append("截止时刻可见的历史平均Si少于5炉")
        if strict_context and not (feature_watermarks.get("chemistry") or {}).get("available"):
            warnings.append("220.12本地镜像暂未提供可见烧结化学背景；保持缺失并记录审计，不回连外部IMES")
        record = {
            "request_id": str(uuid4()),
            "target_meltno": target_meltno,
            "furnace_no": furnace_no,
            "target_open_ts": resolved_open,
            "prediction_cutoff_ts": cutoff_ts,
            "requested_at": execution_started_at,
            "requested_by": requested_by or "operator",
            "requested_role": requested_role,
            "request_mode": request_mode,
            "lead_minutes": lead_minutes,
            "prediction_si_mean": point,
            "prediction_p10": interval["p10"],
            "prediction_p50": interval["p50"],
            "prediction_p90": interval["p90"],
            "actual_si_at_prediction": actual,
            "actual_available_ts_at_prediction": actual_ts,
            "model_schema": model.schema,
            "model_name": model.model_name,
            "model_sha256": model.sha256,
            "feature_snapshot": features,
            "model_contract": {
                "trained_lead_minutes": model.payload.get("lead_minutes", 60),
                "feature_columns": model.feature_columns,
                "target": "mean_si",
                "actual_source": f"{HEAT_TABLE}.si_avg",
                "status": "experimental_shadow",
                "context_groups": model.payload.get("context_groups", {}),
                "strict_as_of_contract": strict_context,
                **(audit_context or {}),
            },
            "prediction_status": "experimental_shadow",
            "execution_completed_at": execution_completed_at,
            "dispatch_delay_seconds": max(
                0.0, _local_elapsed_seconds(execution_started_at, cutoff_ts)
            ) if request_mode == "strict_hourly" else None,
            "attempt_count": max(1, int(attempt_count)),
            "initial_target_meltno": target_meltno if request_mode == "strict_hourly" else None,
            "match_rule_version": (
                "first_open_strictly_after_prediction_completed.v1"
                if request_mode == "strict_hourly" else None
            ),
            "feature_watermarks": feature_watermarks,
            **(record_context or {}),
        }
        inserted = self.store.insert_prediction(record) if persist else {}
        return {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "status": "experimental_shadow",
            "prediction": {
                "request_id": record["request_id"],
                "prediction_id": inserted.get("prediction_id"),
                "target_meltno": target_meltno,
                "target_open_ts": _json_safe(resolved_open),
                "prediction_cutoff_ts": _json_safe(cutoff_ts),
                "lead_minutes": lead_minutes,
                "si_mean": point,
                **interval,
                "actual_si_mean": actual,
                "actual_available_ts": _json_safe(actual_ts),
                "actual_ready": actual is not None,
                "signed_error": point - actual if actual is not None else None,
                "absolute_error": abs(point - actual) if actual is not None else None,
                "hit_abs_le_005": abs(point - actual) <= 0.05 if actual is not None else None,
                "request_mode": request_mode,
                "requested_at": inserted.get("requested_at"),
                "execution_completed_at": _json_safe(execution_completed_at),
                "dispatch_delay_seconds": record.get("dispatch_delay_seconds"),
                "attempt_count": record.get("attempt_count"),
                "persisted": bool(inserted),
                "deduplicated": bool(inserted.get("deduplicated")),
                "warnings": warnings,
            },
            "features": _json_safe(features),
            "feature_watermarks": _json_safe(feature_watermarks),
            "read_only_process_data": True,
            "writes_prediction_audit_only": bool(persist),
        }

    def _resolve_request(self, payload: dict[str, Any]) -> tuple[str, datetime | None, datetime, str]:
        target_meltno = str(payload.get("target_meltno") or "").strip()
        mode = str(payload.get("cutoff_mode") or "now").strip()
        target_open_ts = _datetime(payload.get("target_open_ts"))
        target = self.store.get_target(target_meltno) if target_meltno else None
        known_open = _datetime((target or {}).get("open_ts"))
        if mode == "now":
            cutoff = datetime.now()
            request_mode = "live_click"
        elif mode == "open_minus_60":
            opened = known_open or target_open_ts
            if opened is None:
                raise ValueError("开口前60分钟回放需要目标开口时间")
            cutoff = opened - timedelta(minutes=60)
            request_mode = "historical_replay"
        elif mode == "explicit":
            cutoff = _datetime(payload.get("cutoff_ts"))
            if cutoff is None:
                raise ValueError("显式截止模式需要cutoff_ts")
            request_mode = "manual_cutoff"
        else:
            raise ValueError("cutoff_mode仅支持now/open_minus_60/explicit")
        return target_meltno, target_open_ts, cutoff, request_mode

    def data_readiness(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_meltno, target_open_ts, cutoff, request_mode = self._resolve_request(payload)
        result = self._predict_row(
            target_meltno=target_meltno,
            target_open_ts=target_open_ts,
            cutoff_ts=cutoff,
            request_mode=request_mode,
            requested_by="readiness_probe",
            requested_role="operator",
            persist=False,
        )
        features = result.get("features") or {}
        numeric = [value for value in features.values() if isinstance(value, (int, float))]
        missing = [name for name, value in features.items() if value is None]
        warnings = list(result["prediction"].get("warnings") or [])
        if missing:
            warnings.append(f"{len(missing)}项预测特征缺失，模型按既定缺失值合同处理")
        return {
            "ok": True,
            "schema": "bf.si.v20.data_readiness.v1",
            "status": "experimental_shadow",
            "target_meltno": target_meltno,
            "target_open_ts": _json_safe(result["prediction"].get("target_open_ts")),
            "prediction_cutoff_ts": _json_safe(result["prediction"].get("prediction_cutoff_ts")),
            "request_mode": request_mode,
            "lead_minutes": result["prediction"].get("lead_minutes"),
            "feature_count": len(features),
            "available_feature_count": len(numeric),
            "missing_feature_count": len(missing),
            "missing_features": missing,
            "history": {
                key: features.get(key)
                for key in (
                    "history_mean__Si_lag_1", "history_mean__Si_lag_2",
                    "history_mean__Si_lag_3", "history_mean__Si_lag_4",
                    "history_mean__Si_lag_5", "history_mean__Si_mean_3",
                    "history_mean__Si_mean_5", "history_mean__Si_slope_5",
                    "v20_history__visible_label_count",
                    "v20_history__unlabeled_heat_gap",
                )
            },
            "features": _json_safe(features),
            "warnings": warnings,
            "leakage_contract": {
                "current_target_si_excluded": True,
                "future_labels_excluded": True,
                "actual_source": f"{HEAT_TABLE}.si_avg",
            },
        }

    def prediction_detail(self, prediction_id: int) -> dict[str, Any]:
        row = self.store.get_prediction_detail(prediction_id)
        if not row:
            raise ValueError("未找到指定预测审计记录")
        prediction = dict(row)
        actual = _number(prediction.get("actual_si_mean"))
        point = _number(prediction.get("prediction_si_mean"))
        prediction["actual_ready"] = actual is not None
        prediction["absolute_error"] = abs(point - actual) if point is not None and actual is not None else None
        prediction["hit_abs_le_005"] = (
            prediction["absolute_error"] <= 0.05
            if prediction["absolute_error"] is not None else None
        )
        return {
            "ok": True,
            "schema": "bf.si.v20.prediction_detail.v1",
            "status": "experimental_shadow",
            "prediction": prediction,
            "features": prediction.get("feature_snapshot") or {},
            "model_contract": prediction.get("model_contract") or {},
            "actual_source": f"{HEAT_TABLE}.si_avg",
        }

    def predict(self, payload: dict[str, Any], *, username: str, role: str | None) -> dict[str, Any]:
        target_meltno, target_open_ts, cutoff, request_mode = self._resolve_request(payload)
        return self._predict_row(
            target_meltno=target_meltno,
            target_open_ts=target_open_ts,
            cutoff_ts=cutoff,
            request_mode=request_mode,
            requested_by=username,
            requested_role=role,
            persist=True,
        )

    def hourly_predict(self, payload: dict[str, Any], *, username: str, role: str | None) -> dict[str, Any]:
        """Create one shadow prediction using a whole-hour data cutoff.

        Each furnace and whole-hour cutoff has exactly one audit row. Repeated
        calls return that original record, preserving the strict hourly cadence
        without duplicate points. Server automation may call this endpoint while
        the browser remains closed.
        """

        cutoff = _datetime(payload.get("cutoff_ts"))
        if cutoff is None:
            now = datetime.now()
            cutoff = now.replace(minute=0, second=0, microsecond=0)
        target_meltno = str(payload.get("target_meltno") or "").strip()
        target = self.store.get_target(target_meltno) if target_meltno else None
        target_source = "explicit_request"
        if not target_meltno:
            status = self.status(target_limit=50)
            target = resolve_hourly_target(status, cutoff)
            target_meltno = str((target or {}).get("meltno") or "").strip()
            target_source = str((target or {}).get("source_type") or "status_recommended_target")
        if not target_meltno:
            raise ValueError("当前没有可按小时预测的候选炉次")
        target_open_ts = _datetime(payload.get("target_open_ts")) or _datetime((target or {}).get("open_ts"))
        if target_open_ts is None:
            raise ValueError("按小时预测需要目标炉次的正式或预计开口时间")
        match = MELTNO_RE.fullmatch(target_meltno)
        furnace_no = str((target or {}).get("furnace_no") or (match.group("furnace") if match else "2"))
        existing_reader = getattr(self.store, "get_hourly_prediction", None)
        existing = existing_reader(furnace_no, cutoff) if callable(existing_reader) else None
        if existing:
            point = _number(existing.get("prediction_si_mean"))
            actual_target = self.store.get_target(str(existing.get("target_meltno") or ""))
            actual = _number((actual_target or {}).get("si_avg"))
            return {
                "ok": True,
                "schema": SCHEMA_VERSION,
                "status": "experimental_shadow",
                "prediction": {
                    "request_id": existing.get("request_id"),
                    "prediction_id": existing.get("prediction_id"),
                    "target_meltno": existing.get("target_meltno"),
                    "target_open_ts": existing.get("target_open_ts"),
                    "prediction_cutoff_ts": existing.get("prediction_cutoff_ts"),
                    "lead_minutes": _number(existing.get("lead_minutes")),
                    "si_mean": point,
                    "p10": _number(existing.get("prediction_p10")),
                    "p50": _number(existing.get("prediction_p50")),
                    "p90": _number(existing.get("prediction_p90")),
                    "actual_si_mean": actual,
                    "actual_ready": actual is not None,
                    "absolute_error": abs(point - actual) if point is not None and actual is not None else None,
                    "hit_abs_le_005": abs(point - actual) <= 0.05 if point is not None and actual is not None else None,
                    "request_mode": "hourly_schedule",
                    "requested_at": existing.get("requested_at"),
                    "persisted": True,
                    "deduplicated": True,
                    "warnings": ["该炉号与整点截止已有预测，本次返回原审计记录"],
                },
                "features": existing.get("feature_snapshot") or {},
                "read_only_process_data": True,
                "writes_prediction_audit_only": False,
            }
        return self._predict_row(
            target_meltno=target_meltno,
            target_open_ts=target_open_ts,
            cutoff_ts=cutoff,
            request_mode="hourly_schedule",
            requested_by=username,
            requested_role=role,
            persist=True,
            audit_context={
                "hourly_target_source": target_source,
                "hourly_actual_match_rule": "first_real_heat_open_after_requested_at",
            },
        )

    @staticmethod
    def _strict_slot(value: Any | None = None) -> datetime:
        raw = (
            _datetime(value)
            if value is not None
            else datetime.now().replace(minute=0, second=0, microsecond=0)
        )
        if raw is None:
            raise ValueError("严格整点截止时间格式无效")
        if raw.minute != 0 or raw.second != 0 or raw.microsecond != 0:
            raise ValueError("严格整点截止时间必须为HH:00:00")
        current = datetime.now()
        if raw > current:
            raise ValueError("严格整点截止时间不能位于服务器当前时刻之后")
        return raw

    def strict_hourly_status(self) -> dict[str, Any]:
        model = load_strict_context_model()
        current_slot = datetime.now().replace(minute=0, second=0, microsecond=0)
        schema_ready = self.store.strict_schema_ready()
        slot = self.store.strict_hourly_slot("2", current_slot) if schema_ready else None
        return {
            "ok": True,
            "schema": "bf.si.v20.strict_hourly_status.v1",
            "status": "experimental_shadow",
            "always_enabled": True,
            "operator_configurable": False,
            "schema_ready": schema_ready,
            "current_slot": _json_safe(slot),
            "model": {
                "schema": model.schema,
                "name": model.model_name,
                "sha256": model.sha256,
                "feature_count": len(model.feature_columns),
                "trained_lead_minutes": model.payload.get("lead_minutes", 60),
                "context_groups": model.payload.get("context_groups", {}),
            },
            "contracts": {
                "cutoff": "whole_hour_HH:00:00",
                "source_visibility": "source_ts<=slot_ts and ingested_at<=slot_ts",
                "actual_match": "first_open_strictly_after_prediction_completed.v1",
                "local_database_only": True,
                "production_control_write": False,
            },
        }

    def dispatch_strict_hourly(
        self,
        *,
        now: datetime | None = None,
        username: str = "si_v20_strict_hourly_dispatcher",
        furnace_no: str = "2",
    ) -> dict[str, Any]:
        current = (now or datetime.now()).replace(tzinfo=None)
        current_slot = current.replace(minute=0, second=0, microsecond=0)
        ensure_schedule_schema_once(self.store)
        created = self.store.ensure_strict_hourly_slots(furnace_no, current_slot)
        claimed = self.store.claim_strict_hourly_slots(current, limit=24)
        model = load_strict_context_model()
        results: list[dict[str, Any]] = []
        for slot in claimed:
            slot_id = int(slot["slot_id"])
            slot_ts = _datetime(slot.get("schedule_slot_ts"))
            if slot_ts is None:
                self.store.mark_strict_hourly_failure(slot_id, "时间槽缺少schedule_slot_ts")
                results.append({"slot_id": slot_id, "ok": False, "error": "时间槽缺少schedule_slot_ts"})
                continue
            try:
                existing = self.store.get_strict_prediction(furnace_no, slot_ts, model.sha256)
                if existing:
                    prediction_id = int(existing["prediction_id"])
                    completed_at = _datetime(existing.get("execution_completed_at")) or datetime.now()
                    self.store.mark_strict_hourly_success(
                        slot_id=slot_id,
                        prediction_id=prediction_id,
                        initial_target_meltno=str(existing.get("initial_target_meltno") or existing.get("target_meltno") or ""),
                        completed_at=completed_at,
                        feature_watermarks=dict(existing.get("feature_watermarks") or {}),
                    )
                    results.append({"slot_id": slot_id, "slot_ts": _json_safe(slot_ts), "ok": True, "deduplicated": True, "prediction_id": prediction_id})
                    continue
                status = self.status(target_limit=100)
                target = resolve_hourly_target(status, datetime.now())
                if not target:
                    raise ValueError("预测执行时刻之后没有可用候选炉次")
                target_meltno = str(target.get("meltno") or "")
                target_open_ts = _datetime(target.get("open_ts"))
                if not target_meltno or target_open_ts is None:
                    raise ValueError("严格整点候选缺少炉号或正式/估计开口时间")
                result = self._predict_row(
                    target_meltno=target_meltno,
                    target_open_ts=target_open_ts,
                    cutoff_ts=slot_ts,
                    request_mode="strict_hourly",
                    requested_by=username,
                    requested_role="scheduler",
                    persist=True,
                    strict_context=True,
                    attempt_count=int(slot.get("attempt_count") or 1),
                    audit_context={
                        "strict_hourly": True,
                        "strict_target_source": target.get("source_type"),
                        "strict_actual_match_rule": "first_open_strictly_after_prediction_completed.v1",
                        "local_database_only": True,
                    },
                    record_context={
                        "schedule_slot_ts": slot_ts,
                        "cadence_minutes": 60,
                    },
                )
                prediction = result["prediction"]
                prediction_id = int(prediction["prediction_id"])
                completed_at = _datetime(prediction.get("execution_completed_at")) or datetime.now()
                watermarks = dict(result.get("feature_watermarks") or {})
                if not watermarks:
                    detail = self.store.get_prediction_detail(prediction_id) or {}
                    watermarks = dict(detail.get("feature_watermarks") or {})
                self.store.mark_strict_hourly_success(
                    slot_id=slot_id,
                    prediction_id=prediction_id,
                    initial_target_meltno=target_meltno,
                    completed_at=completed_at,
                    feature_watermarks=watermarks,
                )
                results.append({"slot_id": slot_id, "slot_ts": _json_safe(slot_ts), "ok": True, "prediction": prediction})
            except Exception as exc:  # noqa: BLE001 - each hour retries independently.
                self.store.mark_strict_hourly_failure(slot_id, str(exc))
                results.append({"slot_id": slot_id, "slot_ts": _json_safe(slot_ts), "ok": False, "error": str(exc)})
        matched = self.store.reconcile_strict_hourly_matches()
        return {
            "ok": all(item.get("ok") for item in results),
            "schema": "bf.si.v20.strict_hourly_dispatch.v1",
            "status": "experimental_shadow",
            "checked_at": _json_safe(current),
            "created_slot_count": created,
            "claimed_slot_count": len(claimed),
            "matched_count": matched,
            "results": results,
            "writes_prediction_audit_only": True,
        }

    def strict_hourly_predict(
        self,
        payload: dict[str, Any],
        *,
        username: str,
        role: str | None,
    ) -> dict[str, Any]:
        """Server-validated manual catch-up; browser target and clock are ignored."""

        slot_ts = self._strict_slot(payload.get("cutoff_ts"))
        ensure_schedule_schema_once(self.store)
        self.store.ensure_strict_hourly_slots("2", slot_ts)
        result = self.dispatch_strict_hourly(now=datetime.now(), username=username or "operator")
        row = self.store.strict_hourly_slot("2", slot_ts)
        return {
            "ok": bool(row and row.get("slot_status") == "success"),
            "schema": "bf.si.v20.strict_hourly_manual.v1",
            "status": "experimental_shadow",
            "requested_slot_ts": _json_safe(slot_ts),
            "slot": row,
            "dispatch": result,
            "browser_target_ignored": True,
            "server_clock_authoritative": True,
        }

    def replay(self, payload: dict[str, Any], *, username: str, role: str | None) -> dict[str, Any]:
        date_from = _date(payload.get("date_from"))
        date_to = _date(payload.get("date_to"))
        if date_from is None or date_to is None:
            raise ValueError("历史回放需要date_from和date_to")
        if date_to < date_from:
            raise ValueError("date_to不能早于date_from")
        if (date_to - date_from).days > 31:
            raise ValueError("单次历史回放最多32天")
        limit = max(1, min(int(payload.get("limit") or MAX_REPLAY_HEATS), MAX_REPLAY_HEATS))
        targets = self.store.targets_for_range(date_from, date_to, limit)
        predictions: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for target in targets:
            try:
                opened = _datetime(target.get("open_ts"))
                if opened is None:
                    continue
                result = self._predict_row(
                    target_meltno=str(target["meltno"]),
                    target_open_ts=opened,
                    cutoff_ts=opened - timedelta(minutes=60),
                    request_mode="historical_range_replay",
                    requested_by=username,
                    requested_role=role,
                    persist=True,
                )
                predictions.append(result["prediction"])
            except Exception as exc:  # noqa: BLE001 - one bad heat must not hide the rest.
                failures.append({"meltno": str(target.get("meltno")), "error": str(exc)})
        return {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "status": "experimental_shadow",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "requested_count": len(targets),
            "predicted_count": len(predictions),
            "failed_count": len(failures),
            "predictions": predictions,
            "failures": failures[:20],
        }

    def schedule_status(self) -> dict[str, Any]:
        ensure_schedule_schema_once(self.store)
        reader = getattr(self.store, "get_schedule", None)
        schedule = reader("production_default") if callable(reader) else None
        return {
            "ok": True,
            "schema": "bf.si.v20.schedule_config.v1",
            "status": "experimental_shadow",
            "allowed_cadence_minutes": list(ALLOWED_CADENCE_MINUTES),
            "schedule": schedule,
            "dispatcher_contract": {
                "poll_interval_minutes": 1,
                "browser_required": False,
                "prediction_write_target": TABLE_NAME,
                "production_control_write": False,
            },
        }

    def configure_schedule(
        self,
        payload: dict[str, Any],
        *,
        username: str,
    ) -> dict[str, Any]:
        ensure_schedule_schema_once(self.store)
        cadence = validate_cadence_minutes(payload.get("cadence_minutes", 60))
        enabled_raw = payload.get("enabled", True)
        enabled = enabled_raw if isinstance(enabled_raw, bool) else str(enabled_raw).lower() in {"1", "true", "yes", "on"}
        furnace_no = str(payload.get("furnace_no") or "2").strip()
        if not furnace_no.isdigit():
            raise ValueError("furnace_no必须是数字高炉编号")
        now = datetime.now()
        next_slot = next_schedule_slot(now, cadence)
        writer = getattr(self.store, "configure_schedule", None)
        if not callable(writer):
            raise RuntimeError("定时配置表尚未迁移")
        schedule = writer(
            schedule_key="production_default",
            furnace_no=furnace_no,
            cadence_minutes=cadence,
            enabled=enabled,
            actor=username or "operator",
            next_slot_ts=next_slot,
        )
        return {
            "ok": True,
            "schema": "bf.si.v20.schedule_config.v1",
            "status": "experimental_shadow",
            "schedule": schedule,
            "message": "定时预测配置已保存；后台分钟分发器将在下一时间槽执行。",
        }

    def _scheduled_slot_prediction(
        self,
        *,
        slot_ts: datetime,
        cadence_minutes: int,
        furnace_no: str,
        request_mode: str,
        username: str,
        role: str | None,
        schedule_id: int | None,
        schedule_run_id: int | None,
    ) -> dict[str, Any]:
        cadence = validate_cadence_minutes(cadence_minutes)
        existing_reader = getattr(self.store, "get_scheduled_prediction", None)
        existing = existing_reader(
            schedule_id=schedule_id,
            schedule_run_id=schedule_run_id,
            slot_ts=slot_ts,
        ) if callable(existing_reader) else None
        if existing:
            return {
                "ok": True,
                "schema": SCHEMA_VERSION,
                "status": "experimental_shadow",
                "prediction": {
                    "prediction_id": existing.get("prediction_id"),
                    "request_id": existing.get("request_id"),
                    "target_meltno": existing.get("target_meltno"),
                    "prediction_cutoff_ts": existing.get("prediction_cutoff_ts"),
                    "schedule_slot_ts": existing.get("schedule_slot_ts"),
                    "cadence_minutes": existing.get("cadence_minutes"),
                    "si_mean": _number(existing.get("prediction_si_mean")),
                    "p10": _number(existing.get("prediction_p10")),
                    "p50": _number(existing.get("prediction_p50")),
                    "p90": _number(existing.get("prediction_p90")),
                    "requested_at": existing.get("requested_at"),
                    "request_mode": request_mode,
                    "persisted": True,
                    "deduplicated": True,
                    "warnings": ["该定时时间槽已有预测，本次返回原审计记录"],
                },
                "features": existing.get("feature_snapshot") or {},
                "read_only_process_data": True,
                "writes_prediction_audit_only": False,
            }

        target: dict[str, Any] | None = None
        target_source = "first_real_heat_after_historical_slot"
        if request_mode == "scheduled_time_replay":
            finder = getattr(self.store, "first_heat_after", None)
            target = finder(furnace_no, slot_ts) if callable(finder) else None
        else:
            status = self.status(target_limit=80)
            target = resolve_hourly_target(status, slot_ts)
            target_source = str((target or {}).get("source_type") or "status_recommended_target")
        if not target:
            raise ValueError("该时间点之后没有可匹配的目标炉次")
        target_meltno = str(target.get("meltno") or "")
        target_open_ts = _datetime(target.get("open_ts"))
        if not target_meltno or target_open_ts is None:
            raise ValueError("目标炉次缺少炉号或开口时间")
        match_rule = (
            "first_real_heat_open_at_or_after_schedule_slot"
            if request_mode == "scheduled_time_replay"
            else "first_real_heat_open_after_requested_at"
        )
        return self._predict_row(
            target_meltno=target_meltno,
            target_open_ts=target_open_ts,
            cutoff_ts=slot_ts,
            request_mode=request_mode,
            requested_by=username,
            requested_role=role,
            persist=True,
            audit_context={
                "scheduled_target_source": target_source,
                "scheduled_actual_match_rule": match_rule,
                "cadence_minutes": cadence,
            },
            record_context={
                "schedule_id": schedule_id,
                "schedule_run_id": schedule_run_id,
                "schedule_slot_ts": slot_ts,
                "cadence_minutes": cadence,
            },
        )

    def dispatch_due_schedules(
        self,
        *,
        now: datetime | None = None,
        username: str = "si_v20_schedule_dispatcher",
    ) -> dict[str, Any]:
        current = (now or datetime.now()).replace(tzinfo=None)
        ensure_schedule_schema_once(self.store)
        reader = getattr(self.store, "due_schedules", None)
        marker = getattr(self.store, "mark_schedule_result", None)
        if not callable(reader) or not callable(marker):
            raise RuntimeError("定时配置表尚未迁移")
        due = reader(current)
        results: list[dict[str, Any]] = []
        for schedule in due:
            cadence = validate_cadence_minutes(schedule.get("cadence_minutes"))
            configured_slot = _datetime(schedule.get("next_slot_ts")) or floor_schedule_slot(current, cadence)
            stale = configured_slot < current - timedelta(minutes=cadence * 2)
            slot = floor_schedule_slot(current, cadence) if stale else configured_slot
            try:
                result = self._scheduled_slot_prediction(
                    slot_ts=slot,
                    cadence_minutes=cadence,
                    furnace_no=str(schedule.get("furnace_no") or "2"),
                    request_mode="scheduled_interval",
                    username=username,
                    role="scheduler",
                    schedule_id=int(schedule["schedule_id"]),
                    schedule_run_id=None,
                )
                marker(
                    schedule_id=int(schedule["schedule_id"]),
                    slot_ts=slot,
                    next_slot_ts=next_schedule_slot(slot, cadence),
                    status="success",
                    error=None,
                )
                results.append({"schedule_id": schedule["schedule_id"], "slot_ts": _json_safe(slot), "ok": True, "stale_slot_skipped": stale, "prediction": result.get("prediction")})
            except Exception as exc:  # noqa: BLE001 - every schedule has an independent audit result.
                marker(
                    schedule_id=int(schedule["schedule_id"]),
                    slot_ts=slot,
                    next_slot_ts=next_schedule_slot(slot, cadence),
                    status="failed",
                    error=str(exc)[:1000],
                )
                results.append({"schedule_id": schedule["schedule_id"], "slot_ts": _json_safe(slot), "ok": False, "error": str(exc)})
        return {
            "ok": all(item.get("ok") for item in results),
            "schema": "bf.si.v20.schedule_dispatch.v1",
            "checked_at": _json_safe(current),
            "due_count": len(due),
            "results": results,
            "writes_prediction_audit_only": True,
        }

    def scheduled_replay(
        self,
        payload: dict[str, Any],
        *,
        username: str,
        role: str | None,
    ) -> dict[str, Any]:
        ensure_schedule_schema_once(self.store)
        cadence = validate_cadence_minutes(payload.get("cadence_minutes", 60))
        specified = _datetime(payload.get("cutoff_ts"))
        start = specified or _datetime(payload.get("start_ts"))
        end = specified or _datetime(payload.get("end_ts"))
        if start is None or end is None:
            raise ValueError("批量预测需要start_ts/end_ts，指定时间预测需要cutoff_ts")
        if end > datetime.now() + timedelta(minutes=1):
            raise ValueError("历史定时预测不能包含服务器未来时间")
        slots = schedule_slots(start, end, cadence)
        creator = getattr(self.store, "create_schedule_run", None)
        finisher = getattr(self.store, "finish_schedule_run", None)
        if not callable(creator) or not callable(finisher):
            raise RuntimeError("定时运行批次表尚未迁移")
        run = creator(
            run_kind="specified_time" if specified else "historical_batch",
            schedule_id=None,
            cadence_minutes=cadence,
            range_start_ts=start,
            range_end_ts=end,
            requested_by=username,
            parameters={"furnace_no": str(payload.get("furnace_no") or "2")},
        )
        predictions: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for slot in slots:
            try:
                result = self._scheduled_slot_prediction(
                    slot_ts=slot,
                    cadence_minutes=cadence,
                    furnace_no=str(payload.get("furnace_no") or "2"),
                    request_mode="scheduled_time_replay",
                    username=username,
                    role=role,
                    schedule_id=None,
                    schedule_run_id=int(run["run_id"]),
                )
                predictions.append(result["prediction"])
            except Exception as exc:  # noqa: BLE001
                failures.append({"slot_ts": _json_safe(slot), "error": str(exc)})
        status = "completed" if not failures else "partial" if predictions else "failed"
        finisher(
            run_id=int(run["run_id"]),
            status=status,
            point_count=len(slots),
            success_count=len(predictions),
            failures=failures[:100],
        )
        return {
            "ok": bool(predictions) or not slots,
            "schema": "bf.si.v20.scheduled_replay.v1",
            "status": "experimental_shadow",
            "run_id": run["run_id"],
            "run_status": status,
            "cadence_minutes": cadence,
            "requested_count": len(slots),
            "predicted_count": len(predictions),
            "failed_count": len(failures),
            "predictions": predictions,
            "failures": failures[:20],
        }

    def scheduled_history(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        cadence_minutes: int | None,
        schedule_run_id: int | None,
        limit: int,
    ) -> dict[str, Any]:
        ensure_schedule_schema_once(self.store)
        reader = getattr(self.store, "list_scheduled_outcomes", None)
        items = reader(
            date_from=date_from,
            date_to=date_to,
            cadence_minutes=cadence_minutes,
            schedule_run_id=schedule_run_id,
            limit=limit,
        ) if callable(reader) else []
        evaluated = [item for item in items if item.get("absolute_error") is not None]
        signed = [float(item["signed_error"]) for item in evaluated if item.get("signed_error") is not None]
        return {
            "ok": True,
            "schema": "bf.si.v20.scheduled_history.v1",
            "status": "experimental_shadow",
            "items": items,
            "count": len(items),
            "metrics": {
                "prediction_count": len(items),
                "matched_prediction_count": sum(bool(item.get("matched_actual_meltno")) for item in items),
                "unique_actual_heat_count": len({str(item.get("matched_actual_meltno")) for item in items if item.get("matched_actual_meltno")}),
                "evaluated_count": len(evaluated),
                "mae": sum(float(item["absolute_error"]) for item in evaluated) / len(evaluated) if evaluated else None,
                "rmse": (sum(value ** 2 for value in signed) / len(signed)) ** 0.5 if signed else None,
                "bias": sum(signed) / len(signed) if signed else None,
                "hit_rate_abs_le_002": sum(float(item["absolute_error"]) <= 0.02 for item in evaluated) / len(evaluated) if evaluated else None,
                "hit_rate_abs_le_005": sum(bool(item.get("hit_abs_le_005")) for item in evaluated) / len(evaluated) if evaluated else None,
            },
            "actual_source": f"{HEAT_TABLE}.si_avg",
        }

    def hourly_table(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> dict[str, Any]:
        """Merge strict slots with the independent 60-minute schedule for operator review."""

        ensure_schedule_schema_once(self.store)
        limit = max(1, min(int(limit), 5000))

        def slot_key(value: Any) -> str | None:
            parsed = _datetime(value)
            if parsed is None:
                return None
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed.replace(minute=0, second=0, microsecond=0).isoformat()

        strict_ready = self.store.strict_schema_ready()
        slot_reader = getattr(self.store, "list_strict_hourly_slots", None)
        strict_slots = (
            slot_reader(date_from=date_from, date_to=date_to, limit=limit)
            if strict_ready and callable(slot_reader) else []
        )
        strict_items = (
            self.store.list_strict_hourly_outcomes(
                date_from=date_from,
                date_to=date_to,
                meltno_from=None,
                meltno_to=None,
                limit=limit,
            )
            if strict_ready else []
        )
        scheduled_reader = getattr(self.store, "list_scheduled_outcomes", None)
        scheduled_items = (
            scheduled_reader(
                date_from=date_from,
                date_to=date_to,
                cadence_minutes=60,
                schedule_run_id=None,
                limit=limit,
            )
            if callable(scheduled_reader) else []
        )

        slots_by_key = {
            key: item for item in strict_slots
            if (key := slot_key(item.get("schedule_slot_ts"))) is not None
        }
        strict_by_key = {
            key: item for item in strict_items
            if (key := slot_key(item.get("schedule_slot_ts"))) is not None
        }
        scheduled_by_key: dict[str, dict[str, Any]] = {}
        for item in scheduled_items:
            if item.get("request_mode") != "scheduled_interval":
                continue
            key = slot_key(item.get("schedule_slot_ts"))
            if key is not None and key not in scheduled_by_key:
                scheduled_by_key[key] = item

        keys = sorted(
            set(slots_by_key) | set(strict_by_key) | set(scheduled_by_key),
            reverse=True,
        )[:limit]
        items: list[dict[str, Any]] = []
        for key in keys:
            slot = slots_by_key.get(key, {})
            strict = strict_by_key.get(key)
            scheduled = scheduled_by_key.get(key)
            selected = strict or scheduled or {}
            public_fields = (
                "prediction_id", "request_id", "request_mode", "schedule_slot_ts",
                "prediction_cutoff_ts", "requested_at", "execution_completed_at",
                "prediction_si_mean", "prediction_p10", "prediction_p50", "prediction_p90",
                "prediction_status", "model_schema", "model_name", "cadence_minutes",
                "predicted_target_meltno", "target_meltno", "matched_actual_meltno",
                "matched_actual_open_ts", "matched_actual_close_ts", "actual_si_values",
                "actual_si_mean", "actual_sample_count", "actual_available_ts",
                "signed_error", "absolute_error", "hit_abs_le_005", "has_prediction",
                "actual_ready", "match_status", "history_status",
            )
            row = {name: selected.get(name) for name in public_fields}
            row["schedule_slot_ts"] = row.get("schedule_slot_ts") or slot.get("schedule_slot_ts") or key
            row["strict_slot_status"] = slot.get("slot_status")
            row["strict_attempt_count"] = slot.get("attempt_count")
            row["strict_last_error"] = slot.get("last_error")
            if strict:
                row["prediction_source"] = "strict_hourly"
            elif scheduled:
                row["prediction_source"] = "scheduled_interval_fallback"
            else:
                row["prediction_source"] = "missing"
                row["prediction_si_mean"] = None
                row["prediction_p10"] = None
                row["prediction_p50"] = None
                row["prediction_p90"] = None
                row["actual_si_values"] = []
            row["has_prediction"] = _number(row.get("prediction_si_mean")) is not None
            row["actual_ready"] = _number(row.get("actual_si_mean")) is not None
            items.append(row)

        evaluated = [item for item in items if item.get("absolute_error") is not None]
        return {
            "ok": True,
            "schema": "bf.si.v20.hourly_table.v1",
            "status": "experimental_shadow",
            "items": items,
            "count": len(items),
            "metrics": {
                "hour_count": len(items),
                "prediction_count": sum(bool(item.get("has_prediction")) for item in items),
                "strict_prediction_count": sum(item.get("prediction_source") == "strict_hourly" for item in items),
                "fallback_prediction_count": sum(item.get("prediction_source") == "scheduled_interval_fallback" for item in items),
                "failed_strict_slot_count": sum(item.get("strict_slot_status") == "failed_retryable" for item in items),
                "evaluated_count": len(evaluated),
                "hit_rate_abs_le_005": (
                    sum(bool(item.get("hit_abs_le_005")) for item in evaluated) / len(evaluated)
                    if evaluated else None
                ),
            },
            "actual_source": f"{HEAT_TABLE}.sample_details + si_avg",
            "refresh_contract": "one_natural_hour_per_row; browser refreshes every 60 seconds",
        }

    def history(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        meltno: str | None,
        limit: int,
        latest_per_heat: bool,
        compact: bool = False,
    ) -> dict[str, Any]:
        items = self.store.list_history(
            date_from=date_from,
            date_to=date_to,
            meltno=meltno,
            limit=limit,
            latest_per_heat=latest_per_heat,
        )
        evaluated = [item for item in items if item.get("absolute_error") is not None]
        mae = (
            sum(float(item["absolute_error"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        )
        signed_errors = [float(item["signed_error"]) for item in evaluated if item.get("signed_error") is not None]
        rmse = (
            (sum(float(item["signed_error"]) ** 2 for item in evaluated if item.get("signed_error") is not None) / len(signed_errors)) ** 0.5
            if signed_errors else None
        )
        bias = sum(signed_errors) / len(signed_errors) if signed_errors else None
        hit002 = (
            sum(float(item["absolute_error"]) <= 0.02 for item in evaluated) / len(evaluated)
            if evaluated else None
        )
        hit005 = (
            sum(bool(item["hit_abs_le_005"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        )
        response_items = (
            [
                {key: value for key, value in item.items() if key != "feature_snapshot"}
                for item in items
            ]
            if compact
            else items
        )
        return {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "status": "experimental_shadow",
            "items": response_items,
            "count": len(items),
            "compact": compact,
            "metrics": {
                "actual_count": sum(bool(item.get("actual_ready")) for item in items),
                "prediction_count": sum(bool(item.get("has_prediction")) for item in items),
                "evaluated_count": len(evaluated),
                "mae": mae,
                "rmse": rmse,
                "bias": bias,
                "hit_rate_abs_le_002": hit002,
                "hit_rate_abs_le_005": hit005,
            },
            "actual_source": f"{HEAT_TABLE}.si_avg",
        }

    def hourly_history(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> dict[str, Any]:
        reader = getattr(self.store, "list_hourly_outcomes", None)
        if not callable(reader):
            items: list[dict[str, Any]] = []
        else:
            items = reader(date_from=date_from, date_to=date_to, limit=limit)
        evaluated = [item for item in items if item.get("absolute_error") is not None]
        signed_errors = [float(item["signed_error"]) for item in evaluated if item.get("signed_error") is not None]
        mae = sum(float(item["absolute_error"]) for item in evaluated) / len(evaluated) if evaluated else None
        rmse = (
            (sum(value ** 2 for value in signed_errors) / len(signed_errors)) ** 0.5
            if signed_errors else None
        )
        return {
            "ok": True,
            "schema": "bf.si.v20.hourly_history.v1",
            "status": "experimental_shadow",
            "match_rule": "first_real_heat_open_after_requested_at",
            "items": items,
            "count": len(items),
            "metrics": {
                "prediction_count": len(items),
                "matched_heat_count": sum(bool(item.get("matched_actual_meltno")) for item in items),
                "evaluated_count": len(evaluated),
                "mae": mae,
                "rmse": rmse,
                "bias": sum(signed_errors) / len(signed_errors) if signed_errors else None,
                "hit_rate_abs_le_002": (
                    sum(float(item["absolute_error"]) <= 0.02 for item in evaluated) / len(evaluated)
                    if evaluated else None
                ),
                "hit_rate_abs_le_005": (
                    sum(bool(item.get("hit_abs_le_005")) for item in evaluated) / len(evaluated)
                    if evaluated else None
                ),
            },
            "actual_source": f"{HEAT_TABLE}.si_avg",
        }

    def strict_hourly_history(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        meltno_from: str | None,
        meltno_to: str | None,
        limit: int,
    ) -> dict[str, Any]:
        schema_ready = self.store.strict_schema_ready()
        items = (
            self.store.list_strict_hourly_outcomes(
                date_from=date_from,
                date_to=date_to,
                meltno_from=meltno_from,
                meltno_to=meltno_to,
                limit=limit,
            )
            if schema_ready else []
        )
        evaluated = [item for item in items if item.get("absolute_error") is not None]
        signed = [float(item["signed_error"]) for item in evaluated if item.get("signed_error") is not None]
        return {
            "ok": True,
            "schema": "bf.si.v20.strict_hourly_history.v1",
            "status": "experimental_shadow",
            "schema_ready": schema_ready,
            "match_rule": "first_open_strictly_after_prediction_completed.v1",
            "items": items,
            "count": len(items),
            "metrics": {
                "prediction_count": len(items),
                "matched_heat_count": sum(bool(item.get("matched_actual_meltno")) for item in items),
                "evaluated_count": len(evaluated),
                "mae": sum(float(item["absolute_error"]) for item in evaluated) / len(evaluated) if evaluated else None,
                "rmse": (sum(value ** 2 for value in signed) / len(signed)) ** 0.5 if signed else None,
                "bias": sum(signed) / len(signed) if signed else None,
                "hit_rate_abs_le_002": sum(float(item["absolute_error"]) <= 0.02 for item in evaluated) / len(evaluated) if evaluated else None,
                "hit_rate_abs_le_005": sum(bool(item.get("hit_abs_le_005")) for item in evaluated) / len(evaluated) if evaluated else None,
                "pending_match_count": sum(not item.get("matched_actual_meltno") for item in items),
                "waiting_si_count": sum(bool(item.get("matched_actual_meltno")) and not item.get("actual_ready") for item in items),
            },
            "actual_source": f"{HEAT_TABLE}.si_avg",
            "legacy_hourly_endpoint": "/api/si-v20/hourly-history",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="V20影子预测数据库迁移/状态检查。")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ensure-schema", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    service = SiV20ShadowService()
    if args.ensure_schema:
        service.store.ensure_schema()
    print(json.dumps(service.status(target_limit=3), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
