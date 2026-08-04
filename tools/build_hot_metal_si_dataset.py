# -*- coding: utf-8 -*-
"""Build a time-aligned 2# blast-furnace sensor/diagnosis and hot-metal Si dataset.

Requirement:
    REQ-HOT-METAL-SI-DATASET-20260719

The program reads production PostgreSQL and IMES/Vastbase in read-only mode.
It writes only local CSV/JSON/Markdown artifacts.  IMES ``发布时间`` is a
result/judgement time rather than a confirmed sample/tapping timestamp, so the
feature cutoff is moved backwards by a configurable safety lag.

Documentation:
    docs/铁水硅炉况传感器数据集.md
"""
from __future__ import annotations

import argparse
import base64
import csv
import getpass
import hashlib
import json
import math
import os
import re
import select
import socketserver
import statistics
import sys
import threading
import time as time_module
import traceback
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import paramiko
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "AGENTS.md"
DEFAULT_IMES_ENV_FILE = ROOT / "PT" / "imes_vastbase.local.env"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "铁水硅炉况传感器数据集_20260719"
STATIC_PRESSURE_CATALOG_PATH = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "mcp"
    / "gl02_static_pressure_points.json"
)
IMES_VIEW = "public.v_qpes_inner_batch_insp_final_sample"
REQUIREMENT_ID = "REQ-HOT-METAL-SI-DATASET-20260719"
STATIC_PRESSURE_BUSINESS_LEVELS = {
    "lower": "炉身下部",
    "middle": "炉身中部",
    "upper": "炉身上部",
}
STATIC_PRESSURE_ORIENTATION_STATUS = "relative_only"
STATIC_PRESSURE_HMI_ID_STATUS = "unconfirmed_conflicting_records"
STATIC_PRESSURE_UNIT_STATUS = "configured_kpa_source_metadata_blank_unconfirmed"
DATA_DICTIONARY_COLUMNS = [
    "column",
    "data_type",
    "category",
    "source",
    "source_field",
    "semantic_id",
    "business_level_name",
    "height_m",
    "position",
    "orientation_status",
    "source_description_raw",
    "hmi_instrument_id",
    "hmi_instrument_id_status",
    "description",
    "unit",
    "unit_status",
]
DIAGNOSIS_DISPLAY = {
    "cold": "热制度下行",
    "hot": "热制度上行",
    "normal": "正常顺行",
    "edge": "边缘气流发展",
    "center": "中心气流发展",
    "column": "料柱阻力异常",
    "channel": "管道气流",
    "lowline": "料线偏低",
}
ALLOWED_IMES_ENV_KEYS = {
    "IMES_DB_HOST",
    "IMES_DB_PORT",
    "IMES_DB_NAME",
    "IMES_DB_USER",
    "IMES_DB_PASSWORD",
}
LABEL_COLUMNS = [
    "si_sample_id",
    "si_sample_no",
    "si_result_ts",
    "si_publish_date",
    "furnace_no",
    "hot_metal_tank_no",
    "shift_name",
    "hot_metal_c_pct",
    "hot_metal_si_pct",
    "hot_metal_mn_pct",
    "hot_metal_p_pct",
    "hot_metal_s_pct",
    "feature_lag_minutes",
    "feature_end_ts",
    "alignment_method",
]
DIAGNOSIS_COLUMNS = [
    "diagnosis__ts",
    "diagnosis__lag_seconds",
    "diagnosis__main_label_key",
    "diagnosis__main_label_display",
    "diagnosis__main_score",
    "diagnosis__main_confidence",
    "diagnosis__secondary_label_key",
    "diagnosis__secondary_label_display",
    "diagnosis__secondary_score",
    "diagnosis__secondary_confidence",
    "diagnosis__window_minutes",
    "diagnosis__source_lag_seconds",
    "diagnosis__coverage_ratio",
    "diagnosis__missing_variable_count",
    "sensor__available_count",
    "sensor__missing_count",
    "sensor__bad_quality_count",
    "sensor__unknown_quality_count",
    "sensor__max_age_seconds",
]


class ForwardServer(socketserver.ThreadingTCPServer):
    """Threaded loopback-only SSH forwarding server."""

    daemon_threads = True
    allow_reuse_address = True


class ForwardHandler(socketserver.BaseRequestHandler):
    """Relay one local PostgreSQL socket over the verified SSH transport."""

    ssh_transport: paramiko.Transport
    remote_host: str
    remote_port: int

    def handle(self) -> None:
        channel = self.ssh_transport.open_channel(
            "direct-tcpip",
            (self.remote_host, self.remote_port),
            self.request.getpeername(),
        )
        if channel is None:
            return
        try:
            while True:
                readable, _, _ = select.select([self.request, channel], [], [], 1.0)
                if self.request in readable:
                    payload = self.request.recv(16384)
                    if not payload:
                        break
                    channel.send(payload)
                if channel in readable:
                    payload = channel.recv(16384)
                    if not payload:
                        break
                    self.request.send(payload)
        finally:
            channel.close()
            self.request.close()


def read_agents_value(pattern: str) -> str | None:
    """Read an approved local-only operational value without logging it."""

    if not AGENTS_PATH.is_file():
        return None
    text = AGENTS_PATH.read_text(encoding="utf-8", errors="ignore")
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


@contextmanager
def sensor_ssh_tunnel(
    args: argparse.Namespace,
) -> Iterator[tuple[int, paramiko.SSHClient]]:
    """Open a loopback tunnel to the production PostgreSQL listener."""

    password = os.getenv("BF_22012_SSH_PASSWORD") or read_agents_value(
        r"SSH 密码：([^\r\n]+)"
    )
    if not password:
        password = getpass.getpass(
            f"SSH password for {args.ssh_user}@{args.ssh_host}: "
        )
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            client.connect(
                hostname=args.ssh_host,
                username=args.ssh_user,
                password=password,
                timeout=args.connect_timeout,
                banner_timeout=60,
                auth_timeout=30,
                look_for_keys=False,
                allow_agent=False,
            )
            last_error = None
            break
        except (TimeoutError, paramiko.SSHException) as exc:
            last_error = exc
            emit(
                "ssh_retry",
                attempt=attempt,
                error_type=type(exc).__name__,
            )
            client.close()
            if attempt < 3:
                time_module.sleep(attempt * 2)
    if last_error is not None:
        raise last_error
    transport = client.get_transport()
    if transport is None:
        client.close()
        raise RuntimeError("SSH transport was not opened")
    handler = type(
        "SensorForwardHandler",
        (ForwardHandler,),
        {
            "ssh_transport": transport,
            "remote_host": args.remote_pg_host,
            "remote_port": args.remote_pg_port,
        },
    )
    server = ForwardServer(("127.0.0.1", args.local_tunnel_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield args.local_tunnel_port, client
    finally:
        server.shutdown()
        server.server_close()
        client.close()


def fetch_remote_machine_env(
    client: paramiko.SSHClient, names: Sequence[str]
) -> dict[str, str]:
    """Read only approved PostgreSQL environment keys from the remote machine."""

    ps_names = "@(" + ",".join(
        "'" + name.replace("'", "''") + "'" for name in names
    ) + ")"
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        + f"$names={ps_names}; "
        + "$o=@{}; foreach($n in $names){"
        + "$o[$n]=[Environment]::GetEnvironmentVariable($n,'Machine')}; "
        + "$o | ConvertTo-Json -Compress"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    command = f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    for attempt in range(1, 3):
        try:
            _, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            status = stdout.channel.recv_exit_status()
            if status != 0:
                raise RuntimeError(
                    f"failed to read remote PostgreSQL environment: {error or output}"
                )
            payload = json.loads(output or "{}")
            return {key: str(value or "") for key, value in payload.items()}
        except TimeoutError:
            emit("remote_env_retry", attempt=attempt)
            if attempt < 2:
                time_module.sleep(2)
    raise TimeoutError("remote PostgreSQL environment query timed out")


def remote_sensor_params(
    args: argparse.Namespace,
    tunnel_port: int,
    client: paramiko.SSHClient,
) -> dict[str, Any]:
    """Build the production read connection without exposing credentials."""

    remote_env = fetch_remote_machine_env(
        client, ["GL02_PGUSER", "GL02_PGPASSWORD", "GL02_READER_PASSWORD"]
    )
    user = (
        os.getenv("GL02_REMOTE_PGUSER")
        or remote_env.get("GL02_PGUSER")
        or args.remote_pg_user
    )
    password = (
        os.getenv("GL02_REMOTE_PGPASSWORD")
        or remote_env.get("GL02_PGPASSWORD")
        or remote_env.get("GL02_READER_PASSWORD")
        or ""
    )
    if not password:
        raise RuntimeError("production PostgreSQL read password is unavailable")
    return {
        "host": "127.0.0.1",
        "port": tunnel_port,
        "dbname": args.remote_pg_db,
        "user": user,
        "password": password,
        "connect_timeout": args.connect_timeout,
    }


def emit(event: str, **payload: Any) -> None:
    """Print one structured progress event without credentials."""

    print(json.dumps({"event": event, **payload}, ensure_ascii=False, default=json_default), flush=True)


def json_default(value: Any) -> Any:
    """Serialize timestamps and paths used in manifests and progress logs."""

    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported JSON type: {type(value)!r}")


def chunks(values: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    """Yield deterministic fixed-size chunks."""

    if size <= 0:
        raise ValueError("chunk size must be positive")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def parse_numeric(value: Any) -> float | None:
    """Convert an IMES text result to a finite float; blanks/status text become null."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("%", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def parse_imes_timestamp(value: Any) -> datetime | None:
    """Parse the ISO-like timestamp text returned by the IMES view."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("/", "-")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def display_diagnosis_label(value: Any) -> str:
    """Map internal rule keys to production-safe Chinese display names."""

    key = str(value or "").strip()
    return DIAGNOSIS_DISPLAY.get(key, key)


def flatten_json(
    payload: Mapping[str, Any] | None,
    prefix: str,
    *,
    separator: str = "__",
) -> dict[str, Any]:
    """Flatten nested JSON objects into stable CSV columns."""

    result: dict[str, Any] = {}

    def visit(value: Any, path: list[str]) -> None:
        if isinstance(value, Mapping):
            for key in sorted(value, key=lambda item: str(item)):
                visit(value[key], [*path, str(key)])
            return
        if isinstance(value, list):
            result[separator.join([prefix, *path])] = json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            )
            return
        result[separator.join([prefix, *path])] = value

    for root_key in sorted(payload or {}, key=lambda item: str(item)):
        visit((payload or {})[root_key], [str(root_key)])
    return result


def load_env_file(path: Path) -> dict[str, str]:
    """Read the gitignored IMES credential file without logging secret values."""

    if not path.is_file():
        raise FileNotFoundError(f"IMES environment file not found: {path}")
    values: dict[str, str] = {}
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw_line.strip()
        if not text or text.startswith("#"):
            continue
        if "=" not in text:
            raise ValueError(f"invalid IMES environment entry at line {line_no}")
        key, value = text.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_IMES_ENV_KEYS:
            raise ValueError(f"unsupported IMES environment key: {key}")
        values[key] = value
    return values


def imes_connection_info(args: argparse.Namespace) -> dict[str, Any]:
    """Build a read-only Vastbase connection from process env/local ignored config."""

    file_values = load_env_file(args.imes_env_file)

    def setting(name: str, default: str = "") -> str:
        return str(os.getenv(name) or file_values.get(name) or default)

    password = setting("IMES_DB_PASSWORD")
    user = setting("IMES_DB_USER")
    if not user or not password:
        raise RuntimeError("IMES_DB_USER/IMES_DB_PASSWORD are required")
    return {
        "host": args.imes_host or setting("IMES_DB_HOST", "127.0.0.1"),
        "port": int(args.imes_port or setting("IMES_DB_PORT", "15433")),
        "dbname": setting("IMES_DB_NAME", "vastbase"),
        "user": user,
        "password": password,
        "connect_timeout": args.connect_timeout,
        "options": f"-c default_transaction_read_only=on -c statement_timeout={args.statement_timeout_ms}",
    }


def sensor_bounds(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Return production history bounds without scanning the 19M-row table."""

    row = conn.execute(
        """
        SELECT
            (SELECT ts
             FROM bf_sensor.one_minute_values
             ORDER BY ts ASC
             LIMIT 1) AS min_ts,
            (SELECT ts
             FROM bf_sensor.one_minute_values
             ORDER BY ts DESC
             LIMIT 1) AS max_ts
        """
    ).fetchone()
    return dict(row or {})


def fetch_registry(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    """Read the enabled point dictionary used for stable sensor column names."""

    rows = conn.execute(
        """
        SELECT variable_name, chinese_name, branch, short_name, tag_long_name,
               description, status_usage, is_derived, is_enabled
        FROM bf_sensor.sensor_registry
        WHERE is_enabled
        ORDER BY short_name, tag_long_name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def requested_label_range(
    args: argparse.Namespace,
    min_sensor_ts: datetime,
    max_sensor_ts: datetime,
) -> tuple[datetime, datetime]:
    """Intersect requested business dates with the available sensor history."""

    earliest = min_sensor_ts + timedelta(minutes=args.feature_lag_minutes)
    latest_exclusive = max_sensor_ts + timedelta(seconds=1)
    if args.start_date:
        earliest = max(earliest, datetime.combine(args.start_date, time.min))
    if args.end_date:
        latest_exclusive = min(
            latest_exclusive,
            datetime.combine(args.end_date + timedelta(days=1), time.min),
        )
    if earliest >= latest_exclusive:
        raise RuntimeError("requested dates do not overlap available sensor history")
    return earliest, latest_exclusive


def fetch_imes_labels(
    conn: psycopg.Connection[Any],
    furnace_no: str,
    start_ts: datetime,
    end_ts: datetime,
    feature_lag_minutes: int,
    max_labels: int | None,
) -> list[dict[str, Any]]:
    """Read and normalize 2# hot-metal chemistry labels from the granted view."""

    sql = f"""
        SELECT id,
               "试样号" AS sample_no,
               "发布时间" AS result_ts,
               "发布日期" AS publish_date,
               "高炉" AS furnace_no,
               "罐号" AS tank_no,
               "班次" AS shift_name,
               cvalue, sivalue, mnvalue, pvalue, svalue
        FROM {IMES_VIEW}
        WHERE "高炉" = %s
          AND "发布时间" >= %s
          AND "发布时间" < %s
        ORDER BY "发布时间", id
    """
    raw_rows = conn.execute(
        sql,
        (
            furnace_no,
            start_ts.strftime("%Y-%m-%d %H:%M:%S"),
            end_ts.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchall()
    labels: list[dict[str, Any]] = []
    invalid_ts = 0
    invalid_si = 0
    for raw in raw_rows:
        row = dict(raw)
        result_ts = parse_imes_timestamp(row["result_ts"])
        silicon = parse_numeric(row["sivalue"])
        if result_ts is None:
            invalid_ts += 1
            continue
        if silicon is None:
            invalid_si += 1
            continue
        labels.append(
            {
                "si_sample_id": str(row["id"]),
                "si_sample_no": str(row["sample_no"] or ""),
                "si_result_ts": result_ts,
                "si_publish_date": str(row["publish_date"] or ""),
                "furnace_no": str(row["furnace_no"] or ""),
                "hot_metal_tank_no": str(row["tank_no"] or ""),
                "shift_name": str(row["shift_name"] or ""),
                "hot_metal_c_pct": parse_numeric(row["cvalue"]),
                "hot_metal_si_pct": silicon,
                "hot_metal_mn_pct": parse_numeric(row["mnvalue"]),
                "hot_metal_p_pct": parse_numeric(row["pvalue"]),
                "hot_metal_s_pct": parse_numeric(row["svalue"]),
                "feature_lag_minutes": feature_lag_minutes,
                "feature_end_ts": result_ts - timedelta(minutes=feature_lag_minutes),
                "alignment_method": "imes_result_ts_minus_fixed_safety_lag",
            }
        )
    if max_labels is not None:
        labels = labels[-max_labels:]
    emit(
        "labels_loaded",
        raw_rows=len(raw_rows),
        usable_rows=len(labels),
        invalid_timestamp_rows=invalid_ts,
        invalid_si_rows=invalid_si,
    )
    return labels


def fetch_diagnosis_matches(
    conn: psycopg.Connection[Any],
    labels: Sequence[Mapping[str, Any]],
    max_lag_minutes: int,
    chunk_size: int,
) -> dict[str, dict[str, Any]]:
    """Find the latest versioned diagnosis at or before each feature cutoff."""

    matches: dict[str, dict[str, Any]] = {}
    label_chunks = list(chunks(list(labels), chunk_size))
    for chunk_no, label_chunk in enumerate(label_chunks, 1):
        value_sql = ",".join(["(%s::text,%s::timestamp)"] * len(label_chunk))
        params: list[Any] = []
        for label in label_chunk:
            params.extend([label["si_sample_id"], label["feature_end_ts"]])
        params.append(max_lag_minutes)
        sql = f"""
            WITH labels(label_id, feature_end_ts) AS (
                VALUES {value_sql}
            )
            SELECT labels.label_id,
                   labels.feature_end_ts,
                   d.id,
                   d.diagnosis_ts,
                   d.diagnosis_window_start,
                   d.diagnosis_window_end,
                   d.window_minutes,
                   d.source_lag_seconds,
                   d.main_label,
                   d.main_score,
                   d.main_confidence,
                   d.secondary_label,
                   d.secondary_score,
                   d.secondary_confidence,
                   d.data_coverage,
                   d.missing_variables,
                   d.raw_scores,
                   d.feature_snapshot,
                   d.updated_at
            FROM labels
            LEFT JOIN LATERAL (
                SELECT *
                FROM bf_sensor.diagnosis_snapshots AS candidate
                WHERE candidate.diagnosis_ts <= labels.feature_end_ts
                  AND candidate.diagnosis_ts >=
                      labels.feature_end_ts - (%s * interval '1 minute')
                ORDER BY candidate.diagnosis_ts DESC,
                         candidate.updated_at DESC,
                         candidate.id DESC
                LIMIT 1
            ) AS d ON TRUE
        """
        for row in conn.execute(sql, params).fetchall():
            matches[str(row["label_id"])] = dict(row)
        emit(
            "diagnosis_progress",
            chunk=chunk_no,
            chunks=len(label_chunks),
            labels_processed=min(chunk_no * chunk_size, len(labels)),
        )
    return matches


def fetch_sensor_snapshots(
    conn: psycopg.Connection[Any],
    diagnosis_timestamps: Sequence[datetime],
    max_lag_minutes: int,
    chunk_size: int,
) -> dict[datetime, dict[str, dict[str, Any]]]:
    """Read each point's latest value at or before matched diagnosis timestamps."""

    snapshots: dict[datetime, dict[str, dict[str, Any]]] = defaultdict(dict)
    timestamp_chunks = list(chunks(list(diagnosis_timestamps), chunk_size))
    for chunk_no, timestamp_chunk in enumerate(timestamp_chunks, 1):
        value_sql = ",".join(["(%s::timestamp)"] * len(timestamp_chunk))
        rows = conn.execute(
            f"""
            WITH targets(target_ts) AS (
                VALUES {value_sql}
            )
            SELECT targets.target_ts,
                   r.short_name,
                   r.tag_long_name,
                   observed.ts AS observed_ts,
                   observed.value,
                   observed.quality
            FROM targets
            CROSS JOIN bf_sensor.sensor_registry AS r
            LEFT JOIN LATERAL (
                SELECT v.ts, v.value, v.quality
                FROM bf_sensor.one_minute_values AS v
                WHERE v.tag_long_name = r.tag_long_name
                  AND v.ts <= targets.target_ts
                  AND v.ts >= targets.target_ts - (%s * interval '1 minute')
                ORDER BY v.ts DESC
                LIMIT 1
            ) AS observed ON TRUE
            WHERE r.is_enabled
            ORDER BY targets.target_ts, r.short_name
            """,
            [*timestamp_chunk, max_lag_minutes],
        ).fetchall()
        quality_counts: Counter[str] = Counter()
        for row in rows:
            if row["observed_ts"] is None:
                continue
            quality_text = str(row["quality"] or "")
            quality_counts[quality_text] += 1
            snapshots[row["target_ts"]][str(row["short_name"])] = {
                "value": row["value"],
                "quality": row["quality"],
                "tag_long_name": row["tag_long_name"],
                "observed_ts": row["observed_ts"],
                "age_seconds": int(
                    (row["target_ts"] - row["observed_ts"]).total_seconds()
                ),
            }
        emit(
            "sensor_progress",
            chunk=chunk_no,
            chunks=len(timestamp_chunks),
            timestamps_processed=min(chunk_no * chunk_size, len(diagnosis_timestamps)),
            rows_loaded=len(rows),
            quality_counts=dict(quality_counts),
        )
    return snapshots


def is_good_quality(value: Any) -> bool:
    """Normalize the quality encodings observed in PostgreSQL."""

    text = str(value or "").strip().lower()
    return text in {"good", "0", "192"}


def classify_quality(value: Any) -> str:
    """Classify blank PostgreSQL quality separately from explicit bad quality."""

    text = str(value or "").strip()
    if not text:
        return "unknown"
    return "good" if is_good_quality(text) else "bad"


def value_is_numeric(value: Any) -> bool:
    """Return whether a non-null flattened value is suitable for numeric CSV."""

    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return parse_numeric(value) is not None


def make_dataset_rows(
    labels: Sequence[Mapping[str, Any]],
    diagnoses: Mapping[str, Mapping[str, Any]],
    sensor_snapshots: Mapping[datetime, Mapping[str, Mapping[str, Any]]],
    registry: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Compose one wide row per Si sample without using data after the cutoff."""

    sensor_names = [str(row["short_name"]) for row in registry]
    rows: list[dict[str, Any]] = []
    dynamic_columns: set[str] = set()
    for label in labels:
        row = dict(label)
        label_id = str(label["si_sample_id"])
        diagnosis = diagnoses.get(label_id) or {}
        diagnosis_ts = diagnosis.get("diagnosis_ts")
        feature_end_ts = label["feature_end_ts"]
        coverage = diagnosis.get("data_coverage")
        missing_variables = diagnosis.get("missing_variables")
        row.update(
            {
                "diagnosis__ts": diagnosis_ts,
                "diagnosis__lag_seconds": (
                    int((feature_end_ts - diagnosis_ts).total_seconds())
                    if isinstance(diagnosis_ts, datetime)
                    else None
                ),
                "diagnosis__main_label_key": diagnosis.get("main_label"),
                "diagnosis__main_label_display": display_diagnosis_label(
                    diagnosis.get("main_label")
                ),
                "diagnosis__main_score": diagnosis.get("main_score"),
                "diagnosis__main_confidence": diagnosis.get("main_confidence"),
                "diagnosis__secondary_label_key": diagnosis.get("secondary_label"),
                "diagnosis__secondary_label_display": display_diagnosis_label(
                    diagnosis.get("secondary_label")
                ),
                "diagnosis__secondary_score": diagnosis.get("secondary_score"),
                "diagnosis__secondary_confidence": diagnosis.get("secondary_confidence"),
                "diagnosis__window_minutes": diagnosis.get("window_minutes"),
                "diagnosis__source_lag_seconds": diagnosis.get("source_lag_seconds"),
                "diagnosis__coverage_ratio": (
                    coverage.get("coverage_ratio")
                    if isinstance(coverage, Mapping)
                    else None
                ),
                "diagnosis__missing_variable_count": (
                    len(missing_variables)
                    if isinstance(missing_variables, (Mapping, list))
                    else None
                ),
            }
        )
        flattened_scores = flatten_json(diagnosis.get("raw_scores"), "score")
        flattened_features = flatten_json(diagnosis.get("feature_snapshot"), "feature")
        row.update(flattened_scores)
        row.update(flattened_features)
        dynamic_columns.update(flattened_scores)
        dynamic_columns.update(flattened_features)

        snapshot = sensor_snapshots.get(diagnosis_ts, {}) if diagnosis_ts else {}
        available_count = 0
        bad_quality_count = 0
        unknown_quality_count = 0
        sensor_ages: list[int] = []
        for sensor_name in sensor_names:
            observation = snapshot.get(sensor_name)
            column = f"sensor__{sensor_name}"
            if observation is None:
                row[column] = None
                continue
            row[column] = observation.get("value")
            available_count += 1
            sensor_ages.append(int(observation.get("age_seconds") or 0))
            quality_state = classify_quality(observation.get("quality"))
            if quality_state == "bad":
                bad_quality_count += 1
            elif quality_state == "unknown":
                unknown_quality_count += 1
        row["sensor__available_count"] = available_count
        row["sensor__missing_count"] = len(sensor_names) - available_count
        row["sensor__bad_quality_count"] = bad_quality_count
        row["sensor__unknown_quality_count"] = unknown_quality_count
        row["sensor__max_age_seconds"] = max(sensor_ages) if sensor_ages else None
        rows.append(row)

    score_columns = sorted(column for column in dynamic_columns if column.startswith("score__"))
    feature_columns = sorted(
        column for column in dynamic_columns if column.startswith("feature__")
    )
    sensor_columns = [f"sensor__{name}" for name in sensor_names]
    full_columns = LABEL_COLUMNS + DIAGNOSIS_COLUMNS + score_columns + feature_columns + sensor_columns

    numeric_dynamic_columns = [
        column
        for column in score_columns + feature_columns + sensor_columns
        if all(value_is_numeric(row.get(column)) for row in rows)
    ]
    numeric_columns = (
        LABEL_COLUMNS
        + [
            column
            for column in DIAGNOSIS_COLUMNS
            if column
            not in {
                "diagnosis__main_label_key",
                "diagnosis__main_label_display",
                "diagnosis__secondary_label_key",
                "diagnosis__secondary_label_display",
            }
        ]
        + numeric_dynamic_columns
    )
    return rows, full_columns, numeric_columns


def csv_value(value: Any) -> Any:
    """Convert structured values to stable CSV cells."""

    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (Mapping, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else value


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> int:
    """Write a UTF-8 BOM CSV atomically and return the row count."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    row_count = 0
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_value(row.get(column)) for column in columns})
            row_count += 1
    temporary.replace(path)
    return row_count


def column_type(rows: Sequence[Mapping[str, Any]], column: str) -> str:
    """Infer a concise data-dictionary type from observed non-null values."""

    values = [row.get(column) for row in rows if row.get(column) not in (None, "")]
    if not values:
        return "empty"
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, (int, float, bool)) for value in values):
        return "number"
    if all(isinstance(value, (datetime, date)) for value in values):
        return "datetime"
    return "text"


def load_static_pressure_dictionary_metadata(
    path: Path = STATIC_PRESSURE_CATALOG_PATH,
) -> dict[str, dict[str, Any]]:
    """Build non-authoritative dictionary annotations from the local 18-point catalog.

    The EQ/SI0 tag and raw source description remain the source identity.  Business
    level names are display semantics, while A-F orientation, HMI PE identifiers and
    the configured kPa unit retain explicit confirmation status.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    hmi_groups = payload.get("hmi_instrument_mapping") or {}
    dataset_description = payload.get("dataset_description") or {}
    business_levels_by_height = (
        dataset_description.get("business_level_by_height_m") or {}
    )
    orientation_status = str(
        dataset_description.get("orientation_status")
        or STATIC_PRESSURE_ORIENTATION_STATUS
    )
    hmi_id_status = str(
        dataset_description.get("hmi_instrument_id_status")
        or STATIC_PRESSURE_HMI_ID_STATUS
    )
    unit_status = str(
        dataset_description.get("unit_status") or STATIC_PRESSURE_UNIT_STATUS
    )
    metadata: dict[str, dict[str, Any]] = {}
    for item in payload.get("variables") or []:
        variable_name = str(item.get("variable_name") or "")
        match = re.fullmatch(
            r"P_static_(lower|middle|upper)_([A-F])", variable_name
        )
        if match is None:
            continue
        height_group, position = match.groups()
        hmi_group = str(
            hmi_groups.get(f"P_static_{height_group}_A-F") or ""
        )
        hmi_instrument_id = (
            hmi_group.replace("A-F", position) if "A-F" in hmi_group else ""
        )
        height_m = item.get("height_m")
        try:
            height_key = f"{float(height_m):.3f}"
        except (TypeError, ValueError):
            height_key = ""
        metadata[variable_name] = {
            "semantic_id": variable_name,
            "business_level_name": str(
                business_levels_by_height.get(height_key)
                or STATIC_PRESSURE_BUSINESS_LEVELS[height_group]
            ),
            "height_m": height_m,
            "position": position,
            "orientation_status": orientation_status,
            "source_description_raw": str(item.get("description") or ""),
            "hmi_instrument_id": hmi_instrument_id,
            "hmi_instrument_id_status": hmi_id_status,
            "unit": str(item.get("unit") or ""),
            "unit_status": unit_status,
        }
    return metadata


def build_dictionary_rows(
    rows: Sequence[Mapping[str, Any]],
    full_columns: Sequence[str],
    registry: Sequence[Mapping[str, Any]],
    static_pressure_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Create a source-aware field dictionary for every output column."""

    if static_pressure_metadata is None:
        static_pressure_metadata = load_static_pressure_dictionary_metadata()
    registry_by_column = {
        f"sensor__{item['short_name']}": item for item in registry
    }
    label_descriptions = {
        "si_sample_id": "IMES 化验记录主键，仅用于样本追踪。",
        "si_sample_no": "IMES 铁水试样号。",
        "si_result_ts": "IMES 结果判定/审核完成时间；不是已确认取样或出铁时间。",
        "si_publish_date": "IMES 发布日期。",
        "furnace_no": "高炉编号，本数据集固定为 2。",
        "hot_metal_tank_no": "铁水罐号；可能为空。",
        "shift_name": "IMES 班次。",
        "hot_metal_c_pct": "铁水 C，当前按质量百分含量解释。",
        "hot_metal_si_pct": "监督学习标签：铁水 Si，当前按质量百分含量解释。",
        "hot_metal_mn_pct": "铁水 Mn，当前按质量百分含量解释。",
        "hot_metal_p_pct": "铁水 P，当前按质量百分含量解释。",
        "hot_metal_s_pct": "铁水 S，当前按质量百分含量解释。",
        "feature_lag_minutes": "从 IMES 结果时间向前退让的安全滞后分钟数。",
        "feature_end_ts": "所有炉况/传感器特征允许使用的最晚时刻。",
        "alignment_method": "标签与特征的时间对齐方法。",
    }
    dictionary_rows: list[dict[str, Any]] = []
    for column in full_columns:
        extension: Mapping[str, Any] = {}
        if column in label_descriptions:
            source = IMES_VIEW
            source_field = column
            category = "label_or_identifier"
            description = label_descriptions[column]
        elif column.startswith("sensor__") and column in registry_by_column:
            meta = registry_by_column[column]
            variable_name = str(meta.get("variable_name") or "")
            extension = static_pressure_metadata.get(variable_name, {})
            source = "bf_sensor.one_minute_values"
            source_field = str(meta.get("tag_long_name") or "")
            category = str(meta.get("branch") or "sensor")
            description = "；".join(
                part
                for part in [
                    str(meta.get("chinese_name") or ""),
                    str(meta.get("description") or ""),
                ]
                if part
            )
        elif column.startswith("feature__"):
            source = "bf_sensor.diagnosis_snapshots.feature_snapshot"
            source_field = column.removeprefix("feature__")
            category = "diagnosis_feature"
            description = "炉况规则引擎保存的时点特征；算法版本随快照保留。"
        elif column.startswith("score__"):
            source = "bf_sensor.diagnosis_snapshots.raw_scores"
            source_field = column.removeprefix("score__")
            category = "diagnosis_score"
            description = "8 种炉况内部评分；展示名称不改变数据库键。"
        else:
            source = "bf_sensor.diagnosis_snapshots"
            source_field = column.removeprefix("diagnosis__")
            category = "diagnosis"
            description = "与特征截止时刻匹配的最近炉况快照字段。"
        dictionary_rows.append(
            {
                "column": column,
                "data_type": column_type(rows, column),
                "category": category,
                "source": source,
                "source_field": source_field,
                "semantic_id": extension.get("semantic_id", ""),
                "business_level_name": extension.get("business_level_name", ""),
                "height_m": extension.get("height_m", ""),
                "position": extension.get("position", ""),
                "orientation_status": extension.get("orientation_status", ""),
                "source_description_raw": extension.get(
                    "source_description_raw", ""
                ),
                "hmi_instrument_id": extension.get("hmi_instrument_id", ""),
                "hmi_instrument_id_status": extension.get(
                    "hmi_instrument_id_status", ""
                ),
                "description": description,
                "unit": extension.get("unit", "")
                or (
                    "%"
                    if column.startswith("hot_metal_") and column.endswith("_pct")
                    else ""
                ),
                "unit_status": extension.get("unit_status", ""),
            }
        )
    return dictionary_rows


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Return a deterministic linear-interpolation percentile."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def sha256_file(path: Path) -> str:
    """Hash one local artifact for reproducibility."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    args: argparse.Namespace,
    rows: Sequence[Mapping[str, Any]],
    training_rows: Sequence[Mapping[str, Any]],
    full_columns: Sequence[str],
    numeric_columns: Sequence[str],
    registry: Sequence[Mapping[str, Any]],
    sensor_meta: Mapping[str, Any],
    artifacts: Sequence[Path],
) -> dict[str, Any]:
    """Build the auditable dataset manifest and quality summary."""

    silicon = [float(row["hot_metal_si_pct"]) for row in rows]
    matched = [row for row in rows if row.get("diagnosis__ts")]
    sensor_cells = len(rows) * len(registry)
    missing_sensor_cells = sum(int(row.get("sensor__missing_count") or 0) for row in rows)
    bad_sensor_cells = sum(int(row.get("sensor__bad_quality_count") or 0) for row in rows)
    unknown_quality_cells = sum(
        int(row.get("sensor__unknown_quality_count") or 0) for row in rows
    )
    manifest = {
        "requirement_id": REQUIREMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "read_only_sources": True,
        "writes_production": False,
        "source_contract": {
            "sensor": "220.12 bf_trend.bf_sensor",
            "imes": IMES_VIEW,
            "sensor_history": sensor_meta,
            "enabled_registry_points": len(registry),
        },
        "alignment": {
            "method": "imes_result_ts_minus_fixed_safety_lag",
            "feature_lag_minutes": args.feature_lag_minutes,
            "max_diagnosis_lag_minutes": args.max_diagnosis_lag_minutes,
            "max_sensor_lag_minutes": args.max_sensor_lag_minutes,
            "warning": (
                "IMES 发布时间映射结果判定/审核完成时间，不是已确认取样或出铁时间；"
                "本数据集为代理时间对齐 v1，取得 meltNo/takesampletime 后必须重建。"
            ),
        },
        "shape": {
            "rows": len(rows),
            "full_columns": len(full_columns),
            "numeric_columns": len(numeric_columns),
            "sensor_columns": len(registry),
            "diagnosis_matched_rows": len(matched),
            "diagnosis_unmatched_rows": len(rows) - len(matched),
            "training_ready_rows": len(training_rows),
            "training_ready_rule": (
                f"diagnosis matched and sensor__available_count >= "
                f"{args.min_training_sensors}"
            ),
        },
        "time_range": {
            "si_result_min": min(row["si_result_ts"] for row in rows),
            "si_result_max": max(row["si_result_ts"] for row in rows),
            "feature_end_min": min(row["feature_end_ts"] for row in rows),
            "feature_end_max": max(row["feature_end_ts"] for row in rows),
        },
        "silicon_pct": {
            "count": len(silicon),
            "min": min(silicon),
            "p05": percentile(silicon, 0.05),
            "median": statistics.median(silicon),
            "mean": statistics.fmean(silicon),
            "p95": percentile(silicon, 0.95),
            "max": max(silicon),
            "std": statistics.pstdev(silicon) if len(silicon) > 1 else 0.0,
        },
        "quality": {
            "diagnosis_match_ratio": len(matched) / len(rows),
            "sensor_cell_count": sensor_cells,
            "sensor_missing_cells": missing_sensor_cells,
            "sensor_missing_ratio": (
                missing_sensor_cells / sensor_cells if sensor_cells else None
            ),
            "sensor_bad_quality_cells": bad_sensor_cells,
            "sensor_bad_quality_ratio": (
                bad_sensor_cells / sensor_cells if sensor_cells else None
            ),
            "sensor_unknown_quality_cells": unknown_quality_cells,
            "sensor_unknown_quality_ratio": (
                unknown_quality_cells / sensor_cells if sensor_cells else None
            ),
        },
        "artifacts": {},
    }
    for artifact in artifacts:
        manifest["artifacts"][artifact.name] = {
            "bytes": artifact.stat().st_size,
            "sha256": sha256_file(artifact),
        }
    return manifest


def write_quality_report(path: Path, manifest: Mapping[str, Any]) -> None:
    """Write a concise human-readable quality and leakage-boundary report."""

    shape = manifest["shape"]
    time_range = manifest["time_range"]
    silicon = manifest["silicon_pct"]
    quality = manifest["quality"]
    lines = [
        "# 铁水硅—炉况—传感器数据集质量报告",
        "",
        f"- 需求编号：`{REQUIREMENT_ID}`",
        f"- 样本数：{shape['rows']}",
        f"- 完整字段数：{shape['full_columns']}",
        f"- 数值版字段数：{shape['numeric_columns']}",
        f"- 传感器字段数：{shape['sensor_columns']}",
        (
            f"- 严格训练版样本数：{shape['training_ready_rows']} "
            f"（{shape['training_ready_rule']}）"
        ),
        (
            f"- Si 结果时间：{time_range['si_result_min']} ～ "
            f"{time_range['si_result_max']}"
        ),
        (
            f"- 特征截止时间：{time_range['feature_end_min']} ～ "
            f"{time_range['feature_end_max']}"
        ),
        (
            f"- 炉况匹配：{shape['diagnosis_matched_rows']}/{shape['rows']} "
            f"（{quality['diagnosis_match_ratio']:.2%}）"
        ),
        (
            f"- 传感器缺失单元格：{quality['sensor_missing_cells']}/"
            f"{quality['sensor_cell_count']}（{quality['sensor_missing_ratio']:.2%}）"
        ),
        (
            f"- 非 Good 传感器单元格：{quality['sensor_bad_quality_cells']}/"
            f"{quality['sensor_cell_count']}（{quality['sensor_bad_quality_ratio']:.2%}）"
        ),
        (
            f"- 未记录质量码的传感器单元格：{quality['sensor_unknown_quality_cells']}/"
            f"{quality['sensor_cell_count']}（{quality['sensor_unknown_quality_ratio']:.2%}）"
        ),
        (
            f"- Si（%）：min={silicon['min']:.4f}，P05={silicon['p05']:.4f}，"
            f"median={silicon['median']:.4f}，mean={silicon['mean']:.4f}，"
            f"P95={silicon['p95']:.4f}，max={silicon['max']:.4f}"
        ),
        "",
        "## 时间对齐边界",
        "",
        (
            f"所有炉况和传感器特征截止到 IMES 结果时间前 "
            f"{manifest['alignment']['feature_lag_minutes']} 分钟；"
            "程序不会读取截止时刻之后的数据。"
        ),
        "",
        manifest["alignment"]["warning"],
        "",
        "该版本可用于探索性分析、基线建模和对齐验证；在取得稳定的 "
        "`meltNo/heatno → batchno → takesampletime` 关联前，不得标为生产 Si 预测金标准。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    """Create the documented command-line interface."""

    cli = argparse.ArgumentParser(
        description=(
            "只读连接 220.12 PostgreSQL 与 IMES Vastbase，构建 2# 高炉炉况/"
            "传感器和铁水 Si 的时间对齐数据集。"
        )
    )
    cli.add_argument("--start-date", type=date.fromisoformat, help="标签起始业务日 YYYY-MM-DD")
    cli.add_argument("--end-date", type=date.fromisoformat, help="标签结束业务日 YYYY-MM-DD（含）")
    cli.add_argument("--furnace-no", default="2")
    cli.add_argument(
        "--feature-lag-minutes",
        type=int,
        default=120,
        help="IMES 结果时间向前退让的特征安全滞后，默认 120 分钟",
    )
    cli.add_argument(
        "--max-diagnosis-lag-minutes",
        type=int,
        default=15,
        help="特征截止时刻向前匹配炉况快照的最大间隔，默认 15 分钟",
    )
    cli.add_argument(
        "--max-sensor-lag-minutes",
        type=int,
        default=10,
        help="每个点向前取最近值的最大间隔，默认 10 分钟",
    )
    cli.add_argument(
        "--min-training-sensors",
        type=int,
        default=115,
        help="严格训练版每条样本至少需要的传感器数，默认 115",
    )
    cli.add_argument("--max-labels", type=int, help="仅保留最近 N 个标签，用于冒烟验证")
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    cli.add_argument("--imes-env-file", type=Path, default=DEFAULT_IMES_ENV_FILE)
    cli.add_argument("--imes-host", default="127.0.0.1")
    cli.add_argument("--imes-port", type=int, default=15433)
    cli.add_argument("--connect-timeout", type=int, default=20)
    cli.add_argument("--statement-timeout-ms", type=int, default=180000)
    cli.add_argument("--diagnosis-chunk-size", type=int, default=120)
    cli.add_argument("--sensor-chunk-size", type=int, default=250)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15434)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    return cli


def validate_args(args: argparse.Namespace) -> None:
    """Reject ambiguous or unsafe CLI combinations before connecting."""

    if args.start_date and args.end_date and args.start_date > args.end_date:
        raise ValueError("--start-date must not be later than --end-date")
    if args.feature_lag_minutes < 0:
        raise ValueError("--feature-lag-minutes must be non-negative")
    if args.max_diagnosis_lag_minutes <= 0:
        raise ValueError("--max-diagnosis-lag-minutes must be positive")
    if args.max_sensor_lag_minutes <= 0:
        raise ValueError("--max-sensor-lag-minutes must be positive")
    if args.min_training_sensors <= 0:
        raise ValueError("--min-training-sensors must be positive")
    if args.max_labels is not None and args.max_labels <= 0:
        raise ValueError("--max-labels must be positive")


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the read-only extraction, alignment, validation, and local export."""

    validate_args(args)
    args.output_dir = args.output_dir.resolve()
    args.imes_env_file = args.imes_env_file.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    emit(
        "start",
        requirement_id=REQUIREMENT_ID,
        output_dir=args.output_dir,
        feature_lag_minutes=args.feature_lag_minutes,
    )

    emit("stage", name="open_sensor_ssh_tunnel")
    with sensor_ssh_tunnel(args) as (sensor_port, ssh_client):
        emit("stage", name="sensor_ssh_tunnel_ready")
        sensor_info = remote_sensor_params(args, sensor_port, ssh_client)
        sensor_info["options"] = (
            f"-c default_transaction_read_only=on "
            f"-c statement_timeout={args.statement_timeout_ms}"
        )
        imes_info = imes_connection_info(args)
        emit("stage", name="open_read_only_databases")
        with (
            psycopg.connect(**sensor_info, row_factory=dict_row) as sensor_conn,
            psycopg.connect(**imes_info, row_factory=dict_row) as imes_conn,
        ):
            emit("stage", name="read_only_databases_ready")
            sensor_conn.execute("SET default_transaction_read_only = on")
            imes_conn.execute("SET default_transaction_read_only = on")
            sensor_meta = sensor_bounds(sensor_conn)
            registry = fetch_registry(sensor_conn)
            min_sensor_ts = sensor_meta.get("min_ts")
            max_sensor_ts = sensor_meta.get("max_ts")
            if not isinstance(min_sensor_ts, datetime) or not isinstance(
                max_sensor_ts, datetime
            ):
                raise RuntimeError("sensor history is empty")
            start_ts, end_ts = requested_label_range(
                args, min_sensor_ts, max_sensor_ts
            )
            emit(
                "source_ready",
                sensor_min_ts=min_sensor_ts,
                sensor_max_ts=max_sensor_ts,
                enabled_registry_points=len(registry),
                label_start_ts=start_ts,
                label_end_exclusive=end_ts,
            )
            labels = fetch_imes_labels(
                imes_conn,
                args.furnace_no,
                start_ts,
                end_ts,
                args.feature_lag_minutes,
                args.max_labels,
            )
            if not labels:
                raise RuntimeError("no usable hot-metal Si labels in the requested range")
            diagnoses = fetch_diagnosis_matches(
                sensor_conn,
                labels,
                args.max_diagnosis_lag_minutes,
                args.diagnosis_chunk_size,
            )
            diagnosis_timestamps = sorted(
                {
                    row["diagnosis_ts"]
                    for row in diagnoses.values()
                    if isinstance(row.get("diagnosis_ts"), datetime)
                }
            )
            snapshots = fetch_sensor_snapshots(
                sensor_conn,
                diagnosis_timestamps,
                args.max_sensor_lag_minutes,
                args.sensor_chunk_size,
            )

    rows, full_columns, numeric_columns = make_dataset_rows(
        labels, diagnoses, snapshots, registry
    )
    labels_path = args.output_dir / "hot_metal_si_labels.csv"
    full_path = args.output_dir / "hot_metal_si_dataset_full.csv"
    numeric_path = args.output_dir / "hot_metal_si_dataset_numeric.csv"
    training_path = args.output_dir / "hot_metal_si_dataset_training_ready.csv"
    dictionary_path = args.output_dir / "data_dictionary.csv"
    quality_path = args.output_dir / "quality_report.md"
    manifest_path = args.output_dir / "manifest.json"

    write_csv(labels_path, LABEL_COLUMNS, rows)
    write_csv(full_path, full_columns, rows)
    write_csv(numeric_path, numeric_columns, rows)
    training_rows = [
        row
        for row in rows
        if row.get("diagnosis__ts")
        and int(row.get("sensor__available_count") or 0)
        >= args.min_training_sensors
    ]
    write_csv(training_path, numeric_columns, training_rows)
    dictionary_rows = build_dictionary_rows(rows, full_columns, registry)
    write_csv(
        dictionary_path,
        DATA_DICTIONARY_COLUMNS,
        dictionary_rows,
    )
    artifacts = [
        labels_path,
        full_path,
        numeric_path,
        training_path,
        dictionary_path,
    ]
    manifest = build_manifest(
        args,
        rows,
        training_rows,
        full_columns,
        numeric_columns,
        registry,
        sensor_meta,
        artifacts,
    )
    write_quality_report(quality_path, manifest)
    manifest["artifacts"][quality_path.name] = {
        "bytes": quality_path.stat().st_size,
        "sha256": sha256_file(quality_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    emit(
        "complete",
        rows=len(rows),
        training_ready_rows=len(training_rows),
        full_columns=len(full_columns),
        numeric_columns=len(numeric_columns),
        output_dir=args.output_dir,
        manifest=manifest_path,
    )
    return manifest


def main() -> int:
    """CLI entrypoint."""

    args = parser().parse_args()
    try:
        run(args)
        return 0
    except (OSError, ValueError, RuntimeError, psycopg.Error) as exc:
        emit("failed", error_type=type(exc).__name__, error=str(exc))
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
