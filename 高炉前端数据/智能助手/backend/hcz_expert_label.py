"""Append-only HCZ expert weak-label contracts and PostgreSQL store.

Requirement: REQ-HCZ-EXPERT-WEAK-LABEL-20260810.

The labeler is deliberately blind to the current cohesive-zone estimator.
Each submitted label is bound server-side to a hash of measured process data,
with separate ``observed_at`` and ``available_at`` knowledge times.  Records
remain expert weak labels and must never be represented as direct HCZ truth.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from uuid import uuid4

import pandas as pd


REQUIREMENT_ID = "REQ-HCZ-EXPERT-WEAK-LABEL-20260810"
LABEL_VERSION = "hcz-expert-weak-label.v1"
REFERENCE_TYPE = "expert_weak_label"
SOURCE_SCHEMA_VERSION = "gl02.hcz-label-source.v1"
ROOT_LEVELS = ("high", "normal", "low", "uncertain")
MOVEMENTS = ("up", "stable", "down", "uncertain")
ECCENTRIC_SECTORS = (*tuple("ABCDEFGH"), "none", "uncertain")
EVIDENCE_CODES = (
    "temperature_pattern",
    "pressure_permeability",
    "top_condition",
    "burden_descent",
    "gas_utilisation",
    "hot_metal_quality",
    "operation_log",
    "other",
)
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class HczLabelConfigurationError(RuntimeError):
    """Raised when the label store cannot satisfy its safety contract."""


class HczLabelValidationError(ValueError):
    """Raised when a browser payload violates the label contract."""


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_timestamp(value: Any) -> datetime:
    """Return a timezone-aware timestamp, assuming Asia/Shanghai for naive input."""
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value or "").strip()
            if not text:
                raise ValueError("empty timestamp")
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HczLabelValidationError("时间格式无效") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def iso_timestamp(value: Any) -> str:
    return normalize_timestamp(value).isoformat()


def _optional_float(
    value: Any,
    *,
    label: str,
    minimum: float,
    maximum: float,
) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    number = _finite(value)
    if number is None or not minimum <= number <= maximum:
        raise HczLabelValidationError(f"{label}必须在{minimum:g}到{maximum:g}之间")
    return round(number, 6)


def validate_label_payload(payload: Any) -> dict[str, Any]:
    """Validate only human-entered fields; measured context is rebuilt by the server."""
    if not isinstance(payload, Mapping):
        raise HczLabelValidationError("请求体必须是JSON对象")
    forbidden = {
        "model_output", "model_prediction", "hcz_estimate", "cohesive_zone",
        "estimated_root_height_m", "estimated_movement",
    }
    if forbidden.intersection(payload):
        raise HczLabelValidationError("盲标注请求不得包含任何HCZ模型输出")
    root_level = str(payload.get("root_level_label") or "").strip()
    movement = str(payload.get("movement_label") or "").strip()
    if root_level not in ROOT_LEVELS:
        raise HczLabelValidationError("请选择软熔带位置高低标签")
    if movement not in MOVEMENTS:
        raise HczLabelValidationError("请选择软熔带移动方向")
    confidence = payload.get("confidence_grade")
    try:
        confidence_grade = int(str(confidence).strip())
    except (TypeError, ValueError) as exc:
        raise HczLabelValidationError("可信等级必须是1到5的整数") from exc
    if confidence_grade not in range(1, 6):
        raise HczLabelValidationError("可信等级必须在1到5之间")
    eccentric = str(payload.get("eccentric_sector") or "").strip() or None
    if eccentric is not None and eccentric not in ECCENTRIC_SECTORS:
        raise HczLabelValidationError("偏心方位必须是A到H、无偏心或无法判断")
    raw_evidence = payload.get("evidence_codes") or []
    if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes)):
        raise HczLabelValidationError("判断依据必须是列表")
    evidence_codes = list(dict.fromkeys(str(item).strip() for item in raw_evidence if str(item).strip()))
    unknown_evidence = [item for item in evidence_codes if item not in EVIDENCE_CODES]
    if unknown_evidence:
        raise HczLabelValidationError(f"存在未知判断依据：{','.join(unknown_evidence)}")
    note = str(payload.get("note") or "").strip()
    if len(note) > 2000:
        raise HczLabelValidationError("备注不能超过2000个字符")
    if root_level == "uncertain" and movement == "uncertain" and len(note) < 5:
        raise HczLabelValidationError("位置和方向都无法判断时，请说明原因")
    operator_name = str(payload.get("operator_name") or "").strip()
    if not 2 <= len(operator_name) <= 64:
        raise HczLabelValidationError("请填写2到64个字符的实际标注人姓名或工号")
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not IDEMPOTENCY_RE.fullmatch(idempotency_key):
        raise HczLabelValidationError("幂等键格式无效")
    observed_at = normalize_timestamp(payload.get("observed_at"))
    window_start = normalize_timestamp(payload.get("source_window_start"))
    window_end = normalize_timestamp(payload.get("source_window_end"))
    if window_start >= window_end:
        raise HczLabelValidationError("证据窗口开始时间必须早于结束时间")
    if not window_start <= observed_at <= window_end:
        raise HczLabelValidationError("标注时刻必须位于证据窗口内")
    if window_end - window_start > timedelta(hours=72):
        raise HczLabelValidationError("单条标签的证据窗口不能超过72小时")
    supersedes = payload.get("supersedes_label_id")
    if supersedes in (None, ""):
        supersedes_label_id = None
    else:
        try:
            supersedes_label_id = int(supersedes)
        except (TypeError, ValueError) as exc:
            raise HczLabelValidationError("被修订标签ID无效") from exc
        if supersedes_label_id <= 0:
            raise HczLabelValidationError("被修订标签ID无效")
    return {
        "idempotency_key": idempotency_key,
        "furnace_id": "GL02",
        "observed_at": observed_at,
        "source_window_start": window_start,
        "source_window_end": window_end,
        "root_level_label": root_level,
        "movement_label": movement,
        "center_height_m": _optional_float(
            payload.get("center_height_m"),
            label="中心高度",
            minimum=10.0,
            maximum=35.0,
        ),
        "thickness_m": _optional_float(
            payload.get("thickness_m"),
            label="软熔带厚度",
            minimum=0.5,
            maximum=8.0,
        ),
        "eccentric_sector": eccentric,
        "confidence_grade": confidence_grade,
        "evidence_codes": evidence_codes,
        "note": note,
        "operator_name": operator_name,
        "source_page": str(payload.get("source_page") or "").strip()[:300],
        "supersedes_label_id": supersedes_label_id,
        "expected_source_data_hash": str(payload.get("source_data_hash") or "").strip(),
    }


def _canonical_records(frame: pd.DataFrame) -> list[list[Any]]:
    records: list[list[Any]] = []
    if frame.empty:
        return records
    ordered = frame.sort_index()
    for timestamp, row in ordered.iterrows():
        timestamp_text = pd.Timestamp(timestamp).isoformat()
        for column in sorted(ordered.columns):
            value = _finite(row.get(column))
            if value is not None:
                records.append([timestamp_text, str(column), round(value, 6)])
    return records


def build_source_context(
    frame: pd.DataFrame,
    *,
    observed_at: Any,
    window_start: Any,
    window_end: Any,
    primary_variables: Iterable[str],
    max_snapshot_age_minutes: int = 5,
) -> dict[str, Any]:
    """Bind a blind expert label to measured process data and knowledge times."""
    observed = normalize_timestamp(observed_at)
    start = normalize_timestamp(window_start)
    end = normalize_timestamp(window_end)
    if frame.empty:
        raise HczLabelValidationError("证据窗口没有可用实测数据")
    working = frame.copy().sort_index()
    index = pd.DatetimeIndex(pd.to_datetime(working.index))
    if index.tz is None:
        index = index.tz_localize(timezone(timedelta(hours=8)))
    else:
        index = index.tz_convert(timezone(timedelta(hours=8)))
    working.index = index
    bounded = working.loc[(working.index >= start) & (working.index <= end)].copy()
    if bounded.empty:
        raise HczLabelValidationError("证据窗口没有可用实测数据")
    records = _canonical_records(bounded)
    digest_payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    source_data_hash = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
    snapshot: dict[str, dict[str, Any]] = {}
    cutoff = bounded.loc[bounded.index <= observed]
    max_age = timedelta(minutes=max_snapshot_age_minutes)
    for column in sorted(bounded.columns):
        series = pd.to_numeric(cutoff[column], errors="coerce").dropna()
        if series.empty:
            continue
        sample_time = pd.Timestamp(series.index[-1]).to_pydatetime()
        age = observed - sample_time
        snapshot[str(column)] = {
            "value": round(float(series.iloc[-1]), 6) if age <= max_age else None,
            "sample_time": sample_time.isoformat(),
            "age_seconds": max(0, round(age.total_seconds())),
            "state": "fresh" if age <= max_age else "stale",
        }
    primary = tuple(dict.fromkeys(str(item) for item in primary_variables))
    primary_fresh = sum(
        1 for variable in primary if snapshot.get(variable, {}).get("state") == "fresh"
    )
    context_mode = (
        "retrospective_with_post_observation_evidence"
        if end > observed
        else "contemporaneous_blind"
    )
    return {
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "furnace_id": "GL02",
        "observed_at": observed.isoformat(),
        "source_window_start": start.isoformat(),
        "source_window_end": end.isoformat(),
        "context_mode": context_mode,
        "uses_post_observation_data": end > observed,
        "blind_to_model": True,
        "model_outputs_included": False,
        "source_data_hash": source_data_hash,
        "measurement_record_count": len(records),
        "primary_variable_count": len(primary),
        "primary_fresh_count": primary_fresh,
        "primary_coverage": round(primary_fresh / max(len(primary), 1), 6),
        "measured_snapshot": snapshot,
    }


def _serialize_row(columns: Sequence[str], row: Sequence[Any]) -> dict[str, Any]:
    item = dict(zip(columns, row))
    for key in (
        "observed_at",
        "available_at",
        "source_window_start",
        "source_window_end",
        "created_at",
    ):
        if item.get(key) is not None:
            item[key] = iso_timestamp(item[key])
    return item


class HczExpertLabelStore:
    """Append-only PostgreSQL store for blind expert weak labels."""

    def __init__(
        self,
        connect_factory: Callable[[], Any],
        *,
        schema: str = "bf_assistant",
        ddl_path: Optional[Path] = None,
    ):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise HczLabelConfigurationError("HCZ标签schema名称不安全")
        self.connect_factory = connect_factory
        self.schema = schema
        self.ddl_path = ddl_path or (
            Path(__file__).resolve().parent
            / "schema"
            / "postgresql_hcz_expert_label.sql"
        )

    @property
    def table_name(self) -> str:
        return f"{self.schema}.hcz_expert_label_events"

    def ensure_schema(self) -> None:
        if not self.ddl_path.is_file():
            raise HczLabelConfigurationError(f"HCZ标签DDL不存在：{self.ddl_path}")
        ddl = self.ddl_path.read_text(encoding="utf-8").replace("__SCHEMA__", self.schema)
        with self.connect_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(ddl)

    def save(
        self,
        label: Mapping[str, Any],
        source_context: Mapping[str, Any],
        identity: Mapping[str, Any],
        *,
        client_address: str = "",
    ) -> dict[str, Any]:
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise HczLabelConfigurationError("缺少psycopg JSON支持") from exc
        expected_hash = str(label.get("expected_source_data_hash") or "")
        actual_hash = str(source_context.get("source_data_hash") or "")
        if expected_hash and expected_hash != actual_hash:
            raise HczLabelValidationError("证据窗口数据已变化，请刷新后重新提交")
        reference_id = f"HCZ-{uuid4()}"
        sql = f"""
            INSERT INTO {self.table_name} (
                reference_id, idempotency_key, label_version, reference_type,
                furnace_id, observed_at, available_at, source_window_start,
                source_window_end, context_mode, blind_to_model,
                root_level_label, movement_label, center_height_m, thickness_m,
                eccentric_sector, confidence_grade, evidence_codes, note,
                operator_name, reviewer_username, reviewer_role, identity_mode,
                source_schema_version, source_data_hash, source_context,
                source_page, supersedes_label_id, client_address
            ) VALUES (
                %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, TRUE,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, reference_id, observed_at, available_at,
                      root_level_label, movement_label, center_height_m,
                      thickness_m, eccentric_sector, confidence_grade,
                      evidence_codes, note, operator_name, reviewer_username,
                      reviewer_role, identity_mode, context_mode,
                      blind_to_model, source_data_hash, supersedes_label_id,
                      created_at
        """
        values = (
            reference_id,
            label["idempotency_key"],
            LABEL_VERSION,
            REFERENCE_TYPE,
            label["furnace_id"],
            label["observed_at"],
            label["source_window_start"],
            label["source_window_end"],
            source_context["context_mode"],
            label["root_level_label"],
            label["movement_label"],
            label["center_height_m"],
            label["thickness_m"],
            label["eccentric_sector"],
            label["confidence_grade"],
            Jsonb(label["evidence_codes"]),
            label["note"],
            label["operator_name"],
            str(identity.get("sub") or ""),
            str(identity.get("role") or ""),
            str(identity.get("identity_mode") or ""),
            SOURCE_SCHEMA_VERSION,
            source_context["source_data_hash"],
            Jsonb(dict(source_context)),
            label["source_page"],
            label["supersedes_label_id"],
            str(client_address or "")[:100],
        )
        columns = (
            "id",
            "reference_id",
            "observed_at",
            "available_at",
            "root_level_label",
            "movement_label",
            "center_height_m",
            "thickness_m",
            "eccentric_sector",
            "confidence_grade",
            "evidence_codes",
            "note",
            "operator_name",
            "reviewer_username",
            "reviewer_role",
            "identity_mode",
            "context_mode",
            "blind_to_model",
            "source_data_hash",
            "supersedes_label_id",
            "created_at",
        )
        with self.connect_factory() as connection:
            with connection.cursor() as cursor:
                if label["supersedes_label_id"] is not None:
                    cursor.execute(
                        f"""
                        SELECT furnace_id, observed_at
                        FROM {self.table_name}
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (label["supersedes_label_id"],),
                    )
                    prior = cursor.fetchone()
                    if prior is None:
                        raise HczLabelValidationError("被修订标签不存在")
                    if prior[0] != label["furnace_id"] or normalize_timestamp(prior[1]) != normalize_timestamp(label["observed_at"]):
                        raise HczLabelValidationError("修订记录必须与原标签属于同一炉号和标注时刻")
                cursor.execute(sql, values)
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        f"""
                        SELECT {', '.join(columns)}
                        FROM {self.table_name}
                        WHERE idempotency_key = %s
                        LIMIT 1
                        """,
                        (label["idempotency_key"],),
                    )
                    row = cursor.fetchone()
        if row is None:
            raise HczLabelConfigurationError("HCZ标签写入后未能读取")
        return {**_serialize_row(columns, row), "created": created}

    def list_labels(
        self,
        *,
        start: Optional[Any] = None,
        end: Optional[Any] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 2000))
        clauses = ["furnace_id = 'GL02'"]
        params: list[Any] = []
        if start is not None:
            clauses.append("observed_at >= %s")
            params.append(normalize_timestamp(start))
        if end is not None:
            clauses.append("observed_at <= %s")
            params.append(normalize_timestamp(end))
        params.append(safe_limit)
        columns = (
            "id",
            "reference_id",
            "observed_at",
            "available_at",
            "root_level_label",
            "movement_label",
            "center_height_m",
            "thickness_m",
            "eccentric_sector",
            "confidence_grade",
            "evidence_codes",
            "note",
            "operator_name",
            "reviewer_username",
            "reviewer_role",
            "identity_mode",
            "context_mode",
            "blind_to_model",
            "source_data_hash",
            "supersedes_label_id",
            "created_at",
        )
        sql = f"""
            SELECT {', '.join(columns)}
            FROM {self.table_name}
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at DESC, created_at DESC
            LIMIT %s
        """
        with self.connect_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        return [_serialize_row(columns, row) for row in rows]
