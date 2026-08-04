from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_SYNC_SRC = ROOT / "数据库同步和存取" / "src"
if str(DB_SYNC_SRC) not in sys.path:
    sys.path.insert(0, str(DB_SYNC_SRC))

TREND_BACKEND_CANDIDATES = [
    ROOT / "trend_analysis" / "trend_backend",
    ROOT / "趋势分析" / "trend_backend",
]
for candidate in TREND_BACKEND_CANDIDATES:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from catalog import physical_points  # noqa: E402
import pspace_history  # noqa: E402


DEFAULT_VARIABLES = [
    "T_throat_C",
    "PCI_set",
    "Q_blast",
    "P_blast",
    "L_south",
    "PCI_rate",
    "L_north",
    "PI",
    "P_top_gas_B",
]


CSV_FIELDS = [
    "variable_name",
    "chinese_name",
    "short_name",
    "tag_long_name",
    "timestamp",
    "value",
    "quality",
    "source_server",
    "read_start",
    "read_end",
]


def parse_time(value: str) -> datetime:
    parsed = pspace_history.parse_timestamp(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"Unsupported datetime: {value}")
    return parsed.replace(microsecond=0)


def iter_day_windows(start: datetime, end: datetime):
    cursor = start
    while cursor < end:
        next_midnight = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        chunk_end = min(next_midnight, end)
        yield cursor, chunk_end
        cursor = chunk_end


def resolve_connection() -> dict[str, str]:
    candidates = [
        ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
        ROOT.parent / f"{ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        ROOT.parent / f"{ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    config_path = next((path for path in candidates if path.exists()), None)
    return pspace_history.resolve_connection(config_path=config_path)


def selected_points(config_path: str, variables: list[str]):
    wanted = {item.strip() for item in variables if item.strip()}
    points = [point for point in physical_points(config_path) if point.variable_name in wanted]
    found = {point.variable_name for point in points}
    missing = sorted(wanted - found)
    if missing:
        raise SystemExit(f"Variables not found in required point config: {', '.join(missing)}")
    order = {name: index for index, name in enumerate(variables)}
    return sorted(points, key=lambda point: order.get(point.variable_name, 999))


def write_manifest(path: Path, points: list[Any]) -> None:
    fields = ["variable_name", "chinese_name", "branch", "short_name", "tag_long_name", "description"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for point in points:
            writer.writerow({field: getattr(point, field, "") for field in fields})


def parse_tag_rows(
    result: dict[str, Any],
    T,
    points_by_tag: dict[str, Any],
    start: datetime,
    end: datetime,
    source_server: str,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    for tag, point in points_by_tag.items():
        tag_result = result.get(tag)
        if not isinstance(tag_result, dict):
            errors[tag] = f"missing_raw_result return={result.get(T.Return)}"
            continue

        item_error = tag_result.get("ErrorInfo") or tag_result.get("Error")
        if item_error not in (None, "", 0, "0"):
            errors[tag] = str(item_error)

        tag_count = 0
        for _, record in pspace_history.numeric_items(tag_result):
            if not isinstance(record, dict):
                continue
            parsed_ts = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
            if parsed_ts is None:
                continue
            parsed_ts = parsed_ts.replace(microsecond=0)
            if not (start <= parsed_ts < end):
                continue
            rows.append(
                {
                    "variable_name": point.variable_name,
                    "chinese_name": point.chinese_name,
                    "short_name": point.short_name,
                    "tag_long_name": tag,
                    "timestamp": parsed_ts.isoformat(sep=" "),
                    "value": pspace_history.coerce_number(record.get(T.HisReadRawValueDict)),
                    "quality": str(record.get(T.HisReadRawQualityDict, "") or ""),
                    "source_server": source_server,
                    "read_start": start.isoformat(sep=" "),
                    "read_end": end.isoformat(sep=" "),
                }
            )
            tag_count += 1
        counts[tag] = tag_count

    rows.sort(key=lambda row: (row["timestamp"], row["variable_name"]))
    return rows, counts, errors


def write_daily_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export 5s pSpace raw rows for the 9 zero-prone GL02 sensors.")
    parser.add_argument("--config", default=str(ROOT / "数据库同步和存取" / "config" / "sync_config.json"))
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--variables", default=",".join(DEFAULT_VARIABLES))
    parser.add_argument("--raw-max-values", type=int, default=30000)
    parser.add_argument("--raw-bounds", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = parse_time(args.start_time)
    end = parse_time(args.end_time)
    if start >= end:
        raise SystemExit("start-time must be earlier than end-time")

    variables = [item.strip() for item in args.variables.split(",") if item.strip()]
    points = selected_points(args.config, variables)
    tags = [point.tag_long_name for point in points]
    points_by_tag = {point.tag_long_name: point for point in points}

    output_root = Path(args.output_root)
    daily_dir = output_root / "raw_5s_by_day"
    output_root.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(output_root / "manifest.csv", points)

    connection = resolve_connection()
    source_server = f"{connection['server']}:{connection['port']}"
    PsObject, T = pspace_history.load_sdk(ROOT / "pythonSDK(1)")

    summary_rows: list[dict[str, Any]] = []
    started_at = datetime.now().replace(microsecond=0)
    total_rows = 0
    total_errors: dict[str, str] = {}
    pspace = None

    def get_pspace():
        nonlocal pspace
        if pspace is None:
            pspace = pspace_history.connect_pspace(PsObject, T, connection)
        return pspace

    try:
        for chunk_start, chunk_end in iter_day_windows(start, end):
            day_key = chunk_start.strftime("%Y%m%d")
            out_file = daily_dir / f"raw_5s_{day_key}.csv.gz"
            if out_file.exists() and not args.overwrite:
                summary_rows.append(
                    {
                        "date": day_key,
                        "start": chunk_start.isoformat(sep=" "),
                        "end": chunk_end.isoformat(sep=" "),
                        "status": "skipped_exists",
                        "raw_rows": "",
                        "elapsed_seconds": "",
                        "errors_json": "",
                        "counts_json": "",
                        "file": str(out_file),
                    }
                )
                print(json.dumps({"date": day_key, "status": "skipped_exists", "file": str(out_file)}, ensure_ascii=False), flush=True)
                continue

            attempt = 0
            last_error = ""
            day_started = time.time()
            while attempt < max(1, int(args.retries)):
                attempt += 1
                if attempt > 1 and pspace is not None:
                    pspace_history.close_pspace(pspace)
                    pspace = None
                if attempt > 1:
                    time.sleep(float(args.retry_sleep_seconds))
                try:
                    result = pspace_history.read_raw_batch(
                        get_pspace(),
                        T,
                        tags,
                        chunk_start,
                        chunk_end,
                        max_values=args.raw_max_values,
                        bounds=args.raw_bounds,
                    )
                    rows, counts, errors = parse_tag_rows(result, T, points_by_tag, chunk_start, chunk_end, source_server)
                    write_daily_rows(out_file, rows)
                    total_rows += len(rows)
                    total_errors.update(errors)
                    elapsed = round(time.time() - day_started, 3)
                    summary_rows.append(
                        {
                            "date": day_key,
                            "start": chunk_start.isoformat(sep=" "),
                            "end": chunk_end.isoformat(sep=" "),
                            "status": "ok" if not errors else "ok_with_tag_errors",
                            "raw_rows": len(rows),
                            "elapsed_seconds": elapsed,
                            "errors_json": json.dumps(errors, ensure_ascii=False),
                            "counts_json": json.dumps(counts, ensure_ascii=False),
                            "file": str(out_file),
                        }
                    )
                    print(
                        json.dumps(
                            {
                                "date": day_key,
                                "status": "ok" if not errors else "ok_with_tag_errors",
                                "raw_rows": len(rows),
                                "tag_errors": len(errors),
                                "elapsed_seconds": elapsed,
                                "file": str(out_file),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - keep long export resilient and logged.
                    last_error = repr(exc)
                    if pspace is not None:
                        pspace_history.close_pspace(pspace)
                        pspace = None
                    if attempt >= max(1, int(args.retries)):
                        total_errors[day_key] = last_error
                        summary_rows.append(
                            {
                                "date": day_key,
                                "start": chunk_start.isoformat(sep=" "),
                                "end": chunk_end.isoformat(sep=" "),
                                "status": "failed",
                                "raw_rows": 0,
                                "elapsed_seconds": round(time.time() - day_started, 3),
                                "errors_json": json.dumps({"exception": last_error}, ensure_ascii=False),
                                "counts_json": "",
                                "file": str(out_file),
                            }
                        )
                        print(json.dumps({"date": day_key, "status": "failed", "error": last_error}, ensure_ascii=False), flush=True)
    finally:
        if pspace is not None:
            pspace_history.close_pspace(pspace)

    summary_path = output_root / "daily_summary.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["date", "start", "end", "status", "raw_rows", "elapsed_seconds", "errors_json", "counts_json", "file"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    finished_at = datetime.now().replace(microsecond=0)
    export_summary = {
        "ok": not any(row["status"] == "failed" for row in summary_rows),
        "started_at": started_at,
        "finished_at": finished_at,
        "start": start,
        "end": end,
        "source_server": source_server,
        "variables": variables,
        "tag_count": len(tags),
        "days": len(summary_rows),
        "total_rows": total_rows,
        "failed_days": [row["date"] for row in summary_rows if row["status"] == "failed"],
        "tag_or_day_errors": total_errors,
        "output_root": str(output_root),
        "daily_dir": str(daily_dir),
        "manifest": str(output_root / "manifest.csv"),
        "daily_summary": str(summary_path),
    }
    (output_root / "export_summary.json").write_text(
        json.dumps(export_summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(export_summary, ensure_ascii=False, indent=2, default=str), flush=True)
    return 0 if export_summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
