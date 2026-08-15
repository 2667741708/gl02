"""Explainable two-half-hour furnace thermal trend rule for 8093.

The rule is advisory only.  It compares the latest 30-minute mean with the
preceding 30-minute mean, adds configured weights into separate upward and
downward scores, and can suppress burden-rate evidence while a time-limited
slag/iron drainage exception is active.  It never writes process controls or
changes ABC33 scores.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

REQUIREMENT_ID = "REQ-8093-THERMAL-TREND-20260813"
SCHEMA_VERSION = "bf.thermal-trend.v1"
CONFIG_SCHEMA_VERSION = "bf.thermal-trend.config.v1"
STATE_SCHEMA_VERSION = "bf.thermal-trend.condition.v1"
SENSOR_VARIABLES = (
    "Q_blast", "P_blast_cold", "P_blast", "DP_total",
    "DP_upper", "DP_lower", "GasUtil",
)
TOP_TEMPERATURE_VARIABLES = ("T_top_A", "T_top_B", "T_top_C", "T_top_D")
BASELINE_SENSOR_VARIABLES = (
    "P_blast_cold", "Q_blast", "PI", "DP_total", "DP_upper", "DP_lower", "GasUtil",
    "T_top_A", "T_top_B", "T_top_C", "T_top_D",
)
BASELINE_METRIC_KEYS = (
    "P_blast_cold", "Q_blast", "PI", "DP_total", "DP_upper", "DP_lower", "GasUtil", "top_temperature",
)
ALLOWED_DIRECTIONS = {"increase", "decrease"}
ALLOWED_CONDITION_STATES = {"drained", "not_drained", "unknown"}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif value is None:
        return None
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if result.tzinfo is not None:
        # The existing pSpace burden-rate contract evaluates database samples
        # by the furnace-local wall clock.  Dropping the offset preserves the
        # two adjacent half-hour windows; converting to UTC would shift them.
        result = result.replace(tzinfo=None)
    return result


def _json_hash(value: Mapping[str, Any]) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise ValueError("炉温趋势配置必须是JSON对象")
    value = dict(config)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError("炉温趋势配置版本不正确")
    if int(value.get("window_minutes") or 0) != 30:
        raise ValueError("两个对比窗口必须固定为30分钟")
    coverage = _number(value.get("minimum_window_coverage_ratio"))
    if coverage is None or not 0.5 <= coverage <= 1:
        raise ValueError("窗口覆盖率必须在0.5到1之间")
    maximum_age = int(value.get("maximum_source_age_minutes") or 0)
    if not 1 <= maximum_age <= 30:
        raise ValueError("数据最大时延必须在1到30分钟之间")
    confirmation_score = _number(value.get("confirmation_score_threshold"))
    if confirmation_score is None or not 50 < confirmation_score <= 100:
        raise ValueError("趋势确认分值必须大于50且不超过100")
    exception = value.get("slag_iron_exception")
    if not isinstance(exception, Mapping):
        raise ValueError("缺少渣铁排放异常配置")
    ttl = int(exception.get("confirmation_ttl_minutes") or 0)
    if not 15 <= ttl <= 720:
        raise ValueError("渣铁状态有效期必须在15到720分钟之间")
    metrics = value.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 8:
        raise ValueError("炉温趋势必须且只能配置8项指标")
    expected = {"burden_rate", *SENSOR_VARIABLES}
    seen: set[str] = set()
    weight_sum = 0.0
    for item in metrics:
        if not isinstance(item, Mapping):
            raise ValueError("指标配置必须是对象")
        key = str(item.get("key") or "")
        if key not in expected or key in seen:
            raise ValueError(f"炉温趋势指标不合法: {key}")
        seen.add(key)
        if str(item.get("up_when") or "") not in ALLOWED_DIRECTIONS:
            raise ValueError(f"{key}的上行方向不合法")
        weight = _number(item.get("weight"))
        if weight is None or weight < 0 or weight > 100:
            raise ValueError(f"{key}的权重必须在0到100之间")
        weight_sum += weight
        for field in ("up_threshold", "down_threshold"):
            threshold = item.get(field)
            if threshold is not None and (_number(threshold) is None or float(threshold) <= 0):
                raise ValueError(f"{key}的{field}必须大于0或留空")
        enabled = bool(item.get("enabled"))
        if enabled and (_number(item.get("up_threshold")) is None or _number(item.get("down_threshold")) is None):
            raise ValueError(f"{key}启用前必须填写上行和下行偏差值")
    if seen != expected:
        raise ValueError("炉温趋势8项指标不完整")
    if abs(weight_sum - 100.0) > 1e-6:
        raise ValueError(f"8项指标权重合计必须为100，当前为{weight_sum:g}")
    baseline = value.get("baseline_monitoring")
    if baseline is not None:
        if not isinstance(baseline, Mapping):
            raise ValueError("基准监测配置必须是对象")
        start_date = str(baseline.get("start_date") or "").strip()
        end_date = str(baseline.get("end_date") or "").strip()
        if bool(start_date) != bool(end_date):
            raise ValueError("基准日期必须同时填写开始和结束日期")
        if start_date and end_date:
            try:
                if date.fromisoformat(start_date) > date.fromisoformat(end_date):
                    raise ValueError("基准开始日期不能晚于结束日期")
            except ValueError as exc:
                raise ValueError("基准日期必须为YYYY-MM-DD") from exc
        monitor_metrics = baseline.get("metrics")
        if not isinstance(monitor_metrics, list) or {str(item.get("key") or "") for item in monitor_metrics if isinstance(item, Mapping)} != set(BASELINE_METRIC_KEYS):
            raise ValueError("基准监测必须配置指定的8项指标")
        for item in monitor_metrics:
            if not isinstance(item, Mapping):
                raise ValueError("基准指标配置必须是对象")
            for field in ("low_deviation", "high_deviation"):
                threshold = _number(item.get(field))
                if threshold is None or threshold <= 0:
                    raise ValueError(f"{item.get('key')}的{field}必须大于0")
        top = baseline.get("top_temperature")
        if not isinstance(top, Mapping):
            raise ValueError("缺少炉顶4点温度特殊告警配置")
        for field in ("normal_max_pair_delta", "alarm_max_pair_delta"):
            threshold = _number(top.get(field))
            if threshold is None or threshold <= 0:
                raise ValueError(f"炉顶温度{field}必须大于0")
        if float(top["normal_max_pair_delta"]) >= float(top["alarm_max_pair_delta"]):
            raise ValueError("炉顶温度正常阈值必须小于告警阈值")
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_config(value)


def publish_config(config: Mapping[str, Any], path: str | Path, *, reason: str, actor: str) -> dict[str, Any]:
    if not reason.strip() or not actor.strip():
        raise ValueError("发布炉温趋势配置必须填写原因并保留管理员身份")
    value = validate_config(config)
    payload = dict(value)
    payload["config_hash"] = _json_hash(value)
    payload["published_by"] = actor
    payload["change_reason"] = reason
    payload["published_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(Path(path), payload)
    return {
        "config_version": payload.get("config_version"),
        "config_hash": payload["config_hash"],
        "published_by": actor,
        "change_reason": reason,
    }


def read_condition(path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        value = {"schema_version": STATE_SCHEMA_VERSION, "state": "unknown"}
    state = str(value.get("state") or "unknown")
    expires = _timestamp(value.get("expires_at"))
    now_naive = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
    active = state in {"drained", "not_drained"} and expires is not None and expires > now_naive
    return {
        "state": state if active else "unknown",
        "active": active,
        "confirmed_at": value.get("confirmed_at") if active else None,
        "expires_at": value.get("expires_at") if active else None,
        "reason": str(value.get("reason") or "") if active else "",
    }


def write_condition(
    path: str | Path, *, state: str, actor: str, role: str, ttl_minutes: int,
    reason: str = "", now: datetime | None = None,
) -> dict[str, Any]:
    if state not in ALLOWED_CONDITION_STATES:
        raise ValueError("渣铁状态只能为已出净、排放不畅或未确认")
    if not actor.strip():
        raise ValueError("渣铁状态确认必须保留操作人身份")
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl_minutes)
    payload = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": state,
        "confirmed_by": actor,
        "confirmed_role": role,
        "confirmed_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "reason": reason.strip()[:300],
    }
    _atomic_json(Path(path), payload)
    return read_condition(path, now=now)


def _sensor_rows(connection: Any, evaluation_ts: datetime) -> list[dict[str, Any]]:
    start = evaluation_ts - timedelta(minutes=60)
    rows = connection.execute(
        """
        SELECT r.variable_name, v.ts, avg(v.value)::double precision AS value
        FROM bf_sensor.sensor_registry r
        JOIN bf_sensor.one_minute_values v ON v.tag_long_name=r.tag_long_name
        WHERE r.variable_name=ANY(%s) AND v.ts>%s AND v.ts<=%s AND v.value IS NOT NULL
        GROUP BY r.variable_name,v.ts ORDER BY v.ts,r.variable_name
        """,
        (list((*SENSOR_VARIABLES, "PI", *TOP_TEMPERATURE_VARIABLES)), start, evaluation_ts),
    ).fetchall()
    return [dict(row) if isinstance(row, Mapping) else {"variable_name": row[0], "ts": row[1], "value": row[2]} for row in rows]


def _baseline_rows(connection: Any, start_date: str, end_date: str) -> list[dict[str, Any]]:
    start = datetime.combine(date.fromisoformat(start_date), time.min)
    end = datetime.combine(date.fromisoformat(end_date) + timedelta(days=1), time.min)
    rows = connection.execute(
        """
        SELECT r.variable_name, v.ts, avg(v.value)::double precision AS value
        FROM bf_sensor.sensor_registry r
        JOIN bf_sensor.one_minute_values v ON v.tag_long_name=r.tag_long_name
        WHERE r.variable_name=ANY(%s) AND v.ts>=%s AND v.ts<%s AND v.value IS NOT NULL
        GROUP BY r.variable_name,v.ts ORDER BY v.ts,r.variable_name
        """,
        (list(BASELINE_SENSOR_VARIABLES), start, end),
    ).fetchall()
    return [dict(row) if isinstance(row, Mapping) else {"variable_name": row[0], "ts": row[1], "value": row[2]} for row in rows]


def _baseline_monitoring(connection: Any, config: Mapping[str, Any]) -> dict[str, Any]:
    baseline = config.get("baseline_monitoring") or {}
    start_date = str(baseline.get("start_date") or "").strip()
    end_date = str(baseline.get("end_date") or "").strip()
    if not start_date or not end_date:
        return {"state": "not_configured", "summary": "尚未选择基准日期", "metrics": [], "top_temperature": {}}
    rows = _baseline_rows(connection, start_date, end_date)
    grouped: dict[str, list[float]] = {key: [] for key in BASELINE_SENSOR_VARIABLES}
    for row in rows:
        value = _number(row.get("value"))
        key = str(row.get("variable_name") or "")
        if value is not None and key in grouped:
            grouped[key].append(value)
    configured = {str(item.get("key")): item for item in baseline.get("metrics") or [] if isinstance(item, Mapping)}
    metrics: list[dict[str, Any]] = []
    for key in BASELINE_METRIC_KEYS[:-1]:
        values = grouped.get(key, [])
        spec = configured.get(key, {})
        metrics.append({"label": spec.get("label", key), "key": key, "unit": spec.get("unit", ""), "mean": sum(values) / len(values) if values else None, "sample_count": len(values), "low_deviation": _number(spec.get("low_deviation")), "high_deviation": _number(spec.get("high_deviation"))})
    top_values = [grouped[key] for key in BASELINE_SENSOR_VARIABLES if key.startswith("T_top_")]
    top_flat = [value for values in top_values for value in values]
    top_spec = baseline.get("top_temperature") or {}
    metrics.append({"label": "炉顶4点温度", "key": "top_temperature", "unit": "℃", "mean": sum(top_flat) / len(top_flat) if top_flat else None, "sample_count": len(top_flat), "low_deviation": _number(top_spec.get("low_deviation")), "high_deviation": _number(top_spec.get("high_deviation"))})
    top_samples = {key: grouped.get(key, []) for key in ("T_top_A", "T_top_B", "T_top_C", "T_top_D")}
    top_means = {key: (sum(values) / len(values) if values else None) for key, values in top_samples.items()}
    available = [value for value in top_means.values() if value is not None]
    pair_delta = max(available) - min(available) if len(available) >= 2 else None
    return {"state": "ready" if all(item["mean"] is not None for item in metrics) else "partial", "start_date": start_date, "end_date": end_date, "metrics": metrics, "top_temperature": {"point_means": top_means, "max_pair_delta": pair_delta, "normal_max_pair_delta": _number(top_spec.get("normal_max_pair_delta")), "alarm_max_pair_delta": _number(top_spec.get("alarm_max_pair_delta"))}, "summary": f"基准区间 {start_date} 至 {end_date}，共采集 {len(rows)} 个时序点"}


def _window_values(
    rows: list[dict[str, Any]],
    evaluation_ts: datetime,
    minimum_coverage: float,
    maximum_source_age_minutes: int,
) -> dict[str, dict[str, Any]]:
    split = evaluation_ts - timedelta(minutes=30)
    start = evaluation_ts - timedelta(minutes=60)
    result: dict[str, dict[str, Any]] = {}
    for variable in (*SENSOR_VARIABLES, "PI", *TOP_TEMPERATURE_VARIABLES):
        samples = [(_timestamp(row.get("ts")), _number(row.get("value"))) for row in rows if row.get("variable_name") == variable]
        valid_samples = [(stamp, value) for stamp, value in samples if stamp and value is not None]
        previous = [value for stamp, value in valid_samples if start < stamp <= split]
        current = [value for stamp, value in valid_samples if split < stamp <= evaluation_ts]
        previous_coverage = min(1.0, len(previous) / 30.0)
        current_coverage = min(1.0, len(current) / 30.0)
        latest_sample_ts = max((stamp for stamp, _ in valid_samples), default=None)
        source_age_seconds = (
            max(0.0, (evaluation_ts - latest_sample_ts).total_seconds())
            if latest_sample_ts is not None else None
        )
        source_fresh = (
            source_age_seconds is not None
            and source_age_seconds <= maximum_source_age_minutes * 60
        )
        available = previous_coverage >= minimum_coverage and current_coverage >= minimum_coverage and source_fresh
        previous_mean = sum(previous) / len(previous) if available and previous else None
        current_mean = sum(current) / len(current) if available and current else None
        result[variable] = {
            "available": available,
            "previous_mean": previous_mean,
            "current_mean": current_mean,
            "delta": current_mean - previous_mean if current_mean is not None and previous_mean is not None else None,
            "previous_coverage": previous_coverage,
            "current_coverage": current_coverage,
            "source_age_seconds": source_age_seconds,
        }
    return result


def _direction(delta: float, *, up_when: str, up_threshold: float, down_threshold: float) -> str:
    if up_when == "increase":
        if delta >= up_threshold:
            return "upward"
        if delta <= -down_threshold:
            return "downward"
    else:
        if delta <= -up_threshold:
            return "upward"
        if delta >= down_threshold:
            return "downward"
    return "neutral"


def evaluate_latest(
    connect_factory: Callable[[], Any], *, config_path: str | Path, condition_path: str | Path,
    burden_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # The production service adds its controlled automatic-diagnosis directory
    # to sys.path before importing this adapter.  Import lazily so configuration
    # validation remains testable in the source-light maintainer handoff.
    from abc_burden_rate import fetch_burden_rate_snapshot

    config = load_config(config_path)
    condition = read_condition(condition_path)
    with connect_factory() as connection:
        latest_row = connection.execute(
            """
            SELECT max(v.ts) AS latest_ts FROM bf_sensor.sensor_registry r
            JOIN bf_sensor.one_minute_values v ON v.tag_long_name=r.tag_long_name
            WHERE r.variable_name=ANY(%s)
            """,
        (list((*SENSOR_VARIABLES, "PI", *TOP_TEMPERATURE_VARIABLES)),),
        ).fetchone()
        latest = latest_row.get("latest_ts") if isinstance(latest_row, Mapping) else (latest_row[0] if latest_row else None)
        evaluation_ts = _timestamp(latest)
        if evaluation_ts is None:
            return {
                "ok": True,
                "schema_version": SCHEMA_VERSION,
                "requirement_id": REQUIREMENT_ID,
                "state": "needs_data",
                "summary": "所需指标没有可用数据",
                "confirmation_score_threshold": float(config["confirmation_score_threshold"]),
                "upward_score": 0.0,
                "downward_score": 0.0,
                "available_score_capacity": 0.0,
                "eligible_factor_count": 0,
                "participating_factor_count": 8,
                "upward_votes": 0,
                "downward_votes": 0,
                "condition": {key: condition.get(key) for key in ("state", "active", "confirmed_at", "expires_at")},
                "factors": [],
                "advisory_only": True,
                "automatic_control": "prohibited",
            }
        rows = _sensor_rows(connection, evaluation_ts)
        burden = fetch_burden_rate_snapshot(connection, evaluation_ts, burden_policy or {})
        baseline_monitoring = _baseline_monitoring(connection, config)
    window_values = _window_values(
        rows,
        evaluation_ts,
        float(config["minimum_window_coverage_ratio"]),
        int(config["maximum_source_age_minutes"]),
    )
    burden_values = burden.get("values") or {}
    burden_counts = burden.get("interval_counts") or {}
    burden_available = bool((burden.get("availability") or {}).get("BurdenRateHalfHourDev"))
    values: dict[str, dict[str, Any]] = {
        **window_values,
        "burden_rate": {
            "available": burden_available,
            "previous_mean": _number(burden_values.get("BurdenRate_previous_30_large_per_hour")),
            "current_mean": _number(burden_values.get("BurdenRate_current_30_large_per_hour")),
            "delta": _number(burden_values.get("BurdenRate_delta_large_per_hour")),
            "previous_coverage": _number((burden.get("coverage_by_window") or {}).get("previous_30")),
            "current_coverage": _number((burden.get("coverage_by_window") or {}).get("current_30")),
            "previous_batch_count": _number(burden_counts.get("previous_30_small_events")),
            "current_batch_count": _number(burden_counts.get("current_30_small_events")),
        },
    }
    suppress_burden = bool(
        condition.get("state") == "not_drained"
        and (config.get("slag_iron_exception") or {}).get("suppress_burden_rate", True)
    )
    factors: list[dict[str, Any]] = []
    for spec in config["metrics"]:
        key = str(spec["key"])
        value = values.get(key) or {}
        enabled = bool(spec.get("enabled"))
        suppressed = key == "burden_rate" and suppress_burden
        delta = _number(value.get("delta"))
        available = bool(value.get("available")) and delta is not None
        evidence_state = "suppressed" if suppressed else "disabled" if not enabled else "needs_data" if not available else "neutral"
        direction = "neutral"
        if enabled and not suppressed and available:
            direction = _direction(
                delta,
                up_when=str(spec["up_when"]),
                up_threshold=float(spec["up_threshold"]),
                down_threshold=float(spec["down_threshold"]),
            )
            evidence_state = direction
        factors.append({
            "key": key,
            "label": spec.get("label"),
            "unit": spec.get("unit"),
            "previous_mean": value.get("previous_mean"),
            "current_mean": value.get("current_mean"),
            "delta": delta,
            "configured_weight": float(spec.get("weight") or 0),
            "eligible": enabled and not suppressed and available,
            "evidence_state": evidence_state,
            "suppression_reason": "渣铁排放不畅，料速不参与炉温趋势判断" if suppressed else "",
            "previous_batch_count": value.get("previous_batch_count") if key == "burden_rate" else None,
            "current_batch_count": value.get("current_batch_count") if key == "burden_rate" else None,
            "batch_count_delta": (
                value.get("current_batch_count") - value.get("previous_batch_count")
                if key == "burden_rate"
                and value.get("previous_batch_count") is not None
                and value.get("current_batch_count") is not None
                else None
            ),
            "batch_count_semantics": "探尺下降后回到提尺零位识别的一次下料批次" if key == "burden_rate" else None,
        })
    eligible = [item for item in factors if item["eligible"]]
    # Keep the configured 100-point denominator for disabled, missing, and
    # neutral indicators.  Only an explicitly confirmed slag/iron exception
    # may remove burden rate and renormalize the remaining 80 points.
    scoring_pool_weight = sum(
        item["configured_weight"] for item in factors
        if item["evidence_state"] != "suppressed"
    )
    for item in factors:
        item["effective_weight"] = (
            round(100.0 * item["configured_weight"] / scoring_pool_weight, 3)
            if item["evidence_state"] != "suppressed" and scoring_pool_weight > 0
            else 0.0
        )
        item["direction_score_points"] = (
            item["effective_weight"] if item["evidence_state"] in {"upward", "downward"} else 0.0
        )
        item["maximum_score_points"] = item["effective_weight"]
    upward = [item for item in eligible if item["evidence_state"] == "upward"]
    downward = [item for item in eligible if item["evidence_state"] == "downward"]
    upward_score = round(sum(item["direction_score_points"] for item in upward), 3)
    downward_score = round(sum(item["direction_score_points"] for item in downward), 3)
    available_score_capacity = round(sum(item["effective_weight"] for item in eligible), 3)
    confirmation_score = float(config["confirmation_score_threshold"])
    participating_count = len(config["metrics"]) - (1 if suppress_burden else 0)
    configured_count = sum(bool(item.get("enabled")) for item in config["metrics"])
    if configured_count < 8:
        state, summary = "configuration_incomplete", f"已配置{configured_count}/8项，待偏差值完整后再启用加权评分"
    elif available_score_capacity < confirmation_score:
        state, summary = "needs_data", f"当前可用指标最高仅{available_score_capacity:.1f}分，低于{confirmation_score:.1f}分确认线"
    elif upward_score >= confirmation_score:
        state, summary = "upward", f"炉温上行得分{upward_score:.1f}，达到{confirmation_score:.1f}分确认线"
    elif downward_score >= confirmation_score:
        state, summary = "downward", f"炉温下行得分{downward_score:.1f}，达到{confirmation_score:.1f}分确认线"
    elif upward_score > downward_score:
        state, summary = "upward_watch", f"炉温上行得分{upward_score:.1f}，未达到{confirmation_score:.1f}分确认线"
    elif downward_score > upward_score:
        state, summary = "downward_watch", f"炉温下行得分{downward_score:.1f}，未达到{confirmation_score:.1f}分确认线"
    else:
        state, summary = "stable", "上行与下行得分相同且均未达到确认线，当前趋势平稳"
    public_factors = [
        {
            key: value for key, value in item.items()
            if key not in {"key", "configured_weight", "effective_weight"}
        }
        for item in factors
    ]
    current_monitoring = []
    baseline_by_key = {str(item.get("key")): item for item in (baseline_monitoring.get("metrics") or [])}
    for key, label, unit, current in (("P_blast_cold", "冷风压力", "kPa", values.get("P_blast_cold", {}).get("current_mean")), ("Q_blast", "冷风流量", "Nm³/min", values.get("Q_blast", {}).get("current_mean")), ("PI", "透气性指数", "", values.get("PI", {}).get("current_mean")), ("DP_total", "全炉压差", "kPa", values.get("DP_total", {}).get("current_mean")), ("DP_upper", "上部压差", "kPa", values.get("DP_upper", {}).get("current_mean")), ("DP_lower", "下部压差", "kPa", values.get("DP_lower", {}).get("current_mean")), ("GasUtil", "煤气利用率", "%", values.get("GasUtil", {}).get("current_mean")), ("top_temperature", "炉顶4点温度", "℃", None)):
        baseline_item = baseline_by_key.get(key, {})
        mean = _number(baseline_item.get("mean"))
        current_value = _number(current)
        if key == "top_temperature":
            top_current = [values.get(f"T_top_{point}", {}).get("current_mean") for point in ("A", "B", "C", "D")]
            current_value = sum(v for v in top_current if v is not None) / len([v for v in top_current if v is not None]) if any(v is not None for v in top_current) else None
        deviation = current_value - mean if current_value is not None and mean is not None else None
        low = _number(baseline_item.get("low_deviation")); high = _number(baseline_item.get("high_deviation"))
        alarm = deviation is not None and low is not None and high is not None and (deviation < -abs(low) or deviation > abs(high))
        current_monitoring.append({"label": label, "key": key, "unit": unit, "baseline_mean": mean, "current_mean": current_value, "delta_from_baseline": deviation, "low_deviation": low, "high_deviation": high, "state": "alarm" if alarm else "normal" if deviation is not None else "needs_data"})
    top_current_points = {point: values.get(f"T_top_{point}", {}).get("current_mean") for point in ("A", "B", "C", "D")}
    top_available = [value for value in top_current_points.values() if value is not None]
    top_pair_delta = max(top_available) - min(top_available) if len(top_available) >= 2 else None
    top_spec = baseline_monitoring.get("top_temperature") or {}
    current_monitoring[-1]["top_temperature_points"] = top_current_points
    current_monitoring[-1]["pair_delta"] = top_pair_delta
    current_monitoring[-1]["pair_state"] = "alarm" if top_pair_delta is not None and top_spec.get("alarm_max_pair_delta") is not None and top_pair_delta > top_spec["alarm_max_pair_delta"] else "normal" if top_pair_delta is not None and top_spec.get("normal_max_pair_delta") is not None and top_pair_delta < top_spec["normal_max_pair_delta"] else "watch" if top_pair_delta is not None else "needs_data"
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "state": state,
        "summary": summary,
        "evaluation_ts": evaluation_ts.isoformat(),
        "windows": {
            "previous_start": (evaluation_ts - timedelta(minutes=60)).isoformat(),
            "previous_end": (evaluation_ts - timedelta(minutes=30)).isoformat(),
            "current_start": (evaluation_ts - timedelta(minutes=30)).isoformat(),
            "current_end": evaluation_ts.isoformat(),
        },
        "confirmation_score_threshold": confirmation_score,
        "upward_score": upward_score,
        "downward_score": downward_score,
        "available_score_capacity": available_score_capacity,
        "eligible_factor_count": len(eligible),
        "participating_factor_count": participating_count,
        "upward_votes": len(upward),
        "downward_votes": len(downward),
        "condition": {key: condition.get(key) for key in ("state", "active", "confirmed_at", "expires_at")},
        "factors": public_factors,
        "baseline_monitoring": baseline_monitoring,
        "current_monitoring": current_monitoring,
        "advisory_only": True,
        "automatic_control": "prohibited",
    }


__all__ = [
    "CONFIG_SCHEMA_VERSION", "REQUIREMENT_ID", "evaluate_latest", "load_config",
    "publish_config", "read_condition", "validate_config", "write_condition",
]
