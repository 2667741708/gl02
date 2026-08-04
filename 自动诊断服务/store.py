from __future__ import annotations

import hashlib
import json
import os
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from service_config import PROJECT_ROOT, load_config, project_path


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt.replace(second=0, microsecond=0)


def _date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("T", " ")).date()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.name != "nt":
        return default
    try:
        import winreg

        for root, path in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, path) as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    if value:
                        return str(value)
            except OSError:
                continue
    except Exception:
        return default
    return default


class DiagnosisStore:
    def __init__(self, config_path: str | Path | None = None):
        self.config = load_config(config_path) if config_path else load_config()
        self.db = self.config["database"]
        self.schema = self.db.get("schema", "bf_sensor")
        self.local_csv_path = os.getenv("V3_DIAG_LOCAL_WIDE_CSV", "").strip()
        self._local_df: pd.DataFrame | None = None
        self._session_conn = None
        self._zero_audit_table_exists: bool | None = None

    def pg_params(self) -> dict[str, Any]:
        return {
            "host": _env(self.db.get("host_env", "GL02_PGHOST"), str(self.db.get("default_host", "10.30.220.12"))),
            "port": int(_env(self.db.get("port_env", "GL02_PGPORT"), str(self.db.get("default_port", 5432)))),
            "dbname": _env(self.db.get("database_env", "GL02_PGDATABASE"), str(self.db.get("default_database", "bf_trend"))),
            "user": _env(self.db.get("user_env", "GL02_PGUSER"), ""),
            "password": _env(self.db.get("password_env", "GL02_PGPASSWORD"), ""),
            "connect_timeout": int(self.db.get("connect_timeout_seconds", 10)),
        }

    def connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("缺少 psycopg，无法连接 PostgreSQL。请先安装 psycopg。") from exc
        params = self.pg_params()
        if not params["user"]:
            raise RuntimeError("缺少 PostgreSQL 用户名。请设置 GL02_PGUSER/GL02_PGPASSWORD。")
        return psycopg.connect(**params, row_factory=dict_row)

    def open_session(self) -> None:
        if self.local_csv_path:
            return
        if self._session_conn is None or self._session_conn.closed:
            self._session_conn = self.connect()

    def close_session(self) -> None:
        if self._session_conn is not None and not self._session_conn.closed:
            self._session_conn.close()
        self._session_conn = None

    def connection_scope(self):
        if self._session_conn is not None and not self._session_conn.closed:
            return nullcontext(self._session_conn)
        return self.connect()

    def _load_local_csv(self) -> pd.DataFrame:
        if not self.local_csv_path:
            raise RuntimeError("V3_DIAG_LOCAL_WIDE_CSV is not set")
        if self._local_df is None:
            df = pd.read_csv(self.local_csv_path)
            if "timestamp" not in df.columns:
                raise RuntimeError(f"Local wide CSV has no timestamp column: {self.local_csv_path}")
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            for col in df.columns:
                if col != "timestamp":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "T_top" not in df.columns:
                top_cols = [c for c in ["T_top_A", "T_top_B", "T_top_C", "T_top_D"] if c in df.columns]
                if top_cols:
                    df = pd.concat([df, df[top_cols].mean(axis=1).rename("T_top")], axis=1)
            self._local_df = df.sort_values("timestamp").reset_index(drop=True)
        return self._local_df

    def ensure_schema(self) -> None:
        if self.local_csv_path:
            return
        schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")
        with self.connection_scope() as conn:
            conn.execute(schema_sql)
            self._reset_owned_sequences(conn)
            conn.commit()
        self._zero_audit_table_exists = True

    def reset_owned_sequences(self) -> int:
        if self.local_csv_path:
            return 0
        with self.connection_scope() as conn:
            count = self._reset_owned_sequences(conn)
            conn.commit()
        return count

    def _reset_owned_sequences(self, conn) -> int:
        from psycopg import sql

        rows = conn.execute(
            """
            SELECT table_schema, table_name, column_name,
                   pg_get_serial_sequence(format('%%I.%%I', table_schema, table_name), column_name) AS sequence_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND column_default LIKE 'nextval%%'
            ORDER BY table_name, ordinal_position
            """,
            (self.schema,),
        ).fetchall()
        reset_count = 0
        for row in rows:
            sequence_name = row["sequence_name"]
            if not sequence_name:
                continue
            table_ref = sql.Identifier(row["table_schema"], row["table_name"])
            column_ref = sql.Identifier(row["column_name"])
            conn.execute(
                sql.SQL(
                    """
                    SELECT setval(
                        %s::regclass,
                        GREATEST(COALESCE((SELECT max({column}) FROM {table}), 0), 1),
                        COALESCE((SELECT max({column}) FROM {table}) > 0, false)
                    )
                    """
                ).format(column=column_ref, table=table_ref),
                (sequence_name,),
            )
            reset_count += 1
        return reset_count

    def latest_data_ts(self) -> datetime | None:
        if self.local_csv_path:
            df = self._load_local_csv()
            if df.empty:
                return None
            return df["timestamp"].max().to_pydatetime()
        with self.connection_scope() as conn:
            row = conn.execute("SELECT max(ts) AS ts FROM bf_sensor.one_minute_values").fetchone()
        return row["ts"] if row and row["ts"] else None

    def table_exists(self, table: str) -> bool:
        if self.local_csv_path:
            return False
        with self.connection_scope() as conn:
            row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        return bool(row and row["table_name"])

    def zero_policy_enabled(self) -> bool:
        policy = self.config.get("zero_value_policy", {})
        return bool(policy.get("enabled", True) and policy.get("require_pspace_audit", True))

    def zero_audit_table_exists(self) -> bool:
        if self._zero_audit_table_exists is None:
            self._zero_audit_table_exists = self.table_exists(f"{self.schema}.zero_value_audits")
        return self._zero_audit_table_exists

    def load_variable_map(self) -> dict[str, str]:
        if self.local_csv_path:
            df = self._load_local_csv()
            return {name: name for name in df.columns if name != "timestamp"}
        rows = []
        with self.connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT variable_name, tag_long_name
                FROM bf_sensor.sensor_registry
                WHERE is_enabled = true AND is_derived = false
                ORDER BY variable_name
                """
            ).fetchall()
        return {str(row["tag_long_name"]): str(row["variable_name"]) for row in rows}

    def enabled_point_count(self) -> dict[str, int]:
        if self.local_csv_path:
            df = self._load_local_csv()
            point_count = len([name for name in df.columns if name != "timestamp"])
            return {"enabled": point_count, "physical": point_count}
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                SELECT
                    count(*) FILTER (WHERE is_enabled = true) AS enabled,
                    count(*) FILTER (WHERE is_enabled = true AND is_derived = false) AS physical
                FROM bf_sensor.sensor_registry
                """
            ).fetchone()
        return {"enabled": int(row["enabled"] or 0), "physical": int(row["physical"] or 0)}

    def fetch_wide_frame(self, start: datetime, end: datetime, variables: list[str] | None = None) -> pd.DataFrame:
        start = _naive(start)
        end = _naive(end)
        if self.local_csv_path:
            df = self._load_local_csv()
            mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
            cols = ["timestamp"]
            if variables:
                cols += [c for c in variables if c in df.columns]
            else:
                cols = list(df.columns)
            return df.loc[mask, cols].copy()
        variable_filter = variables or []
        params: list[Any] = [start, end]
        where_extra = ""
        if variable_filter:
            where_extra = " AND r.variable_name = ANY(%s)"
            params.append(variable_filter)
        if self.zero_policy_enabled() and self.zero_audit_table_exists():
            sql = f"""
                SELECT
                    r.variable_name,
                    v.ts,
                    CASE
                        WHEN v.value = 0
                         AND COALESCE(z.verification_status, '') <> 'verified_zero'
                        THEN NULL
                        ELSE v.value
                    END AS value
                FROM bf_sensor.one_minute_values v
                JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
                LEFT JOIN bf_sensor.zero_value_audits z
                  ON z.tag_long_name = v.tag_long_name
                 AND z.ts = v.ts
                 AND z.pspace_aggregate = v.aggregate
                WHERE r.is_enabled = true
                  AND r.is_derived = false
                  AND v.ts >= %s
                  AND v.ts <= %s
                  {where_extra}
                ORDER BY v.ts ASC, r.variable_name ASC
            """
        elif self.zero_policy_enabled():
            sql = f"""
                SELECT r.variable_name, v.ts, CASE WHEN v.value = 0 THEN NULL ELSE v.value END AS value
                FROM bf_sensor.one_minute_values v
                JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
                WHERE r.is_enabled = true
                  AND r.is_derived = false
                  AND v.ts >= %s
                  AND v.ts <= %s
                  {where_extra}
                ORDER BY v.ts ASC, r.variable_name ASC
            """
        else:
            sql = f"""
                SELECT r.variable_name, v.ts, v.value
                FROM bf_sensor.one_minute_values v
                JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
                WHERE r.is_enabled = true
                  AND r.is_derived = false
                  AND v.ts >= %s
                  AND v.ts <= %s
                  {where_extra}
                ORDER BY v.ts ASC, r.variable_name ASC
            """
        with self.connection_scope() as conn:
            rows = conn.execute(sql, params).fetchall()
        if not rows:
            return pd.DataFrame(columns=["timestamp"])
        df = pd.DataFrame(rows)
        wide = df.pivot_table(index="ts", columns="variable_name", values="value", aggfunc="mean").sort_index()
        wide.index = pd.to_datetime(wide.index)
        wide = wide.reset_index().rename(columns={"ts": "timestamp"})
        for col in wide.columns:
            if col != "timestamp":
                wide[col] = pd.to_numeric(wide[col], errors="coerce")
        if "T_top" not in wide.columns:
            top_cols = [c for c in ["T_top_A", "T_top_B", "T_top_C", "T_top_D"] if c in wide.columns]
            if top_cols:
                wide = pd.concat([wide, wide[top_cols].mean(axis=1).rename("T_top")], axis=1)
        return wide

    def data_coverage(self, df: pd.DataFrame, start: datetime, end: datetime, required_variables: list[str]) -> dict[str, Any]:
        expected_minutes = int((end - start).total_seconds() // 60) + 1
        observed_minutes = int(df["timestamp"].nunique()) if "timestamp" in df.columns else 0
        variable_coverage: dict[str, float] = {}
        missing = []
        for var in required_variables:
            if var not in df.columns:
                variable_coverage[var] = 0.0
                missing.append(var)
                continue
            count = int(df[var].notna().sum())
            ratio = count / expected_minutes if expected_minutes else 0
            variable_coverage[var] = round(ratio, 4)
            if ratio <= 0:
                missing.append(var)
        return {
            "expected_minutes": expected_minutes,
            "observed_minutes": observed_minutes,
            "coverage_ratio": round(observed_minutes / expected_minutes, 4) if expected_minutes else 0,
            "variable_coverage": variable_coverage,
        }

    def zero_audit_summary(self, start: datetime, end: datetime, variables: list[str] | None = None) -> dict[str, Any]:
        if self.local_csv_path:
            return {"enabled": False, "reason": "local_csv"}
        start = _naive(start)
        end = _naive(end)
        params: list[Any] = [start, end]
        where_extra = ""
        if variables:
            where_extra = " AND r.variable_name = ANY(%s)"
            params.append(variables)
        if self.zero_audit_table_exists():
            sql = f"""
                SELECT
                    count(*) AS zero_rows,
                    count(*) FILTER (WHERE z.verification_status = 'verified_zero') AS verified_zero_rows,
                    count(*) FILTER (WHERE z.verification_status IS NULL) AS unaudited_zero_rows,
                    count(*) FILTER (WHERE z.verification_status IS NOT NULL AND z.verification_status <> 'verified_zero') AS rejected_zero_rows,
                    array_agg(DISTINCT r.variable_name) FILTER (
                        WHERE z.verification_status IS NULL OR z.verification_status <> 'verified_zero'
                    ) AS variables_need_audit
                FROM bf_sensor.one_minute_values v
                JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
                LEFT JOIN bf_sensor.zero_value_audits z
                  ON z.tag_long_name = v.tag_long_name
                 AND z.ts = v.ts
                 AND z.pspace_aggregate = v.aggregate
                WHERE r.is_enabled = true
                  AND r.is_derived = false
                  AND v.value = 0
                  AND v.ts >= %s
                  AND v.ts <= %s
                  {where_extra}
            """
        else:
            sql = f"""
                SELECT
                    count(*) AS zero_rows,
                    0::bigint AS verified_zero_rows,
                    count(*) AS unaudited_zero_rows,
                    0::bigint AS rejected_zero_rows,
                    array_agg(DISTINCT r.variable_name) AS variables_need_audit
                FROM bf_sensor.one_minute_values v
                JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
                WHERE r.is_enabled = true
                  AND r.is_derived = false
                  AND v.value = 0
                  AND v.ts >= %s
                  AND v.ts <= %s
                  {where_extra}
            """
        with self.connection_scope() as conn:
            row = conn.execute(sql, params).fetchone()
        variables_need_audit = row["variables_need_audit"] if row else []
        return {
            "enabled": self.zero_policy_enabled(),
            "zero_rows": int(row["zero_rows"] or 0) if row else 0,
            "verified_zero_rows": int(row["verified_zero_rows"] or 0) if row else 0,
            "unaudited_zero_rows": int(row["unaudited_zero_rows"] or 0) if row else 0,
            "rejected_zero_rows": int(row["rejected_zero_rows"] or 0) if row else 0,
            "variables_need_audit": sorted(variables_need_audit or []),
        }

    @staticmethod
    def diagnosis_invalid_reason(row: dict[str, Any], min_coverage_ratio: float) -> str:
        coverage = row.get("data_coverage") or {}
        try:
            coverage_ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)
        except Exception:
            coverage_ratio = 0.0
        feature_snapshot = row.get("feature_snapshot") or {}
        raw_scores = row.get("raw_scores") or {}
        main_label = str(row.get("main_label") or "")
        main_score = float(row.get("main_score") or 0.0)
        main_confidence = float(row.get("main_confidence") or 0.0)

        if not feature_snapshot and main_label == "normal" and main_score == 0.0 and main_confidence == 0.0:
            return "empty_normal_snapshot"
        if not feature_snapshot and raw_scores == {} and main_label != "data_quality_low":
            return "empty_feature_snapshot"
        if coverage_ratio < min_coverage_ratio and main_label != "data_quality_low":
            return "coverage_below_threshold"
        if raw_scores == {} and main_label not in {"data_quality_low"}:
            return "empty_raw_scores"
        return ""

    def start_run(self, task_name: str, window_start: datetime | None = None, window_end: datetime | None = None) -> int:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                INSERT INTO bf_sensor.automation_runs(task_name, window_start, window_end)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (task_name, window_start, window_end),
            ).fetchone()
            conn.commit()
        return int(row["id"])

    def finish_run(
        self,
        run_id: int,
        status: str,
        rows_read: int = 0,
        rows_written: int = 0,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connection_scope() as conn:
            conn.execute(
                """
                UPDATE bf_sensor.automation_runs
                SET finished_at=now(), status=%s, rows_read=%s, rows_written=%s, message=%s, details=%s::jsonb
                WHERE id=%s
                """,
                (status, rows_read, rows_written, message, _json(details or {}), run_id),
            )
            conn.commit()

    def upsert_diagnosis(self, payload: dict[str, Any]) -> None:
        with self.connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO bf_sensor.diagnosis_snapshots (
                    diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                    baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                    source, data_coverage, missing_variables, source_lag_seconds,
                    main_label, main_score, main_confidence,
                    secondary_label, secondary_score, secondary_confidence,
                    evidence, raw_scores, feature_snapshot, diagnosis_json, updated_at
                )
                VALUES (
                    %(timestamp)s, %(diagnosis_window_start)s, %(diagnosis_window_end)s,
                    %(baseline_window_start)s, %(baseline_window_end)s, %(baseline_days)s, %(window_minutes)s,
                    %(source)s::jsonb, %(data_coverage)s::jsonb, %(missing_variables)s::jsonb, %(source_lag_seconds)s,
                    %(main_label)s, %(main_score)s, %(main_confidence)s,
                    %(secondary_label)s, %(secondary_score)s, %(secondary_confidence)s,
                    %(evidence)s::jsonb, %(raw_scores)s::jsonb, %(feature_snapshot)s::jsonb, %(diagnosis_json)s::jsonb, now()
                )
                ON CONFLICT (diagnosis_ts, baseline_days, window_minutes, source)
                DO UPDATE SET
                    diagnosis_window_start=excluded.diagnosis_window_start,
                    diagnosis_window_end=excluded.diagnosis_window_end,
                    baseline_window_start=excluded.baseline_window_start,
                    baseline_window_end=excluded.baseline_window_end,
                    data_coverage=excluded.data_coverage,
                    missing_variables=excluded.missing_variables,
                    source_lag_seconds=excluded.source_lag_seconds,
                    main_label=excluded.main_label,
                    main_score=excluded.main_score,
                    main_confidence=excluded.main_confidence,
                    secondary_label=excluded.secondary_label,
                    secondary_score=excluded.secondary_score,
                    secondary_confidence=excluded.secondary_confidence,
                    evidence=excluded.evidence,
                    raw_scores=excluded.raw_scores,
                    feature_snapshot=excluded.feature_snapshot,
                    diagnosis_json=excluded.diagnosis_json,
                    updated_at=now()
                """,
                {
                    **payload,
                    "source": _json(payload.get("source", {})),
                    "data_coverage": _json(payload.get("data_coverage", {})),
                    "missing_variables": _json(payload.get("missing_variables", [])),
                    "evidence": _json(payload.get("evidence", [])),
                    "raw_scores": _json(payload.get("raw_scores", {})),
                    "feature_snapshot": _json(payload.get("feature_snapshot", {})),
                    "diagnosis_json": _json(payload),
                },
            )
            conn.commit()

    def insert_quality_status(self, payload: dict[str, Any]) -> None:
        with self.connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO bf_sensor.data_quality_status (
                    checked_at, window_start, window_end, window_kind, latest_data_ts, source_lag_seconds,
                    expected_minutes, observed_minutes, coverage_ratio,
                    missing_variables, stale_variables, status, details
                )
                VALUES (now(), %(window_start)s, %(window_end)s, %(window_kind)s, %(latest_data_ts)s, %(source_lag_seconds)s,
                        %(expected_minutes)s, %(observed_minutes)s, %(coverage_ratio)s,
                        %(missing_variables)s::jsonb, %(stale_variables)s::jsonb, %(status)s, %(details)s::jsonb)
                """,
                {
                    **payload,
                    "missing_variables": _json(payload.get("missing_variables", [])),
                    "stale_variables": _json(payload.get("stale_variables", [])),
                    "details": _json(payload.get("details", {})),
                },
            )
            conn.commit()

    def create_backfill_task(self, reason: str, variable_name: str, tag_long_name: str, start_ts: datetime, end_ts: datetime) -> None:
        with self.connection_scope() as conn:
            conn.execute(
                """
                INSERT INTO bf_sensor.backfill_tasks(reason, variable_name, tag_long_name, start_ts, end_ts)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(variable_name, tag_long_name, start_ts, end_ts, reason)
                DO UPDATE SET updated_at=now()
                """,
                (reason, variable_name, tag_long_name, start_ts, end_ts),
            )
            conn.commit()

    def upsert_daily_baselines(self, baseline_day: date, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self.connection_scope() as conn:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO bf_sensor.daily_baselines (
                        baseline_day, baseline_window_start, baseline_window_end, baseline_days,
                        variable_name, median_ref, iqr_ref, p10, p50, p90,
                        sample_count, expected_minutes, coverage_ratio, source, updated_at
                    )
                    VALUES (
                        %(baseline_day)s, %(baseline_window_start)s, %(baseline_window_end)s, %(baseline_days)s,
                        %(variable_name)s, %(median_ref)s, %(iqr_ref)s, %(p10)s, %(p50)s, %(p90)s,
                        %(sample_count)s, %(expected_minutes)s, %(coverage_ratio)s, %(source)s::jsonb, now()
                    )
                    ON CONFLICT (baseline_day, baseline_days, variable_name)
                    DO UPDATE SET
                        baseline_window_start=excluded.baseline_window_start,
                        baseline_window_end=excluded.baseline_window_end,
                        median_ref=excluded.median_ref,
                        iqr_ref=excluded.iqr_ref,
                        p10=excluded.p10,
                        p50=excluded.p50,
                        p90=excluded.p90,
                        sample_count=excluded.sample_count,
                        expected_minutes=excluded.expected_minutes,
                        coverage_ratio=excluded.coverage_ratio,
                        source=excluded.source,
                        updated_at=now()
                    """,
                    {**row, "baseline_day": baseline_day, "source": _json(row.get("source", {}))},
                )
            conn.commit()
        return len(rows)

    def query_daily_baselines(self, baseline_day: str | date | datetime, variable: str = "", baseline_days: int = 30) -> list[dict[str, Any]]:
        if self.local_csv_path:
            return []
        params: list[Any] = [_date(baseline_day), baseline_days]
        extra = ""
        if variable:
            extra = " AND variable_name = %s"
            params.append(variable)
        with self.connection_scope() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM bf_sensor.daily_baselines
                WHERE baseline_day = %s AND baseline_days = %s {extra}
                ORDER BY variable_name
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_baseline_day(self) -> date | None:
        if self.local_csv_path:
            return None
        with self.connection_scope() as conn:
            row = conn.execute("SELECT max(baseline_day) AS day FROM bf_sensor.daily_baselines").fetchone()
        return row["day"] if row and row["day"] else None

    def baseline_meta_for_day(self, baseline_day: str | date | datetime, baseline_days: int = 30) -> dict[str, dict[str, float]]:
        rows = self.query_daily_baselines(baseline_day, baseline_days=baseline_days)
        return {
            row["variable_name"]: {
                "median_ref": float(row["median_ref"]),
                "iqr_ref": float(row["iqr_ref"]),
            }
            for row in rows
        }

    def latest_diagnosis_ts(self) -> datetime | None:
        if self.local_csv_path:
            return None
        with self.connection_scope() as conn:
            row = conn.execute("SELECT max(diagnosis_ts) AS ts FROM bf_sensor.diagnosis_snapshots").fetchone()
        return row["ts"] if row and row["ts"] else None

    def list_diagnoses(self, start: datetime | None = None, end: datetime | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if self.local_csv_path:
            return []
        params: list[Any] = []
        where = []
        if start is not None:
            where.append("diagnosis_ts >= %s")
            params.append(_naive(start))
        if end is not None:
            where.append("diagnosis_ts <= %s")
            params.append(_naive(end))
        sql_where = "WHERE " + " AND ".join(where) if where else ""
        params.append(limit)
        with self.connection_scope() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM (
                    SELECT DISTINCT ON (diagnosis_ts) *
                    FROM bf_sensor.diagnosis_snapshots
                    {sql_where}
                    ORDER BY diagnosis_ts, updated_at DESC, id DESC
                ) latest
                ORDER BY diagnosis_ts DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def find_missing_diagnosis_points(self, start: datetime, end: datetime, step_minutes: int = 5) -> list[datetime]:
        start = _naive(start)
        end = _naive(end)
        if self.local_csv_path:
            missing = []
            cursor = start
            while cursor <= end:
                missing.append(cursor)
                cursor += timedelta(minutes=step_minutes)
            return missing
        with self.connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT diagnosis_ts
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                """,
                (start, end),
            ).fetchall()
        existing = {row["diagnosis_ts"].replace(second=0, microsecond=0) for row in rows}
        missing = []
        cursor = start
        while cursor <= end:
            if cursor not in existing:
                missing.append(cursor)
            cursor += timedelta(minutes=step_minutes)
        return missing

    def find_missing_or_invalid_diagnosis_points(
        self,
        start: datetime,
        end: datetime,
        *,
        step_minutes: int = 5,
        window_minutes: int = 60,
        required_variables: list[str],
        min_coverage_ratio: float = 0.75,
        include_invalid: bool = True,
    ) -> tuple[list[datetime], dict[str, Any]]:
        start = _naive(start)
        end = _naive(end)
        missing = self.find_missing_diagnosis_points(start, end, step_minutes=step_minutes)
        if not include_invalid or self.local_csv_path:
            return missing, {"missing": len(missing), "invalid": 0, "invalid_reasons": {}}

        with self.connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (diagnosis_ts)
                    diagnosis_ts, main_label, main_score, main_confidence,
                    data_coverage, raw_scores, feature_snapshot
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                  AND window_minutes = %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
                """,
                (start, end, window_minutes),
            ).fetchall()

        existing_bad: dict[datetime, str] = {}
        for row in rows:
            reason = self.diagnosis_invalid_reason(dict(row), min_coverage_ratio)
            if reason:
                ts = row["diagnosis_ts"].replace(second=0, microsecond=0)
                existing_bad[ts] = reason

        repairable: list[datetime] = []
        reasons: dict[str, int] = {}
        for ts, reason in sorted(existing_bad.items()):
            repairable.append(ts)
            reasons[reason] = reasons.get(reason, 0) + 1

        combined = sorted(set(missing) | set(repairable))
        return combined, {
            "missing": len(missing),
            "invalid": len(repairable),
            "invalid_reasons": reasons,
        }

    def delete_invalid_diagnosis_snapshots(
        self,
        points: list[datetime],
        *,
        baseline_days: int,
        window_minutes: int,
        min_coverage_ratio: float,
    ) -> int:
        if self.local_csv_path or not points:
            return 0
        points = [_naive(point) for point in points]
        with self.connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT id, main_label, main_score, main_confidence,
                       data_coverage, raw_scores, feature_snapshot
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts = ANY(%s)
                  AND baseline_days = %s
                  AND window_minutes = %s
                """,
                (points, baseline_days, window_minutes),
            ).fetchall()
            invalid_ids = [
                int(row["id"])
                for row in rows
                if self.diagnosis_invalid_reason(dict(row), min_coverage_ratio)
            ]
            if not invalid_ids:
                return 0
            conn.execute("DELETE FROM bf_sensor.diagnosis_snapshots WHERE id = ANY(%s)", (invalid_ids,))
            conn.commit()
        return len(invalid_ids)

    def delete_diagnosis_snapshots_after(self, cutoff_ts: datetime) -> int:
        if self.local_csv_path:
            return 0
        cutoff_ts = _naive(cutoff_ts)
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                DELETE FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts > %s
                RETURNING id
                """,
                (cutoff_ts,),
            ).fetchall()
            conn.commit()
        return len(row)

    def make_queue_payload(self, queue_end_ts: datetime, window_minutes: int = 60, step_minutes: int = 5, queue_size: int = 12) -> dict[str, Any]:
        queue_end_ts = _naive(queue_end_ts)
        queue_start_ts = queue_end_ts - timedelta(minutes=window_minutes - step_minutes)
        rows = list(reversed(self.list_diagnoses(queue_start_ts, queue_end_ts, limit=queue_size)))
        diagnosis_ids = [int(row["id"]) for row in rows]
        diagnosis_json = [
            {
                "id": row["id"],
                "diagnosis_ts": row["diagnosis_ts"],
                "main_label": row["main_label"],
                "main_score": row["main_score"],
                "main_confidence": row["main_confidence"],
                "secondary_label": row["secondary_label"],
                "secondary_score": row["secondary_score"],
                "secondary_confidence": row["secondary_confidence"],
                "evidence": row["evidence"],
                "raw_scores": row["raw_scores"],
                "data_coverage": row["data_coverage"],
            }
            for row in rows
        ]
        canonical = _json({"end": queue_end_ts, "ids": diagnosis_ids, "items": diagnosis_json})
        queue_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        queue_id = "dq_" + queue_end_ts.strftime("%Y%m%d_%H%M%S") + "_" + queue_hash[:8]
        expected = int(queue_size)
        return {
            "queue_id": queue_id,
            "queue_hash": queue_hash,
            "queue_start_ts": queue_start_ts,
            "queue_end_ts": queue_end_ts,
            "window_minutes": window_minutes,
            "step_minutes": step_minutes,
            "diagnosis_count": len(rows),
            "expected_count": expected,
            "status": "complete" if len(rows) >= expected else "incomplete",
            "diagnosis_ids": diagnosis_ids,
            "diagnosis_json": diagnosis_json,
        }

    def upsert_diagnosis_queue(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                INSERT INTO bf_sensor.diagnosis_queues (
                    queue_id, queue_hash, queue_start_ts, queue_end_ts, window_minutes, step_minutes,
                    diagnosis_count, expected_count, status, diagnosis_ids, diagnosis_json, updated_at
                )
                VALUES (%(queue_id)s, %(queue_hash)s, %(queue_start_ts)s, %(queue_end_ts)s, %(window_minutes)s, %(step_minutes)s,
                        %(diagnosis_count)s, %(expected_count)s, %(status)s, %(diagnosis_ids)s::jsonb, %(diagnosis_json)s::jsonb, now())
                ON CONFLICT (queue_id) DO UPDATE SET
                    queue_hash=excluded.queue_hash,
                    queue_start_ts=excluded.queue_start_ts,
                    queue_end_ts=excluded.queue_end_ts,
                    window_minutes=excluded.window_minutes,
                    step_minutes=excluded.step_minutes,
                    diagnosis_count=excluded.diagnosis_count,
                    expected_count=excluded.expected_count,
                    status=excluded.status,
                    diagnosis_ids=excluded.diagnosis_ids,
                    diagnosis_json=excluded.diagnosis_json,
                    updated_at=now()
                RETURNING *
                """,
                {**payload, "diagnosis_ids": _json(payload.get("diagnosis_ids", [])), "diagnosis_json": _json(payload.get("diagnosis_json", []))},
            ).fetchone()
            conn.commit()
        return dict(row)

    def get_diagnosis_queue(self, queue_id_or_hash: str) -> dict[str, Any] | None:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM bf_sensor.diagnosis_queues
                WHERE queue_id = %s OR queue_hash = %s
                ORDER BY queue_end_ts DESC
                LIMIT 1
                """,
                (queue_id_or_hash, queue_id_or_hash),
            ).fetchone()
        return dict(row) if row else None

    def latest_diagnosis_queue(self) -> dict[str, Any] | None:
        if self.local_csv_path:
            return None
        with self.connection_scope() as conn:
            row = conn.execute("SELECT * FROM bf_sensor.diagnosis_queues ORDER BY queue_end_ts DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def list_short_window_summaries(self, limit: int = 20) -> list[dict[str, Any]]:
        if self.local_csv_path:
            return []
        with self.connection_scope() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM bf_sensor.short_window_summaries
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_short_window_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                INSERT INTO bf_sensor.short_window_summaries (
                    summary_id, queue_id, queue_hash, model_name, prompt_json, llm_summary,
                    diagnosis_queue_json, docx_path, markdown_path, status, updated_at
                )
                VALUES (%(summary_id)s, %(queue_id)s, %(queue_hash)s, %(model_name)s, %(prompt_json)s::jsonb, %(llm_summary)s,
                        %(diagnosis_queue_json)s::jsonb, %(docx_path)s, %(markdown_path)s, %(status)s, now())
                ON CONFLICT (summary_id) DO UPDATE SET
                    queue_id=excluded.queue_id,
                    model_name=excluded.model_name,
                    queue_hash=excluded.queue_hash,
                    prompt_json=excluded.prompt_json,
                    llm_summary=excluded.llm_summary,
                    diagnosis_queue_json=excluded.diagnosis_queue_json,
                    docx_path=excluded.docx_path,
                    markdown_path=excluded.markdown_path,
                    status=excluded.status,
                    updated_at=now()
                RETURNING *
                """,
                {
                    **payload,
                    "prompt_json": _json(payload.get("prompt_json", {})),
                    "diagnosis_queue_json": _json(payload.get("diagnosis_queue_json", [])),
                },
            ).fetchone()
            conn.commit()
        return dict(row)

    def ensure_short_window_conversation(self, conversation_id: str, queue: dict[str, Any]) -> dict[str, Any]:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                INSERT INTO bf_sensor.short_window_conversations (
                    conversation_id, queue_id, queue_hash, last_queue_diagnosis_ts, updated_at
                )
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (conversation_id) DO UPDATE SET
                    queue_id=excluded.queue_id,
                    queue_hash=excluded.queue_hash,
                    updated_at=now()
                RETURNING *
                """,
                (conversation_id, queue["queue_id"], queue["queue_hash"], queue["queue_end_ts"]),
            ).fetchone()
            conn.commit()
        return dict(row)

    def get_short_window_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.connection_scope() as conn:
            row = conn.execute("SELECT * FROM bf_sensor.short_window_conversations WHERE conversation_id=%s", (conversation_id,)).fetchone()
        return dict(row) if row else None

    def insert_conversation_delta_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connection_scope() as conn:
            row = conn.execute(
                """
                INSERT INTO bf_sensor.conversation_delta_contexts (
                    conversation_id, queue_id, message_ts, previous_queue_end_ts,
                    delta_start_ts, delta_end_ts, delta_diagnosis_ids, operator_message, hidden_context_json
                )
                VALUES (%(conversation_id)s, %(queue_id)s, %(message_ts)s, %(previous_queue_end_ts)s,
                        %(delta_start_ts)s, %(delta_end_ts)s, %(delta_diagnosis_ids)s::jsonb, %(operator_message)s, %(hidden_context_json)s::jsonb)
                RETURNING *
                """,
                {
                    **payload,
                    "delta_diagnosis_ids": _json(payload.get("delta_diagnosis_ids", [])),
                    "hidden_context_json": _json(payload.get("hidden_context_json", {})),
                },
            ).fetchone()
            conn.commit()
        return dict(row)
