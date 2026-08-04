from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from diagnosis_scheduler import floor_to_interval
from store import DiagnosisStore


VALID_SECTIONS = {"sensor", "diagnosis", "baseline", "quality"}


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(second=0, microsecond=0)
        except ValueError:
            continue
    return datetime.fromisoformat(text).replace(second=0, microsecond=0)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_json_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                item[key] = json.dumps(value, ensure_ascii=False, default=json_default)
            else:
                item[key] = value
        normalized.append(item)
    return normalized


def frame_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    records = []
    for row in df.to_dict(orient="records"):
        item = {}
        for key, value in row.items():
            if pd.isna(value):
                item[key] = None
            elif isinstance(value, pd.Timestamp):
                item[key] = value.to_pydatetime()
            else:
                item[key] = value
        records.append(item)
    return records


def query_sensor(store: DiagnosisStore, start: datetime, end: datetime, variables: list[str]) -> list[dict[str, Any]]:
    df = store.fetch_wide_frame(start, end, variables=variables or None)
    return frame_records(df)


def query_diagnosis(store: DiagnosisStore, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
    rows = store.list_diagnoses(start, end, limit=limit)
    return list(reversed(rows))


def query_baseline(store: DiagnosisStore, start: datetime, end: datetime, variables: list[str], baseline_days: int) -> list[dict[str, Any]]:
    params: list[Any] = [start.date(), end.date(), baseline_days]
    extra = ""
    if variables:
        extra = " AND variable_name = ANY(%s)"
        params.append(variables)
    with store.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM bf_sensor.daily_baselines
            WHERE baseline_day >= %s
              AND baseline_day <= %s
              AND baseline_days = %s
              {extra}
            ORDER BY baseline_day ASC, variable_name ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def query_quality(store: DiagnosisStore, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM bf_sensor.data_quality_status
            WHERE checked_at >= %s
              AND checked_at <= %s
            ORDER BY checked_at ASC
            LIMIT %s
            """,
            (start, end, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def sensor_long_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        ts = row.get("timestamp")
        for key, value in row.items():
            if key == "timestamp":
                continue
            output.append({"timestamp": ts, "variable_name": key, "value": value})
    return output


def write_json(payload: dict[str, Any], out: str) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=json_default)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def write_csv(payload: dict[str, Any], sections: list[str], out: str) -> None:
    target = Path(out) if out else None
    fh = target.open("w", encoding="utf-8-sig", newline="") if target else sys.stdout
    try:
        if len(sections) == 1:
            section = sections[0]
            rows = payload.get(section, [])
            if section == "sensor":
                rows = sensor_long_rows(rows)
            rows = normalize_json_cells(rows)
            fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            if rows:
                writer.writerows(rows)
            return

        writer = csv.DictWriter(fh, fieldnames=["section", "payload_json"])
        writer.writeheader()
        for section in sections:
            for row in payload.get(section, []):
                writer.writerow({"section": section, "payload_json": json.dumps(row, ensure_ascii=False, default=json_default)})
    finally:
        if target:
            fh.close()


def write_xlsx(payload: dict[str, Any], sections: list[str], out: str) -> None:
    if not out:
        raise SystemExit("--format xlsx requires --out")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for section in sections:
            rows = payload.get(section, [])
            if section == "sensor":
                df = pd.DataFrame(rows)
            else:
                df = pd.DataFrame(normalize_json_cells(rows))
            if df.empty:
                df = pd.DataFrame([{"empty": True}])
            df.to_excel(writer, index=False, sheet_name=section[:31])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query 220.12 PostgreSQL sensor, diagnosis, baseline, and quality history.")
    parser.add_argument("--config", default="", help="Optional auto_diagnosis_service config path.")
    parser.add_argument("--start", default="", help="Start time, e.g. 2026-03-12 00:00.")
    parser.add_argument("--end", default="", help="End time, defaults to current 5-minute boundary.")
    parser.add_argument("--hours", type=float, default=8.0, help="Used when --start is omitted.")
    parser.add_argument("--include", default="sensor,diagnosis,baseline", help="Comma-separated: sensor,diagnosis,baseline,quality.")
    parser.add_argument("--variables", default="", help="Comma-separated variables for sensor/baseline, e.g. PI,DP_total,T_top.")
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100000, help="Limit for diagnosis/quality rows.")
    parser.add_argument("--format", choices=["json", "csv", "xlsx"], default="json")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    end = parse_time(args.end) or floor_to_interval(datetime.now(), 5)
    start = parse_time(args.start) or (end - timedelta(hours=float(args.hours)))
    sections = parse_csv(args.include)
    unknown = sorted(set(sections) - VALID_SECTIONS)
    if unknown:
        raise SystemExit(f"Unsupported --include values: {', '.join(unknown)}")
    if not sections:
        raise SystemExit("--include cannot be empty")
    variables = parse_csv(args.variables)
    store = DiagnosisStore(args.config or None)

    payload: dict[str, Any] = {
        "ok": True,
        "start": start,
        "end": end,
        "include": sections,
        "variables": variables,
        "baseline_days": args.baseline_days,
    }
    if "sensor" in sections:
        payload["sensor"] = query_sensor(store, start, end, variables)
    if "diagnosis" in sections:
        payload["diagnosis"] = query_diagnosis(store, start, end, args.limit)
    if "baseline" in sections:
        payload["baseline"] = query_baseline(store, start, end, variables, args.baseline_days)
    if "quality" in sections:
        payload["quality"] = query_quality(store, start, end, args.limit)

    if args.format == "json":
        write_json(payload, args.out)
    elif args.format == "csv":
        write_csv(payload, sections, args.out)
    else:
        write_xlsx(payload, sections, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
