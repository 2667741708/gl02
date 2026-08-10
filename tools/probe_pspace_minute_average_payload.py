from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def import_windows_environment(names: tuple[str, ...]) -> None:
    if os.name != "nt":
        return
    import winreg

    registry_locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    )
    for name in names:
        if os.getenv(name):
            continue
        for hive, key_path in registry_locations:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if value:
                os.environ[name] = str(value)
                break


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(float(ordered[index]), 6)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run pSpace raw minute average semantics without database writes.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--raw-module", required=True)
    parser.add_argument("--minutes", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=133)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import_windows_environment(
        ("PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "PSPACE_SDK_ROOT")
    )
    project_root = Path(args.project_root)
    sync_root = project_root / "数据库同步和存取"
    sync_src = sync_root / "src"
    for candidate in (
        project_root / "trend_analysis" / "trend_backend",
        project_root / "趋势分析" / "trend_backend",
        sync_src,
    ):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    import catalog
    import pspace_history

    raw_pipeline = load_module("raw_minute_pipeline_probe", Path(args.raw_module))
    points = catalog.physical_points(sync_root / "config" / "sync_config.json")
    tags = [point.tag_long_name for point in points]
    end = datetime.now().replace(second=0, microsecond=0)
    start = end - timedelta(minutes=max(2, args.minutes))

    config_candidates = [
        project_root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        project_root / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    connection = None
    connection_error = None
    for config_path in [*config_candidates, None]:
        try:
            connection = pspace_history.resolve_connection(config_path=config_path)
            break
        except RuntimeError as exc:
            connection_error = exc
    if connection is None:
        raise RuntimeError("pSpace connection settings are unavailable") from connection_error
    PsObject, T = pspace_history.load_sdk(project_root / "pythonSDK(1)")

    series, audits, raw_records, errors = raw_pipeline.fetch_raw_history_concurrent(
        PsObject,
        T,
        connection,
        tags,
        start,
        end,
        pspace_history=pspace_history,
        target_interval_seconds=60,
        source_interval_seconds=5,
        batch_size=max(1, args.batch_size),
        max_workers=1,
        raw_max_values=20000,
        raw_bounds=0,
    )

    coverage: list[float] = []
    sample_counts: list[float] = []
    quality_counts: Counter[str] = Counter()
    minute_rows = 0
    for tag_audits in audits.values():
        for audit in tag_audits.values():
            minute_rows += 1
            coverage.append(float(audit.get("coverage_ratio") or 0.0))
            sample_counts.append(float(audit.get("sample_count") or 0.0))
    for records in raw_records.values():
        for record in records:
            quality_counts[str(record.get("quality") or "<empty>")] += 1

    samples: list[dict[str, Any]] = []
    for tag in sorted(series)[:5]:
        timestamps = sorted(series[tag])
        if not timestamps:
            continue
        latest = timestamps[-1]
        samples.append(
            {
                "tag": tag,
                "timestamp": latest,
                "mean": series[tag][latest],
                "audit": audits.get(tag, {}).get(latest),
            }
        )

    hard_errors = {
        tag: message
        for tag, message in errors.items()
        if "没有数据" not in str(message)
    }
    payload = {
        "ok": len(series) >= 100 and bool(raw_records) and not hard_errors,
        "dry_run": True,
        "database_writes": 0,
        "start": str(start),
        "end": str(end),
        "physical_tags": len(tags),
        "tags_ok": len(series),
        "tags_error": len(errors),
        "hard_error_count": len(hard_errors),
        "minute_rows": minute_rows,
        "raw_rows": sum(len(rows) for rows in raw_records.values()),
        "coverage_ratio": {
            "p10": percentile(coverage, 0.10),
            "p50": percentile(coverage, 0.50),
            "p90": percentile(coverage, 0.90),
        },
        "sample_count": {
            "p10": percentile(sample_counts, 0.10),
            "p50": percentile(sample_counts, 0.50),
            "p90": percentile(sample_counts, 0.90),
        },
        "quality_counts": dict(quality_counts.most_common(12)),
        "sample_errors": dict(list(errors.items())[:10]),
        "samples": samples,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
