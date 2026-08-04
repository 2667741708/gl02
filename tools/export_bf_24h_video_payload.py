from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - handled at runtime for sample mode.
    psycopg = None
    dict_row = None


SCORE_KEYS = ("normal", "lowline", "edge", "center", "channel", "cold", "hot", "column")

DIAGNOSIS_LABELS = {
    "normal": "正常顺行",
    "lowline": "低料线",
    "edge": "边缘气流发展",
    "center": "中心气流发展",
    "channel": "管道行程",
    "cold": "炉凉",
    "hot": "炉热",
    "column": "悬料/崩料风险",
}

VARIABLES = (
    "DP_total",
    "GasUtil",
    "T_top",
    "Q_blast",
    "P_top",
    "PCI_rate",
    "L",
)

VARIABLE_META = {
    "DP_total": {"label": "全压差", "unit": "kPa"},
    "GasUtil": {"label": "煤气利用率", "unit": "%"},
    "T_top": {"label": "综合顶温", "unit": "°C"},
    "Q_blast": {"label": "风量", "unit": "Nm³/min"},
    "P_top": {"label": "顶压", "unit": "kPa"},
    "PCI_rate": {"label": "喷煤量", "unit": "t/h"},
    "L": {"label": "料线", "unit": "m"},
}


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a read-only 24h blast furnace video payload.")
    parser.add_argument("--hours", type=float, default=24.0, help="History window size in hours.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    parser.add_argument("--sample", action="store_true", help="Generate a deterministic sample payload without DB access.")
    parser.add_argument(
        "--sample-on-error",
        action="store_true",
        help="Fall back to sample payload if PostgreSQL export fails.",
    )
    parser.add_argument("--seed", type=int, default=20260613, help="Sample payload seed.")
    parser.add_argument("--max-points", type=int, default=288, help="Maximum points per variable series.")
    return parser.parse_args()


def pg_params() -> dict[str, Any]:
    user = os.getenv("GL02_PGUSER", "").strip()
    password = os.getenv("GL02_PGPASSWORD", "")
    if not user or not password:
        raise RuntimeError("GL02_PGUSER and GL02_PGPASSWORD must be set for PostgreSQL export.")
    return {
        "host": os.getenv("GL02_PGHOST", "10.30.220.12"),
        "port": int(os.getenv("GL02_PGPORT", "5432")),
        "dbname": os.getenv("GL02_PGDATABASE", "bf_trend"),
        "user": user,
        "password": password,
        "connect_timeout": int(os.getenv("GL02_PG_CONNECT_TIMEOUT", "8")),
    }


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat(sep=" ")


def parse_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def normalize_scores(raw_scores: Any, main_label: str | None, main_score: Any) -> dict[str, float]:
    raw = parse_jsonish(raw_scores)
    raw = raw if isinstance(raw, dict) else {}
    scores: dict[str, float] = {}
    for key in SCORE_KEYS:
        value = safe_float(raw.get(key))
        scores[key] = round(value if value is not None else 0.0, 3)
    label = main_label if main_label in SCORE_KEYS else None
    fallback = safe_float(main_score)
    if label and fallback is not None and scores.get(label, 0.0) == 0.0:
        scores[label] = round(fallback, 3)
    return scores


def normalize_variable_value(key: str, value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    if key == "GasUtil" and abs(number) <= 1.5:
        number *= 100.0
    return round(number, 3)


def fetch_window(conn, hours: float) -> Window:
    row = conn.execute("SELECT max(diagnosis_ts) AS ts FROM bf_sensor.diagnosis_snapshots").fetchone()
    end = row["ts"] if row and row["ts"] else None
    if end is None:
        row = conn.execute("SELECT max(ts) AS ts FROM bf_sensor.one_minute_values").fetchone()
        end = row["ts"] if row and row["ts"] else datetime.now()
    return Window(start=end - timedelta(hours=hours), end=end)


def fetch_diagnosis_rows(conn, window: Window) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (diagnosis_ts)
                   id, diagnosis_ts, main_label, main_score, main_confidence,
                   secondary_label, secondary_score, secondary_confidence,
                   evidence, raw_scores, diagnosis_json, created_at, updated_at
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
            ORDER BY diagnosis_ts, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        )
        SELECT *
        FROM latest
        ORDER BY diagnosis_ts ASC
        """,
        (window.start, window.end),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_variable_map(conn) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT variable_name, tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE is_enabled = true AND is_derived = false
        """
    ).fetchall()
    return {str(row["variable_name"]): str(row["tag_long_name"]) for row in rows if row.get("tag_long_name")}


def downsample(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    sampled = points[::step]
    if sampled[-1]["ts"] != points[-1]["ts"]:
        sampled.append(points[-1])
    return sampled


def fetch_variable_series(conn, window: Window, max_points: int) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = fetch_variable_map(conn)
    physical_vars = [key for key in VARIABLES if key != "T_top" and mapping.get(key)]
    top_vars = [key for key in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if mapping.get(key)]
    tag_to_var = {mapping[key]: key for key in physical_vars + top_vars if mapping.get(key)}
    tags = sorted(tag_to_var)

    rows = []
    if tags:
        rows = conn.execute(
            """
            SELECT tag_long_name, ts, value
            FROM bf_sensor.one_minute_values
            WHERE ts >= %s AND ts <= %s AND tag_long_name = ANY(%s)
            ORDER BY ts ASC
            """,
            (window.start, window.end, tags),
        ).fetchall()

    by_ts: dict[datetime, dict[str, float | None]] = {}
    for row in rows:
        variable = tag_to_var.get(row["tag_long_name"])
        if not variable:
            continue
        by_ts.setdefault(row["ts"], {})[variable] = safe_float(row["value"])

    timestamps = sorted(by_ts)
    variables: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    expected = max(1, int((window.end - window.start).total_seconds() // 60) + 1)

    for key in VARIABLES:
        points: list[dict[str, Any]] = []
        non_null = 0
        for ts in timestamps:
            row = by_ts.get(ts, {})
            if key == "T_top":
                top_values = [row.get(name) for name in top_vars if row.get(name) is not None]
                value = sum(top_values) / len(top_values) if top_values else None
            else:
                value = row.get(key)
            normalized = normalize_variable_value(key, value)
            if normalized is not None:
                non_null += 1
            points.append({"ts": iso(ts), "value": normalized})
        meta = VARIABLE_META[key]
        variables[key] = {
            "label": meta["label"],
            "unit": meta["unit"],
            "points": downsample(points, max_points),
        }
        quality[key] = {
            "expected_points": expected,
            "observed_points": non_null,
            "missing_rate": round(max(0.0, 1.0 - non_null / expected), 4),
        }
    return variables, quality


def build_timeline(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    timeline: list[dict[str, Any]] = []
    score_series = {key: [] for key in SCORE_KEYS}
    for row in rows:
        payload = parse_jsonish(row.get("diagnosis_json")) or {}
        main_label = row.get("main_label") or payload.get("main_label") or payload.get("label") or "normal"
        if main_label not in SCORE_KEYS:
            main_label = "normal"
        secondary_label = row.get("secondary_label") or payload.get("secondary_label")
        scores = normalize_scores(row.get("raw_scores") or payload.get("raw_scores") or payload.get("scores"), main_label, row.get("main_score"))
        main_score = safe_float(row.get("main_score"))
        if main_score is None:
            main_score = scores.get(main_label, 0.0)
        secondary_score = safe_float(row.get("secondary_score"))
        if secondary_score is None and secondary_label in scores:
            secondary_score = scores[secondary_label]

        ts = row["diagnosis_ts"]
        item = {
            "ts": iso(ts),
            "main_label": main_label,
            "main_label_name": DIAGNOSIS_LABELS.get(main_label, main_label),
            "main_score": round(main_score or 0.0, 3),
            "secondary_label": secondary_label if secondary_label in SCORE_KEYS else None,
            "secondary_label_name": DIAGNOSIS_LABELS.get(secondary_label, "") if secondary_label in SCORE_KEYS else "",
            "secondary_score": round(secondary_score or 0.0, 3),
        }
        timeline.append(item)
        for key in SCORE_KEYS:
            score_series[key].append({"ts": item["ts"], "value": scores.get(key, 0.0)})
    return timeline, score_series


def find_windows(timeline: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for item in timeline:
        hit = item["main_label"] == target
        if hit and current is None:
            current = {
                "start": item["ts"],
                "end": item["ts"],
                "label": target,
                "label_name": DIAGNOSIS_LABELS.get(target, target),
                "peak_score": item["main_score"],
            }
        elif hit and current is not None:
            current["end"] = item["ts"]
            current["peak_score"] = max(current["peak_score"], item["main_score"])
        elif not hit and current is not None:
            windows.append(current)
            current = None
    if current is not None:
        windows.append(current)
    return windows


def build_turning_points(timeline: list[dict[str, Any]], variables: dict[str, Any]) -> list[dict[str, Any]]:
    if not timeline:
        return []

    candidates: list[dict[str, Any]] = []
    previous = timeline[0]["main_label"]
    for item in timeline[1:]:
        if item["main_label"] != previous:
            candidates.append(
                {
                    "ts": item["ts"],
                    "title": "主炉况切换",
                    "label": item["main_label_name"],
                    "score": item["main_score"],
                }
            )
            previous = item["main_label"]

    abnormal = [item for item in timeline if item["main_label"] != "normal"]
    abnormal.sort(key=lambda item: item["main_score"], reverse=True)
    for item in abnormal[:3]:
        candidates.append(
            {
                "ts": item["ts"],
                "title": "风险峰值",
                "label": item["main_label_name"],
                "score": item["main_score"],
            }
        )

    dedup: dict[str, dict[str, Any]] = {}
    for item in candidates:
        dedup.setdefault(f"{item['ts']}|{item['label']}", item)

    points = sorted(dedup.values(), key=lambda item: item["ts"])[:5]
    for point in points:
        point["evidence"] = variable_evidence_at(point["ts"], variables)
    return points


def variable_evidence_at(ts: str, variables: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    for key in ("DP_total", "GasUtil", "T_top", "Q_blast"):
        series = variables.get(key, {})
        label = series.get("label", key)
        unit = series.get("unit", "")
        points = [point for point in series.get("points", []) if point.get("value") is not None]
        if not points:
            continue
        nearest = min(points, key=lambda point: abs(parse_ts(point["ts"]) - parse_ts(ts)))
        evidence.append(f"{label} {nearest['value']}{unit}")
    return evidence[:3]


def parse_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def build_summary(timeline: list[dict[str, Any]], variables: dict[str, Any]) -> dict[str, Any]:
    total = max(1, len(timeline))
    counts = Counter(item["main_label"] for item in timeline)
    distribution = [
        {
            "label": key,
            "label_name": DIAGNOSIS_LABELS[key],
            "count": counts.get(key, 0),
            "ratio": round(counts.get(key, 0) / total, 4),
        }
        for key in SCORE_KEYS
    ]

    risk_windows: list[dict[str, Any]] = []
    for key in SCORE_KEYS:
        if key != "normal":
            risk_windows.extend(find_windows(timeline, key))
    risk_windows.sort(key=lambda item: (item["peak_score"], item["start"]), reverse=True)

    watch = []
    if variables.get("DP_total", {}).get("points"):
        watch.append("关注压差与透气性联动，异常上行时优先核对送风制度。")
    if variables.get("GasUtil", {}).get("points"):
        watch.append("关注煤气利用率与顶温同步变化，避免热效率判断滞后。")
    if variables.get("L", {}).get("points"):
        watch.append("关注料线波动和低料线风险窗口，交接班保持同一口径复盘。")

    return {
        "main_distribution": distribution,
        "risk_windows": risk_windows[:5],
        "next_shift_watch": watch[:3],
    }


def latest_variable_ts(variables: dict[str, Any]) -> datetime | None:
    candidates = []
    for series in variables.values():
        for point in series.get("points", []):
            if point.get("value") is not None and point.get("ts"):
                try:
                    candidates.append(datetime.fromisoformat(point["ts"]))
                except ValueError:
                    pass
    return max(candidates) if candidates else None


def build_payload_from_db(hours: float, max_points: int) -> dict[str, Any]:
    if psycopg is None or dict_row is None:
        raise RuntimeError("psycopg is required for PostgreSQL export. Install psycopg or use --sample.")
    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        window = fetch_window(conn, hours)
        rows = fetch_diagnosis_rows(conn, window)
        variables, variable_quality = fetch_variable_series(conn, window, max_points)
    timeline, score_series = build_timeline(rows)
    latest_ts = latest_variable_ts(variables)
    freshness_minutes = None
    if latest_ts is not None:
        freshness_minutes = round(max(0.0, (window.end - latest_ts).total_seconds() / 60.0), 2)
    payload = {
        "meta": {
            "title": "高炉24小时炉况演化",
            "window_start": iso(window.start),
            "window_end": iso(window.end),
            "generated_at": iso(datetime.now()),
            "data_source": "PostgreSQL只读链路",
            "freshness": {
                "latest_variable_ts": iso(latest_ts),
                "lag_minutes": freshness_minutes,
            },
            "coverage": {
                "diagnosis_points": len(timeline),
                "expected_minutes": int((window.end - window.start).total_seconds() // 60) + 1,
                "variable_quality": variable_quality,
                "is_insufficient": len(timeline) < max(6, int(hours * 2)),
            },
        },
        "diagnosisTimeline": timeline,
        "scoreSeries": score_series,
        "variables": variables,
        "turningPoints": build_turning_points(timeline, variables),
        "summary": {},
    }
    payload["summary"] = build_summary(timeline, variables)
    return payload


def sample_wave(seed: int, index: int, base: float, amp: float, noise: float) -> float:
    rnd = random.Random(seed + index * 17)
    phase = index / 288 * math.tau
    return base + math.sin(phase * 1.6) * amp + math.sin(phase * 4.1) * amp * 0.35 + rnd.uniform(-noise, noise)


def build_sample_payload(hours: float, seed: int, max_points: int) -> dict[str, Any]:
    random.seed(seed)
    end = datetime.now().replace(second=0, microsecond=0)
    window = Window(start=end - timedelta(hours=hours), end=end)
    count = min(max_points, 288)
    step_seconds = max(60, int((window.end - window.start).total_seconds() / max(1, count - 1)))
    stamps = [window.start + timedelta(seconds=i * step_seconds) for i in range(count)]

    variables: dict[str, Any] = {}
    configs = {
        "DP_total": (260, 7, 2.4),
        "GasUtil": (42, 3.8, 0.8),
        "T_top": (142, 12, 3.0),
        "Q_blast": (3580, 120, 38),
        "P_top": (258, 2.8, 0.8),
        "PCI_rate": (1.95, 0.22, 0.04),
        "L": (2.15, 0.35, 0.06),
    }
    for key, (base, amp, noise) in configs.items():
        meta = VARIABLE_META[key]
        points = [
            {"ts": iso(ts), "value": round(sample_wave(seed, i, base, amp, noise), 3)}
            for i, ts in enumerate(stamps)
        ]
        variables[key] = {"label": meta["label"], "unit": meta["unit"], "points": points}

    timeline = []
    score_series = {key: [] for key in SCORE_KEYS}
    sample_scenario = ("normal", "edge", "center", "channel", "lowline", "cold", "hot", "column", "normal")
    for i, ts in enumerate(stamps[::12]):
        hour_ratio = i / max(1, len(stamps[::12]) - 1)
        scenario_index = min(len(sample_scenario) - 1, int(hour_ratio * len(sample_scenario)))
        main = sample_scenario[scenario_index]
        scores = {}
        for key in SCORE_KEYS:
            if key == "normal":
                value = 58 + math.sin(i / 3) * 10
                if main != "normal":
                    value = 32 + math.sin(i) * 6
            else:
                value = 18 + math.sin(i / 2 + len(key)) * 7
                if key == main:
                    value = 62 + math.sin(i / 2) * 16
            scores[key] = round(max(0, min(100, value)), 2)
            score_series[key].append({"ts": iso(ts), "value": scores[key]})
        secondary = max((key for key in SCORE_KEYS if key != main), key=lambda key: scores[key])
        timeline.append(
            {
                "ts": iso(ts),
                "main_label": main,
                "main_label_name": DIAGNOSIS_LABELS[main],
                "main_score": scores[main],
                "secondary_label": secondary,
                "secondary_label_name": DIAGNOSIS_LABELS[secondary],
                "secondary_score": scores[secondary],
            }
        )

    variable_quality = {
        key: {"expected_points": int(hours * 60) + 1, "observed_points": len(series["points"]), "missing_rate": 0.0}
        for key, series in variables.items()
    }
    payload = {
        "meta": {
            "title": "高炉24小时炉况演化",
            "window_start": iso(window.start),
            "window_end": iso(window.end),
            "generated_at": iso(datetime.now()),
            "data_source": "样例数据（用于离线渲染验收）",
            "freshness": {"latest_variable_ts": iso(stamps[-1]), "lag_minutes": 0.0},
            "coverage": {
                "diagnosis_points": len(timeline),
                "expected_minutes": int(hours * 60) + 1,
                "variable_quality": variable_quality,
                "is_insufficient": False,
            },
        },
        "diagnosisTimeline": timeline,
        "scoreSeries": score_series,
        "variables": variables,
        "turningPoints": [],
        "summary": {},
    }
    payload["turningPoints"] = build_turning_points(timeline, variables)
    payload["summary"] = build_summary(timeline, variables)
    return payload


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    if args.sample:
        payload = build_sample_payload(args.hours, args.seed, args.max_points)
        write_payload(out, payload)
        print(f"WROTE_SAMPLE_PAYLOAD={out}")
        return 0

    try:
        payload = build_payload_from_db(args.hours, args.max_points)
    except Exception as exc:
        if not args.sample_on_error:
            raise
        payload = build_sample_payload(args.hours, args.seed, args.max_points)
        payload["meta"]["export_warning"] = f"数据库导出失败，已使用样例数据：{type(exc).__name__}"
        write_payload(out, payload)
        print(f"WROTE_SAMPLE_PAYLOAD={out}")
        print(f"EXPORT_WARNING={type(exc).__name__}")
        return 0

    write_payload(out, payload)
    print(f"WROTE_PAYLOAD={out}")
    print(f"DIAGNOSIS_POINTS={len(payload['diagnosisTimeline'])}")
    print(f"VARIABLE_KEYS={','.join(payload['variables'].keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
