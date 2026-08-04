$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$TempDir = Join-Path $env:TEMP "codex_pspace_probe"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
$ProbePy = Join-Path $TempDir "probe_22012_pspace_throat_c.py"

@'
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_CANDIDATES = [
    Path(os.getenv("BF_REMOTE_PROJECT_ROOT", "")) if os.getenv("BF_REMOTE_PROJECT_ROOT") else None,
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V3"),
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V3_AUTO_PREVIEW"),
]

TAGS = {
    "T_throat_A": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0235",
    "T_throat_B": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0236",
    "T_throat_C": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0237",
    "T_throat_D": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0238",
}


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def unique_existing_roots() -> list[Path]:
    seen: set[str] = set()
    roots: list[Path] = []
    for root in ROOT_CANDIDATES:
        if root is None:
            continue
        key = str(root).lower()
        if key in seen or not root.exists():
            continue
        seen.add(key)
        roots.append(root)
    return roots


def resolve_runtime() -> tuple[Path, Path, Path]:
    roots = unique_existing_roots()
    trend_candidates = []
    sdk_candidates = []
    config_candidates = []
    for root in roots:
        trend_candidates.extend(
            [
                root / "trend_analysis" / "trend_backend",
                root / "趋势分析" / "trend_backend",
            ]
        )
        sdk_candidates.append(root / "pythonSDK(1)")
        config_candidates.extend(
            [
                root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
                root / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
            ]
        )
    trend_backend = first_existing([p for p in trend_candidates if (p / "pspace_history.py").exists()])
    sdk_root = first_existing([p for p in sdk_candidates if (p / "PythonAPI" / "PsServer.py").exists()])
    config_path = first_existing(config_candidates)
    missing = []
    if trend_backend is None:
        missing.append("pspace_history.py")
    if sdk_root is None:
        missing.append("pythonSDK(1)/PythonAPI/PsServer.py")
    if config_path is None:
        missing.append("ghsc application yml")
    if missing:
        raise RuntimeError(f"missing runtime files: {', '.join(missing)}; roots={[str(r) for r in roots]}")
    return trend_backend, sdk_root, config_path


def text_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    return text or None


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["value"] for row in rows if row.get("value") is not None]
    nonzero_values = [value for value in values if abs(float(value)) > 1e-12]
    qualities = Counter(str(row.get("quality") or "") for row in rows)
    return {
        "rows": len(rows),
        "non_null": len(values),
        "zero_count": sum(1 for value in values if abs(float(value)) <= 1e-12),
        "nonzero_count": len(nonzero_values),
        "min_value": min(values) if values else None,
        "max_value": max(values) if values else None,
        "first_ts": text_time(rows[0]["ts"]) if rows else None,
        "last_ts": text_time(rows[-1]["ts"]) if rows else None,
        "quality_counts": dict(qualities),
        "last_samples": [
            {
                "ts": text_time(row.get("ts")),
                "value": row.get("value"),
                "quality": row.get("quality"),
                "value_type": row.get("value_type"),
            }
            for row in rows[-12:]
        ],
    }


def parse_raw_records(result: dict[str, Any], pspace_history, T, tag: str) -> tuple[list[dict[str, Any]], str]:
    tag_result = result.get(tag)
    if not isinstance(tag_result, dict):
        return [], f"missing_result return={result.get(getattr(T, 'Return', 'Return'))} error={result.get(getattr(T, 'Error', 'Error'))}"
    item_error = tag_result.get("ErrorInfo") or tag_result.get("Error")
    rows: list[dict[str, Any]] = []
    for _, record in pspace_history.numeric_items(tag_result):
        if not isinstance(record, dict):
            continue
        ts = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
        if ts is None:
            continue
        rows.append(
            {
                "ts": ts,
                "value": pspace_history.coerce_number(record.get(T.HisReadRawValueDict)),
                "quality": str(record.get(T.HisReadRawQualityDict, "") or ""),
                "value_type": str(record.get(T.ReadTypeDict, "") or ""),
            }
        )
    rows.sort(key=lambda item: item["ts"])
    return rows, str(item_error or "")


def parse_processed_records(result: dict[str, Any], pspace_history, T, tag: str) -> tuple[list[dict[str, Any]], str]:
    series, qualities_by_tag, errors = pspace_history.parse_processed_result(result, T, [tag])
    rows: list[dict[str, Any]] = []
    qualities = qualities_by_tag.get(tag, [])
    for index, (ts_text, value) in enumerate(sorted(series.get(tag, {}).items())):
        rows.append(
            {
                "ts": pspace_history.parse_timestamp(ts_text) or ts_text,
                "value": value,
                "quality": qualities[index] if index < len(qualities) else "",
                "value_type": "PS_HIS_AVERAGE",
            }
        )
    return rows, errors.get(tag, "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe pSpace throat temperature C on 220.12.")
    parser.add_argument("--minutes", type=float, default=120.0)
    parser.add_argument("--raw-max-values", type=int, default=20000)
    parser.add_argument("--server", default=os.getenv("PSPACE_SERVER", "10.22.181.243"))
    parser.add_argument("--port", default=os.getenv("PSPACE_PORT", "8889"))
    args = parser.parse_args()

    trend_backend, sdk_root, config_path = resolve_runtime()
    sys.path.insert(0, str(trend_backend))
    import pspace_history  # noqa: E402

    start = datetime.now().replace(microsecond=0) - timedelta(minutes=args.minutes)
    end = datetime.now().replace(microsecond=0)
    connection = pspace_history.resolve_connection(
        config_path=config_path,
        server=args.server,
        port=args.port,
    )
    PsObject, T = pspace_history.load_sdk(sdk_root)
    pspace = pspace_history.connect_pspace(PsObject, T, connection)
    tag_list = list(TAGS.values())
    try:
        realtime_result = pspace_history.read_realtime(pspace, T, tag_list)
        raw_result = pspace_history.read_raw_batch(
            pspace,
            T,
            tag_list,
            start,
            end,
            max_values=args.raw_max_values,
            bounds=0,
        )
        processed_result = pspace_history.read_processed_batch(
            pspace,
            T,
            tag_list,
            start,
            end,
            60,
            "PS_HIS_AVERAGE",
        )
    finally:
        pspace_history.close_pspace(pspace)

    variables: dict[str, Any] = {}
    for variable_name, tag in TAGS.items():
        raw_rows, raw_error = parse_raw_records(raw_result, pspace_history, T, tag)
        processed_rows, processed_error = parse_processed_records(processed_result, pspace_history, T, tag)
        variables[variable_name] = {
            "tag_long_name": tag,
            "realtime": realtime_result.get(tag, {}),
            "raw": summarize_rows(raw_rows),
            "raw_error": raw_error,
            "processed_1min_average": summarize_rows(processed_rows),
            "processed_error": processed_error,
        }

    report = {
        "ok": True,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {
            "pspace_server": f"{connection['server']}:{connection['port']}",
            "trend_backend": str(trend_backend),
            "sdk_root": str(sdk_root),
            "config_path": str(config_path),
        },
        "window": {
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "minutes": args.minutes,
        },
        "variables": variables,
        "conclusion_hint": {
            "T_throat_C_realtime_value": variables["T_throat_C"]["realtime"].get("latest_value"),
            "T_throat_C_raw_nonzero_count": variables["T_throat_C"]["raw"]["nonzero_count"],
            "T_throat_C_processed_nonzero_count": variables["T_throat_C"]["processed_1min_average"]["nonzero_count"],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -Path $ProbePy -Encoding UTF8

& "C:\Program Files\Python311\python.exe" -X utf8 $ProbePy --minutes 120 --raw-max-values 20000
